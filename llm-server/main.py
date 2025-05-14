from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import httpx
from typing import List, Optional
import logging
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

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


# OpenRouter client setup
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

mcp_server_path = "../mcp-server"  # Adjust to your actual path


# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="go",
    args=["run", f"{mcp_server_path}/main.go"],
    env={"DATABASE_CONNECTION_STRING": "postgres://zhao_liu_user:rZX0xpxASQz2WrLo2uNr@db-dev.happyreturns.com/happyreturns"}
)


@app.post("/generate", response_model=LLMResponse)
async def generate_text(request: LLMRequest):
    """Generate text from an LLM using OpenRouter"""
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OpenRouter API key not configured")

    # Create request payload for OpenRouter
    payload = {
        "model": request.model,
        "messages": [{"role": "user", "content": request.prompt}],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }

    # Add tools if provided
    if request.tools:
        payload["tools"] = request.tools

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


@app.post("/execute_tool")
async def execute_tool(tool_call_data: dict):
    """Execute an MCP tool based on the tool call from the LLM"""
    try:
        tool_name = tool_call_data["name"]
        arguments = tool_call_data["arguments"]

        # Execute tool via MCP client
        result = await mcp_client.execute_tool(tool_name, arguments)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/available_tools")
async def get_available_tools():
    """Get available tools from MCP server"""
    try:
        tools = await mcp_client.list_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"Error fetching tools: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read, write, sampling_callback=handle_sampling_message
        ) as session:
            # Initialize the connection
            await session.initialize()

            # List available prompts
            prompts = await session.list_prompts()

            # Get a prompt
            prompt = await session.get_prompt(
                "example-prompt", arguments={"arg1": "value"}
            )

            # List available resources
            resources = await session.list_resources()

            # List available tools
            tools = await session.list_tools()

            # Read a resource
            content, mime_type = await session.read_resource("file://some/path")

            # Call a tool
            result = await session.call_tool("tool-name", arguments={"arg1": "value"})

if __name__ == "__main__":
    import uvicorn
    import asyncio

    asyncio.run(run())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)