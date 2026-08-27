# FreeCode

Terminal-based, MCP-driven AI coding agent built entirely on
[ApiFreeLLM](https://apifreellm.com)'s free tier (~1 request per 20–25s,
no tool-calling, no streaming, 32k flat-string context).

Full spec, architecture, phase plan, and status tracker:
[`FreeCode.md`](./FreeCode.md).

## Status

**All phases ph-00 through ph-13 are done, verified.** See `FreeCode.md` §8.21.

Stack: TUI → AgentLoop → ContextEngine → Scheduler → ApiFreeLLM → repair →
tools (with approval) → events/coalescer → SQLite persistence.

## Install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

export FREECODE_API_KEY="your-key"   # or APIFREELLM_API_KEY
# Optional: cycle keys when one hits the community 50/day limit
export FREECODE_API_KEY_2="second-key"
export FREECODE_API_KEY_3="third-key"
freecode
```

Without an API key the TUI runs in **mock** mode (layout testing only).

## Usage notes

- **Composer:** Enter = newline, **Ctrl+Enter** = send
- **Type `/`** to open the command palette (or use `/help`)
- **Ctrl+E** / `/edit` — edit last prompt
- **Ctrl+X** — interrupt agent
- Sessions: `/sessions`, `/new`, `/session switch <id>`, `/session delete <id>`
- Mutating tools prompt **Allow / Deny**

## Development

```bash
pip install -e ".[dev]"
pytest
freecode
```

Config: copy keys into `.freecode/config.toml` (never commit API keys).
Theme: `.freecode/theme.toml`. State: `.freecode/state.db`.

## Branching

One branch per phase (`ph-00` … `ph-13`). See `FreeCode.md` §8.20–8.21.
