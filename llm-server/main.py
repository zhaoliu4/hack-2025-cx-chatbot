from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import httpx
from typing import List, Optional
import logging
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import re

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

# Models for chat endpoints
class ChatMessage(BaseModel):
    chat_id: Optional[str]
    current_message: str
    chat_history: List[dict]

class ChatResponse(BaseModel):
    response: str
    chat_id: Optional[str]
    qrCode: Optional[str]

# Models for LLM communication
class LLMRequest(BaseModel):
    prompt: str
    model: str = "anthropic/claude-3-sonnet-20240229"
    max_tokens: int = 1024
    temperature: float = 0.7
    tools: Optional[List[dict]] = None

class LLMResponse(BaseModel):
    text: str
    tool_calls: Optional[List[dict]] = None

# Global MCP client
mcp_client = None

# OpenRouter client setup
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

mcp_server_path = "../mcp-server"  # Adjust to your actual path


# Sampling message handler
async def handle_sampling_message(message: types.SamplingMessage):
    """Handle sampling messages from the MCP server"""
    logger.info(f"Sampling: {message.text}")


# Startup event to initialize MCP client
@app.on_event("startup")
async def startup_event():
    global mcp_client
    try:
        # Create server parameters for stdio connection
        server_params = StdioServerParameters(
            command="go",
            args=["run", f"{mcp_server_path}/main.go"],
            env={
                "DATABASE_CONNECTION_STRING": ""}
        )

        # Initialize the MCP client
        read, write = await stdio_client(server_params)
        mcp_client = ClientSession(
            read, write, sampling_callback=handle_sampling_message
        )

        # Initialize the connection
        await mcp_client.initialize()
        logger.info("MCP client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MCP client: {str(e)}")


# Shutdown event to close the MCP client
@app.on_event("shutdown")
async def shutdown_event():
    global mcp_client
    if mcp_client:
        await mcp_client.close()
        logger.info("MCP client closed")


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


@app.post("/api/chat/new")
async def create_new_chat():
    """Create a new chat session"""
    try:
        # Generate a new chat ID (you might want to use a more sophisticated method)
        chat_id = f"chat_{os.urandom(8).hex()}"
        return {"chat_id": chat_id}
    except Exception as e:
        logger.error(f"Error creating new chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def extract_confirmation_code(text: str) -> Optional[str]:
    """Extract confirmation code from text using regex patterns."""
    # Pattern for Happy Returns confirmation code format: HR followed by 6 alphanumeric characters
    patterns = [
        r'confirmation(?:\s+)?(?:code|number)?[:\s]+(HR[A-Z0-9]{6})',  # HR123456
        r'reference(?:\s+)?(?:code|number)?[:\s]+(HR[A-Z0-9]{6})',     # HR123456
        r'tracking(?:\s+)?(?:code|number)?[:\s]+(HR[A-Z0-9]{6})',      # HR123456
        r'return(?:\s+)?(?:code|number)?[:\s]+(HR[A-Z0-9]{6})',        # HR123456
        r'\b(HR[A-Z0-9]{6})\b'                                         # Generic HR code pattern
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()  # Ensure the code is uppercase
    return None

def should_generate_qr(text: str) -> bool:
    """Check if the response indicates a QR code should be generated."""
    qr_indicators = [
        'scan this qr',
        'scan the qr',
        'qr code',
        'show qr',
        'generate qr',
        'display qr'
    ]
    return any(indicator in text.lower() for indicator in qr_indicators)

@app.post("/api/chat", response_model=ChatResponse)
async def handle_chat_message(message: ChatMessage):
    """Handle incoming chat messages"""
    try:
        # Format the prompt with chat history
        formatted_prompt = format_prompt_with_history(message.current_message, message.chat_history)
        
        # Create LLM request
        llm_request = LLMRequest(prompt=formatted_prompt)
        
        # Get response from OpenRouter
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://happyreturns.com",
                    "X-Title": "Happy Returns Support"
                },
                json={
                    "model": llm_request.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are a helpful Happy Returns customer support agent. 
                            Provide clear, concise answers and use markdown formatting when appropriate.
                            When providing confirmation codes or reference numbers, clearly label them and suggest scanning the QR code when available.
                            Always maintain a professional and friendly tone."""
                        },
                        *[{"role": "user" if h["user_message"] else "assistant", 
                           "content": h["user_message"] or h["bot_response"]} 
                          for h in message.chat_history],
                        {"role": "user", "content": message.current_message}
                    ],
                    "max_tokens": llm_request.max_tokens,
                    "temperature": llm_request.temperature
                }
            )

        if response.status_code != 200:
            logger.error(f"OpenRouter API error: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()
        llm_response = result["choices"][0]["message"]["content"]

        # Check for confirmation code and QR code request
        qr_code = None
        confirmation_code = extract_confirmation_code(llm_response)
        if confirmation_code and should_generate_qr(llm_response):
            qr_code = confirmation_code

        return ChatResponse(
            response=llm_response,
            chat_id=message.chat_id,
            qrCode=qr_code
        )

    except Exception as e:
        logger.error(f"Error handling chat message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def format_prompt_with_history(current_message: str, chat_history: List[dict]) -> str:
    """Format the prompt with chat history for better context"""
    formatted_history = "\n".join([
        f"User: {h['user_message']}\nAssistant: {h['bot_response']}"
        for h in chat_history
    ])
    return f"{formatted_history}\nUser: {current_message}"

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)