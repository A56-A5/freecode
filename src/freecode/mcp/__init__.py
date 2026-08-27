"""
mcp/ - MCP client boundary (ph-07 stub).

Local tools in freecode.tools are the default implementation. This package
is the abstraction point for external MCP servers later (GitHub, Docker, …).
"""

# Re-export the local executor so callers can depend on mcp. as a façade.
from freecode.tools import ToolExecutor, ToolResult

__all__ = ["ToolExecutor", "ToolResult"]
