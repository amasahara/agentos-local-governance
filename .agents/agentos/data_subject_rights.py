"""
File: .agents/agentos/data_subject_rights.py

Purpose:
    Enforce the v0.22.7 local data-subject erasure lifecycle without granting TARGET mutation authority.

Responsibilities:
    - Persist immutable erasure requests and immutable, privacy-safe execution plans.
    - Require governed human review and approval before local erasure execution.
    - Tombstone canonical entities and remove local relinkable identity/lineage state.
    - Purge relevant staging/cache/memory/index artifacts while retaining minimal audit evidence.
    - Fail closed around active or in-doubt operations and flag external TARGET erasure separately.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .db import connect
from .governance_enforcement import governed_mutation, mirror_domain_event

MIGRATION_VERSION = 43
ERASURE_POLICY_VERSION = 1
ERASURE_REASON_CODES = {
    "subject_request",
    "consent_withdrawn",
    "retention_expired",
    "legal_or_policy_request",
    "operator_privacy_action",
}
BLOCKING_INSERT_STATUSES = {"running", "committing", "in_doubt"}
BLOCKING_IDENTITY_STATUSES = {"planned", "running", "awaiting_human"}
BLOCKING_EXTRACTION_STATUSES = {"planned", "running"}
BLOCKING_RECOVERY_STATUSES = {"open", "manual_intervention"}


class DataSubjectRightsError(RuntimeError):
    """Raised when privacy lifecycle enforcement fails closed."""


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    """Serialize deterministic privacy-safe JSON."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    """Hash structured evidence without preserving subject values."""
    raw = value if isinstance(value, str) else _json(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _entity_locator_hash(entity_uuid: str) -> str:
    """Return a domain-separated one-way locator for a pseudonymous entity reference."""
    value = str(entity_uuid).strip()
    if not value:
        raise DataSubjectRightsError("canonical_entity_not_found")
    return _hash("agentos:data-subject-erasure-locator:v1:" + value)


def harden_privacy_schema(conn: sqlite3.Connection) -> None:
    """Repair schema-43 privacy guarantees for fresh and already-upgraded databases.

    This helper is intentionally called by both migration 43 and migration 46. Earlier
    v0.22.7 materializations created the lifecycle tables but did not enforce all of the
    declared immutability and one-way-locator guarantees. Migration 46 therefore repairs
    existing databases without introducing a second privacy schema version.
    """
    _add_column(conn, "data_subject_erasure_requests", "entity_locator_hash", "TEXT")
    rows = conn.execute(
        "SELECT id,entity_uuid,entity_locator_hash FROM data_subject_erasure_requests"
    ).fetchall()
    for row in rows:
        current = str(row[2] or "").strip()
        legacy = str(row[1] or "").strip()
        if current:
            locator = current
        elif legacy.startswith("locator:") and len(legacy) > len("locator:"):
            locator = legacy.split(":", 1)[1]
        else:
            locator = _entity_locator_hash(legacy)
        redacted = "locator:" + locator
        if current != locator or legacy != redacted:
            conn.execute(
                "UPDATE data_subject_erasure_requests SET entity_locator_hash=?,entity_uuid=? WHERE id=?",
                (locator, redacted, int(row[0])),
            )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_erasure_requests_locator
            ON data_subject_erasure_requests(entity_locator_hash,created_at);
        CREATE TRIGGER IF NOT EXISTS trg_erasure_request_immutable_update
        BEFORE UPDATE ON data_subject_erasure_requests
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_request'); END;
        CREATE TRIGGER IF NOT EXISTS trg_erasure_request_immutable_delete
        BEFORE DELETE ON data_subject_erasure_requests
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_request'); END;
        CREATE TRIGGER IF NOT EXISTS trg_erasure_plan_immutable_update
        BEFORE UPDATE ON data_subject_erasure_plans
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_plan'); END;
        CREATE TRIGGER IF NOT EXISTS trg_erasure_plan_immutable_delete
        BEFORE DELETE ON data_subject_erasure_plans
        BEGIN SELECT RAISE(ABORT,'immutable_erasure_plan'); END;
        """
    )


