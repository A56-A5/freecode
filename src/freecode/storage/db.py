"""
storage.db - SQLite connection helpers for FreeCode persistence.

Uses stdlib ``sqlite3`` (sync). Adequate for free-tier cadence; swap to ``aiosqlite`` if profiling shows event-loop stalls under load.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    goal TEXT,
    phase TEXT NOT NULL DEFAULT 'idle',
    turn INTEGER NOT NULL DEFAULT 0,
    facts_json TEXT NOT NULL DEFAULT '[]',
    pending_actions_json TEXT NOT NULL DEFAULT '[]',
    history_json TEXT NOT NULL DEFAULT '[]',
    last_message TEXT NOT NULL DEFAULT '',
    last_status TEXT NOT NULL DEFAULT 'continue',
    last_fallback INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    ts REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cooldown (
    session_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'idle',
    remaining_seconds REAL NOT NULL DEFAULT 0,
    total_seconds REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events(session_id, ts);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
