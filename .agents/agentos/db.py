"""
File: .agents/agentos/db.py

Purpose:
    Provide the SQLite persistence layer for AgentOS governance state.

Responsibilities:
    - Open project-local database connections.
    - Bootstrap fresh state at schema 46, then apply ordered post-baseline migrations.
    - Preserve relational integrity for tasks, tool calls, claims, and evidence.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


from .schema_version import CURRENT_SCHEMA_VERSION

SCHEMA_VERSION = CURRENT_SCHEMA_VERSION


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
    connection.execute("PRAGMA secure_delete = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute("PRAGMA busy_timeout = 5000")
    migrate(connection)
    # Schema migrations may open an implicit SQLite transaction on a fresh or
    # upgrading database. Commit the migration boundary before starting the
    # caller's explicit IMMEDIATE transaction so connect(immediate=True) works
    # consistently for clean installs and upgrades.
    connection.commit()
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



@contextmanager
def connect_read_only(root: Path) -> Iterator[sqlite3.Connection]:
    """Open current AgentOS state through a strict SQLite read-only connection.

    This path never creates the state directory/database, never changes journal
    mode, and never executes schema migrations. It fails closed if the database
    is absent or its migration level is not the current AgentOS schema.
    """
    db_path = root.resolve() / ".agents" / "state" / "agentos.db"
    if not db_path.is_file():
        raise RuntimeError("state_database_missing")
    connection = sqlite3.connect(
        db_path.resolve().as_uri() + "?mode=ro",
        timeout=5.0,
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations"
            ).fetchone()
        except sqlite3.Error as exc:
            raise RuntimeError("state_schema_upgrade_required") from exc
        current = int(row["v"]) if row is not None else 0
        if current != SCHEMA_VERSION:
            raise RuntimeError("state_schema_upgrade_required")
        yield connection
    finally:
        connection.close()


def _normalized_schema_sql(value: object) -> str:
    """Normalize SQLite schema SQL for exact legacy-contract comparison."""
    return " ".join(str(value or "").split())


def _schema_object_contract(connection: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Return named user schema objects with normalized SQL."""
    rows = connection.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
          AND name <> 'schema_migrations'
          AND type IN ('table','index','trigger','view')
        ORDER BY name
        """
    ).fetchall()
    return {
        str(row[1]): (str(row[0]), _normalized_schema_sql(row[2]))
        for row in rows
    }


def _legacy_unversioned_reference_contract() -> dict[str, tuple[str, str]]:
    """Build the only legacy direct-schema contract eligible for reconciliation."""
    from .project_identity import migration_32
    from .project_selection import migration_33
    from .project_consolidation import migration_34

    reference = sqlite3.connect(":memory:")
    reference.row_factory = sqlite3.Row
    try:
        migration_32(reference)
        migration_33(reference)
        migration_34(reference)
        return _schema_object_contract(reference)
    finally:
        reference.close()


def _detect_legacy_unversioned_state(
    connection: sqlite3.Connection,
) -> dict[str, object]:
    """Recognize only exact module-local schema 32/33/34 objects."""
    actual = _schema_object_contract(connection)
    if not actual:
        return {
            "recognized": False,
            "reason": "no_legacy_objects",
            "objects": [],
        }

    expected = _legacy_unversioned_reference_contract()
    strong_signatures = {
        "project_identity",
        "project_candidate_sets",
        "project_consolidations",
    }
    if not (set(actual) & strong_signatures):
        return {
            "recognized": False,
            "reason": "missing_legacy_signature",
            "objects": sorted(actual),
        }

    unknown = sorted(set(actual) - set(expected))
    mismatched = sorted(
        name
        for name in set(actual) & set(expected)
        if actual[name] != expected[name]
    )
    return {
        "recognized": not unknown and not mismatched,
        "reason": (
            "exact_legacy_module_local_contract"
            if not unknown and not mismatched
            else "legacy_contract_mismatch"
        ),
        "objects": sorted(actual),
        "unknown_objects": unknown,
        "mismatched_objects": mismatched,
    }


def migrate_with_report(connection: sqlite3.Connection) -> dict[str, object]:
    """Bring AgentOS state to the current schema and report the selected path.

    Fresh empty DB:
        schema-46 bootstrap, then migrations 47..50.

    Existing versioned DB:
        incremental from recorded schema version.

    Exact legacy module-local unversioned DB:
        one-time reconciliation through the historical chain. This compatibility
        path is deliberately separate from fresh bootstrap.
    """
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)"
    )
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations"
    ).fetchone()
    current = int(row["v"] if isinstance(row, sqlite3.Row) else row[0])
    migrations = _all_migrations()
    if len(migrations) != SCHEMA_VERSION:
        raise RuntimeError(
            f"migration_registry_length_mismatch:{len(migrations)}:{SCHEMA_VERSION}"
        )

    starting_version = current
    mode = "noop" if current == SCHEMA_VERSION else "incremental"
    bootstrap_version: int | None = None
    applied: list[int] = []
    bootstrap_report: dict[str, object] | None = None
    legacy_reconcile: dict[str, object] | None = None

    if current == 0:
        from .schema_bootstrap import (
            BASELINE_SCHEMA_VERSION,
            apply_schema_bootstrap,
            is_pristine_for_bootstrap,
        )
        if is_pristine_for_bootstrap(connection):
            bootstrap_report = apply_schema_bootstrap(connection)
            current = BASELINE_SCHEMA_VERSION
            bootstrap_version = BASELINE_SCHEMA_VERSION
            mode = "bootstrap"
            if bootstrap_report.get("historical_migrations_invoked") != 0:
                raise RuntimeError("schema_bootstrap_replayed_historical_migrations")
        else:
            legacy_reconcile = _detect_legacy_unversioned_state(connection)
            if legacy_reconcile.get("recognized") is not True:
                raise RuntimeError(
                    "unversioned_nonempty_state_database:"
                    + repr(legacy_reconcile)
                )
            mode = "legacy_reconcile"
            current = 0

    for version, migration in enumerate(migrations, start=1):
        if version <= current:
            continue
        migration(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version) VALUES(?)",
            (version,),
        )
        applied.append(version)

    return {
        "mode": mode,
        "starting_version": starting_version,
        "bootstrap_version": bootstrap_version,
        "bootstrap": bootstrap_report,
        "legacy_reconcile": legacy_reconcile,
        "applied_migrations": applied,
        "current_version": SCHEMA_VERSION,
    }


def migrate(connection: sqlite3.Connection) -> None:
    """Apply required migrations while preserving the historical None API."""
    migrate_with_report(connection)
    return None


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


def _m12(c: sqlite3.Connection) -> None:
    """Add coordination enforcement, expiry, reclaim, and signed-audit linkage."""
    c.executescript("""
    ALTER TABLE resource_leases ADD COLUMN expired_at TEXT;
    ALTER TABLE resource_leases ADD COLUMN release_reason TEXT;
    ALTER TABLE resource_leases ADD COLUMN overlap_warning_json TEXT;
    ALTER TABLE tasks ADD COLUMN stale_at TEXT;
    ALTER TABLE tasks ADD COLUMN reclaim_status TEXT;
    ALTER TABLE tasks ADD COLUMN reclaim_requested_by TEXT;
    CREATE TABLE task_reclaims(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
        old_owner_session_id TEXT, new_owner_session_id TEXT,
        requested_by_session_id TEXT NOT NULL, reason TEXT NOT NULL,
        status TEXT NOT NULL, requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT, FOREIGN KEY(task_id) REFERENCES tasks(id));
    CREATE TABLE coordination_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, session_id TEXT NOT NULL,
        event_type TEXT NOT NULL, resource_type TEXT, resource_key TEXT, lease_id INTEGER,
        decision TEXT NOT NULL, reason TEXT, payload_hash TEXT NOT NULL,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id), FOREIGN KEY(lease_id) REFERENCES resource_leases(id));
    CREATE INDEX idx_coordination_events_task ON coordination_events(task_id,created_at);
    """)



def _m13(c: sqlite3.Connection) -> None:
    """Add gateway ownership and external signed-state linkage."""
    c.executescript("""
    CREATE TABLE session_tokens(
        token_hash TEXT PRIMARY KEY, token_id TEXT NOT NULL UNIQUE,
        session_id TEXT NOT NULL, task_id TEXT NOT NULL,
        capability_set_json TEXT NOT NULL DEFAULT '[]',
        issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL, revoked_at TEXT,
        last_sequence INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(task_id) REFERENCES tasks(id));
    CREATE TABLE signed_state_index(
        id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT NOT NULL,
        row_key TEXT NOT NULL, external_event_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(table_name,row_key,external_event_hash));
    CREATE INDEX idx_signed_state_lookup ON signed_state_index(table_name,row_key);
    CREATE TABLE gateway_state(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), instance_id TEXT NOT NULL,
        security_profile TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)