def _add_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    """Add one SQLite column only when absent."""
    cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def migration_43(conn: sqlite3.Connection) -> None:
    """Create immutable erasure lifecycle state and canonical tombstone metadata."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_subject_erasure_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_uuid TEXT NOT NULL UNIQUE,
            canonical_entity_id INTEGER NOT NULL,
            entity_uuid TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            request_hash TEXT NOT NULL UNIQUE,
            requested_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id)
        );
        CREATE TABLE IF NOT EXISTS data_subject_erasure_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_uuid TEXT NOT NULL UNIQUE,
            request_id INTEGER NOT NULL UNIQUE,
            policy_version INTEGER NOT NULL,
            plan_hash TEXT NOT NULL UNIQUE,
            affected_counts_json TEXT NOT NULL,
            affected_artifact_hashes_json TEXT NOT NULL,
            external_target_erasure_required INTEGER NOT NULL CHECK(external_target_erasure_required IN (0,1)),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(request_id) REFERENCES data_subject_erasure_requests(id)
        );
        CREATE TABLE IF NOT EXISTS data_subject_erasure_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL UNIQUE,
            decision TEXT NOT NULL CHECK(decision IN ('reviewed','rejected')),
            reviewed_by TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            FOREIGN KEY(plan_id) REFERENCES data_subject_erasure_plans(id)
        );
        CREATE TABLE IF NOT EXISTS data_subject_erasure_approvals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL UNIQUE,
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            approval_hash TEXT NOT NULL UNIQUE,
            FOREIGN KEY(plan_id) REFERENCES data_subject_erasure_plans(id)
        );
        CREATE TABLE IF NOT EXISTS data_subject_erasure_executions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL UNIQUE,
            execution_uuid TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('completed','failed')),
            local_erasure_completed INTEGER NOT NULL CHECK(local_erasure_completed IN (0,1)),
            external_target_erasure_required INTEGER NOT NULL CHECK(external_target_erasure_required IN (0,1)),
            deleted_counts_json TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            executed_by TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            failure_code TEXT,
            FOREIGN KEY(plan_id) REFERENCES data_subject_erasure_plans(id)
        );
        CREATE TABLE IF NOT EXISTS privacy_tombstones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_entity_id INTEGER NOT NULL UNIQUE,
            tombstone_uuid TEXT NOT NULL UNIQUE,
            request_hash TEXT NOT NULL,
            plan_hash TEXT NOT NULL,
            tombstone_marker_hash TEXT NOT NULL UNIQUE,
            external_target_erasure_required INTEGER NOT NULL CHECK(external_target_erasure_required IN (0,1)),
            created_at TEXT NOT NULL,
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id)
        );
        CREATE TABLE IF NOT EXISTS data_subject_erasure_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            plan_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            governed_operation_id TEXT,
            external_event_hash TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_erasure_requests_entity ON data_subject_erasure_requests(canonical_entity_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_erasure_events_plan ON data_subject_erasure_events(plan_id,event_type);
        """
    )
    _add_column(conn, "canonical_entities", "privacy_status", "TEXT NOT NULL DEFAULT 'active'")
    _add_column(conn, "canonical_entities", "tombstoned_at", "TEXT")
    _add_column(conn, "canonical_entities", "erasure_request_hash", "TEXT")
    harden_privacy_schema(conn)


def sync_schema(root: Path | str) -> dict[str, Any]:
    """Ensure schema 43 through the unified database connection."""
    with connect(Path(root).resolve()) as conn:
        version = int(conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0)
        fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    return {"ok": version >= MIGRATION_VERSION and fk == 1, "schema": version, "foreign_keys": fk}


def _safe_event(root: Path, event_type: str, *, request_id: int | None = None, plan_id: int | None = None,
                payload: dict[str, Any] | None = None) -> None:
    """Write privacy-safe event metadata and mirror it to signed audit when governed."""
    safe = dict(payload or {})
    forbidden_fragments = ("identifier", "credential", "secret", "password", "token", "fingerprint", "record", "raw", "value")
    for key in safe:
        if any(fragment in key.lower() for fragment in forbidden_fragments):
            raise DataSubjectRightsError("sensitive erasure event payload rejected")
    mirror = mirror_domain_event(event_type, safe)
    with connect(root) as conn:
        conn.execute(
            """INSERT INTO data_subject_erasure_events(request_id,plan_id,event_type,event_json,created_at,governed_operation_id,external_event_hash)
               VALUES(?,?,?,?,?,?,?)""",
            (request_id, plan_id, event_type, _json(safe), utc_now(), mirror.get("governed_operation_id"), mirror.get("external_event_hash")),
        )


def _entity(root: Path, entity_uuid: str) -> sqlite3.Row:
    """Load an active entity directly or a tombstoned entity through a one-way locator."""
    value = str(entity_uuid).strip()
    with connect(root) as conn:
        row = conn.execute("SELECT * FROM canonical_entities WHERE entity_uuid=?", (value,)).fetchone()
        if row is None:
            locator = _entity_locator_hash(value)
            row = conn.execute(
                """SELECT c.* FROM canonical_entities c
                   JOIN data_subject_erasure_requests r ON r.canonical_entity_id=c.id
                   WHERE r.entity_locator_hash=? ORDER BY r.id DESC LIMIT 1""",
                (locator,),
            ).fetchone()
    if not row:
        raise DataSubjectRightsError("canonical_entity_not_found")
    return row


