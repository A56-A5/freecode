# FreeCode

A terminal-based, MCP-driven AI coding agent built using
[ApiFreeLLM](https://apifreellm.com)'s free tier.

No expensive API.  
No huge model.  
No fancy infrastructure.

Just a heavily rate-limited free LLM and a bunch of code trying to make it useful.

ApiFreeLLM gives you roughly **one request every 20–25 seconds**, doesn't support
native tool calling or streaming, and gives you a flat-string context. Community
keys are also capped at about **50 requests / 24 hours** each.

So FreeCode has to handle the rest — figuring out what the model wants to do,
running tools, feeding results back, managing context, rotating keys, and
keeping the whole thing moving.

The idea is pretty simple:

> If the big companies can build coding agents with huge models and expensive
> infrastructure, how far can I get with a free one?

This isn't trying to be another Cursor or Claude Code.  
I'm just trying to make the shit work.

Full architecture and phase history: [`FreeCode.md`](./FreeCode.md).

---

## Requirements

- Python **3.11+**
- A free key from [apifreellm.com](https://apifreellm.com) (Google sign-in)

## Install

```bash
git clone https://github.com/A56-A5/freecode.git
cd freecode
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

For development (tests):

```bash
pip install -e ".[dev]"
pytest
```

See also [`INSTALL.md`](./INSTALL.md).

## Configure API keys

Keys come from the environment only — never from TOML.

```bash
# Primary key
export FREECODE_API_KEY="your-key"
# or
export APIFREELLM_API_KEY="your-key"

# Optional: rotate when a key hits the community 50/day limit
export FREECODE_API_KEY_2="second-key"
export FREECODE_API_KEY_3="third-key"

# Optional second provider (OpenAI-compatible Groq free tier)
export GROQ_API_KEY="gsk_..."
export GROQ_API_KEY_2="gsk_backup..."
# Optional default Groq model
export GROQ_MODEL="llama-3.3-70b-versatile"
```

Then:

```bash
freecode
```

Without a key, FreeCode still launches in **mock** mode so you can poke at the TUI.

Optional project config (no secrets): `.freecode/config.toml`  
Theme overrides: `.freecode/theme.toml`  
Session DB: `.freecode/state.db` (gitignored)

## Usage

Pin context with **`@path`** in a message (e.g. `fix @src/main.py`).  
The model can request **web lookups** via `{"type":"web","url":"..."}` or `{"type":"web","query":"..."}` — you get an **Allow / Deny** prompt first.


| Input | Action |
|-------|--------|
| **Enter** | New line in the composer |
| **Ctrl+Enter** | Send message |
| **/** or **Ctrl+/** | Command palette |
| **Ctrl+E** | Edit last prompt |
| **Ctrl+X** | Interrupt the agent |
| **Ctrl+C** | Quit |

### Slash commands

| Command | What it does |
|---------|----------------|
| `/help` | Shortcuts + commands |
| `/sessions` | List sessions (numbered) |
| `/session switch 1` | Switch by list number (or short id) |
| `/session delete 1` | Delete by list number (or short id) |
| `/session new [title]` | New session |
| `/new` | Fresh chat |
| `/edit` | Load last prompt into the composer |
| `/theme` / `/theme <name>` | List or switch themes |
| `/provider` / `/provider <name>` | ApiFreeLLM ↔ Groq |
| `/model` / `/model <id>` | Groq model (no 20–25s wait on Groq) |
| `/plan` | Dry-run: propose tools only, no side effects |
| `/undo` | Restore files from the last edit batch |

Mutating tools (edits, shell, git writes) show an **Allow / Deny** dialog.

## How it works (short)

```
TUI → AgentLoop → ContextEngine → Scheduler → ApiFreeLLM
    → response repair → approval → tools → events/coalescer → SQLite
```

The free tier forces:

- a **scheduler** around live `delaySeconds` / 429 backoff  
- **JSON repair** when the model mangles structured replies  
- **tool + approval** instead of native function calling  
- **key rotation** across `FREECODE_API_KEY`, `_2`, `_3`, … when daily quota hits  

## Development

```bash
pip install -e ".[dev]"
pytest
freecode
```

Contributions: see [`CONTRIBUTING.md`](./CONTRIBUTING.md).  
License: [`LICENSE`](./LICENSE) (MIT).

## Status

Phases **ph-00 through ph-13** are implemented and tested. Details in
`FreeCode.md` §8.21.
