"""
File: .agents/agentos/risk_tiered_batch_review.py

Purpose:
    Provide deterministic risk-tiered mapping review for primary-project consolidation.

Responsibilities:
    - Classify component mappings without LLM authority.
    - Batch only LOW-risk mappings into immutable plan-hash-pinned review bundles.
    - Bind bundle hashes to the external Ed25519 signed audit chain.
    - Require explicit human confirmation for bundle and individual mapping review.
    - Preserve existing whole-plan human approval and execution gates.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from .db import connect
from .external_audit import append_signed_event
from .project_consolidation import (
    ProjectConsolidationError,
    _assert_primary_authority,
    _current_plan_hash,
    _load_header,
    _mapping_rows,
    _verify_registered_sources,
    utc_now,
)

SCHEMA_VERSION = 48
CLASSIFIER_VERSION = "risk_tiered_mapping_v1"
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_BLOCKED = "BLOCKED"

class RiskTieredBatchReviewError(RuntimeError):
    """Raised when a risk-tiered review invariant is violated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _audit_context() -> tuple[str | None, str | None]:
    """Return governed task/session context when invoked through Unified CLI."""
    return os.environ.get("AGENTOS_TASK_ID"), os.environ.get("AGENTOS_SESSION_ID")


def migration_48(conn: sqlite3.Connection) -> None:
    """Create schema-48 risk-tiered batch-review state."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS consolidation_review_bundles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bundle_id TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            plan_hash TEXT NOT NULL,
            classifier_version TEXT NOT NULL,
            risk_tier TEXT NOT NULL CHECK(risk_tier='LOW'),
            mapping_count INTEGER NOT NULL,
            mapping_ids_json TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            bundle_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'created',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            review_reason TEXT,
            signed_event_hash TEXT NOT NULL,
            signed_key_id TEXT NOT NULL,
            signed_signature TEXT NOT NULL,
            review_event_hash TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id)
        );
        CREATE INDEX IF NOT EXISTS idx_consolidation_review_bundles_plan
            ON consolidation_review_bundles(consolidation_id,plan_hash,status);

        CREATE TABLE IF NOT EXISTS consolidation_mapping_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            mapping_id INTEGER NOT NULL,
            plan_hash TEXT NOT NULL,
            mapping_hash TEXT NOT NULL,
            risk_tier TEXT NOT NULL,
            review_mode TEXT NOT NULL CHECK(review_mode IN ('batch_bundle','individual')),
            bundle_id TEXT,
            reviewed_by TEXT NOT NULL,
            review_reason TEXT NOT NULL,
            human_confirmed INTEGER NOT NULL CHECK(human_confirmed=1),
            external_event_hash TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id),
            FOREIGN KEY(mapping_id) REFERENCES project_component_mappings(id),
            UNIQUE(mapping_id,plan_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_consolidation_mapping_reviews_plan
            ON consolidation_mapping_reviews(consolidation_id,plan_hash,risk_tier);

        CREATE TRIGGER IF NOT EXISTS trg_consolidation_review_bundles_no_delete
        BEFORE DELETE ON consolidation_review_bundles
        BEGIN SELECT RAISE(ABORT, 'signed review bundles are append-only'); END;

        CREATE TRIGGER IF NOT EXISTS trg_consolidation_review_bundles_core_immutable
        BEFORE UPDATE OF bundle_id,consolidation_id,plan_hash,classifier_version,risk_tier,mapping_count,
                         mapping_ids_json,payload_json,bundle_hash,created_by,created_at,
                         signed_event_hash,signed_key_id,signed_signature
        ON consolidation_review_bundles
        BEGIN SELECT RAISE(ABORT, 'signed review bundle core is immutable'); END;

        CREATE TRIGGER IF NOT EXISTS trg_consolidation_review_bundles_status_transition
        BEFORE UPDATE OF status ON consolidation_review_bundles
        WHEN NEW.status != OLD.status AND NOT (OLD.status='created' AND NEW.status='reviewed')
        BEGIN SELECT RAISE(ABORT, 'invalid signed review bundle status transition'); END;

        CREATE TRIGGER IF NOT EXISTS trg_consolidation_mapping_reviews_no_update
        BEFORE UPDATE ON consolidation_mapping_reviews
        BEGIN SELECT RAISE(ABORT, 'mapping review attestations are immutable'); END;

        CREATE TRIGGER IF NOT EXISTS trg_consolidation_mapping_reviews_no_delete
        BEFORE DELETE ON consolidation_mapping_reviews
        BEGIN SELECT RAISE(ABORT, 'mapping review attestations are append-only'); END;
        """
    )


