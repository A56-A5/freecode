# Installation

## Quick start

```bash
git clone https://github.com/A56-A5/freecode.git
cd freecode
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
export FREECODE_API_KEY="your-key"
freecode
```

## From a wheel (local build)

```bash
pip install build
python -m build --wheel
pip install dist/freecode-*.whl
```

## API keys

| Variable | Purpose |
|----------|---------|
| `FREECODE_API_KEY` or `APIFREELLM_API_KEY` | Primary community key |
| `FREECODE_API_KEY_2`, `_3`, … | Extra keys; rotated on daily quota (50 req / 24h per key) |
| `GROQ_API_KEY`, `GROQ_API_KEY_2`, … | Optional Groq provider (also multi-key) |

Get a free key: sign in at [apifreellm.com](https://apifreellm.com).

**Never** put keys in `.freecode/config.toml` or commit them.

## Optional config

Create `.freecode/config.toml` in your project:

```toml
[llm]
timeout_seconds = 120

[scheduler]
cooldown_floor_seconds = 20

[approval]
default_policy = "auto_readonly"   # ask | auto_readonly | auto

[logging]
level = "INFO"
```

Themes: `.freecode/theme.toml` with optional `name = "freecode-dark"` (also
`freecode-light`, `freecode-hc`) plus color overrides.

## Verify

```bash
pip install -e ".[dev]"
pytest -q
freecode   # should open the TUI
```

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Mock replies only | Set `FREECODE_API_KEY` and restart |
| “50 requests / 24h” | Add `FREECODE_API_KEY_2` (and more) |
| “Community request timed out” | Shorter prompt; wait for cooldown |
| `ModuleNotFoundError: httpx` | `pip install -e .` again in the venv |