def _m14(c: sqlite3.Connection) -> None:
    """Add authenticated request replay protection and credential history."""
    c.executescript("""
    CREATE TABLE authenticated_requests(
        request_id TEXT PRIMARY KEY, token_id TEXT NOT NULL, task_id TEXT NOT NULL,
        session_id TEXT NOT NULL, sequence INTEGER NOT NULL, body_hash TEXT NOT NULL,
        decision TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_authenticated_requests_token ON authenticated_requests(token_id,sequence);
    CREATE TABLE session_revocations(
        id INTEGER PRIMARY KEY AUTOINCREMENT, token_id TEXT NOT NULL,
        revoked_by TEXT NOT NULL, reason TEXT NOT NULL,
        external_event_hash TEXT, revoked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)


def _m15(c: sqlite3.Connection) -> None:
    """Add isolated execution manifests and denial evidence."""
    c.executescript("""
    CREATE TABLE execution_manifests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
        session_id TEXT NOT NULL, command_hash TEXT NOT NULL, cwd TEXT NOT NULL,
        sandbox_profile TEXT NOT NULL, workspace_path TEXT,
        environment_hash TEXT NOT NULL, network_allowed INTEGER NOT NULL DEFAULT 0,
        decision TEXT NOT NULL, reason TEXT, external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_execution_manifests_task ON execution_manifests(task_id,created_at);
    """)


def _m16(c: sqlite3.Connection) -> None:
    """Add reconciliation checkpoints and recovery history."""
    c.executescript("""
    ALTER TABLE workflow_steps ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'unverified';
    ALTER TABLE workflow_steps ADD COLUMN external_event_hash TEXT;
    CREATE TABLE state_reconciliation_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ok INTEGER NOT NULL,
        checked_rows INTEGER NOT NULL, unverifiable_rows INTEGER NOT NULL,
        details_json TEXT NOT NULL, latest_external_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE recovery_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
        status TEXT NOT NULL, details_json TEXT NOT NULL,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)


