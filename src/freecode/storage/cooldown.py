"""
storage.cooldown - persist scheduler cooldown snapshot per session.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from freecode.storage.db import connect


@dataclass(frozen=True, slots=True)
class CooldownSnapshot:
    mode: str
    remaining_seconds: float
    total_seconds: float
    updated_at: float


class CooldownStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn = connect(self.db_path)

    def close(self) -> None:
        self._conn.close()

    def save(
        self,
        session_id: str,
        *,
        mode: str,
        remaining_seconds: float,
        total_seconds: float,
    ) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO cooldown (session_id, mode, remaining_seconds, total_seconds, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                mode = excluded.mode,
                remaining_seconds = excluded.remaining_seconds,
                total_seconds = excluded.total_seconds,
                updated_at = excluded.updated_at
            """,
            (session_id, mode, remaining_seconds, total_seconds, now),
        )
        self._conn.commit()

    def load(self, session_id: str) -> CooldownSnapshot | None:
        row = self._conn.execute(
            "SELECT * FROM cooldown WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return CooldownSnapshot(
            mode=row["mode"],
            remaining_seconds=float(row["remaining_seconds"]),
            total_seconds=float(row["total_seconds"]),
            updated_at=float(row["updated_at"]),
        )
