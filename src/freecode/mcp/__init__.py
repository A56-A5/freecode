"""
mcp/ - MCP server and client integration.

This package contains:
- MCPServer: Core MCP server that exposes FreeCode's tools and resources
- MCPEndpoint: JSON-RPC transport layer for MCP protocol over stdio
- Local tools (freecode.tools) are wrapped as MCP tools

Usage:
    from freecode.mcp import MCPServer, run_mcp_server
    
    # Or run as a server:
    python -m freecode.mcp /path/to/project
"""

from freecode.mcp.server import MCPServer, MCP_SERVER_INFO
from freecode.mcp.endpoint import MCPEndpoint, run_mcp_server
from freecode.tools import ToolExecutor, ToolResult

__all__ = [
    "MCPServer",
    "MCPEndpoint",
    "MCP_SERVER_INFO",
    "run_mcp_server",
    "ToolExecutor",
    "ToolResult",
]
