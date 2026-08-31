# FreeCode MCP Server

The **FreeCode MCP (Model Context Protocol) Server** enables external LLMs and tools — such as Claude, Cursor, and other MCP clients — to interact with FreeCode's complete toolkit for code analysis, file operations, shell commands, and git workflows.

## Overview

The MCP server wraps FreeCode's local tools and project context as an MCP endpoint, communicating via JSON-RPC 2.0 over standard I/O (stdio). This means:

- **Claude (Desktop, Web, API)** can use FreeCode's tools to understand your project, run commands, and make edits
- **Cursor** can integrate FreeCode's capabilities into its agent features
- **Any MCP-compatible client** gains instant access to a full coding toolkit
- **No external API calls** — everything runs locally, instantly, without rate limits

## Features

The MCP server exposes:

### Tools (10+)

| Tool | Description | Type |
|------|-------------|------|
| `read_file` | Read file contents | Read-only |
| `write_file` | Create/edit files | Mutating |
| `list_dir` | List directory contents | Read-only |
| `delete_file` | Delete files | Mutating |
| `run_command` | Execute shell commands | Mutating |
| `git_status` | Show git status | Read-only |
| `git_diff` | Show git diff (staged/unstaged) | Read-only |
| `git_log` | Show commit history | Read-only |
| `grep_search` | Search files with patterns | Read-only |
| `find_files` | Find files by glob pattern | Read-only |

### Resources (Context)

| Resource | Description |
|----------|-------------|
| `freecode://project-name/root` | Project root info & directory tree |
| `freecode://project-name/config` | FreeCode project configuration |
| `freecode://project-name/git-info` | Git status and recent commits |
| `freecode://project-name/project-config` | Python project config (pyproject.toml) |

## Installation

FreeCode MCP server is included in the main FreeCode package:

```bash
# Install FreeCode with dev dependencies
git clone https://github.com/A56-A5/freecode.git
cd freecode
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Or with dev extras:
pip install -e ".[dev]"
```

## Usage

### 1. Launch the MCP Server

```bash
# Run MCP server on current project
freecode mcp

# Or specify a project directory
freecode mcp /path/to/my-project

# Or as a module
python -m freecode.mcp /path/to/my-project
```

The server will:
1. Initialize from the project directory
2. Load FreeCode config (.freecode/config.toml) if present
3. Listen on stdin for JSON-RPC 2.0 requests
4. Write responses to stdout

Leave the server running while your MCP client is connected.

### 2. Connect from Claude (Desktop)

**In your `claude_desktop_config.json`** (usually `~/.claude/claude_desktop_config.json` on macOS/Linux):

```json
{
  "mcpServers": {
    "freecode": {
      "command": "freecode",
      "args": ["mcp", "/path/to/your/project"],
      "disabled": false
    }
  }
}
```

Then restart Claude Desktop. FreeCode's tools and resources will appear in Claude's context menu.

### 3. Connect from Cursor

**In Cursor settings** (Cmd+K → Settings → Features → MCP), add:

```json
{
  "mcpServers": [
    {
      "name": "freecode",
      "command": "freecode",
      "args": ["mcp", "/path/to/your/project"]
    }
  ]
}
```

Cursor will now use FreeCode's tools in its agent features.

### 4. Use with Custom MCP Client

Any language/tool that speaks MCP 2.0 can connect:

```bash
# Launch the server and pipe to your client
freecode mcp /path/to/project | your_mcp_client
```

## Example: Claude + FreeCode

**Your prompt to Claude:**
```
I need to fix the authentication bug in /src/auth.py and ensure all tests pass.
```

**Claude can now:**
1. Read the auth.py file → `read_file` tool
2. Search for usages of the auth function → `grep_search` tool
3. Check git diff to see what changed recently → `git_diff` tool
4. Run the test suite → `run_command` tool
5. Write fixes → `write_file` tool (with approval via your MCP client)
6. Commit changes → `run_command` tool (git commit)

All without ever hitting an API rate limit, and all operations happen locally and instantly.

## Configuration

### FreeCode Project Config

Create `.freecode/config.toml` in your project:

