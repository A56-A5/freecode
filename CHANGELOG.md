# Changelog

## 0.1.0 — main

- Multi-provider router: **ApiFreeLLM** + **Groq** (each with multi-key rotation)
- `/provider` command; footer shows active provider
- `/theme` choice persisted to `.freecode/theme.toml`
- Session switch/delete hints in command palette by list #
- Footer files-edited covered by integration test
- Honest project README + INSTALL guide
- API key rotation across `FREECODE_API_KEY`, `_2`, `_3`, … on community daily quota
- Session switch/delete by list number (`/session delete 1`)
- Command palette: live filter, Enter = top match, clears composer residue
- Full stack (TUI, agent loop, tools + approval, context, events, SQLite)
- Hardening tests, CI workflow, themes (`freecode-dark` / `light` / `hc`)

## 0.0.1 — ph-13

Initial packaged hardening release (phases 00–13).
