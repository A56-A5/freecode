"""Phase 10 (Persistence) unit tests."""
from __future__ import annotations

from pathlib import Path

from freecode.domain.actions import EditAction
from freecode.domain.events import tool_result_event
from freecode.domain.state import AgentPhase, AgentState
from freecode.storage import CooldownStore, EventStore, SessionStore


def test_session_create_and_load(tmp_path: Path):
    db = tmp_path / "state.db"
    store = SessionStore(db)
    state = AgentState(goal="fix auth", phase=AgentPhase.RUNNING, turn=2)
    state.facts = ("uses jwt",)
    state.append_user("hi")
    state.append_assistant("hello")
    state.pending_actions = (EditAction(file="a.py", old="x", new="y"),)
    sid = store.create(title="auth", state=state)
    loaded = store.load_state(sid)
    assert loaded is not None
    assert loaded.goal == "fix auth"
    assert loaded.turn == 2
    assert loaded.facts == ("uses jwt",)
    assert len(loaded.history) == 2
    assert len(loaded.pending_actions) == 1
    assert store.active_session_id() == sid
    store.close()


def test_session_save_roundtrip(tmp_path: Path):
    db = tmp_path / "state.db"
    store = SessionStore(db)
    sid = store.create(title="t")
    state = AgentState(goal="g", phase=AgentPhase.DONE, turn=5)
    state.last_message = "done"
    store.save_state(sid, state, summary="shipped")
    loaded = store.load_state(sid)
    assert loaded is not None
    assert loaded.phase is AgentPhase.DONE
    assert loaded.last_message == "done"
    assert store.get_summary(sid) == "shipped"
    sessions = store.list_sessions()
    assert any(s.id == sid for s in sessions)
    store.close()


def test_event_store(tmp_path: Path):
    db = tmp_path / "state.db"
    sessions = SessionStore(db)
    sid = sessions.create()
    events = EventStore(db)
    e1 = tool_result_event("shell", "ok", "hi")
    e2 = tool_result_event("read_file", "ok", "data")
    events.append(sid, e1)
    events.append_many(sid, [e2])
    listed = events.list_for_session(sid)
    assert len(listed) == 2
    assert listed[0].type == "tool_result"
    events.close()
    sessions.close()


def test_cooldown_store(tmp_path: Path):
    db = tmp_path / "state.db"
    sessions = SessionStore(db)
    sid = sessions.create()
    cd = CooldownStore(db)
    cd.save(sid, mode="cooldown", remaining_seconds=12.5, total_seconds=20.0)
    snap = cd.load(sid)
    assert snap is not None
    assert snap.mode == "cooldown"
    assert snap.remaining_seconds == 12.5
    cd.close()
    sessions.close()


def test_delete_session(tmp_path: Path):
    db = tmp_path / "state.db"
    store = SessionStore(db)
    sid = store.create()
    EventStore(db).append(sid, tool_result_event("t", "ok"))
    store.delete_session(sid)
    assert store.load_state(sid) is None
    store.close()
