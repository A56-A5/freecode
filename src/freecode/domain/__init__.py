"""
domain/ - shared data contracts (dataclasses, enums, exceptions) used across
the whole app. This package must never import Textual, httpx, aiosqlite,
MCP, or anything from tui/llm/agent/tools/context/storage - it's the stable
core everything else depends on, not the other way around.

Populated incrementally as each phase needs concrete contracts:
  models.py   - core domain types (project, file, etc.)   ph-01+
  actions.py  - the edit/command action schema             ph-05
  events.py   - local execution event types                ph-09
  state.py    - agent/session state shape                  ph-06
  errors.py   - shared exception types                     as needed
"""