```toml
[approval]
# auto: approve all actions automatically
# ask: prompt for approval on mutating ops
# auto_readonly: auto-approve read-only, ask for mutating
default_policy = "ask"

# Commands that are considered "read-only"
readonly_allowlist = ["git", "grep", "ls", "cat", "head", "tail"]

[context]
# Token budget for LLM context (doesn't affect MCP server)
token_budget = 8000

[scheduler]
# Cooldown floor in seconds (doesn't affect MCP server)
cooldown_floor_seconds = 20
```

### MCP Server Permissions

The server respects FreeCode's approval policies:
- **Read-only tools** (read_file, list_dir, git_*, grep_search, find_files) run instantly
- **Mutating tools** (write_file, delete_file, run_command) may require approval based on config

In Claude/Cursor, you'll see approval prompts for sensitive operations.

## Architecture

```
┌────────────────────────────────────┐
│   Claude / Cursor / MCP Client     │
└─────────────────┬──────────────────┘
                  │ JSON-RPC 2.0 (stdio)
                  ▼
        ┌──────────────────────┐
        │   MCPEndpoint        │
        │  (JSON-RPC parser)   │
        └──────────────┬───────┘
                       │
                       ▼
        ┌──────────────────────────┐
        │    MCPServer             │
        │  (tool dispatcher)       │
        └──────────────┬───────────┘
                       │
        ┌──────────────┴───────────────┐
        │                              │
        ▼                              ▼
    FreeCode Tools              FreeCode Resources
    - filesystem                - Project config
    - shell                     - Git info
    - git                       - File tree
    - search
    
        │                              │
        └──────────────┬───────────────┘
                       │
                       ▼
              Local Filesystem & Commands
              (No external API calls)
```

## Troubleshooting

### Server won't start

```bash
# Check if FreeCode is installed
python -c "from freecode.mcp import MCPServer; print('OK')"

# Check project directory
ls /path/to/project/.git  # Should exist for a real project

# Run with debug logging
FREECODE_LOG_LEVEL=DEBUG freecode mcp /path/to/project
```

### Claude doesn't see the tools

1. **Restart Claude Desktop** after updating config
2. **Check server is running** in a terminal
3. **Verify config path**: Claude config is usually `~/.claude/claude_desktop_config.json`
4. **Test MCP manually**:
   ```bash
   freecode mcp /path/to/project &
   # In another terminal:
   echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}' | nc localhost 9000
   ```

### Commands execute but results are empty

- Check file/command exists and is readable
- Verify you're in the correct project directory
- Check file encoding (MCP server handles UTF-8)
- Look at server logs for more details

## Performance Notes

- **File I/O**: Instant (no network)
- **Shell commands**: Depends on command (default 60s timeout)
- **Search**: Fast with ripgrep (requires system ripgrep or grep)
- **Git ops**: Instant (local repo metadata)

Unlike the main FreeCode agent, the MCP server is **not rate-limited**. You can spam requests as much as you like.

## Security

The MCP server operates on a single project directory and:
- **Respects project boundaries** — no path traversal above project root
- **Enforces approval policies** — mutating operations can be gated
- **Logs all operations** — see `.freecode/mcp-server.log`
- **No credentials in output** — API keys and secrets are redacted

**⚠️ Do not run the MCP server on sensitive projects without review of approval policies.**

## Extending the MCP Server

To add new tools:

1. Implement the tool in `freecode.tools.*`
2. Add it to `MCPServer._build_tool_catalog()` in `freecode/mcp/server.py`
3. Implement handler in `MCPEndpoint._execute_tool()` in `freecode/mcp/endpoint.py`

Example:

```python
# In MCPServer._build_tool_catalog():
"my_tool": MCPTool(
    name="my_tool",
    description="Does something useful",
    parameters={
        "properties": {
            "arg": {"type": "string", "description": "An argument"},
        },
        "required": ["arg"],
    },
    read_only=True,
),

# In MCPEndpoint._execute_tool():
case "my_tool":
    return await my_tool_implementation(args["arg"])
```

## License

FreeCode MCP server is part of FreeCode and is released under the MIT license.

## See Also

- [FreeCode GitHub](https://github.com/A56-A5/freecode)
- [MCP Protocol Spec](https://modelcontextprotocol.io)
- [Claude Desktop Integration](https://claude.ai/mcp)
- [Cursor MCP Documentation](https://www.cursor.com/docs)
