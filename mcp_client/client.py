import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from config.settings import TAVILY_API_KEY

def build_mcp_client(workspace_path: str, provider: str = None, model: str = None , output_dir: str = None) -> MultiServerMCPClient:
    """
    Connects to all 3 required MCP servers:
    1. filesystem  — read/write/list local files
    2. tavily      — web search (external resource)
    3. rag         — custom local vector DB with HyDE (SSE transport)
    """
    return MultiServerMCPClient(
        {
            "filesystem": {
                "transport": "stdio",
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    workspace_path,
                    output_dir,
                ],
            },
            "tavily": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "tavily-mcp@0.1.4"],
                "env": {
                    **os.environ,
                    "TAVILY_API_KEY": TAVILY_API_KEY or "",
                },
            },
            "rag": {
                "transport": "sse",
                "url": "http://127.0.0.1:8001/sse",
            },
        }
    )
