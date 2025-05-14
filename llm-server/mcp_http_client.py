"""
HTTP MCP Client - Client for connecting to MCP server over HTTP.
"""
import httpx
import logging
import json
from typing import Dict, Any, List, Optional, Callable, Awaitable

# Configure logging
logger = logging.getLogger(__name__)

class MCPHTTPClient:
    """Client for connecting to MCP server over HTTP."""
    
    def __init__(self, base_url: str, sampling_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None):
        """
        Initialize the HTTP MCP client.
        
        Args:
            base_url (str): The base URL of the MCP HTTP server.
            sampling_callback (Optional[Callable]): Callback for sampling messages.
        """
        self.base_url = base_url.rstrip('/')
        self.sampling_callback = sampling_callback
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def initialize(self) -> None:
        """Initialize the connection to the MCP server."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                logger.info("Successfully connected to MCP HTTP server")
            else:
                logger.error(f"Failed to connect to MCP HTTP server: {response.text}")
                raise Exception(f"Failed to connect to MCP HTTP server: {response.status_code}")
        except Exception as e:
            logger.error(f"Error initializing HTTP MCP client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Close the connection to the MCP server."""
        await self.client.aclose()
        logger.info("HTTP MCP client connection closed")
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools from the MCP server.
        
        Returns:
            List[Dict[str, Any]]: List of available tools.
        """
        try:
            response = await self.client.get(f"{self.base_url}/tools")
            if response.status_code == 200:
                tools = response.json()
                return tools
            else:
                logger.error(f"Failed to list tools: {response.text}")
                raise Exception(f"Failed to list tools: {response.status_code}")
        except Exception as e:
            logger.error(f"Error listing tools: {str(e)}")
            raise
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.
        
        Args:
            tool_name (str): Name of the tool to call.
            arguments (Dict[str, Any]): Arguments for the tool.
            
        Returns:
            Dict[str, Any]: Result of the tool call.
        """
        try:
            payload = {
                "name": tool_name,
                "arguments": arguments
            }
            
            response = await self.client.post(
                f"{self.base_url}/tools/{tool_name}/invoke", 
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                # If there's a sampling callback, call it
                if self.sampling_callback and "text" in result:
                    await self.sampling_callback({"text": result["text"]})
                return result
            else:
                logger.error(f"Failed to call tool {tool_name}: {response.text}")
                raise Exception(f"Failed to call tool {tool_name}: {response.status_code}")
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {str(e)}")
            raise
