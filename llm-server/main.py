import os
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from typing import List, Optional
import logging
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from llm.llm_service import get_return_status_response_with_tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="LLM Server", description="API for interacting with LLMs via OpenRouter and MCP")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models for request/response
class LLMRequest(BaseModel):
    prompt: str
    model: str = "anthropic/claude-3-sonnet-20240229"
    max_tokens: int = 1024
    temperature: float = 0.7
    tools: Optional[List[dict]] = None


class LLMResponse(BaseModel):
    text: str
    tool_calls: Optional[List[dict]] = None


# Global variables
mcp_client = None
stdio_context = None

# OpenRouter client setup
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

mcp_server_path = "../mcp-server"  # Adjust to your actual path


# Sampling message handler
async def handle_sampling_message(message: types.SamplingMessage):
    """Handle sampling messages from the MCP server"""
    logger.info(f"Sampling: {message.text}")


# Global variables to properly manage MCP resources
mcp_client = None
stdio_context = None  # To hold the context manager reference

# Use FastAPI's startup and shutdown events instead of lifespan
@app.on_event("startup")
async def startup_event():
    global mcp_client, stdio_context
    # Startup: Initialize MCP client
    try:
        # Create server parameters for stdio connection to use the executable
        server_params = StdioServerParameters(
            command=f"{mcp_server_path}/mcp-server",
            args=[],
            env={}
        )

        # Initialize the stdio client
        stdio_context = stdio_client(server_params)
        
        # Use the stdio_context properly with async with
        read, write = None, None
        context_manager = stdio_client(server_params)
        
        # This part needs special handling because we need to keep the context open
        # We can't use an async with block directly since it would close the connection
        # when the block exits
        
        # Get the async iterator
        stdio_aiter = context_manager.__aenter__()
        # Get the read/write handles
        r, w = await stdio_aiter
        read, write = r, w
        
        # Store the context manager for cleanup
        stdio_context = context_manager
        
        # Create the MCP client session with the obtained handles
        mcp_client = ClientSession(
            read, write, sampling_callback=handle_sampling_message
        )

        # Initialize the connection
        await mcp_client.initialize()
        logger.info("MCP client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MCP client: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    global mcp_client, stdio_context
    # Shutdown: Close the MCP client when the app is shutting down
    if mcp_client:
        try:
            await mcp_client.close()
            logger.info("MCP client closed")
        except Exception as e:
            logger.error(f"Error closing MCP client: {str(e)}")
    
    # Close the stdio context if it exists
    if stdio_context:
        try:
            await stdio_context.__aexit__(None, None, None)
            logger.info("Stdio context closed")
        except Exception as e:
            logger.error(f"Error closing stdio context: {str(e)}")


@app.post("/generate", response_model=LLMResponse)
async def generate_text(request: LLMRequest):
    """Generate text from an LLM using OpenRouter with context from MCP"""
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OpenRouter API key not configured")

    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")

    try:
        # Get relevant tools from MCP server
        tools = await mcp_client.list_tools()

        # Format tools for OpenRouter if needed
        openrouter_tools = []
        if tools and not request.tools:
            # Convert MCP tools to OpenRouter format
            for tool in tools:
                openrouter_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"]
                    }
                })

        # Create request payload for OpenRouter
        payload = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        # Add tools if provided in the request or from MCP
        if request.tools:
            payload["tools"] = request.tools
        elif openrouter_tools:
            payload["tools"] = openrouter_tools

        # Send request to OpenRouter
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json=payload,
                timeout=60.0,
            )

        if response.status_code != 200:
            logger.error(f"OpenRouter API error: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()

        # Extract text and tool calls
        text = result["choices"][0]["message"]["content"]
        tool_calls = result["choices"][0]["message"].get("tool_calls", [])

        return LLMResponse(text=text, tool_calls=tool_calls)

    except Exception as e:
        logger.error(f"Error generating with context: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/execute_tool")
async def execute_tool(tool_call_data: dict):
    """Execute an MCP tool based on the tool call from the LLM"""
    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")

    try:
        tool_name = tool_call_data["name"]
        arguments = tool_call_data["arguments"]

        # Execute tool via MCP client
        result = await mcp_client.call_tool(tool_name, arguments=arguments)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: Request):
    """Chat endpoint that supports tool usage via MCP"""
    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")
        
    try:
        data = await request.json()
        
        if not data.get("message"):
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Extract chat history if provided, or start with empty history
        chat_history = data.get("chat_history", [])
        user_message = data.get("message")
        
        # Process with tools
        response_text, updated_history = await get_return_status_response_with_tools(
            chat_history, 
            user_message,
            mcp_client
        )
        
        return {
            "response": response_text,
            "chat_history": updated_history
        }
    except Exception as e:
        logger.error(f"Error in chat processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/available_tools")
async def get_available_tools():
    """Get available tools from MCP server"""
    if not mcp_client:
        raise HTTPException(status_code=500, detail="MCP client not initialized")

    try:
        tools = await mcp_client.list_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"Error fetching tools: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Removed duplicate /chat endpoint here


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)