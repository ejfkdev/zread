# -*- coding: utf-8 -*-
"""SQLite connection factory + schema init, with sqlite-vec vector storage.

Single-file DB; the vec0 virtual table holds embeddings keyed by chunk_id.
"""

import sqlite3
import threading
from typing import Any, Optional

import sqlite_vec

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
  repo_id      TEXT PRIMARY KEY,          -- "{owner}/{repo}@{ref}"
  owner        TEXT NOT NULL,
  repo         TEXT NOT NULL,
  ref          TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'indexing',  -- indexing | success | error
  file_count   INTEGER NOT NULL DEFAULT 0,
  chunk_count  INTEGER NOT NULL DEFAULT 0,
  indexed_at   REAL,
  error        TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id     TEXT NOT NULL,
  file_path   TEXT NOT NULL,
  heading     TEXT NOT NULL DEFAULT '',
  ordinal     INTEGER NOT NULL DEFAULT 0,
  content     TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_repo ON chunks(repo_id);

CREATE TABLE IF NOT EXISTS talks (
  talk_id           TEXT PRIMARY KEY,
  repo_id           TEXT NOT NULL,
  model             TEXT,
  created_at        REAL NOT NULL,
  parent_message_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_talks_repo ON talks(repo_id);

CREATE TABLE IF NOT EXISTS talk_messages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  talk_id    TEXT NOT NULL,
  role       TEXT NOT NULL,        -- 'user' | 'assistant' | 'system'
  content    TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_talk ON talk_messages(talk_id, id);
"""

_VEC_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS embeddings USING vec0(
  chunk_id  INTEGER PRIMARY KEY,
  embedding FLOAT[{dim}]
);
"""

_lock = threading.Lock()


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a connection, load sqlite-vec, enable WAL + FK."""
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.enable_load_extension(True)
    try:
        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
    return conn


_conn: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    """Return the process-wide connection (created + initialized lazily).

    FastAPI runs on a single event loop; SQLite connections are thread-safe
    here because we guard mutations with a lock and use check_same_thread=False.
    """
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                conn = _connect(str(settings.db_file()))
                conn.executescript(_SCHEMA)
                conn.execute(_VEC_SCHEMA.format(dim=settings.embed_dim))
                conn.commit()
                _conn = conn
    return _conn


def close_db() -> None:
    """Close the shared connection (mainly for tests)."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def reset_db() -> sqlite3.Connection:
    """Drop and recreate all tables — used by the test suite for isolation."""
    conn = get_db()
    with _lock:
        conn.executescript(
            "DELETE FROM embeddings;"
            "DELETE FROM chunks;"
            "DELETE FROM talk_messages;"
            "DELETE FROM talks;"
            "DELETE FROM repos;"
        )
        conn.commit()
    return conn
