# FreeCode

Terminal-based, MCP-driven AI coding agent built entirely on
[ApiFreeLLM](https://apifreellm.com)'s free tier (~1 request per 20-25s,
no tool-calling, no streaming, 32k flat-string context).

Full spec, architecture, phase plan, and status tracker: see
[`FreeCode.md`](./FreeCode.md).

## Status

Currently on `ph-00` (Foundation). See `FreeCode.md` §8.21 for the
per-phase status table.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
freecode                          # runs the current entry point stub
```

## Branching

One branch per phase, named `ph-NN` (e.g. `ph-00`, `ph-01`, ...). See
`FreeCode.md` §8.20-8.21 for the full phase list and current status.
