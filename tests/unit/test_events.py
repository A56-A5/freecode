"""Phase 9 (Events + coalescing) unit tests."""
from __future__ import annotations

from freecode.context import ContextEngine, EventCoalescer
from freecode.domain.events import (
    Event,
    approval_result_event,
    command_finished_event,
    file_changed_event,
    tool_result_event,
    user_message_event,
)
from freecode.domain.state import AgentState
from freecode.config.settings import ContextSettings
from pathlib import Path


def test_event_factories():
    e = tool_result_event("shell", "ok", "hi")
    assert e.type == "tool_result"
    assert e.payload["tool"] == "shell"
    d = e.to_dict()
    assert d["type"] == "tool_result"


def test_coalescer_emit_and_drain():
    c = EventCoalescer()
    c.emit(user_message_event("hello"))
    c.emit(file_changed_event("a.py"))
    assert len(c) == 2
    drained = c.clear()
    assert len(drained) == 2
    assert len(c) == 0


def test_coalescer_caps():
    c = EventCoalescer(caps={"file_changed": 3})  # type: ignore[arg-type]
    for i in range(10):
        c.emit(file_changed_event(f"f{i}.py"))
    assert len(c) == 3
    paths = [e.payload["path"] for e in c.events]
    assert paths == ["f7.py", "f8.py", "f9.py"]


def test_coalesce_for_prompt_budget():
    c = EventCoalescer()
    for i in range(20):
        c.emit(tool_result_event("t", "ok", "x" * 500))
    text = c.coalesce_for_prompt(token_budget=100, chars_per_token=4.0, drain=False)
    assert "Events since last" in text
    assert len(text) < 2000


def test_engine_includes_drained_events(tmp_path: Path):
    engine = ContextEngine(tmp_path, ContextSettings(token_budget=4000, context_window=8000))
    engine.coalescer.emit(tool_result_event("pytest", "ok", "1 passed"))
    engine.coalescer.emit(file_changed_event("src/a.py"))
    state = AgentState(goal="test")
    prompt = engine.assemble(state, "run tests")
    assert "Events since last" in prompt or "pytest" in prompt
    assert "run tests" in prompt
    # drained
    assert len(engine.coalescer) == 0


def test_approval_and_command_events():
    a = approval_result_event(True, "edit a.py")
    assert a.payload["approved"] is True
    c = command_finished_event("pytest", 0, "ok")
    assert c.payload["exit_code"] == 0