def _mapping_snapshot(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    m = dict(row)
    snapshot = {
        "mapping_id": int(m["id"]),
        "consolidation_id": int(m["consolidation_id"]),
        "source_project_uuid": str(m["source_project_uuid"]),
        "source_path": str(m["source_path"]),
        "source_hash": str(m["source_hash"]),
        "source_size": int(m["source_size"]),
        "target_path": m.get("target_path"),
        "target_expected_hash": m.get("target_expected_hash"),
        "target_expected_absent": bool(m.get("target_expected_absent")),
        "action": str(m["action"]),
        "status": str(m["status"]),
        "rationale_hash": hashlib.sha256(str(m.get("rationale") or "").encode("utf-8")).hexdigest(),
    }
    snapshot["mapping_hash"] = _sha256_json(snapshot)
    return snapshot


def classify_mapping(mapping: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Classify one component mapping deterministically; LLM output is never authority."""
    m = dict(mapping)
    action = str(m.get("action") or "").upper()
    if action == "CONFLICT":
        tier, code = RISK_BLOCKED, "unresolved_conflict"
    elif action == "IGNORE":
        tier, code = RISK_LOW, "no_target_write"
    elif action == "REUSE":
        tier, code = RISK_LOW, "existing_primary_reuse_no_write"
    elif action == "MOVE" and int(m.get("target_expected_absent") or 0) == 1:
        tier, code = RISK_LOW, "exact_copy_to_absent_target"
    elif action == "MOVE":
        tier, code = RISK_MEDIUM, "exact_copy_replaces_existing_target"
    elif action in {"ADAPT", "REIMPLEMENT"}:
        tier, code = RISK_HIGH, "semantic_content_change"
    else:
        tier, code = RISK_BLOCKED, "unsupported_action"
    snap = _mapping_snapshot(m)
    return {
        "mapping_id": snap["mapping_id"],
        "risk_tier": tier,
        "reason_code": code,
        "classifier_version": CLASSIFIER_VERSION,
        "mapping_hash": snap["mapping_hash"],
        "action": action,
    }


def _load_plan(root: Path, consolidation_id: int) -> tuple[dict[str, Any], list[sqlite3.Row], str]:
    with connect(root) as conn:
        migration_48(conn)
        header = _load_header(conn, int(consolidation_id))
        _assert_primary_authority(root, header)
        rows = _mapping_rows(conn, int(consolidation_id))
        plan_hash = _current_plan_hash(conn, int(consolidation_id))
    return dict(header), rows, plan_hash


def assess_consolidation_risk(root: Path | str, consolidation_id: int) -> dict[str, Any]:
    """Return deterministic risk tiers without changing review authority."""
    root = Path(root).resolve()
    header, mappings, plan_hash = _load_plan(root, consolidation_id)
    assessments = [classify_mapping(row) for row in mappings]
    counts = {tier: sum(1 for item in assessments if item["risk_tier"] == tier) for tier in (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_BLOCKED)}
    return {
        "ok": True,
        "consolidation_id": int(consolidation_id),
        "status": header["status"],
        "plan_hash": plan_hash,
        "classifier_version": CLASSIFIER_VERSION,
        "counts": counts,
        "mappings": assessments,
        "batch_eligible_mapping_ids": [item["mapping_id"] for item in assessments if item["risk_tier"] == RISK_LOW],
    }


def _bundle_payload(consolidation_id: int, plan_hash: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": 1,
        "kind": "agentos.low_risk_mapping_review_bundle",
        "classifier_version": CLASSIFIER_VERSION,
        "consolidation_id": int(consolidation_id),
        "plan_hash": plan_hash,
        "risk_tier": RISK_LOW,
        "mapping_count": len(snapshots),
        "mappings": snapshots,
    }


def create_low_risk_bundle(
    root: Path | str,
    consolidation_id: int,
    *,
    created_by: str,
    mapping_ids: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Create and externally sign one immutable LOW-risk mapping bundle."""
    if not str(created_by).strip():
        raise RiskTieredBatchReviewError("created_by is required")
    root = Path(root).resolve()
    header, mappings, plan_hash = _load_plan(root, consolidation_id)
    if str(header["status"]) != "draft":
        raise RiskTieredBatchReviewError("low-risk bundle can only be created for a draft consolidation")
    with connect(root) as conn:
        _verify_registered_sources(conn, int(consolidation_id))
    by_id = {int(row["id"]): row for row in mappings}
    selected = sorted(set(int(x) for x in mapping_ids)) if mapping_ids is not None else sorted(
        mid for mid, row in by_id.items() if classify_mapping(row)["risk_tier"] == RISK_LOW
    )
    if not selected:
        raise RiskTieredBatchReviewError("no LOW-risk mappings selected for bundle")
    missing = [mid for mid in selected if mid not in by_id]
    if missing:
        raise RiskTieredBatchReviewError(f"mapping ids are not part of consolidation: {missing}")
    snapshots: list[dict[str, Any]] = []
    for mid in selected:
        row = by_id[mid]
        assessment = classify_mapping(row)
        if assessment["risk_tier"] != RISK_LOW:
            raise RiskTieredBatchReviewError(f"mapping {mid} is {assessment['risk_tier']}; only LOW may be batched")
        snapshots.append(_mapping_snapshot(row))
    payload = _bundle_payload(int(consolidation_id), plan_hash, snapshots)
    bundle_hash = _sha256_json(payload)
    with connect(root) as conn:
        migration_48(conn)
        existing = conn.execute("SELECT bundle_id FROM consolidation_review_bundles WHERE bundle_hash=?", (bundle_hash,)).fetchone()
    if existing is not None:
        return {**get_batch_bundle(root, str(existing["bundle_id"])), "idempotent": True}
    bundle_id = f"lrb_{uuid.uuid4().hex}"
    signed = append_signed_event(
        root,
        "consolidation.low_risk_review_bundle.created",
        {
            "bundle_id": bundle_id,
            "bundle_hash": bundle_hash,
            "consolidation_id": int(consolidation_id),
            "plan_hash": plan_hash,
            "mapping_ids": selected,
            "mapping_count": len(selected),
            "classifier_version": CLASSIFIER_VERSION,
        },
        *_audit_context(),
    )
    now = utc_now()
    with connect(root, immediate=True) as conn:
        migration_48(conn)
        current = _current_plan_hash(conn, int(consolidation_id))
        if current != plan_hash:
            raise RiskTieredBatchReviewError("plan changed while bundle was being signed; create a new bundle")
        conn.execute(
            """
            INSERT INTO consolidation_review_bundles(
                bundle_id,consolidation_id,plan_hash,classifier_version,risk_tier,mapping_count,
                mapping_ids_json,payload_json,bundle_hash,status,created_by,created_at,
                signed_event_hash,signed_key_id,signed_signature
            ) VALUES(?,?,?,?,?,?,?,?,?,'created',?,?,?,?,?)
            """,
            (
                bundle_id, int(consolidation_id), plan_hash, CLASSIFIER_VERSION, RISK_LOW, len(selected),
                _canonical_json(selected), _canonical_json(payload), bundle_hash, str(created_by).strip(), now,
                signed["event_hash"], signed["key_id"], signed["signature"],
            ),
        )
    return get_batch_bundle(root, bundle_id)


def get_batch_bundle(root: Path | str, bundle_id: str) -> dict[str, Any]:
    root = Path(root).resolve()
    with connect(root) as conn:
        migration_48(conn)
        row = conn.execute("SELECT * FROM consolidation_review_bundles WHERE bundle_id=?", (str(bundle_id),)).fetchone()
    if row is None:
        raise RiskTieredBatchReviewError("review bundle not found")
    value = dict(row)
    value["mapping_ids"] = json.loads(value.pop("mapping_ids_json"))
    value["payload"] = json.loads(value.pop("payload_json"))
    return {"ok": True, "bundle": value}


def _validate_bundle_current(root: Path, bundle: sqlite3.Row) -> tuple[list[dict[str, Any]], str]:
    consolidation_id = int(bundle["consolidation_id"])
    with connect(root) as conn:
        _verify_registered_sources(conn, consolidation_id)
    header, mappings, plan_hash = _load_plan(root, consolidation_id)
    if str(header["status"]) != "draft":
        raise RiskTieredBatchReviewError("bundle review requires a draft consolidation")
    if plan_hash != str(bundle["plan_hash"]):
        raise RiskTieredBatchReviewError("bundle is stale because plan_hash changed")
    ids = [int(x) for x in json.loads(str(bundle["mapping_ids_json"]))]
    by_id = {int(r["id"]): r for r in mappings}
    snapshots: list[dict[str, Any]] = []
    for mid in ids:
        row = by_id.get(mid)
        if row is None:
            raise RiskTieredBatchReviewError(f"bundle mapping disappeared: {mid}")
        assessment = classify_mapping(row)
        if assessment["risk_tier"] != RISK_LOW:
            raise RiskTieredBatchReviewError(f"bundle mapping {mid} is no longer LOW risk")
        snapshots.append(_mapping_snapshot(row))
    payload = _bundle_payload(consolidation_id, plan_hash, snapshots)
    if _sha256_json(payload) != str(bundle["bundle_hash"]):
        raise RiskTieredBatchReviewError("bundle payload no longer matches current mapping snapshots")
    return snapshots, plan_hash


def _finalize_if_complete(root: Path, consolidation_id: int, plan_hash: str) -> dict[str, Any]:
    with connect(root, immediate=True) as conn:
        header = _load_header(conn, consolidation_id)
        current = _current_plan_hash(conn, consolidation_id)
        if current != plan_hash:
            raise RiskTieredBatchReviewError("plan changed during risk review")
        mappings = _mapping_rows(conn, consolidation_id)
        assessments = [classify_mapping(row) for row in mappings]
        if any(item["risk_tier"] == RISK_BLOCKED for item in assessments):
            return {"finalized": False, "reason": "blocked_mapping_present"}
        reviewed = {
            int(row["mapping_id"]): str(row["mapping_hash"])
            for row in conn.execute(
                "SELECT mapping_id,mapping_hash FROM consolidation_mapping_reviews WHERE consolidation_id=? AND plan_hash=?",
                (consolidation_id, plan_hash),
            ).fetchall()
        }
        missing = [item["mapping_id"] for item in assessments if reviewed.get(item["mapping_id"]) != item["mapping_hash"]]
        if missing:
            return {"finalized": False, "reason": "mapping_reviews_incomplete", "missing_mapping_ids": missing}
        if str(header["status"]) == "draft":
            now = utc_now()
            conn.execute(
                "INSERT INTO project_consolidation_reviews(consolidation_id,plan_hash,reviewed_by,reviewed_at,review_reason,status) VALUES(?,?,?,?,?,'reviewed')",
                (consolidation_id, plan_hash, "risk-tiered-review", now, "All mappings reviewed under risk-tiered review v1; LOW mappings may be covered by signed bundles."),
            )
            conn.execute(
                "UPDATE project_consolidations SET status='reviewed',plan_hash=?,updated_at=? WHERE id=?",
                (plan_hash, now, consolidation_id),
            )
        return {"finalized": True, "reason": "all_mapping_reviews_current"}


def review_low_risk_bundle(
    root: Path | str,
    bundle_id: str,
    *,
    reviewed_by: str,
    reason: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Human-review every mapping in one immutable LOW-risk signed bundle."""
    if human_confirmed is not True:
        raise RiskTieredBatchReviewError("batch review requires explicit human confirmation")
    if not str(reviewed_by).strip() or len(str(reason).strip()) < 8:
        raise RiskTieredBatchReviewError("reviewed_by and meaningful review reason are required")
    root = Path(root).resolve()
    with connect(root) as conn:
        migration_48(conn)
        bundle = conn.execute("SELECT * FROM consolidation_review_bundles WHERE bundle_id=?", (str(bundle_id),)).fetchone()
    if bundle is None:
        raise RiskTieredBatchReviewError("review bundle not found")
    if str(bundle["status"]) == "reviewed":
        current = get_risk_review_status(root, int(bundle["consolidation_id"]))
        if str(current["plan_hash"]) != str(bundle["plan_hash"]):
            raise RiskTieredBatchReviewError("reviewed bundle is stale because plan_hash changed")
        return {**get_batch_bundle(root, bundle_id), "idempotent": True, "review_status": current}
    snapshots, plan_hash = _validate_bundle_current(root, bundle)
    reason_hash = hashlib.sha256(str(reason).strip().encode("utf-8")).hexdigest()
    signed = append_signed_event(
        root,
        "consolidation.low_risk_review_bundle.reviewed",
        {
            "bundle_id": str(bundle_id),
            "bundle_hash": str(bundle["bundle_hash"]),
            "consolidation_id": int(bundle["consolidation_id"]),
            "plan_hash": plan_hash,
            "mapping_count": len(snapshots),
            "reviewed_by": str(reviewed_by).strip(),
            "review_reason_hash": reason_hash,
            "human_confirmed": True,
        },
        *_audit_context(),
    )
    now = utc_now()
    with connect(root, immediate=True) as conn:
        current_bundle = conn.execute("SELECT * FROM consolidation_review_bundles WHERE bundle_id=?", (str(bundle_id),)).fetchone()
        if current_bundle is None or str(current_bundle["status"]) != "created":
            raise RiskTieredBatchReviewError("bundle state changed during review")
        if _current_plan_hash(conn, int(bundle["consolidation_id"])) != plan_hash:
            raise RiskTieredBatchReviewError("plan changed during bundle review")
        for snap in snapshots:
            conn.execute(
                """
                INSERT INTO consolidation_mapping_reviews(
                    consolidation_id,mapping_id,plan_hash,mapping_hash,risk_tier,review_mode,bundle_id,
                    reviewed_by,review_reason,human_confirmed,external_event_hash,reviewed_at
                ) VALUES(?,?,?,?,?,'batch_bundle',?,?,?,1,?,?)
                ON CONFLICT(mapping_id,plan_hash) DO NOTHING
                """,
                (
                    int(bundle["consolidation_id"]), int(snap["mapping_id"]), plan_hash, str(snap["mapping_hash"]), RISK_LOW,
                    str(bundle_id), str(reviewed_by).strip(), str(reason).strip(), signed["event_hash"], now,
                ),
            )
        conn.execute(
            "UPDATE consolidation_review_bundles SET status='reviewed',reviewed_by=?,reviewed_at=?,review_reason=?,review_event_hash=? WHERE bundle_id=?",
            (str(reviewed_by).strip(), now, str(reason).strip(), signed["event_hash"], str(bundle_id)),
        )
    final = _finalize_if_complete(root, int(bundle["consolidation_id"]), plan_hash)
    return {**get_batch_bundle(root, bundle_id), "review_event": signed, "plan_review": final, "review_status": get_risk_review_status(root, int(bundle["consolidation_id"]))}


def review_mapping_individual(
    root: Path | str,
    consolidation_id: int,
    mapping_id: int,
    *,
    reviewed_by: str,
    reason: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Human-review one MEDIUM/HIGH mapping; LOW mappings use signed batch bundles."""
    if human_confirmed is not True:
        raise RiskTieredBatchReviewError("individual mapping review requires explicit human confirmation")
    if not str(reviewed_by).strip() or len(str(reason).strip()) < 8:
        raise RiskTieredBatchReviewError("reviewed_by and meaningful review reason are required")
    root = Path(root).resolve()
    with connect(root) as conn:
        _verify_registered_sources(conn, int(consolidation_id))
    header, mappings, plan_hash = _load_plan(root, consolidation_id)
    if str(header["status"]) != "draft":
        raise RiskTieredBatchReviewError("individual mapping review requires a draft consolidation")
    row = next((r for r in mappings if int(r["id"]) == int(mapping_id)), None)
    if row is None:
        raise RiskTieredBatchReviewError("mapping not found")
    assessment = classify_mapping(row)
    if assessment["risk_tier"] == RISK_LOW:
        raise RiskTieredBatchReviewError("LOW-risk mappings must use a signed batch bundle")
    if assessment["risk_tier"] == RISK_BLOCKED:
        raise RiskTieredBatchReviewError("BLOCKED mapping cannot be reviewed; resolve the conflict first")
    snap = _mapping_snapshot(row)
    with connect(root) as conn:
        migration_48(conn)
        existing = conn.execute(
            "SELECT * FROM consolidation_mapping_reviews WHERE mapping_id=? AND plan_hash=?",
            (int(mapping_id), plan_hash),
        ).fetchone()
    if existing is not None:
        if str(existing["mapping_hash"]) != str(snap["mapping_hash"]) or str(existing["risk_tier"]) != str(assessment["risk_tier"]):
            raise RiskTieredBatchReviewError("existing mapping review attestation does not match current mapping snapshot")
        return {"ok": True, "mapping_id": int(mapping_id), "risk": assessment, "idempotent": True, "review_status": get_risk_review_status(root, int(consolidation_id))}
    signed = append_signed_event(
        root,
        "consolidation.mapping_review.individual",
        {
            "consolidation_id": int(consolidation_id),
            "mapping_id": int(mapping_id),
            "plan_hash": plan_hash,
            "mapping_hash": snap["mapping_hash"],
            "risk_tier": assessment["risk_tier"],
            "reviewed_by": str(reviewed_by).strip(),
            "review_reason_hash": hashlib.sha256(str(reason).strip().encode("utf-8")).hexdigest(),
            "human_confirmed": True,
        },
        *_audit_context(),
    )
    now = utc_now()
    with connect(root, immediate=True) as conn:
        if _current_plan_hash(conn, int(consolidation_id)) != plan_hash:
            raise RiskTieredBatchReviewError("plan changed during individual review")
        conn.execute(
            """
            INSERT INTO consolidation_mapping_reviews(
                consolidation_id,mapping_id,plan_hash,mapping_hash,risk_tier,review_mode,bundle_id,
                reviewed_by,review_reason,human_confirmed,external_event_hash,reviewed_at
            ) VALUES(?,?,?,?,?,'individual',NULL,?,?,1,?,?)
            ON CONFLICT(mapping_id,plan_hash) DO NOTHING
            """,
            (
                int(consolidation_id), int(mapping_id), plan_hash, snap["mapping_hash"], assessment["risk_tier"],
                str(reviewed_by).strip(), str(reason).strip(), signed["event_hash"], now,
            ),
        )
    final = _finalize_if_complete(root, int(consolidation_id), plan_hash)
    return {"ok": True, "mapping_id": int(mapping_id), "risk": assessment, "external_event": signed, "plan_review": final, "review_status": get_risk_review_status(root, int(consolidation_id))}


def get_risk_review_status(root: Path | str, consolidation_id: int) -> dict[str, Any]:
    """Return current-plan review coverage; stale reviews never count."""
    root = Path(root).resolve()
    header, mappings, plan_hash = _load_plan(root, consolidation_id)
    assessments = [classify_mapping(row) for row in mappings]
    with connect(root) as conn:
        migration_48(conn)
        reviews = [dict(row) for row in conn.execute(
            "SELECT * FROM consolidation_mapping_reviews WHERE consolidation_id=? AND plan_hash=? ORDER BY mapping_id",
            (int(consolidation_id), plan_hash),
        ).fetchall()]
        bundles = [dict(row) for row in conn.execute(
            "SELECT bundle_id,bundle_hash,risk_tier,mapping_count,status,created_by,created_at,reviewed_by,reviewed_at,signed_event_hash,review_event_hash FROM consolidation_review_bundles WHERE consolidation_id=? AND plan_hash=? ORDER BY id",
            (int(consolidation_id), plan_hash),
        ).fetchall()]
    reviewed = {int(row["mapping_id"]): row for row in reviews}
    missing = [item["mapping_id"] for item in assessments if reviewed.get(item["mapping_id"], {}).get("mapping_hash") != item["mapping_hash"]]
    counts = {tier: sum(1 for item in assessments if item["risk_tier"] == tier) for tier in (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_BLOCKED)}
    return {
        "ok": True,
        "consolidation_id": int(consolidation_id),
        "consolidation_status": header["status"],
        "plan_hash": plan_hash,
        "classifier_version": CLASSIFIER_VERSION,
        "risk_counts": counts,
        "mapping_count": len(assessments),
        "reviewed_mapping_count": len(assessments) - len(missing),
        "missing_mapping_ids": missing,
        "ready_for_plan_approval": not missing and counts[RISK_BLOCKED] == 0 and str(header["status"]) == "reviewed",
        "assessments": assessments,
        "reviews": reviews,
        "bundles": bundles,
    }
