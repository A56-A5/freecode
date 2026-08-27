# FreeCode

Terminal-based, MCP-driven AI coding agent built entirely on
[ApiFreeLLM](https://apifreellm.com)'s free tier (~1 request per 20-25s,
no tool-calling, no streaming, 32k flat-string context).

Full spec, architecture, phase plan, and status tracker: see
[`FreeCode.md`](./FreeCode.md).

## Status

Currently on `ph-02` (Configuration + logging). See `FreeCode.md` §8.21 for
the per-phase status table.

### ph-02 Configuration + logging

Configuration is loaded from:

1. Packaged defaults (`freecode/config/defaults.toml`)
2. Optional project override: `.freecode/config.toml`
3. Environment variables (credentials and a few operational knobs)

Exposed settings include ApiFreeLLM endpoint/model, cooldown floor, token
budget, approval policy, and project/runtime paths.

**API keys are never read from TOML.** Set one of:

```bash
export FREECODE_API_KEY=...
# or
export APIFREELLM_API_KEY=...
```

Optional env overrides: `FREECODE_LOG_LEVEL`, `FREECODE_LLM_ENDPOINT`,
`FREECODE_LLM_MODEL`, `FREECODE_CONFIG` (explicit path to config.toml).

Structured logging is configured on startup under the `freecode` logger
(text or JSON). File logging is optional via `[logging] to_file = true`.

Example `.freecode/config.toml`:

```toml
[llm]
timeout_seconds = 90

[scheduler]
cooldown_floor_seconds = 25

[context]
token_budget = 24000

[approval]
default_policy = "ask"   # ask | auto_readonly | auto

[logging]
level = "DEBUG"
format = "text"
to_file = false
```

### ph-01 TUI behavior

The TUI remains a working mocked shell. It does not yet connect to
ApiFreeLLM or an Agent Core.

On launch, FreeCode shows the landing screen with the FreeCode ASCII logo
and an input field. The landing input is focused initially.

Submitting the first non-empty message transitions to the conversation
layout and focuses the chat input. The submitted user message is added to
the transcript, followed by a mock assistant response.

The mock response is intentionally demo behavior for `ph-01`. It is selected
from the submitted text:

* messages containing `hello` or `hi` receive a greeting/test response
* messages containing `help` receive a mock command-list response
* messages containing `test` receive a longer mock UI-testing response
* other messages receive a generic mock response

Further messages remain in the same conversation and are appended to the
transcript. The transcript automatically scrolls to the latest message.

The activity indicator, cooldown bar, footer statistics, and configurable
theme are implemented as TUI components. The cooldown widget exposes the
interface that the future Scheduler will use, but the real Scheduler and
API-driven cooldown behavior arrive in later phases.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
freecode                          # runs the current TUI shell
```

## Branching

One branch per phase, named `ph-NN` (e.g. `ph-00`, `ph-01`, ...). See
`FreeCode.md` §8.20-8.21 for the full phase list and current status.
