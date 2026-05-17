from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


_CONNECTION_LOCKS: dict[int, threading.RLock] = {}
_REGISTRY_LOCK = threading.Lock()


def lock_for(connection: sqlite3.Connection) -> threading.RLock:
    """Return the per-connection :class:`threading.RLock`, creating it on demand.

    Routes (Starlette threadpool), the lifespan poller (event loop), and the
    recording manager all share one connection with ``check_same_thread=False``;
    multi-statement repo methods need a single lock to keep their internals
    atomic. ``sqlite3.Connection`` is a C extension that doesn't permit
    attribute assignment, so we keep the registry in a module-level dict keyed
    by ``id(connection)``. The dict holds no strong reference to the connection
    itself, but for a single-user app the connection lives for the process
    lifetime; for tests the leak is bounded by the test count.

    One lock per connection — repos that share a connection share the lock.
    """
    with _REGISTRY_LOCK:
        key = id(connection)
        lock = _CONNECTION_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _CONNECTION_LOCKS[key] = lock
        return lock


def _release_lock_for(connection: sqlite3.Connection) -> None:
    """Drop the registry entry for ``connection``. Optional cleanup hook —
    callers that close a connection mid-process can use this to bound the leak.
    Tests that recycle connections call this in their teardown."""
    with _REGISTRY_LOCK:
        _CONNECTION_LOCKS.pop(id(connection), None)


SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rtsp_url TEXT NOT NULL,
    username TEXT,
    password TEXT,
    sub_stream_url TEXT,
    ptz_enabled INTEGER NOT NULL DEFAULT 0,
    record_mode TEXT NOT NULL DEFAULT 'off'
        CHECK (record_mode IN ('off', 'video_only', 'video_audio')),
    retention_days INTEGER NOT NULL DEFAULT 7,
    display_rotation INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recording_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    path TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    duration_seconds INTEGER,
    has_audio INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    lock_for(connection)  # attach the per-connection RLock eagerly
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    # Lightweight migration: add columns that were introduced after the
    # initial schema. SQLite's CREATE TABLE IF NOT EXISTS won't add new
    # columns to a pre-existing table.
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(cameras)").fetchall()
    }
    if "display_rotation" not in existing_columns:
        connection.execute(
            "ALTER TABLE cameras ADD COLUMN display_rotation INTEGER NOT NULL DEFAULT 0"
        )
    connection.commit()
