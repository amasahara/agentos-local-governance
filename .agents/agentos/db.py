"""
File: .agents/agentos/db.py

Purpose:
    Provide the SQLite persistence layer for AgentOS governance state.

Responsibilities:
    - Open project-local database connections.
    - Apply ordered schema migrations.
    - Preserve relational integrity for tasks, tool calls, claims, and evidence.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 4


def _db_path(root: Path) -> Path:
    """Return the project-local SQLite database path.

    Args:
        root: Absolute or relative project root.

    Returns:
        Path to the AgentOS state database.
    """
    path = root.resolve() / ".agents" / "state" / "agentos.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect(root: Path) -> Iterator[sqlite3.Connection]:
    """Open a migrated SQLite connection with foreign keys enabled.

    Args:
        root: Project root.

    Yields:
        Configured SQLite connection.
    """
    connection = sqlite3.connect(_db_path(root))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrate(connection)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate(connection: sqlite3.Connection) -> None:
    """Apply all required schema migrations.

    Args:
        connection: Open SQLite connection.

    Returns:
        None.
    """
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)")
    current = connection.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()["v"]
    migrations = [_m1, _m2, _m3, _m4]
    for version, fn in enumerate(migrations, start=1):
        if version > current:
            fn(connection)
            connection.execute("INSERT INTO schema_migrations(version) VALUES(?)", (version,))


def _m1(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE tasks(
        id TEXT PRIMARY KEY,
        request TEXT NOT NULL,
        approved INTEGER NOT NULL DEFAULT 0,
        approved_scope TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE write_audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        target TEXT NOT NULL,
        allowed INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    """)


def _m2(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE tool_calls(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        classification TEXT NOT NULL,
        input_json TEXT NOT NULL,
        success INTEGER NOT NULL,
        output_summary TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE TABLE symbol_index(
        path TEXT NOT NULL,
        qualname TEXT NOT NULL,
        kind TEXT NOT NULL,
        line_start INTEGER NOT NULL,
        line_end INTEGER NOT NULL,
        signature TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        PRIMARY KEY(path, qualname)
    );
    """)


def _m3(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE claims(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        claim_text TEXT NOT NULL,
        claim_type TEXT NOT NULL,
        risk TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE TABLE claim_evidence(
        claim_id INTEGER NOT NULL,
        tool_call_id INTEGER NOT NULL,
        evidence_role TEXT NOT NULL DEFAULT 'supports',
        FOREIGN KEY(claim_id) REFERENCES claims(id) ON DELETE CASCADE,
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(id),
        PRIMARY KEY(claim_id, tool_call_id, evidence_role)
    );
    """)


def _m4(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE INDEX IF NOT EXISTS idx_tool_calls_task_id ON tool_calls(task_id);
    CREATE INDEX IF NOT EXISTS idx_claims_task_id ON claims(task_id);
    CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim_id ON claim_evidence(claim_id);
    """)
