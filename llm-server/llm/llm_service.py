import httpx
import openai
import os
import json
import asyncio

# It's good practice to load your API key from an environment variable
OPENROUTER_API_KEY = "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"

# Configure OpenAI with OpenRouter
openai.api_key = OPENROUTER_API_KEY
openai.api_base = "https://openrouter.ai/api/v1"

HTTP_MCP_SERVER_URL = os.environ.get("HTTP_MCP_SERVER_URL", "http://localhost:53000/mcp")

# Define the system prompt separately for clarity
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are a customer service expert for 'Happy Returns'. "
        "Your sole responsibility is to provide information about the status of customer returns. "
        "You have access to tools that can look up return information when a customer provides a confirmation code. "
        "Always use the get_return_by_confirmation_code tool when a customer mentions their confirmation code (an 8-character string starting with 'HR'). "
        "You must not answer any questions or engage in conversations on any other topic. "
        "If a customer asks about something other than a return status, "
        "politely state that you can only help with return status inquiries. "
        "Be courteous and professional in all your responses."
    )
}

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
        print(f"Error making JSON-RPC request to MCP server: {str(e)}")
        return {"error": str(e)}



def get_return_status_response_with_history(chat_history, customer_query):
    """
    Gets a response from the LLM for a customer query, maintaining chat history.

    Args:
        chat_history (list): A list of message dictionaries representing the conversation so far.
                             Example: [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]
        customer_query (str): The latest query from the customer.

    Returns:
        tuple: (assistant_response_content, updated_chat_history)
               assistant_response_content (str): The content of the assistant's response.
               updated_chat_history (list): The chat history including the latest interaction.
    """
    # Make a local copy of the history to avoid modifying the original list if it's passed around
    current_conversation = list(chat_history)

    # Ensure the system prompt is the first message if history is empty or doesn't have it
    if not current_conversation or current_conversation[0].get("role") != "system":
        current_conversation.insert(0, SYSTEM_PROMPT)
    # Or if it's there but different (e.g., updated system prompt), replace it
    elif current_conversation[0].get("role") == "system" and current_conversation[0]["content"] != SYSTEM_PROMPT["content"]:
        current_conversation[0] = SYSTEM_PROMPT


    # Add the new user query to the conversation
    current_conversation.append({"role": "user", "content": customer_query})

    try:
        # Specify max_tokens to limit the request size
        completion = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",  # Less expensive model
            messages=current_conversation,
            max_tokens=1000  # Limit response length to reduce token usage
        )
        
        # Check if we received an error response
        if isinstance(completion, dict) and "error" in completion:
            raise Exception(f"API Error: {completion['error']['message']}")
        
        # Otherwise, extract the content based on the response structure
        if isinstance(completion, dict) and "choices" in completion:
            # Dict-like response
            assistant_response_content = completion["choices"][0]["message"]["content"]
        else:
            # Object-like response
            assistant_response_content = completion.choices[0].message.content

        # Add the assistant's response to the conversation history
        current_conversation.append({"role": "assistant", "content": assistant_response_content})

        return assistant_response_content, current_conversation
    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(error_message)
        # Add a generic error response to history to inform the user
        current_conversation.append({"role": "assistant", "content": "I'm sorry, but I'm unable to process your request at the moment."})
        return "I'm sorry, but I'm unable to process your request at the moment.", current_conversation