def _m17(c: sqlite3.Connection) -> None:
    """Add deterministic context packages for v0.15.0."""
    c.executescript("""
    CREATE TABLE context_packs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
        revision INTEGER NOT NULL, content_hash TEXT NOT NULL,
        manifest_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id), UNIQUE(task_id,revision));
    CREATE INDEX idx_context_packs_task ON context_packs(task_id,status,revision);
    """)


def _m18(c: sqlite3.Connection) -> None:
    """Add project findings and provenance-aware memory for v0.15.1."""
    c.executescript("""
    CREATE TABLE project_findings(
        id INTEGER PRIMARY KEY AUTOINCREMENT, finding_key TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL, path TEXT, symbol TEXT, message TEXT NOT NULL,
        first_seen_task_id TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'active',
        first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_project_findings_lookup ON project_findings(kind,status,occurrences);
    CREATE TABLE project_memory(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, statement TEXT NOT NULL,
        source_path TEXT, source_hash TEXT, first_seen_task_id TEXT,
        last_confirmed_task_id TEXT, confidence REAL NOT NULL DEFAULT 1.0,
        evidence_hash TEXT, status TEXT NOT NULL DEFAULT 'active', supersedes_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(supersedes_id) REFERENCES project_memory(id));
    CREATE INDEX idx_project_memory_query ON project_memory(kind,status,confidence);
    """)


def _m19(c: sqlite3.Connection) -> None:
    """Add asynchronous execution jobs for v0.16.0."""
    c.executescript("""
    CREATE TABLE async_jobs(
        job_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, session_id TEXT NOT NULL,
        spec_json TEXT NOT NULL, spec_hash TEXT NOT NULL, state TEXT NOT NULL,
        pid INTEGER, exit_code INTEGER, timeout_seconds INTEGER NOT NULL,
        stdout_path TEXT NOT NULL, stderr_path TEXT NOT NULL, cancel_reason TEXT,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at TEXT, finished_at TEXT, FOREIGN KEY(task_id) REFERENCES tasks(id));
    CREATE INDEX idx_async_jobs_task_state ON async_jobs(task_id,state,created_at);
    CREATE TABLE job_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
        event_type TEXT NOT NULL, details_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES async_jobs(job_id));
    CREATE INDEX idx_job_events_job ON job_events(job_id,created_at);
    """)


