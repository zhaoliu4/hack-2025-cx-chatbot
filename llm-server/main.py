import os
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from typing import List, Optional
import logging
from mcp_http_client import MCPHTTPClient
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

# OpenRouter client setup
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "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")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# HTTP MCP server settings
HTTP_MCP_SERVER_URL = os.environ.get("HTTP_MCP_SERVER_URL", "http://localhost:53000/mcp")


# Sampling message handler
async def handle_sampling_message(message):
    """Handle sampling messages from the MCP server"""
    logger.info(f"Sampling: {message.get('text', '')}")



def transform_jsonrpc_to_openrouter_tools(jsonrpc_response):
    """
    Transform the JSON-RPC tools response format to OpenRouter tools format.

    Args:
        jsonrpc_response: The response from the list_tools_jsonrpc call

    Returns:
        List of tools in OpenRouter format
    """
    openrouter_tools = []

    # Check if we have a valid response with tools
    if (jsonrpc_response and
            "result" in jsonrpc_response and
            "tools" in jsonrpc_response["result"]):

        # Process each tool
        for tool in jsonrpc_response["result"]["tools"]:
            openrouter_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]  # Map inputSchema to parameters
                }
            })

    return openrouter_tools

async def list_tools():
    """Make a direct JSON-RPC request to the MCP server to list tools."""
    url = HTTP_MCP_SERVER_URL

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {
                    "listChanged": True
                }
            },
            "clientInfo": {
                "name": "mcp",
                "version": "0.1.0"
            }
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            return transform_jsonrpc_to_openrouter_tools(response.json())
    except Exception as e:
        logger.error(f"Error making JSON-RPC request to MCP server: {str(e)}")
        return {"error": str(e)}



# Use FastAPI's startup and shutdown events instead of lifespan
@app.on_event("startup")
async def startup_event():
    global mcp_client
    # Startup: Initialize HTTP MCP client
    try:
        logger.info("initializing mcp client")
        tools = await list_tools()
        logger.info(f"MCP tools list: {tools}")
        logger.info(f"HTTP MCP client initialized successfully, connected to {HTTP_MCP_SERVER_URL}")
    except Exception as e:
        logger.error(f"Failed to initialize HTTP MCP client: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    global mcp_client
    # Shutdown: Close the MCP client when the app is shutting down
    if mcp_client:
        try:
            await mcp_client.close()
            logger.info("HTTP MCP client closed")
        except Exception as e:
            logger.error(f"Error closing HTTP MCP client: {str(e)}")


@app.post("/generate", response_model=LLMResponse)
async def generate_text(request: LLMRequest):
    """Generate text from an LLM using OpenRouter with context from MCP"""
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OpenRouter API key not configured")

    try:
        # Get relevant tools from MCP server
        tools = await list_tools()


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
        elif tools:
            payload["tools"] = tools

        print(f'OPEN ROUTER URL: {OPENROUTER_URL}')
        print(f'OPENROUTER_API_KEY: {OPENROUTER_API_KEY}')        # Send request to OpenRouter
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
    # Explicit import here to avoid linting errors
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)