async def get_return_status_response_with_tools(chat_history, customer_query, mcp_client):
    """
    Gets a response from the LLM for a customer query, with tool calling capability via MCP.

    Args:
        chat_history (list): A list of message dictionaries representing the conversation so far.
        customer_query (str): The latest query from the customer.
        mcp_client: The initialized MCP client session

    Returns:
        tuple: (assistant_response_content, updated_chat_history)
               assistant_response_content (str): The content of the assistant's response.
               updated_chat_history (list): The chat history including the latest interaction.
    """
    # Make a local copy of the history to avoid modifying the original list if it's passed around
    current_conversation = list(chat_history)

    # Ensure the system prompt is the first message if history is empty or doesn't have it
    if not current_conversation or current_conversation[0].get("role") != "system":
        current_conversation.insert(0, SYSTEM_PROMPT)
    # Or if it's there but different (e.g., updated system prompt), replace it
    elif current_conversation[0].get("role") == "system" and current_conversation[0]["content"] != SYSTEM_PROMPT["content"]:
        current_conversation[0] = SYSTEM_PROMPT

    # Add the new user query to the conversation
    current_conversation.append({"role": "user", "content": customer_query})

    try:

        # Get relevant tools from MCP server
        openai_tools = await list_tools()

        # Request the model with tools enabled
        completion = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=current_conversation,
            max_tokens=1000,
            tools=openai_tools,
            tool_choice="auto"  # Let the model decide when to use tools
        )
        
        # Check if we received an error response
        if isinstance(completion, dict) and "error" in completion:
            raise Exception(f"API Error: {completion['error']['message']}")
            
        # Extract the assistant message
        assistant_message = completion["choices"][0]["message"]
        
        # Check for tool calls
        if "tool_calls" in assistant_message and assistant_message["tool_calls"]:
            # Add the assistant's message with tool calls to the conversation
            current_conversation.append(assistant_message)
            
            # Process each tool call
            for tool_call in assistant_message["tool_calls"]:
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                
                print(f"Executing tool: {function_name} with args: {function_args}")
                
                # Execute the tool via MCP
                tool_result = await mcp_client.call_tool(function_name, arguments=function_args)
                
                # Add the tool result to the conversation
                current_conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": json.dumps(tool_result) if isinstance(tool_result, dict) else tool_result
                })
            
            # Make a second call to process the tool results
            second_completion = openai.ChatCompletion.create(
                model="openai/gpt-3.5-turbo",
                messages=current_conversation,
                max_tokens=1000
            )
            
            # Extract the final response
            assistant_response_content = second_completion["choices"][0]["message"]["content"]
            current_conversation.append({"role": "assistant", "content": assistant_response_content})
        else:
            # No tool calls, just use the content
            assistant_response_content = assistant_message["content"]
            current_conversation.append({"role": "assistant", "content": assistant_response_content})
        
        return assistant_response_content, current_conversation
    
    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(error_message)
        # Add a generic error response to history to inform the user
        current_conversation.append({"role": "assistant", "content": "I'm sorry, but I'm unable to process your request at the moment."})
        return "I'm sorry, but I'm unable to process your request at the moment.", current_conversation

# Example usage within your Python server for a multi-turn conversation:
if __name__ == "__main__":
    # Initialize an empty chat history for a new conversation
    conversation_history = []

    # Turn 1
    query1 = "Hello, I want to know about my return."
    print(f"Customer: {query1}")
    assistant_reply1, conversation_history = get_return_status_response_with_history(conversation_history, query1)
    print(f"Chatbot: {assistant_reply1}")
    print(f"Current History: {conversation_history}\n")

    print("-" * 20)

    # Turn 2: Customer provides more information
    query2 = "My order number is #RMA12345. Can you check it?"
    print(f"Customer: {query2}")
    assistant_reply2, conversation_history = get_return_status_response_with_history(conversation_history, query2)
    print(f"Chatbot: {assistant_reply2}")
    print(f"Current History: {conversation_history}\n")

    print("-" * 20)

    # Turn 3: Customer asks an unrelated question
    query3 = "What's the weather like today?"
    print(f"Customer: {query3}")
    assistant_reply3, conversation_history = get_return_status_response_with_history(conversation_history, query3)
    print(f"Chatbot: {assistant_reply3}")
    print(f"Current History: {conversation_history}\n")

    print("-" * 20)

    # Turn 4: Customer asks another related question
    query4 = "Okay, for order #RMA12345, has the refund been processed?"
    print(f"Customer: {query4}")
    assistant_reply4, conversation_history = get_return_status_response_with_history(conversation_history, query4)
    print(f"Chatbot: {assistant_reply4}")
    print(f"Current History: {conversation_history}\n")