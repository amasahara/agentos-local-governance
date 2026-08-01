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

SCHEMA_VERSION = 11


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
def connect(root: Path, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a migrated SQLite connection with foreign keys enabled.

    Args:
        root: Project root.
        immediate: Whether to begin an immediate write transaction after migration.

    Yields:
        Configured SQLite connection.
    """
    connection = sqlite3.connect(_db_path(root), timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute("PRAGMA busy_timeout = 5000")
    migrate(connection)
    if immediate:
        connection.execute("BEGIN IMMEDIATE")
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
    migrations = [_m1, _m2, _m3, _m4, _m5, _m6, _m7, _m8, _m9, _m10, _m11]
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


def _m8(c: sqlite3.Connection) -> None:
    """Add trust-boundary hardening state and provenance.

    Args:
        c: Open SQLite connection.

    Returns:
        None.
    """
    c.executescript("""
    ALTER TABLE workflow_steps ADD COLUMN completion_source TEXT NOT NULL DEFAULT 'none';
    ALTER TABLE workflow_steps ADD COLUMN evidence_type TEXT;
    ALTER TABLE workflow_steps ADD COLUMN evidence_id TEXT;
    ALTER TABLE workflow_steps ADD COLUMN result_hash TEXT;
    ALTER TABLE workflow_steps ADD COLUMN command_name TEXT;
    ALTER TABLE workflow_steps ADD COLUMN exit_code INTEGER;

    ALTER TABLE governance_baseline ADD COLUMN acknowledgement_method TEXT NOT NULL DEFAULT 'legacy';
    ALTER TABLE governance_baseline ADD COLUMN session_id TEXT;

    CREATE TABLE guarded_executions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        execution_token TEXT NOT NULL UNIQUE,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        classification TEXT NOT NULL,
        args_hash TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        target TEXT,
        reason_code TEXT,
        justification TEXT,
        issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        completed_at TEXT,
        success INTEGER,
        tool_call_id INTEGER,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(id)
    );
    CREATE INDEX idx_guarded_executions_task_id ON guarded_executions(task_id);

    CREATE TABLE policy_override_approvals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        reviewed_by TEXT,
        review_method TEXT,
        reviewed_at TEXT,
        note TEXT,
        UNIQUE(content_hash)
    );

    CREATE TABLE audit_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        task_id TEXT,
        session_id TEXT,
        payload_json TEXT NOT NULL,
        previous_hash TEXT,
        event_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)


def _m9(c: sqlite3.Connection) -> None:
    """Add MCP proxy and external audit checkpoint state.

    Args:
        c: Open SQLite connection.

    Returns:
        None.
    """
    c.executescript("""
    CREATE TABLE proxy_executions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        capability TEXT NOT NULL,
        decision TEXT NOT NULL,
        success INTEGER,
        tool_call_id INTEGER,
        external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(id)
    );
    CREATE INDEX idx_proxy_executions_task ON proxy_executions(task_id);
    CREATE TABLE external_audit_checkpoints(
        project_id TEXT PRIMARY KEY,
        last_sequence INTEGER NOT NULL,
        last_event_hash TEXT NOT NULL,
        key_id TEXT NOT NULL,
        verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)


def _m10(c: sqlite3.Connection) -> None:
    """Add process execution audit and signing-key rotation state.

    Args:
        c: Open SQLite connection.

    Returns:
        None.
    """
    c.executescript("""
    CREATE TABLE process_exec_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        command_json TEXT NOT NULL,
        cwd TEXT NOT NULL,
        command_profile TEXT NOT NULL,
        decision TEXT NOT NULL,
        success INTEGER,
        exit_code INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE INDEX idx_process_exec_events_task ON process_exec_events(task_id);
    CREATE TABLE audit_key_rotations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        old_key_id TEXT NOT NULL,
        new_key_id TEXT NOT NULL,
        identity TEXT NOT NULL,
        reason TEXT NOT NULL,
        event_hash TEXT NOT NULL,
        rotated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)


def _m11(c: sqlite3.Connection) -> None:
    """Add multi-process coordination, task ownership, and file version state."""
    c.executescript("""
    ALTER TABLE tasks ADD COLUMN owner_session_id TEXT;
    ALTER TABLE tasks ADD COLUMN task_state TEXT NOT NULL DEFAULT 'ready';
    ALTER TABLE tasks ADD COLUMN last_heartbeat TEXT;
    CREATE TABLE resource_leases(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_type TEXT NOT NULL,
        resource_key TEXT NOT NULL,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        lease_mode TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        acquired_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        heartbeat_at TEXT NOT NULL,
        released_at TEXT,
        base_hash TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE INDEX idx_resource_leases_resource ON resource_leases(resource_type,resource_key,status);
    CREATE INDEX idx_resource_leases_task ON resource_leases(task_id,status);
    CREATE TABLE file_versions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL,
        version INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        previous_hash TEXT,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        lease_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(lease_id) REFERENCES resource_leases(id),
        UNIQUE(path,version)
    );
    CREATE INDEX idx_file_versions_path ON file_versions(path,version);
    CREATE TABLE task_handoffs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        from_session_id TEXT NOT NULL,
        to_session_id TEXT NOT NULL,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    """)
