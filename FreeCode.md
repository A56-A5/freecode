# FreeCode — Project Context & Specification

**A terminal-based, MCP-driven AI coding agent built entirely on ApiFreeLLM's free tier.**

This document is the single source of truth for the project going forward. It supersedes the earlier draft's assumptions about the LLM API (which assumed a generic \~30s-rate-limited, tool-calling-capable API) with verified facts, and folds in every architectural decision made since.

---

## 1. Project Description

FreeCode is a terminal UI (TUI) coding agent, in the spirit of OpenCode / Cline / Aider, whose entire design is organized around one hard constraint: the LLM backing it is **free, single-string, no-tool-calling, and rate-limited to roughly one request per 20-25 seconds**.

Where a normal agent bounces between LLM and tools constantly (LLM → tool → LLM → tool → LLM...), FreeCode inverts that: the LLM produces a *plan*, a local **MCP tool layer** executes as much of that plan as it can without asking permission again, and all resulting events are batched, compressed, and coalesced into the **next single LLM call**. The model is used exclusively for reasoning; everything else — reading files, running shell commands, git operations, searching code — happens locally and instantly.

The product is not "a chatbot with file access." It's an asynchronous, event-driven agent runtime that happens to be very good at making each expensive reasoning step count, wrapped in a terminal UI that never blocks while waiting on that step.

**Design philosophy in one line:** *the machine keeps working while the model cools down.*

---

## 2. Features

### Core (v1 / MVP-and-up)

- Interactive TUI: chat pane, diff pane, command output pane, agent/status pane
- Live rate-limit cooldown bar (see §4)
- Chat with the agent; natural-language coding requests
- Project-aware context (file tree, language/framework detection, relevant-file selection)
- File read/edit with **diff previews** before anything touches disk
- Shell command execution with visible stdout/stderr/exit code
- Git awareness (status, diff, log) surfaced to both the model and the user
- MCP tool layer (filesystem, shell, git, search) as the only way the model touches the system
- Multi-step agent chains that survive multiple cooldown cycles unattended
- Request queueing with priority (user interruption > tool result > continuation > background)
- Request **coalescing** — multiple events arriving during one cooldown become one LLM call
- Context compression (rolling conversation summary instead of full history resend)
- Local project indexing (ripgrep/tree-sitter-based, no LLM involved)
- Persistent agent state (SQLite) — survives app restart and crashes mid-chain
- Explicit approval gate for mutating actions (write/delete/execute/commit)
- Cancel/interrupt/override the running agent at any time

### Stretch (post-v1)

