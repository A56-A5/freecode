"""Phase 12 (Full integration) — stack without TUI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from freecode.agent import AgentCore, AgentLoop
from freecode.config.settings import ApprovalSettings, ContextSettings
from freecode.context import ContextEngine
from freecode.domain.state import AgentPhase
from freecode.llm.response import ChatResponse, ResponseFeatures
from freecode.security import ApprovalGate
from freecode.tools import ToolExecutor


class ScriptedLLM:
    """Returns successive scripted ChatResponses."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0
        self.prompts: list[str] = []

    async def __call__(self, message: str) -> ChatResponse:
        self.prompts.append(message)
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return ChatResponse(
            text=text,
            features=ResponseFeatures(delay_seconds=0.0),
        )


@pytest.mark.asyncio
async def test_full_stack_plain_reply(tmp_path: Path):
    llm = ScriptedLLM(['{"message":"hello back","actions":[],"status":"done"}'])
    engine = ContextEngine(tmp_path, ContextSettings(token_budget=4000, context_window=8000))
    core = AgentCore(send=llm, build_prompt=engine.prompt_builder)
    tools = ToolExecutor(tmp_path, ApprovalSettings(default_policy="auto"))
    gate = ApprovalGate(ApprovalSettings(default_policy="auto"))

    async def authorize(action):
        return gate.authorize(action)

    loop = AgentLoop(core, tools, authorize=authorize, max_steps=2)
    outcome = await loop.run_user_message("hi")
    assert outcome.last is not None
    assert outcome.last.response.message == "hello back"
    assert outcome.last.phase is AgentPhase.DONE
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_full_stack_edit_action(tmp_path: Path):
    payload = {
        "message": "creating file",
        "actions": [{"type": "edit", "file": "hello.py", "old": "", "new": "print(1)\n"}],
        "status": "done",
    }
    llm = ScriptedLLM([json.dumps(payload)])
    engine = ContextEngine(tmp_path, ContextSettings(token_budget=4000, context_window=8000))
    core = AgentCore(send=llm, build_prompt=engine.prompt_builder)
    tools = ToolExecutor(tmp_path, ApprovalSettings(default_policy="auto"), coalescer=engine.coalescer)
    gate = ApprovalGate(ApprovalSettings(default_policy="auto"))

    async def authorize(action):
        return True

    loop = AgentLoop(core, tools, authorize=authorize, max_steps=1)
    outcome = await loop.run_user_message("write hello.py")
    assert (tmp_path / "hello.py").read_text() == "print(1)\n"
    assert outcome.steps[0].tool_results[0].ok


@pytest.mark.asyncio
async def test_denied_action_not_executed(tmp_path: Path):
    payload = {
        "message": "wipe",
        "actions": [{"type": "command", "command": "echo should-not-run"}],
        "status": "done",
    }
    llm = ScriptedLLM([json.dumps(payload)])
    core = AgentCore(send=llm)
    tools = ToolExecutor(tmp_path, ApprovalSettings(default_policy="ask"))

    async def deny(action):
        return False

    loop = AgentLoop(core, tools, authorize=deny, max_steps=1)
    outcome = await loop.run_user_message("run it")
    assert outcome.steps[0].tool_results[0].status == "denied"


@pytest.mark.asyncio
async def test_context_engine_in_prompt(tmp_path: Path):
    (tmp_path / "auth.py").write_text("def login():\n    pass\n", encoding="utf-8")
    llm = ScriptedLLM(['{"message":"ok","actions":[],"status":"done"}'])
    engine = ContextEngine(tmp_path, ContextSettings(token_budget=8000, context_window=16000))
    engine.refresh_index()
    core = AgentCore(send=llm, build_prompt=engine.prompt_builder)
    await core.handle_user_message("fix auth login")
    assert llm.prompts
    assert "FreeCode" in llm.prompts[0] or "auth" in llm.prompts[0].lower()
