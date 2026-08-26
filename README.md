# FreeCode

Terminal-based, MCP-driven AI coding agent built entirely on
[ApiFreeLLM](https://apifreellm.com)'s free tier (~1 request per 20-25s,
no tool-calling, no streaming, 32k flat-string context).

Full spec, architecture, phase plan, and status tracker: see
[`FreeCode.md`](./FreeCode.md).

## Status

Currently on `ph-01` (TUI shell). See `FreeCode.md` §8.21 for the
per-phase status table.

### ph-01 TUI behavior

The `ph-01` TUI is a working mocked shell. It does not yet connect to
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
interface that the future Scheduler will use, but `ph-01` does not contain
the real Scheduler or API-driven cooldown behavior.

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
