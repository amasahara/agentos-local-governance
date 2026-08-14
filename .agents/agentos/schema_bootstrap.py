"""
File: .agents/agentos/schema_bootstrap.py

Purpose:
    Materialize a deterministic schema-46 baseline for a brand-new AgentOS state
    database without invoking historical migration functions 1..46.

Responsibilities:
    - Apply the release-pinned schema-46 DDL snapshot transactionally.
    - Verify the canonical schema fingerprint before accepting the baseline.
    - Record migration coverage 1..46 without replaying those migration functions.
    - Run compatibility initializers for fresh-state semantics that historically
      came from migrations rather than DDL.
    - Keep existing/versioned databases on the ordinary incremental path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

BASELINE_SCHEMA_VERSION = 46
BOOTSTRAP_FORMAT_VERSION = 2
COMPATIBILITY_INITIALIZERS = ("project_identity_v32",)


def _schema_dir() -> Path:
    """Return release-pinned schema artifacts shipped with AgentOS."""
    return Path(__file__).resolve().parent.parent / "schema"


def _metadata_path() -> Path:
    return _schema_dir() / "bootstrap_v46.json"


def _sql_path() -> Path:
    return _schema_dir() / "bootstrap_v46.sql"


def _canonical_schema_objects(connection: sqlite3.Connection) -> list[dict[str, str]]:
    """Return canonical user-schema objects excluding migration metadata."""
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
          AND name <> 'schema_migrations'
          AND type IN ('table','index','trigger','view')
        ORDER BY
          CASE type
            WHEN 'table' THEN 1
            WHEN 'index' THEN 2
            WHEN 'trigger' THEN 3
            WHEN 'view' THEN 4
            ELSE 9
          END,
          name
        """
    ).fetchall()
    return [
        {
            "type": str(row[0]),
            "name": str(row[1]),
            "table": str(row[2]),
            "sql": " ".join(str(row[3]).split()),
        }
        for row in rows
    ]