def _m20(c: sqlite3.Connection) -> None:
    """Add versioned task plans and pre-commit records for v0.16.1."""
    c.executescript("""
    CREATE TABLE task_plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, revision INTEGER NOT NULL,
        status TEXT NOT NULL, plan_json TEXT NOT NULL, plan_hash TEXT NOT NULL,
        submitted_by TEXT NOT NULL, approved_by TEXT, approval_note TEXT,
        submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, approved_at TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id), UNIQUE(task_id,revision));
    CREATE INDEX idx_task_plans_active ON task_plans(task_id,status,revision);
    CREATE TABLE precommit_checks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ok INTEGER NOT NULL,
        changed_files_json TEXT NOT NULL, blockers_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id));
    """)


def _m21(c: sqlite3.Connection) -> None:
    """Add evaluation runs and benchmark metadata for v0.16.2."""
    c.executescript("""
    CREATE TABLE evaluation_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, metrics_schema_version INTEGER NOT NULL,
        agent_name TEXT, model_name TEXT, policy_version TEXT NOT NULL,
        repository_version TEXT NOT NULL, filters_json TEXT NOT NULL, metrics_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_evaluation_runs_dimensions ON evaluation_runs(agent_name,model_name,policy_version,created_at);
    """)


def _m22(c: sqlite3.Connection) -> None:
    """Add evaluation-driven controlled evolution for v0.17.0."""
    c.executescript("""
    CREATE TABLE evolution_proposals(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, status TEXT NOT NULL,
        trigger_findings_json TEXT NOT NULL, policy_patch_json TEXT NOT NULL,
        expected_benefit TEXT NOT NULL, risks_json TEXT NOT NULL, rollback_plan_json TEXT NOT NULL,
        baseline_evaluation_run_id INTEGER NOT NULL, simulation_json TEXT, proposal_hash TEXT NOT NULL UNIQUE,
        created_by TEXT NOT NULL, reviewed_by TEXT, review_note TEXT, external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(baseline_evaluation_run_id) REFERENCES evaluation_runs(id));
    CREATE INDEX idx_evolution_proposals_status ON evolution_proposals(status,created_at);
    CREATE TABLE evolution_stage_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id INTEGER NOT NULL, from_status TEXT NOT NULL,
        to_status TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL, external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(proposal_id) REFERENCES evolution_proposals(id));
    """)


def _m23(c: sqlite3.Connection) -> None:
    """Add role- and context-isolated multi-agent protocol for v0.17.1."""
    c.executescript("""
    CREATE TABLE task_role_assignments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, session_id TEXT NOT NULL, token_id TEXT NOT NULL,
        role TEXT NOT NULL, permissions_json TEXT NOT NULL, assigned_by TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(task_id) REFERENCES tasks(id));
    CREATE INDEX idx_task_roles_active ON task_role_assignments(task_id,session_id,status);
    CREATE TABLE task_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT NOT NULL UNIQUE, correlation_id TEXT NOT NULL,
        causation_id TEXT, task_id TEXT NOT NULL, from_session TEXT NOT NULL, to_session TEXT NOT NULL,
        kind TEXT NOT NULL, payload_json TEXT NOT NULL, payload_schema_version INTEGER NOT NULL,
        disclosure_level TEXT NOT NULL, artifact_refs_json TEXT NOT NULL, status TEXT NOT NULL,
        external_event_hash TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id));
    CREATE INDEX idx_task_messages_route ON task_messages(task_id,to_session,created_at);
    """)


def _m24(c: sqlite3.Connection) -> None:
    """Add versioned skill-promotion state for v0.18.1."""
    c.executescript("""
    CREATE TABLE promoted_skills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_key TEXT NOT NULL, version INTEGER NOT NULL,
        memory_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
        candidate_path TEXT NOT NULL, graduated_path TEXT,
        status TEXT NOT NULL DEFAULT 'candidate', content_hash TEXT NOT NULL,
        promoted_by TEXT NOT NULL, approved_by TEXT, approval_note TEXT,
        external_event_hash TEXT, supersedes_skill_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, graduated_at TEXT,
        revoked_at TEXT, revoke_reason TEXT,
        UNIQUE(skill_key,version),
        FOREIGN KEY(memory_id) REFERENCES project_memory(id),
        FOREIGN KEY(supersedes_skill_id) REFERENCES promoted_skills(id));
    CREATE INDEX idx_promoted_skills_status ON promoted_skills(status,skill_key,version);
    """)


