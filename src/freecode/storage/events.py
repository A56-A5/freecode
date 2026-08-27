"""
storage.events - persist domain events for a session.
"""
from __future__ import annotations

import json
from pathlib import Path

from freecode.domain.events import Event
from freecode.storage.db import connect


class EventStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn = connect(self.db_path)

    def close(self) -> None:
        self._conn.close()

    def append(self, session_id: str, event: Event) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO events (id, session_id, type, summary, payload_json, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                session_id,
                event.type,
                event.summary,
                json.dumps(event.payload),
                event.ts,
            ),
        )
        self._conn.commit()

    def append_many(self, session_id: str, events: list[Event]) -> None:
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO events (id, session_id, type, summary, payload_json, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (e.id, session_id, e.type, e.summary, json.dumps(e.payload), e.ts)
                for e in events
            ],
        )
        self._conn.commit()

    def list_for_session(
        self, session_id: str, *, limit: int = 200
    ) -> list[Event]:
        rows = self._conn.execute(
            """
            SELECT id, type, summary, payload_json, ts FROM events
            WHERE session_id = ? ORDER BY ts ASC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        out: list[Event] = []
        for r in rows:
            out.append(
                Event(
                    id=r["id"],
                    type=r["type"],  # type: ignore[arg-type]
                    summary=r["summary"],
                    payload=json.loads(r["payload_json"] or "{}"),
                    ts=r["ts"],
                )
            )
        return out
