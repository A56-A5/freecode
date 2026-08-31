#!/usr/bin/env python3
"""
mcp_demo.py - Demonstration of FreeCode MCP server usage

This script shows how to use the FreeCode MCP server programmatically.
You can use this as a reference for integrating FreeCode with other tools.

Usage:
    python examples/mcp_demo.py /path/to/project
"""

import asyncio
import json
import sys
from pathlib import Path


async def demo_mcp_server(project_root: str = ".") -> None:
    """Run a demo of the FreeCode MCP server."""
    from freecode.mcp import MCPServer
    
    print(f"🚀 FreeCode MCP Server Demo")
    print(f"📁 Project: {Path(project_root).resolve()}")
    print()
    
    # Initialize server
    print("Initializing MCP server...")
    server = MCPServer(project_root)
    print("✓ MCP server initialized")
    print()
    
    # List available tools
    print("Available Tools:")
    print("-" * 60)
    tools = server.list_tools()
    for i, tool in enumerate(tools, 1):
        print(f"{i:2}. {tool['name']:20} {tool['description'][:35]}...")
    print()
    
    # List available resources
    print("Available Resources:")
    print("-" * 60)
    resources = server.get_resources()
    for resource in resources:
        print(f"- {resource['name']:25} {resource['description']}")
    print()
    
    # Demo: Call some tools
    print("Tool Execution Examples:")
    print("=" * 60)
    
    # Example 1: List directory
    print("\n1. List project root directory:")
    result = await server.call_tool("list_dir", {"path": "."})
    if not result["isError"]:
        output = result["content"][0]["text"]
        lines = output.split("\n")[:5]  # First 5 lines
        for line in lines:
            print(f"   {line}")
        if len(output.split("\n")) > 5:
            print(f"   ... ({len(output.split(chr(10)))} total lines)")
    else:
        print(f"   Error: {result['content'][0]['text']}")
    
    # Example 2: Read a file
    print("\n2. Read README.md (first 20 lines):")
    result = await server.call_tool("read_file", {"path": "README.md"})
    if not result["isError"]:
        lines = result["content"][0]["text"].split("\n")[:10]
        for line in lines:
            print(f"   {line}")
        print("   ...")
    else:
        print(f"   Info: {result['content'][0]['text']}")
    
    # Example 3: Git status
    print("\n3. Git status:")
    result = await server.call_tool("git_status", {})
    if not result["isError"]:
        output = result["content"][0]["text"]
        lines = output.split("\n")[:5]
        for line in lines:
            if line:
                print(f"   {line}")
    else:
        print(f"   Info: {result['content'][0]['text']}")
    
    # Example 4: Git log
    print("\n4. Recent commits:")
    result = await server.call_tool("git_log", {"n": 3})
    if not result["isError"]:
        output = result["content"][0]["text"]
        for line in output.split("\n")[:3]:
            if line:
                print(f"   {line}")
    else:
        print(f"   Info: {result['content'][0]['text']}")
    
    # Example 5: Search files
    print("\n5. Find Python files:")
    result = await server.call_tool("find_files", {"pattern": "*.py"})
    if not result["isError"]:
        files = result["content"][0]["text"].split("\n")[:5]
        for f in files:
            if f:
                print(f"   {f}")
        total = len(result["content"][0]["text"].split("\n"))
        if total > 5:
            print(f"   ... ({total} total files)")
    else:
        print(f"   Info: {result['content'][0]['text']}")
    
    print()
    print("=" * 60)
    print("✓ Demo complete!")
    print()
    print("To use with Claude Desktop:")
    print(f"  Add to ~/.claude/claude_desktop_config.json:")
    print(f'''
  "freecode": {{
    "command": "freecode",
    "args": ["mcp", "{Path(project_root).resolve()}"]
  }}
''')
    print("See docs/MCP.md for full documentation")


def main() -> int:
    """Entry point."""
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        return 0
    
    project_root = sys.argv[1] if len(sys.argv) > 1 else "."
    try:
        asyncio.run(demo_mcp_server(project_root))
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