def _m25(c: sqlite3.Connection) -> None:
    """Add local retrieval observability for v0.18.2."""
    c.executescript("""
    CREATE TABLE knowledge_retrieval_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, query_hash TEXT NOT NULL,
        backend TEXT NOT NULL, kinds_json TEXT NOT NULL, limit_value INTEGER NOT NULL,
        result_count INTEGER NOT NULL, result_ids_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_knowledge_retrieval_backend ON knowledge_retrieval_events(backend,created_at);
    """)


def _m26(c: sqlite3.Connection) -> None:
    """Add optional local embedding and RAG state for v0.19.0."""
    c.executescript("""
    CREATE TABLE knowledge_embeddings(
        source_kind TEXT NOT NULL, source_id TEXT NOT NULL, content_hash TEXT NOT NULL,
        backend TEXT NOT NULL, dimensions INTEGER NOT NULL, vector_json TEXT NOT NULL,
        text_snapshot TEXT NOT NULL, metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(source_kind,source_id,backend));
    CREATE INDEX idx_knowledge_embeddings_backend ON knowledge_embeddings(backend,source_kind);
    CREATE TABLE rag_retrieval_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, query_hash TEXT NOT NULL, backend TEXT NOT NULL,
        kinds_json TEXT NOT NULL, top_k INTEGER NOT NULL, result_count INTEGER NOT NULL,
        context_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)


def _m27(c: sqlite3.Connection) -> None:
    """Add use-case-driven knowledge relationship graph for v0.19.1."""
    c.executescript("""
    CREATE TABLE knowledge_nodes(
        node_id TEXT PRIMARY KEY, node_type TEXT NOT NULL, label TEXT NOT NULL,
        properties_json TEXT NOT NULL, content_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_knowledge_nodes_type ON knowledge_nodes(node_type,status);
    CREATE TABLE knowledge_edges(
        edge_id TEXT PRIMARY KEY, from_node_id TEXT NOT NULL, to_node_id TEXT NOT NULL,
        relation TEXT NOT NULL, evidence_json TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
        status TEXT NOT NULL DEFAULT 'active', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(from_node_id) REFERENCES knowledge_nodes(node_id),
        FOREIGN KEY(to_node_id) REFERENCES knowledge_nodes(node_id));
    CREATE INDEX idx_knowledge_edges_from ON knowledge_edges(from_node_id,relation,status);
    CREATE INDEX idx_knowledge_edges_to ON knowledge_edges(to_node_id,relation,status);
    """)


def _m28(c: sqlite3.Connection) -> None:
    """Add unified context-knowledge observability for v0.19.2."""
    c.executescript("""
    CREATE TABLE context_knowledge_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, context_revision INTEGER,
        candidate_count INTEGER NOT NULL, included_count INTEGER NOT NULL, omitted_count INTEGER NOT NULL,
        fallback_used INTEGER NOT NULL DEFAULT 0, manifest_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_context_knowledge_task ON context_knowledge_events(task_id,created_at);
    """)

def _m29(c: sqlite3.Connection) -> None:
    """Add task outcomes and comparison cohorts for v0.19.3."""
    c.executescript("""
    CREATE TABLE task_outcomes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, outcome TEXT NOT NULL, rated_by TEXT NOT NULL,
        test_pass_rate REAL, rework_count INTEGER NOT NULL DEFAULT 0, note TEXT, benchmark_key TEXT, task_category TEXT,
        agent_id TEXT, model_id TEXT, policy_revision TEXT, context_revision TEXT, retrieval_backend TEXT, repository_revision TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(task_id) REFERENCES tasks(id));
    CREATE INDEX idx_task_outcomes_cohort ON task_outcomes(task_category,agent_id,model_id,policy_revision,created_at);
    """)

def _m30(c: sqlite3.Connection) -> None:
    """Add scoped and privacy-aware memory metadata for v0.19.4."""
    c.execute("ALTER TABLE project_memory ADD COLUMN owner_scope TEXT NOT NULL DEFAULT 'project'")
    c.execute("ALTER TABLE project_memory ADD COLUMN sensitivity TEXT NOT NULL DEFAULT 'normal'")
    c.execute("ALTER TABLE project_memory ADD COLUMN consent_source TEXT")
    c.execute("ALTER TABLE project_memory ADD COLUMN expires_at TEXT")
    c.execute("ALTER TABLE project_memory ADD COLUMN revoked_at TEXT")
    c.execute("CREATE INDEX idx_project_memory_scope ON project_memory(owner_scope,status,created_at)")

def _m31(c: sqlite3.Connection) -> None:
    """Add storage retention, signed archive, and embedding BLOB support for v0.19.5."""
    c.executescript("""
    ALTER TABLE knowledge_embeddings ADD COLUMN vector_blob BLOB;
    ALTER TABLE knowledge_embeddings ADD COLUMN vector_dtype TEXT NOT NULL DEFAULT 'float32';
    ALTER TABLE knowledge_embeddings ADD COLUMN vector_version INTEGER NOT NULL DEFAULT 1;
    CREATE TABLE audit_segments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, first_event_id INTEGER NOT NULL, last_event_id INTEGER NOT NULL,
        event_count INTEGER NOT NULL, first_event_hash TEXT, last_event_hash TEXT, segment_hash TEXT NOT NULL,
        archive_path TEXT NOT NULL, signature TEXT, status TEXT NOT NULL DEFAULT 'verified',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE retention_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, deleted_count INTEGER NOT NULL,
        retained_count INTEGER NOT NULL, parameters_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE backup_manifests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, backup_path TEXT NOT NULL, manifest_hash TEXT NOT NULL,
        authoritative_json TEXT NOT NULL, rebuildable_json TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)


