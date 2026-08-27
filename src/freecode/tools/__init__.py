"""
tools/ - local execution layer (ph-07).

Filesystem, shell, git, and search. MCP package stays a future adapter.
"""
from freecode.tools.executor import ToolExecutor, action_needs_approval, is_readonly_command
from freecode.tools.results import ToolResult, ToolStatus

__all__ = [
    "ToolExecutor",
    "ToolResult",
    "ToolStatus",
    "action_needs_approval",
    "is_readonly_command",
]
