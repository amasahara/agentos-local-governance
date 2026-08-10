"""
File: .agents/agentos/consolidation_cockpit.py

Purpose:
    Provide one privacy-safe, read-only cockpit snapshot for the complete
    AgentOS project/database consolidation pipeline.

Responsibilities:
    - Open the local governance database in SQLite read-only/query-only mode.
    - Aggregate project selection, project consolidation, database boundary,
      schema/mapping, extraction, identity, target-insert, and recovery state.
    - Scope cross-stage counts to the selected consolidation whenever the
      historical schema provides an explicit or joinable relationship.
    - Return status/count/hash-safe metadata only; never return business rows,
      credentials, secret material, staging contents, or identity tokens.
    - Tolerate partially initialized historical schemas without mutating them.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any, Iterator

VERSION = "0.23.3"


def _db_path(root: Path) -> Path:
    """Return the project-local AgentOS governance database path."""
    return root.resolve() / ".agents" / "state" / "agentos.db"


@contextmanager
def _connect_readonly(root: Path) -> Iterator[sqlite3.Connection]:
    """Open AgentOS state without creating files, WALs, or write transactions."""
    path = _db_path(root)
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
        yield conn
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _count(
    conn: sqlite3.Connection,
    table: str,
    *,
    where: str = "",
    params: tuple[Any, ...] = (),
) -> int:
    if not _table_exists(conn, table):
        return 0
    sql = f"SELECT COUNT(*) AS n FROM {table}"
    if where:
        sql += " WHERE " + where
    return int(conn.execute(sql, params).fetchone()["n"])


def _status_counts(
    conn: sqlite3.Connection,
    table: str,
    *,
    where: str = "",
    params: tuple[Any, ...] = (),
) -> dict[str, int]:
    if "status" not in _columns(conn, table):
        return {}
    sql = f"SELECT status, COUNT(*) AS n FROM {table}"
    if where:
        sql += " WHERE " + where
    sql += " GROUP BY status ORDER BY status"
    return {str(row["status"]): int(row["n"]) for row in conn.execute(sql, params)}


def _query_status_counts(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
    *,
    required_tables: tuple[str, ...],
) -> dict[str, int]:
    if any(not _table_exists(conn, table) for table in required_tables):
        return {}
    return {str(row["status"]): int(row["n"]) for row in conn.execute(sql, params)}


def _latest_id(conn: sqlite3.Connection, table: str) -> int | None:
    if not _table_exists(conn, table) or "id" not in _columns(conn, table):
        return None
    row = conn.execute(f"SELECT MAX(id) AS id FROM {table}").fetchone()
    return int(row["id"]) if row and row["id"] is not None else None


def _scoped_where(
    conn: sqlite3.Connection, table: str, column: str, value: int | None
) -> tuple[str, tuple[Any, ...]]:
    if value is None or column not in _columns(conn, table):
        return "", ()
    return f"{column}=?", (value,)


def _scoped_status(
    conn: sqlite3.Connection, table: str, column: str, value: int | None
) -> dict[str, int]:
    where, params = _scoped_where(conn, table, column, value)
    return _status_counts(conn, table, where=where, params=params)


def _scoped_count(
    conn: sqlite3.Connection, table: str, column: str, value: int | None
) -> int:
    where, params = _scoped_where(conn, table, column, value)
    return _count(conn, table, where=where, params=params)


def _project_scope(
    conn: sqlite3.Connection,
    candidate_set_id: int | None,
    project_consolidation_id: int | None,
) -> dict[str, Any]:
    compatibility: dict[str, int] = {}
    if _table_exists(conn, "project_compatibility") and candidate_set_id is not None:
        rows = conn.execute(
            """
            SELECT compatibility_status AS status, COUNT(*) AS n
            FROM project_compatibility
            WHERE candidate_set_id=?
            GROUP BY compatibility_status ORDER BY compatibility_status
            """,
            (candidate_set_id,),
        )
        compatibility = {str(row["status"]): int(row["n"]) for row in rows}

    conditional_unconfirmed = 0
    if _table_exists(conn, "project_compatibility") and candidate_set_id is not None:
        cols = _columns(conn, "project_compatibility")
        if {"compatibility_status", "human_confirmed", "candidate_set_id"}.issubset(cols):
            conditional_unconfirmed = _count(
                conn,
                "project_compatibility",
                where="candidate_set_id=? AND compatibility_status='conditionally_compatible' AND human_confirmed=0",
                params=(candidate_set_id,),
            )

    selection_status = _scoped_status(
        conn, "primary_project_selections", "candidate_set_id", candidate_set_id
    )
    component_status = _scoped_status(
        conn, "project_component_mappings", "consolidation_id", project_consolidation_id
    )
    return {
        "candidate_set": {
            "id": candidate_set_id,
            "sets": _scoped_status(conn, "project_candidate_sets", "id", candidate_set_id),
            "candidate_count": _scoped_count(
                conn, "project_candidates", "candidate_set_id", candidate_set_id
            ),
            "compatibility": compatibility,
            "conditional_unconfirmed": conditional_unconfirmed,
            "primary_selection": selection_status,
        },
        "project_consolidation": {
            "id": project_consolidation_id,
            "status": _scoped_status(
                conn, "project_consolidations", "id", project_consolidation_id
            ),
            "source_count": _scoped_count(
                conn,
                "project_consolidation_sources",
                "consolidation_id",
                project_consolidation_id,
            ),
            "components": component_status,
            "reviews": _scoped_status(
                conn,
                "project_consolidation_reviews",
                "consolidation_id",
                project_consolidation_id,
            ),
            "approvals": _scoped_status(
                conn,
                "project_consolidation_approvals",
                "consolidation_id",
                project_consolidation_id,
            ),
            "provenance_count": _scoped_count(
                conn,
                "project_component_provenance",
                "consolidation_id",
                project_consolidation_id,
            ),
        },
    }


def _db_scope(conn: sqlite3.Connection, consolidation_id: int | None) -> dict[str, Any]:
    # Identity tables do not all carry consolidation_id, so scope through the
    # extraction batch relationship instead of returning cross-consolidation totals.
    identity_runs = _query_status_counts(
        conn,
        """
        SELECT r.status AS status, COUNT(*) AS n
        FROM identity_resolution_runs r
        JOIN db_extraction_batches b ON b.id=r.extraction_batch_id
        WHERE b.consolidation_id=?
        GROUP BY r.status ORDER BY r.status
        """,
        (consolidation_id,),
        required_tables=("identity_resolution_runs", "db_extraction_batches"),
    ) if consolidation_id is not None else _status_counts(conn, "identity_resolution_runs")

    identity_candidates = _query_status_counts(
        conn,
        """
        SELECT c.status AS status, COUNT(*) AS n
        FROM identity_candidates c
        JOIN identity_resolution_runs r ON r.id=c.resolution_run_id
        JOIN db_extraction_batches b ON b.id=r.extraction_batch_id
        WHERE b.consolidation_id=?
        GROUP BY c.status ORDER BY c.status
        """,
        (consolidation_id,),
        required_tables=("identity_candidates", "identity_resolution_runs", "db_extraction_batches"),
    ) if consolidation_id is not None else _status_counts(conn, "identity_candidates")

    reconciliation_runs = _query_status_counts(
        conn,
        """
        SELECT r.status AS status, COUNT(*) AS n
        FROM db_reconciliation_runs r
        JOIN db_target_insert_runs i ON i.id=r.insert_run_id
        WHERE i.consolidation_id=?
        GROUP BY r.status ORDER BY r.status
        """,
        (consolidation_id,),
        required_tables=("db_reconciliation_runs", "db_target_insert_runs"),
    ) if consolidation_id is not None else _status_counts(conn, "db_reconciliation_runs")

    recovery_cases = _query_status_counts(
        conn,
        """
        SELECT c.status AS status, COUNT(*) AS n
        FROM db_recovery_cases c
        JOIN db_target_insert_runs i ON i.id=c.insert_run_id
        WHERE i.consolidation_id=?
        GROUP BY c.status ORDER BY c.status
        """,
        (consolidation_id,),
        required_tables=("db_recovery_cases", "db_target_insert_runs"),
    ) if consolidation_id is not None else _status_counts(conn, "db_recovery_cases")

    validation_findings = 0
    if consolidation_id is not None and _table_exists(conn, "db_validation_findings") and _table_exists(conn, "db_extraction_batches"):
        validation_findings = int(conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM db_validation_findings f
            JOIN db_extraction_batches b ON b.id=f.batch_id
            WHERE b.consolidation_id=?
            """,
            (consolidation_id,),
        ).fetchone()["n"])
    elif consolidation_id is None:
        validation_findings = _count(conn, "db_validation_findings")

    referenced_snapshots = 0
    if consolidation_id is not None and _table_exists(conn, "db_field_mappings"):
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT source_snapshot_id) AS n
            FROM db_field_mappings WHERE consolidation_id=?
            """,
            (consolidation_id,),
        ).fetchone()
        referenced_snapshots = int(row["n"] or 0)
        if _table_exists(conn, "target_schema_contracts"):
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT target_snapshot_id) AS n
                FROM target_schema_contracts WHERE consolidation_id=?
                """,
                (consolidation_id,),
            ).fetchone()
            referenced_snapshots += int(row["n"] or 0)
    elif consolidation_id is None:
        referenced_snapshots = _count(conn, "db_schema_snapshots")

    unverified_sources = 0
    if consolidation_id is not None and _table_exists(conn, "db_consolidation_sources"):
        if "readonly_verified_at_registration" in _columns(conn, "db_consolidation_sources"):
            unverified_sources = _count(
                conn,
                "db_consolidation_sources",
                where="consolidation_id=? AND readonly_verified_at_registration=0",
                params=(consolidation_id,),
            )

    return {
        "database_boundary": {
            "id": consolidation_id,
            "status": _scoped_status(conn, "db_consolidations", "id", consolidation_id),
            "source_count": _scoped_count(
                conn, "db_consolidation_sources", "consolidation_id", consolidation_id
            ),
            "unverified_source_count": unverified_sources,
            "connection_count": _count(conn, "db_connections"),
        },
        "schema_mapping": {
            "referenced_snapshot_count": referenced_snapshots,
            "contracts": _scoped_status(
                conn, "target_schema_contracts", "consolidation_id", consolidation_id
            ),
            "mappings": _scoped_status(
                conn, "db_field_mappings", "consolidation_id", consolidation_id
            ),
        },
        "extraction": {
            "batches": _scoped_status(
                conn, "db_extraction_batches", "consolidation_id", consolidation_id
            ),
            "validation_finding_count": validation_findings,
        },
        "identity": {
            "policies": _scoped_status(
                conn, "identity_resolution_policies", "consolidation_id", consolidation_id
            ),
            "runs": identity_runs,
            "candidates": identity_candidates,
        },
        "target_insert": {
            "runs": _scoped_status(
                conn, "db_target_insert_runs", "consolidation_id", consolidation_id
            ),
        },
        "reconciliation": {
            "runs": reconciliation_runs,
            "recovery_cases": recovery_cases,
        },
    }


