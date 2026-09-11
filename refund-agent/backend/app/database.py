"""SQLite access layer.

A thin wrapper around the stdlib `sqlite3` module: connection factory with
`Row` access, schema initialization from `schema.sql`, and a FastAPI dependency.
SQLite is intentionally simple and file-based so the whole system boots with no
external database service.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .config import settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with row access and FK enforcement enabled."""
    settings.db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create tables from schema.sql if they do not already exist."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        # Migrate existing DBs: add media_ids column if it was created before
        # this column existed. sqlite3 raises OperationalError on duplicate columns.
        try:
            conn.execute(
                "ALTER TABLE reasoning_logs ADD COLUMN "
                "media_ids TEXT NOT NULL DEFAULT '[]'"
            )
            conn.commit()
        except Exception:
            pass  # column already present
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency yielding a connection that is always closed."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
