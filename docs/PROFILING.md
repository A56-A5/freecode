# Performance profiling notes (ph-13)

Primary latency is **external**: ApiFreeLLM free tier enforces ~20–25s between
successful requests (`delaySeconds`). Local work (repair, context assembly,
SQLite) is negligible next to that floor.

| Segment | Typical cost | Notes |
|---------|--------------|--------|
| ContextEngine.assemble | < 50ms on medium repos | Index walk is the heavier local piece |
| repair_response | < 5ms | Pure string/JSON |
| SQLite session save | < 10ms | Sync `sqlite3`; fine at 1 turn / 20s |
| Tool shell | command-dependent | User-approved only |

## When to revisit

- If turn rate rises (paid tier / no cooldown), profile `ContextEngine` indexing
  and consider `aiosqlite` for non-blocking session writes.
- Command palette and markdown typing reveal are UI-thread work; keep lists short.

No continuous benchmark harness is shipped: the external API dominates CI timing.