def _m41(c: sqlite3.Connection) -> None:
    """Add unified governed-operation and signed-domain-event correlation for v0.22.4."""
    c.executescript("""
    CREATE TABLE governed_operations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id TEXT NOT NULL UNIQUE,
        task_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        intent_hash TEXT NOT NULL,
        execution_token_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        denial_reason TEXT,
        external_request_hash TEXT,
        external_completion_hash TEXT,
        success INTEGER,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE INDEX idx_governed_operations_task ON governed_operations(task_id,session_id,status,started_at);
    """)
    event_tables = (
        "db_boundary_events",
        "db_schema_mapping_events",
        "db_extraction_events",
        "db_target_insert_events",
        "identity_resolution_events",
        "db_recovery_events",
    )
    for table in event_tables:
        columns = {str(row[1]) for row in c.execute(f"PRAGMA table_info({table})")}
        if "governed_operation_id" not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN governed_operation_id TEXT")
        if "external_event_hash" not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN external_event_hash TEXT")


def _feature_migrations() -> list:
    """Load feature migrations lazily so feature modules may use central db.connect()."""
    from .project_identity import migration_32
    from .project_selection import migration_33
    from .project_consolidation import migration_34
    from .database_boundary import migration_35
    from .schema_mapping import migration_36
    from .read_only_extraction import migration_37
    from .controlled_target_insert import migration_38
    from .identity_resolution import migration_39
    from .reconciliation_recovery import migration_40
    from .secret_lineage import migration_42
    from .data_subject_rights import migration_43
    from .context_transport import migration_44
    from .adaptive_budget import migration_45
    from .context_evaluation import migration_46
    from .indexing import migration_47
    from .risk_tiered_batch_review import migration_48
    from .db_aware_context_projection import migration_49
    from .architecture_contract import migration_50
    from .architecture_discovery import migration_51
    from .architecture_compliance import migration_52
    from .architecture_change import migration_53
    from .architecture_planning import migration_54
    from .architecture_structural import migration_55
    from .architecture_runtime import migration_56
    from .architecture_quality import migration_57
    from .skill_contract_v2 import migration_58
    from .skill_selection import migration_59
    from .multi_agent_supervisor import migration_60
    from .multi_agent_workspace import migration_61
    from .completion_verification import migration_62
    from .context_authority import migration_63
    return [migration_32, migration_33, migration_34, migration_35, migration_36, migration_37, migration_38, migration_39, migration_40, _m41, migration_42, migration_43, migration_44, migration_45, migration_46, migration_47, migration_48, migration_49, migration_50, migration_51, migration_52, migration_53, migration_54, migration_55, migration_56, migration_57, migration_58, migration_59, migration_60, migration_61, migration_62, migration_63]


MIGRATIONS = [_m1, _m2, _m3, _m4, _m5, _m6, _m7, _m8, _m9, _m10, _m11, _m12, _m13, _m14, _m15, _m16, _m17, _m18, _m19, _m20, _m21, _m22, _m23, _m24, _m25, _m26, _m27, _m28, _m29, _m30, _m31]


def _all_migrations() -> list:
    """Return the complete ordered migration chain through the current schema."""
    return [*MIGRATIONS, *_feature_migrations()]
