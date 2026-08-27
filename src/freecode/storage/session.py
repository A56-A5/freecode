"""
storage.session - persist and restore AgentState + session metadata.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from freecode.domain.actions import CommandAction, EditAction, parse_action
from freecode.domain.state import AgentPhase, AgentState, TurnRecord
from freecode.storage.db import connect


def _new_session_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass(slots=True)
class SessionMeta:
    id: str
    title: str
    created_at: float
    updated_at: float
    goal: str | None
    phase: str
    turn: int
    summary: str


class SessionStore:
    """SQLite-backed session persistence."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn = connect(self.db_path)

    def close(self) -> None:
        self._conn.close()

    def create(
        self,
        *,
        title: str = "",
        state: AgentState | None = None,
        session_id: str | None = None,
    ) -> str:
        sid = session_id or _new_session_id()
        now = time.time()
        st = state or AgentState()
        self._conn.execute(
            """
            INSERT INTO sessions (
                id, created_at, updated_at, title, goal, phase, turn,
                facts_json, pending_actions_json, history_json,
                last_message, last_status, last_fallback, error, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                now,
                now,
                title or (st.goal or "session")[:80],
                st.goal,
                st.phase.value if isinstance(st.phase, AgentPhase) else str(st.phase),
                st.turn,
                json.dumps(list(st.facts)),
                json.dumps([_action_to_dict(a) for a in st.pending_actions]),
                json.dumps([{"role": t.role, "content": t.content} for t in st.history]),
                st.last_message,
                st.last_status,
                1 if st.last_fallback else 0,
                st.error,
                "",
            ),
        )
        self._conn.commit()
        self.set_meta("active_session_id", sid)
        return sid

    def save_state(self, session_id: str, state: AgentState, *, summary: str | None = None) -> None:
        now = time.time()
        row = self._conn.execute(
            "SELECT summary FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            self.create(state=state, session_id=session_id)
            return
        summ = summary if summary is not None else row["summary"]
        self._conn.execute(
            """
            UPDATE sessions SET
                updated_at = ?, goal = ?, phase = ?, turn = ?,
                facts_json = ?, pending_actions_json = ?, history_json = ?,
                last_message = ?, last_status = ?, last_fallback = ?,
                error = ?, summary = ?,
                title = COALESCE(NULLIF(title, ''), ?)
            WHERE id = ?
            """,
            (
                now,
                state.goal,
                state.phase.value if isinstance(state.phase, AgentPhase) else str(state.phase),
                state.turn,
                json.dumps(list(state.facts)),
                json.dumps([_action_to_dict(a) for a in state.pending_actions]),
                json.dumps([{"role": t.role, "content": t.content} for t in state.history]),
                state.last_message,
                state.last_status,
                1 if state.last_fallback else 0,
                state.error,
                summ,
                (state.goal or "session")[:80],
                session_id,
            ),
        )
        self._conn.commit()

    def load_state(self, session_id: str) -> AgentState | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        facts = tuple(json.loads(row["facts_json"] or "[]"))
        history_raw = json.loads(row["history_json"] or "[]")
        history = [
            TurnRecord(role=h["role"], content=h["content"])
            for h in history_raw
            if isinstance(h, dict)
        ]
        pending_raw = json.loads(row["pending_actions_json"] or "[]")
        pending = []
        for item in pending_raw:
            try:
                pending.append(parse_action(item))
            except (ValueError, TypeError):
                continue
        phase_raw = row["phase"] or "idle"
        try:
            phase = AgentPhase(phase_raw)
        except ValueError:
            phase = AgentPhase.IDLE
        return AgentState(
            goal=row["goal"],
            phase=phase,
            turn=int(row["turn"] or 0),
            facts=facts,
            pending_actions=tuple(pending),
            last_message=row["last_message"] or "",
            last_status=row["last_status"] or "continue",
            last_fallback=bool(row["last_fallback"]),
            history=history,
            error=row["error"],
        )

    def get_summary(self, session_id: str) -> str:
        row = self._conn.execute(
            "SELECT summary FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row["summary"] if row else ""

    def set_summary(self, session_id: str, summary: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET summary = ?, updated_at = ? WHERE id = ?",
            (summary, time.time(), session_id),
        )
        self._conn.commit()

    def list_sessions(self, *, limit: int = 50) -> list[SessionMeta]:
        rows = self._conn.execute(
            """
            SELECT id, title, created_at, updated_at, goal, phase, turn, summary
            FROM sessions ORDER BY updated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            SessionMeta(
                id=r["id"],
                title=r["title"] or "",
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                goal=r["goal"],
                phase=r["phase"],
                turn=r["turn"],
                summary=r["summary"] or "",
            )
            for r in rows
        ]

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM cooldown WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def active_session_id(self) -> str | None:
        return self.get_meta("active_session_id")


def _action_to_dict(action: Any) -> dict[str, Any]:
    if hasattr(action, "to_dict"):
        return action.to_dict()
    if isinstance(action, dict):
        return action
    return {"type": "unknown"}
