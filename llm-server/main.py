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


if __name__ == "__main__":
    # Explicit import here to avoid linting errors
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)