def _derive_blockers(stages: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    candidate = stages["project"]["candidate_set"]
    compatibility = candidate["compatibility"]
    if compatibility.get("incompatible", 0):
        blockers.append("project_domain_incompatibility")
    if candidate.get("conditional_unconfirmed", 0):
        blockers.append("project_compatibility_requires_human_confirmation")
    if candidate.get("id") is not None and not candidate.get("primary_selection"):
        blockers.append("primary_project_not_selected")

    project_consolidation = stages["project"]["project_consolidation"]
    components = project_consolidation.get("components", {})
    if components.get("conflict", 0) or components.get("CONFLICT", 0):
        blockers.append("project_component_conflict")
    if project_consolidation.get("id") is not None and not project_consolidation.get("approvals"):
        blockers.append("project_consolidation_not_approved")

    database = stages["database"]
    if database["database_boundary"].get("unverified_source_count", 0):
        blockers.append("database_source_readonly_not_verified")
    contracts = database["schema_mapping"]["contracts"]
    if contracts.get("draft", 0) or contracts.get("reviewed", 0):
        blockers.append("target_contract_requires_approval")
    mappings = database["schema_mapping"]["mappings"]
    if mappings.get("proposed", 0) or mappings.get("stale", 0):
        blockers.append("field_mappings_require_attention")
    candidates = database["identity"]["candidates"]
    if candidates.get("pending", 0) or candidates.get("awaiting_human", 0):
        blockers.append("identity_candidates_require_human_decision")
    inserts = database["target_insert"]["runs"]
    if inserts.get("in_doubt", 0) or inserts.get("committing", 0):
        blockers.append("target_commit_requires_reconciliation")
    recovery = database["reconciliation"]["recovery_cases"]
    if recovery.get("manual_intervention", 0):
        blockers.append("recovery_manual_intervention_required")
    return sorted(set(blockers))


def consolidation_status(
    root: Path,
    consolidation_id: int | None = None,
    *,
    candidate_set_id: int | None = None,
    project_consolidation_id: int | None = None,
) -> dict[str, Any]:
    """Return one read-only snapshot of the complete consolidation pipeline.

    Args:
        root: Governed AgentOS project root.
        consolidation_id: Optional database-consolidation identifier.
        candidate_set_id: Optional project candidate-set identifier.
        project_consolidation_id: Optional primary-project consolidation identifier.

    Returns:
        Machine-readable status/count metadata. Business row values, credentials,
        staging contents, secret material, and identity tokens are never returned.
    """
    root = root.resolve()
    path = _db_path(root)
    if not path.is_file():
        return {
            "ok": True,
            "version": VERSION,
            "schema_expected": 46,
            "database_present": False,
            "database_path": ".agents/state/agentos.db",
            "scope": {
                "candidate_set_id": candidate_set_id,
                "project_consolidation_id": project_consolidation_id,
                "db_consolidation_id": consolidation_id,
            },
            "stages": {},
            "blockers": ["governance_database_not_initialized"],
            "overall_state": "not_initialized",
            "read_only": True,
            "privacy": {
                "raw_record_values_returned": False,
                "credentials_returned": False,
                "secret_material_returned": False,
                "identity_tokens_returned": False,
            },
        }

    with _connect_readonly(root) as conn:
        selected_candidate_set = candidate_set_id
        if selected_candidate_set is None:
            selected_candidate_set = _latest_id(conn, "project_candidate_sets")
        selected_project_consolidation = project_consolidation_id
        if selected_project_consolidation is None:
            selected_project_consolidation = _latest_id(conn, "project_consolidations")
        selected_db_consolidation = consolidation_id
        if selected_db_consolidation is None:
            selected_db_consolidation = _latest_id(conn, "db_consolidations")

        stages = {
            "project": _project_scope(
                conn, selected_candidate_set, selected_project_consolidation
            ),
            "database": _db_scope(conn, selected_db_consolidation),
        }
        blockers = _derive_blockers(stages)
        schema_version = None
        if _table_exists(conn, "schema_migrations"):
            row = conn.execute(
                "SELECT COALESCE(MAX(version),0) AS version FROM schema_migrations"
            ).fetchone()
            schema_version = int(row["version"])

        return {
            "ok": True,
            "version": VERSION,
            "schema_expected": 46,
            "schema_observed": schema_version,
            "database_present": True,
            "database_path": ".agents/state/agentos.db",
            "scope": {
                "candidate_set_id": selected_candidate_set,
                "project_consolidation_id": selected_project_consolidation,
                "db_consolidation_id": selected_db_consolidation,
            },
            "stages": stages,
            "blockers": blockers,
            "overall_state": "blocked" if blockers else "ready_or_in_progress",
            "read_only": True,
            "privacy": {
                "raw_record_values_returned": False,
                "credentials_returned": False,
                "secret_material_returned": False,
                "identity_tokens_returned": False,
            },
        }
