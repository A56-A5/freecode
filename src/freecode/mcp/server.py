"""
freecode.mcp.server - MCP server exposing FreeCode's tools and project context.

This module implements a Model Context Protocol (MCP) server that allows external
LLMs and tools to interact with FreeCode's capabilities:
- File system operations (read/write/list/search)
- Shell command execution
- Git operations
- Code search and project indexing
- Project context and configuration

The MCP server wraps FreeCode's local tool executors and presents them as
MCP resources and tools, with proper error handling and approval policies.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from freecode.config.logging import get_logger
from freecode.config.settings import ApprovalSettings
from freecode.tools.executor import ToolExecutor
from freecode.tools.results import ToolResult

log = get_logger(__name__)


class MCPTool:
    """Represents a single MCP tool definition."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        read_only: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.read_only = read_only

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            },
        }


class MCPServer:
    """
    MCP Server for FreeCode.

    Exposes file system, shell, git, and search tools over the MCP protocol.
    Integrates with FreeCode's approval policy for sensitive operations.
    """

    def __init__(
        self,
        project_root: Path | str,
        approval_settings: ApprovalSettings | None = None,
    ) -> None:
        self.root = Path(project_root).resolve()
        self.approval = approval_settings or ApprovalSettings()
        self.executor = ToolExecutor(self.root, approval=self.approval)
        self._tools = self._build_tool_catalog()

    def _build_tool_catalog(self) -> dict[str, MCPTool]:
        """Build the catalog of available MCP tools."""
        return {
            # Filesystem tools
            "read_file": MCPTool(
                name="read_file",
                description="Read the contents of a file from the project.",
                parameters={
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to file, relative to project root",
                        },
                    },
                    "required": ["path"],
                },
                read_only=True,
            ),
            "write_file": MCPTool(
                name="write_file",
                description="Write content to a file. Creates parent directories if needed.",
                parameters={
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to file, relative to project root",
                        },
                        "content": {
                            "type": "string",
                            "description": "File content",
                        },
                    },
                    "required": ["path", "content"],
                },
                read_only=False,
            ),
            "list_dir": MCPTool(
                name="list_dir",
                description="List contents of a directory.",
                parameters={
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to directory (default: '.')",
                        },
                    },
                    "required": [],
                },
                read_only=True,
            ),
            "delete_file": MCPTool(
                name="delete_file",
                description="Delete a file from the project.",
                parameters={
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to file, relative to project root",
                        },
                    },
                    "required": ["path"],
                },
                read_only=False,
            ),
            # Shell tools
            "run_command": MCPTool(
                name="run_command",
                description="Execute a shell command in the project root.",
                parameters={
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute",
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Timeout in seconds (default: 60)",
                            "default": 60,
                        },
                    },
                    "required": ["command"],
                },
                read_only=False,
            ),
            # Git tools
            "git_status": MCPTool(
                name="git_status",
                description="Get git status of the project (short format).",
                parameters={
                    "properties": {},
                    "required": [],
                },
                read_only=True,
            ),
            "git_diff": MCPTool(
                name="git_diff",
                description="Show git diff (unstaged changes by default).",
                parameters={
                    "properties": {
                        "staged": {
                            "type": "boolean",
                            "description": "Show staged changes instead (default: false)",
                            "default": False,
                        },
                    },
                    "required": [],
                },
                read_only=True,
            ),
            "git_log": MCPTool(
                name="git_log",
                description="Show git commit log.",
                parameters={
                    "properties": {
                        "n": {
                            "type": "integer",
                            "description": "Number of commits to show (default: 10)",
                            "default": 10,
                        },
                    },
                    "required": [],
                },
                read_only=True,
            ),
            # Search tools
            "grep_search": MCPTool(
                name="grep_search",
                description="Search for patterns in project files using grep/ripgrep.",
                parameters={
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Search pattern (regex or literal)",
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "File glob pattern to search in (default: '*')",
                        },
                        "is_regex": {
                            "type": "boolean",
                            "description": "Treat pattern as regex (default: false)",
                            "default": False,
                        },
                    },
                    "required": ["pattern"],
                },
                read_only=True,
            ),
            "find_files": MCPTool(
                name="find_files",
                description="Find files matching a glob pattern.",
                parameters={
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern for files to find",
                        },
                    },
                    "required": ["pattern"],
                },
                read_only=True,
            ),
        }

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP-format list of available tools."""
        return [tool.to_dict() for tool in self._tools.values()]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a tool and return MCP-format result.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            MCP result object with content array
        """
        if name not in self._tools:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            }

        try:
            result = await self._execute_tool(name, arguments)
            # Format ToolResult as string
            text_parts = []
            if result.output:
                text_parts.append(result.output)
            if result.error:
                text_parts.append(f"[Error] {result.error}")
            if result.status not in ("ok", "error"):
                text_parts.append(f"[{result.status.upper()}]")
            
            text = "\n".join(text_parts) if text_parts else f"[{result.status}]"
            
            return {
                "isError": result.status == "error",
                "content": [{"type": "text", "text": text}],
            }
        except Exception as e:
            log.exception(f"Tool execution error: {name}")
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Error executing {name}: {str(e)}"}],
            }

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Execute tool and return result."""
        from freecode.tools import filesystem, git, search, shell

        match name:
            case "read_file":
                return filesystem.read_file(self.root, args["path"])
            case "write_file":
                return filesystem.write_file(self.root, args["path"], args["content"])
            case "list_dir":
                path = args.get("path", ".")
                return filesystem.list_dir(self.root, path)
            case "delete_file":
                return await self._delete_file(args["path"])
            case "run_command":
                timeout = args.get("timeout", 60.0)
                return await shell.run_command(args["command"], cwd=self.root, timeout=timeout)
            case "git_status":
                return await git.git_status(self.root)
            case "git_diff":
                staged = args.get("staged", False)
                return await git.git_diff(self.root, staged=staged)
            case "git_log":
                n = args.get("n", 10)
                return await git.git_log(self.root, n=n)
            case "grep_search":
                return await search.grep_search(
                    self.root,
                    args["pattern"],
                    file_pattern=args.get("file_pattern", "*"),
                    is_regex=args.get("is_regex", False),
                )
            case "find_files":
                return await search.find_files(self.root, args["pattern"])
            case _:
                return ToolResult(
                    tool=name,
                    status="error",
                    error=f"Tool not implemented: {name}",
                )

    async def _delete_file(self, path: str) -> ToolResult:
        """Delete a file (filesystem doesn't have this yet)."""
        try:
            from freecode.tools.filesystem import _resolve

            target = _resolve(self.root, path)
            if not target.is_file():
                return ToolResult(tool="delete_file", status="error", error=f"not a file: {path}", mutating=True)
            target.unlink()
            return ToolResult(
                tool="delete_file",
                status="ok",
                output=f"deleted {path}",
                data={"path": str(target)},
                mutating=True,
            )
        except Exception as e:
            return ToolResult(tool="delete_file", status="error", error=str(e), mutating=True)

    def get_resources(self) -> list[dict[str, Any]]:
        """
        Return MCP resources (project context, configuration, etc).

        Resources provide read-only context about the project.
        """
        resources = []

        # Root directory resource
        resources.append({
            "uri": f"freecode://{self.root.name}/root",
            "name": "Project Root",
            "description": f"FreeCode project root directory: {self.root}",
            "mimeType": "text/plain",
        })

        # Config resource
        config_path = self.root / ".freecode" / "config.toml"
        if config_path.exists():
            resources.append({
                "uri": f"freecode://{self.root.name}/config",
                "name": "FreeCode Config",
                "description": "FreeCode project configuration",
                "mimeType": "text/plain",
            })

        # Git info resource
        if (self.root / ".git").exists():
            resources.append({
                "uri": f"freecode://{self.root.name}/git-info",
                "name": "Git Information",
                "description": "Current git status and log",
                "mimeType": "text/plain",
            })

        # pyproject.toml resource
        if (self.root / "pyproject.toml").exists():
            resources.append({
                "uri": f"freecode://{self.root.name}/project-config",
                "name": "Project Configuration",
                "description": "Python project configuration (pyproject.toml)",
                "mimeType": "text/plain",
            })

        return resources

    async def read_resource(self, uri: str) -> str:
        """
        Read a resource by URI.

        Args:
            uri: Resource URI (freecode://project-name/resource-type)

        Returns:
            Resource content as string
        """
        if "/root" in uri:
            return self._describe_root()
        elif "/config" in uri:
            return self._read_config()
        elif "/git-info" in uri:
            return await self._get_git_info()
        elif "/project-config" in uri:
            return self._read_project_config()
        else:
            return f"Unknown resource: {uri}"

    def _describe_root(self) -> str:
        """Describe the project root."""
        lines = [f"FreeCode Project: {self.root.name}", f"Root: {self.root}", ""]

        # File tree preview
        lines.append("Directory structure (top level):")
        try:
            for item in sorted(self.root.iterdir()):
                if item.name.startswith("."):
                    continue
                kind = "[DIR]" if item.is_dir() else "[FILE]"
                lines.append(f"  {kind} {item.name}")
        except Exception as e:
            lines.append(f"  Error listing directory: {e}")

        return "\n".join(lines)

    def _read_config(self) -> str:
        """Read FreeCode config if present."""
        config_path = self.root / ".freecode" / "config.toml"
        if config_path.exists():
            try:
                return config_path.read_text()
            except Exception as e:
                return f"Error reading config: {e}"
        return "No FreeCode config found at .freecode/config.toml"

    def _read_project_config(self) -> str:
        """Read pyproject.toml if present."""
        config_path = self.root / "pyproject.toml"
        if config_path.exists():
            try:
                return config_path.read_text()
            except Exception as e:
                return f"Error reading config: {e}"
        return "No pyproject.toml found"

    async def _get_git_info(self) -> str:
        """Get git status and log summary."""
        from freecode.tools import git

        lines = []
        try:
            status_result = await git.git_status(self.root)
            if status_result.output:
                lines.append("=== Git Status ===")
                lines.append(status_result.output)
                lines.append("")
        except Exception as e:
            lines.append(f"Error getting git status: {e}")
            lines.append("")

        try:
            log_result = await git.git_log(self.root, n=5)
            if log_result.output:
                lines.append("=== Recent Commits ===")
                lines.append(log_result.output)
        except Exception as e:
            lines.append(f"Error getting git log: {e}")

        return "\n".join(lines) or "Git repository not found or not initialized"


# Metadata for MCP server
MCP_SERVER_INFO = {
    "name": "freecode",
    "version": "0.1.0",
    "description": "MCP server for FreeCode — terminal AI coding agent on ApiFreeLLM's free tier",
    "author": "FreeCode contributors",
    "license": "MIT",
    "homepage": "https://github.com/A56-A5/freecode",
}
