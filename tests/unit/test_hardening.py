"""
Phase 13 — Hardening tests: malformed responses, context overflow,
interrupt, approval, crash-ish recovery of session state.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from freecode.agent import AgentCore, AgentLoop
from freecode.config.settings import ApprovalSettings, ContextSettings
from freecode.context import ContextEngine, estimate_tokens, trim_to_budget
from freecode.domain.actions import CommandAction, EditAction
from freecode.domain.state import AgentPhase, AgentState
from freecode.llm.repair import repair_response
from freecode.llm.response import ChatResponse, ResponseFeatures
from freecode.security import ApprovalGate, Decision
from freecode.storage import SessionStore
from freecode.tools import ToolExecutor


class ScriptedLLM:
    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0

    async def __call__(self, message: str) -> ChatResponse:
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return ChatResponse(text=text, features=ResponseFeatures(delay_seconds=0.0))


class BoomLLM:
    async def __call__(self, message: str) -> ChatResponse:
        from freecode.domain.errors import LLMTransportError

        raise LLMTransportError("Community request timed out.")


def test_malformed_json_recovers_message_not_blob():
    raw = 'Sure.\n{"message": "Hello world", "status": "done", "actions": []\n'
    resp = repair_response(raw)
    assert "Hello world" in resp.message
    assert not resp.message.strip().startswith("{")


def test_truncated_json_with_code_fence_noise():
    raw = '```json\n{"message": "partial answer about auth", "actions": [\n```'
    resp = repair_response(raw)
    assert "partial answer" in resp.message or resp.fallback


def test_context_overflow_trim():
    huge = "x" * 50_000
    out = trim_to_budget(huge, budget=100, chars_per_token=4.0)
    assert estimate_tokens(out, 4.0) <= 120
    assert len(out) < len(huge)


def test_context_engine_stays_under_budget(tmp_path: Path):
    for i in range(30):
        (tmp_path / f"mod_{i}.py").write_text("def f():\n    return %d\n" % i * 50)
    engine = ContextEngine(
        tmp_path,
        ContextSettings(token_budget=800, context_window=2000, chars_per_token=4.0),
    )
    state = AgentState(goal="touch every module")
    for i in range(20):
        state.append_user("msg %d" % i)
        state.append_assistant("reply %d " % i + ("y" * 200))
    prompt = engine.assemble(state, "final question")
    assert estimate_tokens(prompt, 4.0) <= 900


@pytest.mark.asyncio
async def test_interrupt_cooperative():
    core_holder: dict = {}

    async def send(message: str) -> ChatResponse:
        core_holder["core"].interrupt()
        return ChatResponse(
            text='{"message":"late","status":"done","actions":[]}',
            features=ResponseFeatures(),
        )

    core = AgentCore(send=send)
    core_holder["core"] = core
    result = await core.handle_user_message("go")
    assert result.phase is AgentPhase.INTERRUPTED or result.error == "interrupted"


@pytest.mark.asyncio
async def test_llm_transport_error_surfaces():
    core = AgentCore(send=BoomLLM())
    result = await core.handle_user_message("x")
    assert result.error
    assert "timed out" in result.error.lower() or "timed out" in result.message.lower()


@pytest.mark.asyncio
async def test_approval_blocks_then_allows(tmp_path: Path):
    payload = {
        "message": "writing",
        "actions": [{"type": "edit", "file": "a.py", "old": "", "new": "ok\n"}],
        "status": "done",
    }
    core = AgentCore(send=ScriptedLLM([json.dumps(payload)]))
    tools = ToolExecutor(tmp_path, ApprovalSettings(default_policy="ask"))

    async def deny(_):
        return False

    loop = AgentLoop(core, tools, authorize=deny, max_steps=1)
    out = await loop.run_user_message("write a.py")
    assert out.steps[0].tool_results[0].status == "denied"
    assert not (tmp_path / "a.py").exists()

    core2 = AgentCore(send=ScriptedLLM([json.dumps(payload)]))
    tools2 = ToolExecutor(tmp_path, ApprovalSettings(default_policy="auto"))

    async def allow(_):
        return True

    loop2 = AgentLoop(core2, tools2, authorize=allow, max_steps=1)
    out2 = await loop2.run_user_message("write a.py")
    assert (tmp_path / "a.py").read_text() == "ok\n"


def test_session_recovery_after_save(tmp_path: Path):
    db = tmp_path / "state.db"
    store = SessionStore(db)
    state = AgentState(goal="recover me", phase=AgentPhase.RUNNING, turn=3)
    state.append_user("hello")
    state.append_assistant("hi")
    sid = store.create(title="crash-test", state=state)
    store.close()

    store2 = SessionStore(db)
    loaded = store2.load_state(sid)
    assert loaded is not None
    assert loaded.goal == "recover me"
    assert loaded.turn == 3
    assert len(loaded.history) == 2
    store2.close()


def test_gate_destructive_prompts():
    gate = ApprovalGate(ApprovalSettings(default_policy="auto_readonly"))
    req = gate.decide(CommandAction(command="rm -rf /tmp/x"))
    assert req.decision is Decision.PROMPT
