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

SCHEMA_VERSION = 7


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
    migrations = [_m1, _m2, _m3, _m4, _m5, _m6, _m7]
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


def _m5(c: sqlite3.Connection) -> None:
    """Create tool audit, egress audit, and file-read cache tables.

    Args:
        c: Open SQLite connection receiving the migration.

    Returns:
        None.
    """
    c.executescript("""
    CREATE TABLE tool_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        event_type TEXT NOT NULL,
        classification_json TEXT NOT NULL,
        args_hash TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        success INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE TABLE egress_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        target TEXT,
        reason_code TEXT,
        justification TEXT,
        decision TEXT NOT NULL,
        success INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE TABLE file_read_cache(
        task_id TEXT NOT NULL,
        path TEXT NOT NULL,
        range_key TEXT NOT NULL,
        mtime_ns INTEGER NOT NULL,
        size INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        summary TEXT NOT NULL,
        accessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(task_id, path, range_key),
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE INDEX IF NOT EXISTS idx_tool_events_task_id ON tool_events(task_id);
    CREATE INDEX IF NOT EXISTS idx_egress_events_task_id ON egress_events(task_id);
    CREATE INDEX IF NOT EXISTS idx_file_read_cache_task_id ON file_read_cache(task_id);
    """)


def _m6(c: sqlite3.Connection) -> None:
    """Create persistent workflow checklist state.

    Args:
        c: Open SQLite connection.

    Returns:
        None.
    """
    c.executescript("""
    CREATE TABLE workflow_steps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        workflow_name TEXT NOT NULL,
        step_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        skip_reason TEXT,
        note TEXT,
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        UNIQUE(task_id, workflow_name, step_name)
    );
    CREATE INDEX IF NOT EXISTS idx_workflow_steps_task_id ON workflow_steps(task_id);
    """)


def _m7(c: sqlite3.Connection) -> None:
    """Create governance baseline and change-log tables.

    Args:
        c: Open SQLite connection.

    Returns:
        None.
    """
    c.executescript("""
    CREATE TABLE governance_baseline(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        acknowledged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        acknowledged_by TEXT NOT NULL DEFAULT 'human',
        git_commit TEXT
    );
    CREATE TABLE governance_change_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        old_hash TEXT,
        new_hash TEXT NOT NULL,
        detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        detected_by TEXT NOT NULL,
        task_id TEXT,
        acknowledged INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE INDEX IF NOT EXISTS idx_governance_baseline_file ON governance_baseline(file_path);
    CREATE INDEX IF NOT EXISTS idx_governance_change_ack ON governance_change_log(acknowledged);
    """)
