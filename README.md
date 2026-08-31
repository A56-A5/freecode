# FreeCode

A terminal-based AI coding agent built on [ApiFreeLLM](https://apifreellm.com)’s free tier — with optional [Groq](https://console.groq.com) as a second provider.

No expensive API.  
No huge model.  
No fancy infrastructure.

Just a heavily rate-limited free LLM and a bunch of code trying to make it useful.

ApiFreeLLM is roughly **one request every 20–25 seconds**, no native tool calling, no streaming, flat-string context, and about **50 requests / 24h** per community key. FreeCode handles the rest: structured replies, tools, approval, context, sessions, and key/provider rotation.

> If the big companies can build coding agents with huge models and expensive infrastructure, how far can I get with a free one?

This isn’t trying to be another Cursor or Claude Code.  
I’m just trying to make the shit work.

Architecture notes: [`FreeCode.md`](./FreeCode.md).

---

## Requirements

- Python **3.11+**
- At least one API key (ApiFreeLLM and/or Groq)

## Install

```bash
git clone https://github.com/A56-A5/freecode.git
cd freecode
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

Dev / tests:

```bash
pip install -e ".[dev]"
pytest
```

More detail: [`INSTALL.md`](./INSTALL.md).

## API keys

Keys are **environment-only** (never committed in TOML).

```bash
# ApiFreeLLM (community)
export FREECODE_API_KEY="your-key"       # or APIFREELLM_API_KEY
export FREECODE_API_KEY_2="second-key"   # optional rotation (50/day per key)
export FREECODE_API_KEY_3="third-key"

# Groq (optional, faster — no 20–25s floor)
export GROQ_API_KEY="gsk_..."
export GROQ_API_KEY_2="gsk_..."
export GROQ_MODEL="openai/gpt-oss-20b"
```

```bash
freecode
```

No key → mock mode (UI only).

Optional project config: `.freecode/config.toml` (timeouts, approval policy, logging).  
Theme: `.freecode/theme.toml`. Session DB: `.freecode/state.db`.

## Usage

| Input | Action |
|-------|--------|
| **Enter** | New line |
| **Ctrl+Enter** | Send |
| **/** or **Ctrl+/** | Command palette |
| **Ctrl+E** | Edit last prompt |
| **Ctrl+X** | Interrupt agent |

Pin files in a message with **`@path`** (example: `fix @src/main.py`).

### Commands

| Command | What it does |
|---------|----------------|
| `/help` | Shortcuts + commands |
| `/sessions` | List sessions (numbered) |
| `/session switch 1` | Switch by list # or id prefix |
| `/session delete 1` | Delete by list # or id prefix |
| `/new` | Fresh chat |
| `/edit` | Load last prompt into the composer |
| `/plan` | Toggle dry-run (propose tools only) |
| `/undo` | Restore files from the last edit batch |
| `/provider` / `/provider groq` | List / force provider |
| `/model` / `/model <id>` | Groq model (after `/provider groq`) |
| `/theme` / `/theme <name>` | Color themes |

Mutating tools, outside-root paths, and **web lookups** show **Allow / Deny**.

### Web lookup

The model can request:

```json
{"type": "web", "url": "https://example.com/docs"}
{"type": "web", "query": "some search terms"}
```

You approve first; FreeCode fetches the page (or a lightweight search) and feeds text back into the next turn.

### Providers

- **ApiFreeLLM** — free community tier; cooldown from live `delaySeconds` (~20–25s floor).
- **Groq** — OpenAI-compatible; no artificial inter-request floor; multi-key rotation on quota/429.

Footer shows the active provider (and Groq model when relevant).

## MCP Server

Run FreeCode as an **MCP (Model Context Protocol) server** to give Claude, Cursor, or other MCP clients instant access to your project's tools:

```bash
# Launch MCP server on your project
freecode mcp /path/to/project

# Or in current directory
freecode mcp .
```

Then connect from:

- **Claude Desktop** — add to `~/.claude/claude_desktop_config.json`:
  ```json
  "mcpServers": {
    "freecode": {
      "command": "freecode",
      "args": ["mcp", "/path/to/project"]
    }
  }
  ```

- **Cursor** — add to settings (MCP servers section):
  ```json
  {
    "name": "freecode",
    "command": "freecode",
    "args": ["mcp", "/path/to/project"]
  }
  ```

The server exposes 10+ tools (read/write files, run shell commands, git operations, code search) without rate limits. Full details: [`docs/MCP.md`](./docs/MCP.md).

## How it works

```
TUI → AgentLoop → ContextEngine → Scheduler → LLM (ApiFreeLLM or Groq)
    → response repair → approval → tools → events → SQLite
```

Local tools: filesystem, shell, git, search, web. No native tool-calling on the free API — the model emits JSON; FreeCode repairs and executes it.

## License

MIT — see [`LICENSE`](./LICENSE).
