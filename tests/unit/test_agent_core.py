"""Phase 6 (Agent Core) unit tests."""
from __future__ import annotations

import json

import pytest

from freecode.agent import (
    AgentCore,
    AgentPhase,
    AgentState,
    apply_response,
    default_prompt,
    transition,
)
from freecode.agent.lifecycle import LifecycleError
from freecode.domain.actions import EditAction
from freecode.llm.protocol import AgentResponse, ContextUpdate
from freecode.llm.response import ChatResponse, ResponseFeatures


class FakeChat:
    def __init__(self, text: str, delay: float | None = 20.0) -> None:
        self._text = text
        self._delay = delay

    async def __call__(self, message: str) -> ChatResponse:
        return ChatResponse(
            text=self._text,
            features=ResponseFeatures(delay_seconds=self._delay),
        )


@pytest.mark.asyncio
async def test_handle_user_message_structured():
    payload = {
        "message": "I'll fix auth",
        "actions": [
            {"type": "edit", "file": "a.py", "old": "x", "new": "y"},
        ],
        "status": "continue",
        "context_update": {"facts": ["auth broken"]},
    }
    core = AgentCore(send=FakeChat(json.dumps(payload)))
    result = await core.handle_user_message("fix auth")
    assert result.response.message == "I'll fix auth"
    assert result.phase is AgentPhase.WAITING_APPROVAL
    assert len(result.response.actions) == 1
    assert isinstance(result.response.actions[0], EditAction)
    assert "auth broken" in core.state.facts
    assert core.state.goal == "fix auth"
    assert core.state.turn == 1


@pytest.mark.asyncio
async def test_handle_plain_text_fallback():
    core = AgentCore(send=FakeChat("just a plain answer"))
    result = await core.handle_user_message("hi")
    assert result.response.fallback is True
    assert result.phase is AgentPhase.RUNNING
    assert "plain answer" in result.message


@pytest.mark.asyncio
async def test_done_status():
    payload = {"message": "All good", "actions": [], "status": "done"}
    core = AgentCore(send=FakeChat(json.dumps(payload)))
    result = await core.handle_user_message("ship it")
    assert result.phase is AgentPhase.DONE


@pytest.mark.asyncio
async def test_needs_input():
    payload = {"message": "Which file?", "actions": [], "status": "needs_input"}
    core = AgentCore(send=FakeChat(json.dumps(payload)))
    result = await core.handle_user_message("edit something")
    assert result.phase is AgentPhase.NEEDS_INPUT


@pytest.mark.asyncio
async def test_interrupt_during_send():
    core_holder: dict = {}

    async def send_then_self_interrupt(message: str) -> ChatResponse:
        core_holder["core"].interrupt()
        return ChatResponse(text='{"message":"late","status":"done","actions":[]}')

    core = AgentCore(send=send_then_self_interrupt)
    core_holder["core"] = core
    result = await core.handle_user_message("go")
    assert result.phase is AgentPhase.INTERRUPTED
    assert result.error == "interrupted"


def test_lifecycle_transition_guard():
    state = AgentState(phase=AgentPhase.DONE)
    with pytest.raises(LifecycleError):
        transition(state, AgentPhase.WAITING_APPROVAL)


def test_apply_response_merges_facts():
    state = AgentState(facts=("a",))
    resp = AgentResponse(
        message="m",
        actions=(),
        context_update=ContextUpdate(facts=("a", "b")),
        status="continue",
    )
    transition(state, AgentPhase.RUNNING)
    apply_response(state, resp)
    assert state.facts == ("a", "b")


def test_default_prompt_includes_goal_and_facts():
    state = AgentState(goal="ship", facts=("use pytest",))
    state.append_user("hi")
    prompt = default_prompt(state, "next step")
    assert "ship" in prompt
    assert "use pytest" in prompt
    assert "next step" in prompt


@pytest.mark.asyncio
async def test_history_grows():
    core = AgentCore(send=FakeChat('{"message":"ok","status":"continue","actions":[]}'))
    await core.handle_user_message("one")
    await core.handle_user_message("two")
    roles = [t.role for t in core.state.history]
    assert roles == ["user", "assistant", "user", "assistant"]