def schema_fingerprint(connection: sqlite3.Connection) -> str:
    """Return SHA-256 over canonical SQLite schema objects."""
    payload = json.dumps(
        _canonical_schema_objects(connection),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def baseline_metadata() -> dict[str, Any]:
    """Load and validate release-pinned bootstrap metadata."""
    path = _metadata_path()
    if not path.is_file():
        raise RuntimeError("schema_bootstrap_metadata_missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("format_version", -1)) != BOOTSTRAP_FORMAT_VERSION:
        raise RuntimeError("schema_bootstrap_format_unsupported")
    if int(payload.get("baseline_schema", -1)) != BASELINE_SCHEMA_VERSION:
        raise RuntimeError("schema_bootstrap_baseline_mismatch")
    fingerprint = str(payload.get("schema_fingerprint") or "")
    if len(fingerprint) != 64:
        raise RuntimeError("schema_bootstrap_fingerprint_invalid")
    initializers = tuple(str(x) for x in payload.get("compatibility_initializers", []))
    if initializers != COMPATIBILITY_INITIALIZERS:
        raise RuntimeError("schema_bootstrap_initializer_contract_mismatch")
    return payload


def _migration_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _non_bootstrap_objects(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
          AND name <> 'schema_migrations'
        ORDER BY name
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def is_pristine_for_bootstrap(connection: sqlite3.Connection) -> bool:
    """Return True only for an empty versioned database safe to bootstrap."""
    return _migration_version(connection) == 0 and not _non_bootstrap_objects(connection)


def _iter_sql_statements(script: str) -> Iterator[str]:
    """Split canonical SQLite DDL while preserving trigger bodies."""
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if not sqlite3.complete_statement(buffer):
            continue
        statement = buffer.strip()
        buffer = ""
        if not statement:
            continue
        cleaned = "\n".join(
            item for item in statement.splitlines()
            if not item.lstrip().startswith("--")
        ).strip()
        if cleaned:
            yield cleaned
    if buffer.strip():
        raise RuntimeError("schema_bootstrap_sql_incomplete")


def _infer_root_from_connection(connection: sqlite3.Connection) -> Path | None:
    """Infer <project-root> only from the canonical .agents/state/agentos.db path."""
    for row in connection.execute("PRAGMA database_list"):
        raw = str(row[2] or "")
        if not raw:
            continue
        path = Path(raw).resolve()
        if path.parent.name == "state" and path.parent.parent.name == ".agents":
            return path.parent.parent.parent
    return None


def _initialize_project_identity_v32(connection: sqlite3.Connection) -> dict[str, Any]:
    """Preserve fresh-state identity/purpose semantics without calling migration_32."""
    root = _infer_root_from_connection(connection)
    if root is None:
        return {
            "name": "project_identity_v32",
            "status": "not_applicable_no_file_backed_root",
        }

    from .project_identity import (
        _canonical_json,
        ensure_project_id,
        load_purpose,
        utc_now,
    )

    project = ensure_project_id(root)
    project_uuid = str(project["project_uuid"])

    # On a pristine DB these tables contain no pre-existing rows, but retaining
    # the backfill updates preserves the migration-32 semantic contract if a
    # future bootstrap artifact seeds compatible rows.
    for table in (
        "symbol_index",
        "project_findings",
        "promoted_skills",
        "resource_leases",
    ):
        columns = {
            str(row[1])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        if "project_uuid" in columns:
            connection.execute(
                f'UPDATE "{table}" SET project_uuid=? WHERE project_uuid IS NULL',
                (project_uuid,),
            )

    connection.execute(
        """
        INSERT INTO project_identity(
            singleton, project_uuid, origin_project_uuid, audit_project_id,
            identity_version, identity_hash, created_at, created_by
        ) VALUES(1,?,?,?,?,?,?,?)
        ON CONFLICT(singleton) DO UPDATE SET
            project_uuid=excluded.project_uuid,
            origin_project_uuid=excluded.origin_project_uuid,
            audit_project_id=excluded.audit_project_id,
            identity_version=excluded.identity_version,
            identity_hash=excluded.identity_hash,
            created_at=excluded.created_at,
            created_by=excluded.created_by
        """,
        (
            project_uuid,
            project.get("origin_project_uuid"),
            project["audit_project_id"],
            project["identity_version"],
            project["identity_hash"],
            project["created_at"],
            project["created_by"],
        ),
    )

    purpose = load_purpose(root)
    purpose_seeded = False
    if purpose is not None:
        confirm = purpose["human_confirmation"]
        purpose_json = _canonical_json(purpose)
        connection.execute(
            """
            INSERT INTO project_purpose(
                singleton, project_uuid, purpose_json, purpose_hash,
                confirmed_by, confirmed_at, updated_at
            ) VALUES(1,?,?,?,?,?,?)
            ON CONFLICT(singleton) DO UPDATE SET
                project_uuid=excluded.project_uuid,
                purpose_json=excluded.purpose_json,
                purpose_hash=excluded.purpose_hash,
                confirmed_by=excluded.confirmed_by,
                confirmed_at=excluded.confirmed_at,
                updated_at=excluded.updated_at
            """,
            (
                project_uuid,
                purpose_json,
                purpose["purpose_hash"],
                confirm["confirmed_by"],
                confirm["confirmed_at"],
                utc_now(),
            ),
        )
        existing = connection.execute(
            """
            SELECT 1 FROM project_purpose_history
            WHERE project_uuid=? AND purpose_hash=? LIMIT 1
            """,
            (project_uuid, purpose["purpose_hash"]),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO project_purpose_history(
                    project_uuid, purpose_json, purpose_hash,
                    confirmed_by, confirmed_at
                ) VALUES(?,?,?,?,?)
                """,
                (
                    project_uuid,
                    purpose_json,
                    purpose["purpose_hash"],
                    confirm["confirmed_by"],
                    confirm["confirmed_at"],
                ),
            )
        purpose_seeded = True

    return {
        "name": "project_identity_v32",
        "status": "initialized",
        "project_identity_seeded": True,
        "project_purpose_seeded": purpose_seeded,
        "raw_identity_data_exposed": False,
    }


def _run_compatibility_initializers(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Run the small allowlisted fresh-state compatibility initializer registry."""
    registry = {
        "project_identity_v32": _initialize_project_identity_v32,
    }
    results: list[dict[str, Any]] = []
    for name in COMPATIBILITY_INITIALIZERS:
        initializer = registry.get(name)
        if initializer is None:
            raise RuntimeError(f"schema_bootstrap_initializer_missing:{name}")
        results.append(initializer(connection))
    return results


def apply_schema_bootstrap(connection: sqlite3.Connection) -> dict[str, Any]:
    """Apply schema-46 baseline and fresh-state compatibility semantics."""
    if not is_pristine_for_bootstrap(connection):
        raise RuntimeError("schema_bootstrap_requires_pristine_database")

    metadata = baseline_metadata()
    sql_path = _sql_path()
    if not sql_path.is_file():
        raise RuntimeError("schema_bootstrap_sql_missing")

    connection.execute("SAVEPOINT agentos_schema_bootstrap")
    try:
        statement_count = 0
        for statement in _iter_sql_statements(
            sql_path.read_text(encoding="utf-8")
        ):
            connection.execute(statement)
            statement_count += 1

        actual = schema_fingerprint(connection)
        expected = str(metadata["schema_fingerprint"])
        if actual != expected:
            raise RuntimeError("schema_bootstrap_fingerprint_mismatch")

        connection.executemany(
            "INSERT INTO schema_migrations(version) VALUES(?)",
            [
                (version,)
                for version in range(1, BASELINE_SCHEMA_VERSION + 1)
            ],
        )
        initializer_results = _run_compatibility_initializers(connection)
        connection.execute("RELEASE SAVEPOINT agentos_schema_bootstrap")
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT agentos_schema_bootstrap")
        connection.execute("RELEASE SAVEPOINT agentos_schema_bootstrap")
        raise

    return {
        "mode": "bootstrap",
        "baseline_schema": BASELINE_SCHEMA_VERSION,
        "schema_fingerprint": actual,
        "object_count": len(_canonical_schema_objects(connection)),
        "statement_count": statement_count,
        "historical_migrations_invoked": 0,
        "compatibility_initializers": initializer_results,
    }


def bootstrap_artifact_status() -> dict[str, Any]:
    """Validate the bootstrap artifact without requiring a project filesystem."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)"
        )
        result = apply_schema_bootstrap(connection)
        metadata = baseline_metadata()
        result["ok"] = (
            result["schema_fingerprint"] == metadata["schema_fingerprint"]
            and result["object_count"] == int(metadata["object_count"])
            and _migration_version(connection) == BASELINE_SCHEMA_VERSION
            and result["historical_migrations_invoked"] == 0
        )
        return result
    finally:
        connection.close()
