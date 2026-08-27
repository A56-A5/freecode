# Contributing

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Branch model

One branch per phase: `ph-NN`. Keep changes reviewable and tested.

## Tests

```bash
pytest
```

Add unit tests for new behavior. TUI Pilot tests should use an isolated
`Config` with `tmp_path` for the SQLite DB (see `tests/unit/test_tui.py`).

## Style

- Python 3.11+, type hints where practical
- Domain layer stays free of TUI / HTTP / filesystem imports
- Never commit API keys or `.freecode/` state