def _artifact_paths(conn: sqlite3.Connection, canonical_entity_id: int) -> list[str]:
    """Collect local staging/manifest paths related to one entity without reading subject contents."""
    paths: set[str] = set()
    runs = conn.execute("SELECT DISTINCT resolution_run_id FROM identity_bindings WHERE canonical_entity_id=?", (canonical_entity_id,)).fetchall()
    run_ids = [int(r[0]) for r in runs]
    for run_id in run_ids:
        row = conn.execute("SELECT input_staging_path,output_staging_path,manifest_path,extraction_batch_id FROM identity_resolution_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            continue
        for value in row[:3]:
            if value:
                paths.add(str(value))
        batch = conn.execute("SELECT staging_path,quarantine_path,manifest_path FROM db_extraction_batches WHERE id=?", (int(row[3]),)).fetchone()
        if batch:
            for value in batch:
                if value:
                    paths.add(str(value))
    lineages = conn.execute("SELECT DISTINCT insert_run_id,extraction_batch_id FROM target_record_lineage WHERE canonical_entity_id=?", (canonical_entity_id,)).fetchall()
    for lineage in lineages:
        insert_row = conn.execute("SELECT staging_path FROM db_target_insert_runs WHERE id=?", (int(lineage[0]),)).fetchone()
        if insert_row and insert_row[0]:
            paths.add(str(insert_row[0]))
        batch = conn.execute("SELECT staging_path,quarantine_path,manifest_path FROM db_extraction_batches WHERE id=?", (int(lineage[1]),)).fetchone()
        if batch:
            for value in batch:
                if value:
                    paths.add(str(value))
    return sorted(paths)


def _path_hashes(root: Path, paths: Iterable[str]) -> list[str]:
    """Convert artifact paths into hashes so immutable plans never persist raw local paths."""
    values = []
    for raw in paths:
        try:
            path = Path(raw)
            if not path.is_absolute():
                path = (root / path).resolve()
            else:
                path = path.resolve()
            path.relative_to(root)
            values.append(_hash(str(path.relative_to(root))))
        except (ValueError, OSError):
            values.append(_hash("outside-root-redacted"))
    return sorted(set(values))


def _affected_snapshot(conn: sqlite3.Connection, root: Path, canonical_entity_id: int) -> dict[str, Any]:
    """Return counts and non-relinkable artifact hashes for an immutable erasure plan."""
    counts = {
        "identity_bindings": int(conn.execute("SELECT COUNT(*) FROM identity_bindings WHERE canonical_entity_id=?", (canonical_entity_id,)).fetchone()[0]),
        "identity_candidates": int(conn.execute(
            "SELECT COUNT(*) FROM identity_candidates WHERE matched_entity_uuid=(SELECT entity_uuid FROM canonical_entities WHERE id=?)", (canonical_entity_id,)
        ).fetchone()[0]),
        "target_record_lineage": int(conn.execute("SELECT COUNT(*) FROM target_record_lineage WHERE canonical_entity_id=?", (canonical_entity_id,)).fetchone()[0]),
    }
    paths = _artifact_paths(conn, canonical_entity_id)
    return {
        "counts": counts,
        "artifact_hashes": _path_hashes(root, paths),
        "artifact_count": len(paths),
        "external_target_erasure_required": counts["target_record_lineage"] > 0,
    }


def _assert_no_active_operations(conn: sqlite3.Connection, canonical_entity_id: int) -> None:
    """Fail closed if identity/extraction/TARGET/recovery work is active or uncertain."""
    entity_row = conn.execute(
        "SELECT entity_uuid FROM canonical_entities WHERE id=?", (canonical_entity_id,)
    ).fetchone()
    entity_uuid = str(entity_row[0]) if entity_row else ""

    resolution_ids = {
        int(r[0]) for r in conn.execute(
            "SELECT DISTINCT resolution_run_id FROM identity_bindings WHERE canonical_entity_id=?",
            (canonical_entity_id,),
        )
    }
    if entity_uuid:
        candidate_rows = conn.execute(
            """SELECT DISTINCT c.resolution_run_id,c.status,r.status,r.extraction_batch_id
                 FROM identity_candidates c
                 LEFT JOIN identity_resolution_runs r ON r.id=c.resolution_run_id
                WHERE c.matched_entity_uuid=?""",
            (entity_uuid,),
        ).fetchall()
        for candidate in candidate_rows:
            resolution_ids.add(int(candidate[0]))
            if str(candidate[1] or "") in {"pending", "awaiting_human"} or str(candidate[2] or "") in BLOCKING_IDENTITY_STATUSES:
                raise DataSubjectRightsError(f"active_identity_operation:{int(candidate[0])}:{candidate[2] or candidate[1]}")

    extraction_batch_ids: set[int] = set()
    for run_id in sorted(resolution_ids):
        row = conn.execute(
            "SELECT status,extraction_batch_id FROM identity_resolution_runs WHERE id=?", (run_id,)
        ).fetchone()
        if not row:
            continue
        if str(row[0]) in BLOCKING_IDENTITY_STATUSES:
            raise DataSubjectRightsError(f"active_identity_operation:{run_id}:{row[0]}")
        if row[1] is not None:
            batch_id = int(row[1]); extraction_batch_ids.add(batch_id)
            batch = conn.execute("SELECT status FROM db_extraction_batches WHERE id=?", (batch_id,)).fetchone()
            if batch and str(batch[0]) in BLOCKING_EXTRACTION_STATUSES:
                raise DataSubjectRightsError(f"active_extraction_operation:{batch_id}:{batch[0]}")

    insert_ids = {
        int(r[0]) for r in conn.execute(
            "SELECT DISTINCT insert_run_id FROM target_record_lineage WHERE canonical_entity_id=?",
            (canonical_entity_id,),
        ) if r[0] is not None
    }
    for batch_id in extraction_batch_ids:
        for row in conn.execute(
            "SELECT id,status FROM db_target_insert_runs WHERE extraction_batch_id=?", (batch_id,)
        ):
            insert_ids.add(int(row[0]))
            if str(row[1]) in BLOCKING_INSERT_STATUSES:
                raise DataSubjectRightsError(f"active_or_in_doubt_target_operation:{int(row[0])}:{row[1]}")

    for insert_id in sorted(insert_ids):
        row = conn.execute("SELECT status FROM db_target_insert_runs WHERE id=?", (insert_id,)).fetchone()
        if row and str(row[0]) in BLOCKING_INSERT_STATUSES:
            raise DataSubjectRightsError(f"active_or_in_doubt_target_operation:{insert_id}:{row[0]}")
        if conn.execute(
            "SELECT COUNT(*) FROM db_recovery_cases WHERE insert_run_id=? AND status IN ('open','manual_intervention')",
            (insert_id,),
        ).fetchone()[0]:
            raise DataSubjectRightsError(f"active_recovery_case:{insert_id}")
        if conn.execute(
            "SELECT COUNT(*) FROM db_reconciliation_runs WHERE insert_run_id=? AND status IN ('planned','running')",
            (insert_id,),
        ).fetchone()[0]:
            raise DataSubjectRightsError(f"active_reconciliation:{insert_id}")


@governed_mutation("privacy.erasure.request")
def create_erasure_request(root: Path | str, entity_uuid: str, *, reason_code: str, requested_by: str,
                           human_confirmed: bool) -> dict[str, Any]:
    """Create one immutable erasure request while retaining only a one-way entity locator."""
    root = Path(root).resolve()
    reason = str(reason_code).strip()
    if not human_confirmed or not requested_by.strip() or not reason:
        raise DataSubjectRightsError("human-confirmed erasure request is required")
    if reason not in ERASURE_REASON_CODES:
        raise DataSubjectRightsError("unsupported_erasure_reason_code")
    entity = _entity(root, entity_uuid)
    locator_hash = _entity_locator_hash(entity_uuid)
    if str(entity["privacy_status"] or "active") == "tombstoned":
        with connect(root) as conn:
            old = conn.execute(
                """SELECT id,request_uuid,request_hash FROM data_subject_erasure_requests
                   WHERE canonical_entity_id=? AND entity_locator_hash=? ORDER BY id DESC LIMIT 1""",
                (int(entity["id"]), locator_hash),
            ).fetchone()
        if old:
            return {"ok": True, "idempotent": True, "request_id": int(old[0]), "request_uuid": old[1],
                    "request_hash": old[2], "already_tombstoned": True, "entity_locator_retained": "one_way_hash_only"}
    request_uuid = str(uuid.uuid4())
    payload = {"request_uuid": request_uuid, "entity_locator_hash": locator_hash, "reason_code": reason,
               "policy_version": ERASURE_POLICY_VERSION}
    request_hash = _hash(payload)
    with connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id,request_uuid,request_hash FROM data_subject_erasure_requests WHERE canonical_entity_id=? ORDER BY id DESC LIMIT 1",
            (int(entity["id"]),),
        ).fetchone()
        if existing:
            conn.commit()
            return {"ok": True, "idempotent": True, "request_id": int(existing[0]), "request_uuid": existing[1],
                    "request_hash": existing[2], "entity_locator_retained": "one_way_hash_only"}
        cur = conn.execute(
            """INSERT INTO data_subject_erasure_requests(
                   request_uuid,canonical_entity_id,entity_uuid,entity_locator_hash,reason_code,request_hash,requested_by,created_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (request_uuid, int(entity["id"]), "locator:" + locator_hash, locator_hash, reason, request_hash,
             requested_by.strip(), utc_now()),
        )
        request_id = int(cur.lastrowid)
        conn.commit()
    _safe_event(root, "data_subject_erasure_requested", request_id=request_id,
                payload={"request_hash": request_hash, "policy_version": ERASURE_POLICY_VERSION})
    return {"ok": True, "request_id": request_id, "request_uuid": request_uuid, "request_hash": request_hash,
            "raw_identifier_included": False, "entity_locator_retained": "one_way_hash_only"}


@governed_mutation("privacy.erasure.plan")
def create_erasure_plan(root: Path | str, request_id: int, *, created_by: str) -> dict[str, Any]:
    """Create one immutable plan containing counts/hashes but no relinkable identifiers or record values."""
    root = Path(root).resolve()
    if not created_by.strip():
        raise DataSubjectRightsError("created_by is required")
    with connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        request = conn.execute("SELECT * FROM data_subject_erasure_requests WHERE id=?", (int(request_id),)).fetchone()
        if not request:
            raise DataSubjectRightsError("erasure_request_not_found")
        existing = conn.execute("SELECT * FROM data_subject_erasure_plans WHERE request_id=?", (int(request_id),)).fetchone()
        if existing:
            conn.commit()
            return _plan_public(existing)
        _assert_no_active_operations(conn, int(request["canonical_entity_id"]))
        affected = _affected_snapshot(conn, root, int(request["canonical_entity_id"]))
        plan_uuid = str(uuid.uuid4())
        plan_core = {
            "plan_uuid": plan_uuid,
            "request_hash": request["request_hash"],
            "policy_version": ERASURE_POLICY_VERSION,
            "counts": affected["counts"],
            "artifact_hashes": affected["artifact_hashes"],
            "external_target_erasure_required": bool(affected["external_target_erasure_required"]),
            "target_mutation_authority": False,
        }
        plan_hash = _hash(plan_core)
        cur = conn.execute(
            """INSERT INTO data_subject_erasure_plans(plan_uuid,request_id,policy_version,plan_hash,affected_counts_json,affected_artifact_hashes_json,external_target_erasure_required,created_by,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (plan_uuid, int(request_id), ERASURE_POLICY_VERSION, plan_hash, _json(affected["counts"]), _json(affected["artifact_hashes"]), int(bool(affected["external_target_erasure_required"])), created_by.strip(), utc_now()),
        )
        plan_id = int(cur.lastrowid)
        conn.commit()
    _safe_event(root, "data_subject_erasure_planned", request_id=int(request_id), plan_id=plan_id,
                payload={"plan_hash": plan_hash, "artifact_count": affected["artifact_count"], "external_target_erasure_required": bool(affected["external_target_erasure_required"])})
    return erasure_plan_get(root, plan_id)


def _plan_public(row: sqlite3.Row) -> dict[str, Any]:
    """Render immutable plan metadata without subject identifiers."""
    return {
        "ok": True, "plan_id": int(row["id"]), "plan_uuid": row["plan_uuid"], "request_id": int(row["request_id"]),
        "policy_version": int(row["policy_version"]), "plan_hash": row["plan_hash"],
        "affected_counts": json.loads(row["affected_counts_json"]),
        "affected_artifact_hashes": json.loads(row["affected_artifact_hashes_json"]),
        "external_target_erasure_required": bool(row["external_target_erasure_required"]),
        "target_update_delete_permitted": False,
    }


def erasure_request_get(root: Path | str, request_id: int) -> dict[str, Any]:
    """Read immutable request metadata without returning an entity reference or locator hash."""
    with connect(Path(root).resolve()) as conn:
        row = conn.execute(
            "SELECT id,request_uuid,reason_code,request_hash,requested_by,created_at FROM data_subject_erasure_requests WHERE id=?",
            (int(request_id),),
        ).fetchone()
    if not row:
        raise DataSubjectRightsError("erasure_request_not_found")
    value = dict(row)
    value.update({"ok": True, "raw_identifier_included": False, "entity_locator_retained": "one_way_hash_only"})
    return value


def erasure_plan_get(root: Path | str, plan_id: int) -> dict[str, Any]:
    """Read one immutable erasure plan and lifecycle decisions."""
    root = Path(root).resolve()
    with connect(root) as conn:
        row = conn.execute("SELECT * FROM data_subject_erasure_plans WHERE id=?", (int(plan_id),)).fetchone()
        if not row:
            raise DataSubjectRightsError("erasure_plan_not_found")
        review = conn.execute("SELECT decision,reviewed_by,reviewed_at,evidence_hash FROM data_subject_erasure_reviews WHERE plan_id=?", (int(plan_id),)).fetchone()
        approval = conn.execute("SELECT approved_by,approved_at,approval_hash FROM data_subject_erasure_approvals WHERE plan_id=?", (int(plan_id),)).fetchone()
        execution = conn.execute("SELECT status,local_erasure_completed,external_target_erasure_required,deleted_counts_json,evidence_hash,executed_by,executed_at,failure_code FROM data_subject_erasure_executions WHERE plan_id=?", (int(plan_id),)).fetchone()
    result = _plan_public(row)
    result["review"] = dict(review) if review else None
    result["approval"] = dict(approval) if approval else None
    if execution:
        e = dict(execution); e["local_erasure_completed"] = bool(e["local_erasure_completed"]); e["external_target_erasure_required"] = bool(e["external_target_erasure_required"]); e["deleted_counts"] = json.loads(e.pop("deleted_counts_json")); result["execution"] = e
    else:
        result["execution"] = None
    return result


@governed_mutation("privacy.erasure.review")
def review_erasure_plan(root: Path | str, plan_id: int, *, reviewed_by: str, human_confirmed: bool,
                        approve_review: bool = True) -> dict[str, Any]:
    """Record one immutable human review decision for an erasure plan."""
    root = Path(root).resolve()
    if not human_confirmed or not reviewed_by.strip():
        raise DataSubjectRightsError("human-confirmed review is required")
    with connect(root) as conn:
        plan = conn.execute("SELECT * FROM data_subject_erasure_plans WHERE id=?", (int(plan_id),)).fetchone()
        if not plan:
            raise DataSubjectRightsError("erasure_plan_not_found")
        request = conn.execute("SELECT canonical_entity_id FROM data_subject_erasure_requests WHERE id=?", (int(plan["request_id"]),)).fetchone()
        _assert_no_active_operations(conn, int(request[0]))
        existing = conn.execute("SELECT * FROM data_subject_erasure_reviews WHERE plan_id=?", (int(plan_id),)).fetchone()
        decision = "reviewed" if approve_review else "rejected"
        if existing:
            if existing["decision"] != decision:
                raise DataSubjectRightsError("immutable_review_already_recorded")
            return erasure_plan_get(root, int(plan_id))
        evidence_hash = _hash({"plan_hash": plan["plan_hash"], "decision": decision, "reviewed_by": reviewed_by.strip()})
        conn.execute("INSERT INTO data_subject_erasure_reviews(plan_id,decision,reviewed_by,reviewed_at,evidence_hash) VALUES(?,?,?,?,?)", (int(plan_id), decision, reviewed_by.strip(), utc_now(), evidence_hash))
    _safe_event(root, "data_subject_erasure_reviewed", plan_id=int(plan_id), payload={"decision": decision, "evidence_hash": evidence_hash})
    return erasure_plan_get(root, int(plan_id))


@governed_mutation("privacy.erasure.approve")
def approve_erasure_plan(root: Path | str, plan_id: int, *, approved_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Record a human approval bound to the exact immutable plan hash."""
    root = Path(root).resolve()
    if not human_confirmed or not approved_by.strip():
        raise DataSubjectRightsError("human-confirmed approval is required")
    with connect(root) as conn:
        plan = conn.execute("SELECT * FROM data_subject_erasure_plans WHERE id=?", (int(plan_id),)).fetchone()
        if not plan:
            raise DataSubjectRightsError("erasure_plan_not_found")
        review = conn.execute("SELECT decision FROM data_subject_erasure_reviews WHERE plan_id=?", (int(plan_id),)).fetchone()
        if not review or review[0] != "reviewed":
            raise DataSubjectRightsError("erasure_plan_requires_positive_human_review")
        request = conn.execute("SELECT canonical_entity_id FROM data_subject_erasure_requests WHERE id=?", (int(plan["request_id"]),)).fetchone()
        _assert_no_active_operations(conn, int(request[0]))
        existing = conn.execute("SELECT * FROM data_subject_erasure_approvals WHERE plan_id=?", (int(plan_id),)).fetchone()
        if existing:
            return erasure_plan_get(root, int(plan_id))
        approval_hash = _hash({"plan_hash": plan["plan_hash"], "approved_by": approved_by.strip(), "decision": "approved"})
        conn.execute("INSERT INTO data_subject_erasure_approvals(plan_id,approved_by,approved_at,approval_hash) VALUES(?,?,?,?)", (int(plan_id), approved_by.strip(), utc_now(), approval_hash))
    _safe_event(root, "data_subject_erasure_approved", plan_id=int(plan_id), payload={"plan_hash": plan["plan_hash"], "approval_hash": approval_hash})
    return erasure_plan_get(root, int(plan_id))


def _resolve_artifact_path(root: Path, raw: str) -> Path | None:
    """Resolve one stored artifact only inside the dedicated data-staging subtree.

    Symlink artifacts or symlinked parent components are rejected so compromised local
    state cannot turn privacy cleanup into arbitrary project-file deletion.
    """
    try:
        staging_root = (root / ".agents/runtime/data-staging").resolve()
        candidate = Path(raw)
        candidate = (root / candidate) if not candidate.is_absolute() else candidate
        lexical = candidate.absolute()
        current = lexical
        while True:
            if current.is_symlink():
                return None
            if current == root or current.parent == current:
                break
            current = current.parent
        resolved = lexical.resolve()
        relative = resolved.relative_to(staging_root)
        if not relative.parts:
            return None
        return resolved
    except (ValueError, OSError):
        return None


def _delete_artifacts(root: Path, paths: Iterable[str]) -> tuple[int, int]:
    """Delete bounded data-staging artifacts plus the dedicated derived cache root."""
    files = 0; directories = 0
    for raw in sorted(set(paths)):
        p = _resolve_artifact_path(root, raw)
        if p is None or not p.exists():
            continue
        if p.is_dir():
            shutil.rmtree(p); directories += 1
        else:
            p.unlink(); files += 1
    cache_root = (root / ".agents/cache").resolve()
    if cache_root.exists() and not cache_root.is_symlink():
        shutil.rmtree(cache_root); directories += 1
    return files, directories


def _purge_local_indexes(conn: sqlite3.Connection, entity_uuid: str, artifact_paths: Iterable[str]) -> dict[str, int]:
    """Remove cache/memory/embedding/index entries that can reference the erased subject or staging paths."""
    counts: dict[str, int] = {}
    patterns = [f"%{entity_uuid}%"]
    for raw in artifact_paths:
        patterns.append(f"%{raw}%")
    before = conn.total_changes
    for pat in patterns:
        conn.execute("DELETE FROM file_read_cache WHERE path LIKE ? OR summary LIKE ?", (pat, pat))
    counts["file_read_cache"] = conn.total_changes - before

    memory_ids: list[str] = []
    for pat in patterns:
        memory_ids.extend(str(r[0]) for r in conn.execute("SELECT id FROM project_memory WHERE statement LIKE ? OR COALESCE(source_path,'') LIKE ?", (pat, pat)))
    before = conn.total_changes
    if memory_ids:
        qs = ",".join("?" for _ in memory_ids)
        conn.execute(f"DELETE FROM knowledge_embeddings WHERE source_kind='memory' AND source_id IN ({qs})", memory_ids)
        conn.execute(f"DELETE FROM project_memory WHERE CAST(id AS TEXT) IN ({qs})", memory_ids)
    for pat in patterns:
        conn.execute("DELETE FROM knowledge_embeddings WHERE text_snapshot LIKE ? OR metadata_json LIKE ?", (pat, pat))
    counts["memory_embeddings"] = conn.total_changes - before

    before = conn.total_changes
    for pat in patterns:
        conn.execute("DELETE FROM symbol_index WHERE path LIKE ? OR qualname LIKE ? OR signature LIKE ?", (pat, pat, pat))
    counts["symbol_index"] = conn.total_changes - before
    return counts


@governed_mutation("privacy.erasure.execute")
def execute_erasure_plan(root: Path | str, plan_id: int, *, executed_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Execute local erasure only; never mutate an external TARGET database."""
    root = Path(root).resolve()
    if not human_confirmed or not executed_by.strip():
        raise DataSubjectRightsError("human-confirmed local erasure execution is required")
    with connect(root) as conn:
        existing = conn.execute("SELECT * FROM data_subject_erasure_executions WHERE plan_id=?", (int(plan_id),)).fetchone()
        if existing:
            return {**erasure_plan_get(root, int(plan_id)), "idempotent": True}
        plan = conn.execute("SELECT * FROM data_subject_erasure_plans WHERE id=?", (int(plan_id),)).fetchone()
        if not plan:
            raise DataSubjectRightsError("erasure_plan_not_found")
        approval = conn.execute("SELECT approval_hash FROM data_subject_erasure_approvals WHERE plan_id=?", (int(plan_id),)).fetchone()
        if not approval:
            raise DataSubjectRightsError("erasure_plan_not_approved")
        request = conn.execute("SELECT * FROM data_subject_erasure_requests WHERE id=?", (int(plan["request_id"]),)).fetchone()
        canonical_entity_id = int(request["canonical_entity_id"])
        _assert_no_active_operations(conn, canonical_entity_id)
        current = _affected_snapshot(conn, root, canonical_entity_id)
        if _json(current["counts"]) != plan["affected_counts_json"] or _json(current["artifact_hashes"]) != plan["affected_artifact_hashes_json"]:
            raise DataSubjectRightsError("erasure_plan_drift_detected_replan_required")
        artifact_paths = _artifact_paths(conn, canonical_entity_id)
        entity_row = conn.execute("SELECT entity_uuid FROM canonical_entities WHERE id=?", (canonical_entity_id,)).fetchone()
        entity_uuid = str(entity_row[0]) if entity_row else ""
        external_required = bool(plan["external_target_erasure_required"])

    # Remove filesystem-derived material before committing local unlinking. A rerun remains safe if a later DB step fails.
    removed_files, removed_dirs = _delete_artifacts(root, artifact_paths)

    with connect(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM data_subject_erasure_executions WHERE plan_id=?", (int(plan_id),)).fetchone()
        if existing:
            conn.commit(); return {**erasure_plan_get(root, int(plan_id)), "idempotent": True}
        _assert_no_active_operations(conn, canonical_entity_id)
        deleted: dict[str, int] = {"artifact_files": removed_files, "artifact_directories": removed_dirs}
        before = conn.total_changes; conn.execute("DELETE FROM identity_candidates WHERE matched_entity_uuid=?", (entity_uuid,)); deleted["identity_candidates"] = conn.total_changes - before
        before = conn.total_changes; conn.execute("DELETE FROM target_record_lineage WHERE canonical_entity_id=?", (canonical_entity_id,)); deleted["target_record_lineage"] = conn.total_changes - before
        before = conn.total_changes; conn.execute("DELETE FROM identity_bindings WHERE canonical_entity_id=?", (canonical_entity_id,)); deleted["identity_bindings"] = conn.total_changes - before
        deleted.update(_purge_local_indexes(conn, entity_uuid, artifact_paths))
        marker = "erased:" + _hash(secrets.token_bytes(32).hex())
        tombstone_uuid = "tombstone:" + uuid.uuid4().hex
        now = utc_now()
        conn.execute(
            """UPDATE canonical_entities
                  SET entity_uuid=?,exact_key_fingerprint=?,key_id=NULL,privacy_status='tombstoned',tombstoned_at=?,erasure_request_hash=?
                WHERE id=?""",
            (tombstone_uuid, marker, now, request["request_hash"], canonical_entity_id),
        )
        tombstone_marker_hash = _hash(marker)
        conn.execute(
            """INSERT INTO privacy_tombstones(canonical_entity_id,tombstone_uuid,request_hash,plan_hash,tombstone_marker_hash,external_target_erasure_required,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (canonical_entity_id, tombstone_uuid, request["request_hash"], plan["plan_hash"], tombstone_marker_hash, int(external_required), now),
        )
        evidence_hash = _hash({"plan_hash": plan["plan_hash"], "deleted_counts": deleted, "local_erasure_completed": True, "external_target_erasure_required": external_required})
        conn.execute(
            """INSERT INTO data_subject_erasure_executions(plan_id,execution_uuid,status,local_erasure_completed,external_target_erasure_required,deleted_counts_json,evidence_hash,executed_by,executed_at)
               VALUES(?,?,'completed',1,?,?,?,?,?)""",
            (int(plan_id), str(uuid.uuid4()), int(external_required), _json(deleted), evidence_hash, executed_by.strip(), now),
        )
        conn.commit()
    _safe_event(root, "data_subject_local_erasure_completed", request_id=int(request["id"]), plan_id=int(plan_id),
                payload={"plan_hash": plan["plan_hash"], "evidence_hash": evidence_hash, "local_erasure_completed": True, "external_target_erasure_required": external_required, "deleted_item_count": sum(deleted.values())})
    return erasure_plan_get(root, int(plan_id))


def erasure_status_get(root: Path | str, entity_uuid: str) -> dict[str, Any]:
    """Return local erasure state, resolving old references only through a one-way locator."""
    root = Path(root).resolve()
    supplied = str(entity_uuid).strip()
    entity = _entity(root, supplied)
    tombstoned = str(entity["privacy_status"] or "active") == "tombstoned"
    with connect(root) as conn:
        tomb = conn.execute(
            "SELECT tombstone_uuid,request_hash,plan_hash,external_target_erasure_required,created_at FROM privacy_tombstones WHERE canonical_entity_id=?",
            (int(entity["id"]),),
        ).fetchone()
        plan = conn.execute(
            """SELECT p.id FROM data_subject_erasure_plans p JOIN data_subject_erasure_requests r ON r.id=p.request_id
               WHERE r.canonical_entity_id=? ORDER BY p.id DESC LIMIT 1""", (int(entity["id"]),)
        ).fetchone()
    result = {
        "ok": True,
        "privacy_status": entity["privacy_status"],
        "tombstoned_at": entity["tombstoned_at"],
        "entity_reference": "one_way_request_locator" if tombstoned and supplied != str(entity["entity_uuid"]) else "canonical_entity_uuid",
        "tombstone": dict(tomb) if tomb else None,
        "plan": erasure_plan_get(root, int(plan[0])) if plan else None,
        "target_mutation_performed": False,
        "raw_identifier_included": False,
    }
    if not tombstoned:
        result["entity_uuid"] = str(entity["entity_uuid"])
    return result

