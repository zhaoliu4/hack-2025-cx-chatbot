import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import logging
from llm.llm_service import get_return_status_response_with_tools
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
            user_message
        )

        return {
            "response": response_text,
            "chat_history": updated_history
        }
    except Exception as e:
        logger.error(f"Error in chat processing: {str(e)}")
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

def format_prompt_with_history(current_message: str, chat_history: List[dict]) -> str:
    """Format the prompt with chat history for better context"""
    formatted_history = "\n".join([
        f"User: {h['user_message']}\nAssistant: {h['bot_response']}"
        for h in chat_history
    ])
    return f"{formatted_history}\nUser: {current_message}"

if __name__ == "__main__":
    # Explicit import here to avoid linting errors
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)