- Additional MCP servers: GitHub, Docker, Postgres, browser
- Multiple concurrent agent tasks (still serialized against the single LLM slot, but tracked independently)
- Local static-analysis pre-pass (lint/type-check results fed in as free context, no LLM cost)
- Token-budget visualizer in the TUI (show how full the next request's context is)
- "Dry run" mode that plans without ever calling the mutating tools

---

## 3. Limits — Verified Ground Truth (ApiFreeLLM, free tier)

This is what we're actually building against, confirmed from apifreellm.com/en, /docs, and /api-access as of Aug 2026:

| Aspect Reality        |                                                                                                                                                                                                                                                 |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Endpoint              | `POST https://apifreellm.com/api/v1/chat`                                                                                                                                                                                                       |
| Request body          | `{"message": "<string>", "model": "apifreellm"}` — **no roles, no message array**                                                                                                                                                               |
| Response body         | `{"success", "response", "tier", "features": {"unlimited", "delaySeconds", "priorityProcessing"}}`                                                                                                                                              |
| Rate limit            | \~1 request per 20-25s. Site is inconsistent (pricing card & 429 text say 20s; observed response payload says `delaySeconds: 25`). **Treat** **`delaySeconds`** **from the live response as source of truth; 20s as hardcoded floor fallback.** |
| Tool/function calling | **Not available on free tier** (premium-only). Model must be prompted to emit structured JSON as plain text; we parse it ourselves.                                                                                                             |
| Streaming             | **Not available on free tier.** Full response arrives at once.                                                                                                                                                                                  |
| Context window        | 32k tokens. **Silently truncated if exceeded — no error.** Must budget locally.                                                                                                                                                                 |
| System/user roles     | None. One flat `message` string in, one flat `response` string out. Everything (system instructions, context, agent state, tool results, user turn) must be serialized into that single string.                                                 |
| Priority              | "Low priority (after premium users)" — the stated delay is a floor, not a guarantee.                                                                                                                                                            |
| Availability          | Best-effort / community sandbox. Docs explicitly say don't treat it as a production dependency; handle 429/5xx; capped backoff; no retry storms.                                                                                                |
| Cost/quota            | No request cap, free for personal and commercial use, no credit card. "Unlimited" = no billing/quota ceiling, **not** a latency or uptime guarantee.                                                                                            |
| Model identity        | Undisclosed on free tier (alias `apifreellm` only). Treat capability empirically — log real response quality/latency once live rather than assume.                                                                                              |

**Consequence this drives into the architecture:** the single flat string + no tool-calling + 32k truncating context is a bigger design constraint than the 20-25s delay itself. The delay is just a scheduling problem. The flat-string/truncation limit is a *context engineering* problem, and it's why the Context Engine is as important a component as the LLM client.

---

## 4. Project Flow (system-level)

```
 USER TYPES A GOAL
         │
         ▼
  AGENT CORE records goal, builds initial plan skeleton
         │
         ▼
  CONTEXT ENGINE assembles smallest useful context
         │
         ▼
  PROMPT COMPILER flattens everything into ONE string, token-budgeted
         │
         ▼
  SCHEDULER checks: are we in cooldown?
     │                     │
    yes                    no
     │                     │
  → QUEUE               → SEND to ApiFreeLLM
     │                     │
     │                     ▼
     │              RESPONSE REPAIR (strip fences, parse JSON, fallback heuristics)
     │                     │
     │                     ▼
     │              AGENT CORE applies: message → chat pane
     │                                  actions[] → MCP calls (with approval gate on mutating ones)
     │                                  context_update → context store
     │                                  status → continue / done / needs_input
     │                     │
     │                     ▼
     │              MCP TOOLS execute locally & instantly (read/write/shell/git/search)
     │                     │
     │                     ▼
     │              EVENTS generated (tool_result, file_changed, command_finished, ...)
     │                     │
     │                     ▼
     │              EVENT COALESCER buffers events until next allowed slot
     │                     │
     └─────────────────────┘
              (loop continues until status == done, or user interrupts)

```

Key property: only the "SEND to ApiFreeLLM → RESPONSE REPAIR" segment is rate-limited. Everything else — MCP execution, event coalescing, context assembly — happens as fast as the local machine allows, in parallel with the cooldown countdown.

---

## 5. User Flow (what it feels like to use)

1. **Launch** — `freecode` in a project directory. TUI opens; background indexing starts immediately (no LLM cost) — file tree, language detection, git state.
2. **Ask** — user types a goal in the chat pane ("fix the auth bug and make sure tests pass").
3. **First reasoning call** — cooldown bar appears (indeterminate until the first response calibrates it), request goes out.
4. **Plan comes back** — chat pane shows the model's message; diff pane shows proposed edits; command pane shows proposed commands. Mutating actions are queued as **pending approval**, not yet applied.
5. **User reviews** — accept / reject / edit each proposed change (`[a]/[r]/[e]/[d]`). Read-only actions (grep, read, git status/diff) may run automatically per policy; user can tighten this in config.
6. **Local execution** — approved actions run immediately (file writes, shell commands, git ops). Results stream into the command/status pane in real time — this part is NOT rate-limited.
7. **Waiting** — the cooldown bar fills toward the next allowed slot. User is free to: keep reading output, browse diffs, queue another instruction, cancel the in-flight chain, or just tab away — nothing blocks.
8. **Next reasoning call** — fires automatically at the next allowed slot, carrying the coalesced results of everything that happened locally since the last call (test failures, new diffs, additional user messages).
9. **Repeat** until the model reports `status: done`, or the user interrupts/redirects.
10. **Session persists** — closing FreeCode mid-chain is safe; state (goal, plan, pending actions, cooldown timer, conversation summary) is in SQLite and resumes on next launch.

---

## 6. Architecture

Same five-responsibility shape as before, refined for the real API's single-string/no-tool-calling constraint:

```
┌────────────────────────────────────────────────────────────────┐
│                          FREECODE TUI                          │
│   Chat │ Diff │ Commands │ Cooldown Bar │ Agent/Status          │
└──────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│                          AGENT CORE                             │
│  Goal & plan tracking · Agent state machine · Approval gating   │
│  Chain continuation · Interrupt handling                        │
└───────────┬───────────────────────────────────┬─────────────────┘
            │                                   │
            ▼                                   ▼
┌───────────────────────┐         ┌─────────────────────────────┐
│      MCP CLIENT        │         │        CONTEXT ENGINE        │
│  Tool discovery/exec    │         │  Project indexing (L0-L3)    │
│  filesystem/shell/git/  │         │  Relevance selection          │
│  search servers          │         │  Conversation summarization  │
└───────────┬─────────────┘         │  Token-budget accounting      │
            │                       └───────────────┬───────────────┘
            ▼                                       │
     local execution                                ▼
     (unlimited, instant)              ┌─────────────────────────────┐
            │                          │      PROMPT COMPILER         │
            ▼                          │  Flattens system+context+    │
      EVENT QUEUE ◄─────────────────── │  state+tool-results+user     │
      (coalescer)                      │  turn into ONE string,       │
            │                          │  budget-capped (~26k/32k)    │
            │                          └───────────────┬───────────────┘
            │                                          │
            ▼                                          ▼
┌────────────────────────────────────────────────────────────────┐
│                       REQUEST SCHEDULER                         │
│  Priority queue (user > tool-result > continuation > background)│
│  Cooldown timer driven by live `delaySeconds` from last response│
│  429/5xx capped backoff (separate state from normal cooldown)   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│                       APIFREELLM CLIENT                         │
│         POST /api/v1/chat  { message, model: "apifreellm" }     │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────┐
│                      RESPONSE REPAIR LAYER                      │
│  Strip markdown fences/prose · strict JSON parse ·               │
│  forgiving fallback parse · degrade-to-plain-text on failure     │
│  (no blind retry — a failed parse must not burn another slot)    │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                └────────► back to AGENT CORE

```

**New/changed vs. the original draft:**

- **Prompt Compiler** replaces "Request Builder" — its whole job is flattening structured context into one string under a hard token budget, since there's no message-array API to lean on.
- **Response Repair Layer** is new — required because there's no tool-calling grammar to guarantee valid JSON back. This sits between the HTTP client and the Agent Core and is responsible for never silently corrupting a 20-25s-expensive response.
- **Scheduler** now tracks two distinct timer states — normal cooldown (from `delaySeconds`) and 429 backoff (jittered, capped) — surfaced differently in the TUI so the user knows which is happening.

### Structured LLM response contract (unchanged in shape, still required since no tool-calling exists)

```json
{
  "message": "human-readable summary of reasoning/status",
  "actions": [
    { "type": "edit", "file": "src/auth.py", "old": "...", "new": "..." },
    { "type": "command", "command": "pytest tests/test_auth.py", "reason": "..." }
  ],
  "context_update": { "facts": ["..."] },
  "status": "continue | done | needs_input"
}

```

The Prompt Compiler's system block must instruct the model to emit **only** this JSON, nothing else — but the Response Repair layer exists precisely because that instruction won't be perfectly obeyed 100% of the time on a non-tool-calling free model.

---

## 7. Potential Tech Stack

| Layer Choice Why  |                                                                            |                                                                                                        |
| ----------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Language          | Python 3.11+                                                               | Fast to iterate, strong async support, good TUI and MCP ecosystem                                      |
| TUI               | [Textual](https://github.com/Textualize/textual)                           | Async-native, widget-rich, handles the "never block on cooldown" requirement well                      |
| HTTP client       | `httpx` (async)                                                            | Async requests to ApiFreeLLM without blocking the TUI event loop                                       |
| MCP               | Python MCP SDK                                                             | Standard tool/capability layer, keeps servers swappable                                                |
| Storage           | SQLite (`aiosqlite`)                                                       | Local, zero-setup, durable agent state / crash recovery                                                |
| Token counting    | `tiktoken` (approximate) or a simple heuristic counter                     | Model's real tokenizer is unknown (undisclosed model) — needs to be a conservative estimate, not exact |
| Code search       | `ripgrep` (shelled out)                                                    | Fast, no LLM cost, standard                                                                            |
| Code parsing      | `tree-sitter`                                                              | Symbol-level context selection without sending whole files                                             |
| Git               | `GitPython` or raw `git` CLI via `asyncio.subprocess`                      | Either works; CLI is simpler and matches "local tools = shell out" philosophy                          |
| Diffing           | `difflib` / unified diff format                                            | Standard, TUI-renderable                                                                               |
| Config            | TOML (`tomllib`)                                                           | Simple, human-editable `.freecode/config.toml`                                                         |
| Process execution | `asyncio.subprocess`                                                       | Non-blocking shell command execution                                                                   |
| JSON repair       | Custom small module (regex/heuristic fallback) + strict `json.loads` first | No off-the-shelf tool is a perfect fit for this API's failure modes                                    |

---

## 8. Implementation Architecture & Development Strategy

The architecture is intentionally modular. No single file should become the
"god module" for a subsystem. Components are split by responsibility so that
each part can be tested, replaced, and debugged independently.

### 8.1 Technology choice

**Language: Python 3.11+**

Python is the preferred v1 implementation language. FreeCode is primarily
I/O-bound and orchestration-heavy rather than CPU-bound: the dominant latency
comes from the remote LLM cooldown, while filesystem access, search, git,
SQLite, JSON parsing, and TUI operations are comparatively inexpensive.

Python also gives the project a strong ecosystem for the selected architecture:

- **Textual** — async-native terminal UI
- **httpx** — async HTTP client
- **asyncio** — non-blocking subprocess and concurrency primitives
- **aiosqlite** — persistent local state
- **Python MCP SDK** — MCP integration
- **tree-sitter / ripgrep** — local code indexing and search

Rust or C may be considered later for isolated performance-sensitive
components if profiling demonstrates a real need. They are not justified as
the initial implementation language.

### 8.2 Dependency philosophy

The project uses a dependency direction that keeps the core domain independent
from infrastructure.

```text
                    ┌──────────────┐
                    │    domain    │
                    │ data/contracts│
                    └──────▲───────┘
                           │
             ┌─────────────┼─────────────┐
             │             │             │
           agent          llm          tools
             │             │             │
             └─────────────┼─────────────┘
                           │
                          tui
```

`domain/` contains data structures and contracts only. It must not depend on
Textual, HTTP, SQLite, MCP, shell commands, or the filesystem.

This makes the domain layer the stable contract between the rest of the
application.

### 8.3 Proposed folder structure

```text
freecode/
│
├── pyproject.toml
├── README.md
├── .gitignore
│
├── src/
│   └── freecode/
│       │
│       ├── main.py
│       │
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── actions.py
│       │   ├── events.py
│       │   ├── state.py
│       │   └── errors.py
│       │
│       ├── tui/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── layout.py
│       │   ├── theme.py
│       │   │
│       │   ├── panes/
│       │   │   ├── chat.py
│       │   │   ├── diff.py
│       │   │   ├── commands.py
│       │   │   └── agent.py
│       │   │
│       │   └── widgets/
│       │       ├── cooldown.py
│       │       ├── input.py
│       │       └── status.py
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── request.py
│       │   ├── response.py
│       │   ├── protocol.py
│       │   ├── repair.py
│       │   ├── scheduler.py
│       │   └── queue.py
│       │
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── core.py
│       │   ├── lifecycle.py
│       │   ├── planner.py
│       │   ├── approvals.py
│       │   └── coordinator.py
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── filesystem.py
│       │   ├── shell.py
│       │   ├── git.py
│       │   └── search.py
│       │
│       ├── mcp/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── manager.py
│       │   └── permissions.py
│       │
│       ├── context/
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   ├── indexer.py
│       │   ├── selector.py
│       │   ├── compressor.py
│       │   ├── budget.py
│       │   └── store.py
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── database.py
│       │   ├── migrations.py
│       │   └── repositories.py
│       │
│       ├── security/
│       │   ├── __init__.py
│       │   ├── command_policy.py
│       │   └── sandbox.py
│       │
│       └── config/
│           ├── __init__.py
│           ├── loader.py
│           └── defaults.toml
│
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

The important design rule is that files such as `agent/core.py`,
`llm/client.py`, and `tui/app.py` remain focused. They should orchestrate
their subsystem rather than absorb every related responsibility.

### 8.4 Build philosophy

FreeCode will be developed in independently runnable stages rather than as a
single large implementation.

Each stage must produce a working artifact that can be tested before the next
stage is integrated.

```text
Phase 0   Foundation
   ↓
Phase 1   TUI shell
   ↓
Phase 2   Configuration + logging
   ↓
Phase 3   ApiFreeLLM client
   ↓
Phase 4   Scheduler + cooldown
   ↓
Phase 5   Response protocol + repair
   ↓
Phase 6   Agent Core
   ↓
Phase 7   Tool system / MCP
   ↓
Phase 8   Context Engine
   ↓
Phase 9   Event system + coalescing
   ↓
Phase 10  Persistence
   ↓
Phase 11  Approval + security
   ↓
Phase 12  Full integration
   ↓
Phase 13  Hardening + packaging
```

The stages are intentionally ordered so that expensive integration is delayed
until the underlying components are independently testable.

### 8.5 Phase 0 — Foundation

Create the Python package, test structure, project metadata, configuration
conventions, and basic entry point.

The phase is complete when the project can be installed and launched through
the package entry point.

### 8.6 Phase 1 — TUI shell

Build a realistic but initially mocked TUI.

The first TUI should already establish the permanent UI structure:

```text
┌─────────────────────────────────────────────────────────────┐
│ FREECODE                                      READY         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Chat                                                        │
│                                                             │
│ > hello                                                     │
│                                                             │
├──────────────────────────────┬──────────────────────────────┤
│ Diff                         │ Commands                     │
│                              │                              │
│ No changes                   │ No commands                  │
├──────────────────────────────┴──────────────────────────────┤
│ Agent: IDLE                  Cooldown: --                   │
└─────────────────────────────────────────────────────────────┘
```

The TUI must be split into independent panes and widgets rather than placing
all UI behavior in `app.py`.

The TUI at this stage does not need a real LLM or agent.

### 8.7 Phase 2 — Configuration + logging

Introduce configuration loading and structured application logging.

Configuration should expose, at minimum:

- ApiFreeLLM endpoint/model settings
- cooldown floor
- token budget
- approval policy
- project/runtime paths

API credentials should prefer environment variables. Credentials should not
be casually stored in the normal project configuration file.

### 8.8 Phase 3 — ApiFreeLLM client

Implement and test the HTTP client independently from the TUI and Agent Core.

Target interface:

```python
response = await client.send(message)
```

The client owns HTTP transport and API-specific response metadata. It should
not own scheduling, agent state, prompt compilation, or UI behavior.

### 8.9 Phase 4 — Scheduler + cooldown

Implement the request scheduler independently.

It must model two separate timing states:

1. Normal cooldown based on the API's live `delaySeconds`.
2. Capped/jittered backoff for 429/5xx failures.

The scheduler should be testable with a fake clock so cooldown behavior does
not require waiting 20–25 seconds during unit tests.

### 8.10 Phase 5 — Response protocol + repair

Implement:

```text
LLM response
     ↓
JSON extraction
     ↓
strict parsing
     ↓
validation
     ↓
Action[] / status / context update
```

The repair layer must handle fenced JSON, surrounding prose, malformed output,
and a safe plain-text fallback.

A failed parse must not automatically burn another expensive LLM slot.

### 8.11 Phase 6 — Agent Core

Connect goals, state, planning, response interpretation, and continuation.

The Agent Core should not directly implement HTTP, shell execution, filesystem
operations, or TUI rendering.

Its responsibility is orchestration.

### 8.12 Phase 7 — Tools / MCP

Introduce the local execution layer:

- filesystem
- shell
- git
- search

Read-only actions can be automatically executable according to policy.
Mutating operations remain behind approval gates.

MCP should remain an abstraction boundary so tool providers can later be
replaced or extended.

### 8.13 Phase 8 — Context Engine

Implement project indexing, relevance selection, conversation compression,
and token budgeting.

This phase is critical because the API uses one flat string and silently
truncates context beyond its effective window.

The Context Engine must therefore assemble the smallest useful context rather
than blindly replaying conversation history.

### 8.14 Phase 9 — Events + coalescing

Formalize local execution events:

```text
tool_result
file_changed
command_started
command_finished
git_changed
user_message
approval_result
```

The Event Coalescer batches events occurring during the cooldown into the
next reasoning request.

This is one of the central performance mechanisms of FreeCode.

### 8.15 Phase 10 — Persistence

Add SQLite persistence for:

- goals
- agent state
- conversation summary
- pending actions
- events
- cooldown state
- session metadata

A session interrupted during a chain should be recoverable after restart.

### 8.16 Phase 11 — Approval + security

Implement explicit policies for:

- file writes
- deletes
- shell commands
- git mutations
- commits

The approval system should be independent from the TUI so that policy can be
tested without rendering the application.

### 8.17 Phase 12 — Full integration

Connect:

```text
TUI
 ↓
Agent Core
 ↓
Prompt Compiler / Context
 ↓
Scheduler
 ↓
ApiFreeLLM
 ↓
Response Repair
 ↓
Agent Core
 ↓
MCP / Tools
 ↓
Events
 ↓
Coalescer
 ↓
Scheduler
```

At this point the system becomes the full asynchronous coding agent described
in the earlier architecture.

### 8.18 Phase 13 — Hardening + packaging

Final work includes:

- crash recovery testing
- API failure handling
- malformed response testing
- context overflow testing
- approval/security testing
- cancellation/interrupt behavior
- packaging
- installation documentation
- performance profiling
- optional isolated optimization of components if profiling justifies it

### 8.19 Development rule

Do not integrate the entire stack at once.

Each boundary should be validated independently:

```text
TUI          → works
Config       → works
LLM client   → works
Scheduler    → works
Protocol     → works
Agent        → works
Tools        → works
Context      → works
Persistence  → works
Integration  → works
```

This makes failures local and keeps the project debuggable.

### 8.20 Git workflow

Each phase should be completed as a small, reviewable unit, on its own branch.

Branch pattern (branch number = phase number, always two digits):

```text
main
 ├── ph-00   Foundation
 ├── ph-01   TUI shell
 ├── ph-02   Configuration + logging
 ├── ph-03   ApiFreeLLM client
 ├── ph-04   Scheduler + cooldown
 ├── ph-05   Response protocol + repair
 ├── ph-06   Agent Core
 ├── ph-07   Tool system / MCP
 ├── ph-08   Context Engine
 ├── ph-09   Event system + coalescing
 ├── ph-10   Persistence
 ├── ph-11   Approval + security
 ├── ph-12   Full integration
 └── ph-13   Hardening + packaging
```

Every completed phase should include:

- implementation
- unit tests
- manual verification
- README/documentation updates
- a Git commit

The project should be recoverable to the last known-good phase if a later
integration introduces a regression.

### 8.21 Phase status

Kept current so anyone re-entering the project — human or LLM — can tell
what's actually done vs. merely started, without re-reading every branch.

| Branch | Phase | Status |
|---|---|---|
| ph-00 | Foundation | done, verified |
| ph-01 | TUI shell | in progress |
| ph-02 | Configuration + logging | done, verified |
| ph-03 | ApiFreeLLM client | not started |
| ph-04 | Scheduler + cooldown | not started |
| ph-05 | Response protocol + repair | not started |
| ph-06 | Agent Core | not started |
| ph-07 | Tool system / MCP | not started |
| ph-08 | Context Engine | not started |
| ph-09 | Event system + coalescing | not started |
| ph-10 | Persistence | not started |
| ph-11 | Approval + security | not started |
| ph-12 | Full integration | not started |
| ph-13 | Hardening + packaging | not started |

Status values: `not started` / `in progress` / `done, unverified` / `done, verified`.
Use `done, verified` only after tests pass AND manual verification happened
(automated where possible, on-device for anything touching the real API).

---

## 9. Open Questions Before Build

Worth deciding before writing code, since they shape early modules:

1. **Approval default policy** — should shell commands default to "always ask," or auto-run a small allowlist (e.g. `pytest`, `git status`) given how expensive a wasted cooldown cycle is if the agent has to ask again?
2. **Token counting accuracy** — since the real model/tokenizer is undisclosed, do we want a conservative fixed ratio (e.g. \~4 chars/token) or pull in `tiktoken` as a best-effort approximation, accepting it won't be exact?
3. **Multiple concurrent goals** — v1 single active agent chain, or build the queue/priority system to support several from day one?
4. **API key handling** — where does the user's ApiFreeLLM key live (`.freecode/config.toml`, env var, OS keychain)?

None of these block starting the scheduler/client/TUI skeleton — happy to proceed with sensible defaults and flag them as we hit each one.