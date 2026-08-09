"""
File: .agents/agentos/context_evaluation.py

Purpose:
    Provide bounded context expansion telemetry and deterministic compression
    evaluation for AgentOS v0.23.2.

Responsibilities:
    - Persist expansion metadata without storing expanded source content.
    - Evaluate canonical-to-transport accountability, requirement preservation,
      integrity, budget compliance, and compression stability.
    - Compare transport revisions in shadow mode without granting LLM mutation authority.
    - Preserve the v0.23.0 metric contract while adding explicit hard gates and warnings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .context_transport import ContextTransportError, context_transport_get
from .db import connect
from .policy import load_policy

MIGRATION_VERSION = 46
EVALUATION_VERSION = 2


class ContextEvaluationError(RuntimeError):
    """Raised when expansion/evaluation state cannot be inspected safely."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def migration_46(c: Any) -> None:
    """Create v0.23.2 expansion telemetry and compression-evaluation state.

    Args:
        c: Open SQLite connection receiving migration 46.

    Returns:
        None.
    """
    from .data_subject_rights import harden_privacy_schema
    harden_privacy_schema(c)
    c.executescript(
        """
        CREATE TABLE context_expansion_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            transport_hash TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            requirement_ids_json TEXT NOT NULL,
            requested_handle_count INTEGER NOT NULL,
            expanded_handle_count INTEGER NOT NULL,
            failed_handle_count INTEGER NOT NULL,
            returned_tokens INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX idx_context_expansion_session_task
            ON context_expansion_sessions(task_id,transport_pack_id,created_at);

        ALTER TABLE context_expansion_events ADD COLUMN session_id INTEGER;
        ALTER TABLE context_expansion_events ADD COLUMN request_hash TEXT;
        ALTER TABLE context_expansion_events ADD COLUMN line_start INTEGER;
        ALTER TABLE context_expansion_events ADD COLUMN line_end INTEGER;
        ALTER TABLE context_expansion_events ADD COLUMN returned_tokens INTEGER;
        ALTER TABLE context_expansion_events ADD COLUMN reason_code TEXT;
        ALTER TABLE context_expansion_events ADD COLUMN requirement_ids_json TEXT;
        ALTER TABLE context_expansion_events ADD COLUMN transport_hash TEXT;

        CREATE TABLE context_compression_evaluation_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            transport_hash TEXT NOT NULL,
            evaluation_version INTEGER NOT NULL,
            evaluation_hash TEXT NOT NULL,
            gate_status TEXT NOT NULL,
            hard_failures_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            canonical_candidate_count INTEGER NOT NULL,
            included_candidate_count INTEGER NOT NULL,
            expandable_candidate_count INTEGER NOT NULL,
            accounted_candidate_count INTEGER NOT NULL,
            unaccounted_candidate_count INTEGER NOT NULL,
            handle_integrity_rate REAL NOT NULL,
            raw_tokens INTEGER NOT NULL,
            transport_tokens INTEGER NOT NULL,
            compression_ratio REAL NOT NULL,
            requirement_preservation_rate REAL NOT NULL,
            context_miss_count INTEGER NOT NULL,
            expansion_request_count INTEGER NOT NULL,
            expansion_success_count INTEGER NOT NULL,
            expansion_failure_count INTEGER NOT NULL,
            budget_utilization REAL NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(transport_pack_id,evaluation_hash)
        );
        CREATE INDEX idx_context_compression_eval_task
            ON context_compression_evaluation_runs(task_id,created_at);

        CREATE TABLE context_compression_comparisons(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            baseline_pack_id INTEGER NOT NULL,
            candidate_pack_id INTEGER NOT NULL,
            comparison_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            regression_flags_json TEXT NOT NULL,
            comparison_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            FOREIGN KEY(baseline_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(candidate_pack_id) REFERENCES context_transport_packs(id)
        );
        CREATE INDEX idx_context_compression_compare_task
            ON context_compression_comparisons(task_id,created_at);
        """
    )


def _cfg(root: Path) -> dict[str, Any]:
    policy = load_policy(root)
    value = policy.get("context_expansion_evaluation_policy", {})
    return value if isinstance(value, dict) else {}


def _task_outcome_metrics(root: Path, task_id: str) -> tuple[float | None, float | None, int | None]:
    with connect(root) as c:
        row = c.execute(
            "SELECT outcome,test_pass_rate,rework_count FROM task_outcomes WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    if not row:
        return None, None, None
    outcome = str(row["outcome"] or "").lower()
    success = 1.0 if outcome in {"success", "passed", "complete", "completed"} else 0.0 if outcome else None
    return success, row["test_pass_rate"], row["rework_count"]


def _expansion_counts(root: Path, pack_id: int) -> tuple[int, int, int]:
    with connect(root) as c:
        success = int(c.execute(
            "SELECT COUNT(*) AS n FROM context_expansion_events WHERE transport_pack_id=? AND outcome='expanded'",
            (pack_id,),
        ).fetchone()["n"])
        session = c.execute(
            """
            SELECT COALESCE(SUM(failed_handle_count),0) AS failed,
                   COALESCE(SUM(requested_handle_count),0) AS requested
              FROM context_expansion_sessions WHERE transport_pack_id=?
            """,
            (pack_id,),
        ).fetchone()
    failed = int(session["failed"] or 0)
    requested = max(success + failed, int(session["requested"] or 0))
    return requested, success, failed


def _candidate_accounting(manifest: dict[str, Any]) -> dict[str, Any]:
    evidence = manifest.get("evidence_plane", {})
    included = list(evidence.get("included", []))
    omitted = list(evidence.get("omitted", []))
    handles = list(evidence.get("expansion_index", []))
    candidate_count = int(evidence.get("candidate_count", 0) or 0)
    included_ids = {str(item.get("candidate_id")) for item in included if item.get("candidate_id")}
    handle_by_id = {str(item.get("handle_id")): item for item in handles if item.get("handle_id")}
    expandable_ids = {str(item.get("candidate_id")) for item in handles if item.get("candidate_id")}
    omitted_ids = {str(item.get("candidate_id")) for item in omitted if item.get("candidate_id")}
    accounted = included_ids | expandable_ids
    unaccounted_count = max(0, candidate_count - len(accounted))

    valid_handles = 0
    broken_handles: list[str] = []
    for item in omitted:
        handle_id = str(item.get("handle_id") or "")
        handle = handle_by_id.get(handle_id)
        valid = bool(
            handle
            and handle.get("candidate_id") == item.get("candidate_id")
            and handle.get("source_hash")
            and handle.get("canonical_revision") == manifest.get("context_revision")
            and handle.get("expandable") is True
        )
        if valid:
            valid_handles += 1
        else:
            broken_handles.append(handle_id or str(item.get("candidate_id") or "unknown"))
    handle_integrity_rate = (valid_handles / len(omitted)) if omitted else 1.0
    return {
        "canonical_candidate_count": candidate_count,
        "included_candidate_count": len(included_ids),
        "omitted_candidate_count": len(omitted_ids),
        "expandable_candidate_count": len(expandable_ids),
        "accounted_candidate_count": len(accounted),
        "unaccounted_candidate_count": unaccounted_count,
        "handle_integrity_rate": handle_integrity_rate,
        "broken_handles": broken_handles,
    }


def evaluate_compression(
    root: Path,
    task_id: str,
    revision: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Evaluate one READY transport against deterministic v0.23.2 safety gates."""
    root = root.resolve()
    try:
        pack = context_transport_get(root, task_id, revision, allow_historical=revision is not None)
    except ContextTransportError as exc:
        raise ContextEvaluationError(str(exc)) from exc
    manifest = pack["manifest"]
    metrics = dict(manifest.get("metrics", {}))
    accounting = _candidate_accounting(manifest)
    requested, expansion_success, expansion_failure = _expansion_counts(root, int(pack["pack_id"]))
    with connect(root) as c:
        tool_call_count = int(c.execute(
            "SELECT COUNT(*) AS n FROM tool_calls WHERE task_id=?",
            (task_id,),
        ).fetchone()["n"])
    task_success, test_pass, rework = _task_outcome_metrics(root, task_id)
    budget = manifest.get("budget", {})
    input_budget = max(1, int(budget.get("input_budget", metrics.get("transport_tokens", 0)) or 1))
    transport_tokens = int(metrics.get("transport_tokens", 0) or 0)
    ratio = float(metrics.get("compression_ratio", 0.0) or 0.0)
    preservation = float(metrics.get("requirement_preservation_rate", 0.0) or 0.0)
    budget_utilization = transport_tokens / input_budget

    hard_failures: list[str] = []
    warnings: list[str] = []
    if pack.get("stale"):
        hard_failures.append("transport_pack_stale")
    if abs(preservation - 1.0) > 1e-12:
        hard_failures.append("requirement_preservation_below_100_percent")
    if accounting["unaccounted_candidate_count"]:
        hard_failures.append("canonical_candidates_unaccounted")
    if abs(float(accounting["handle_integrity_rate"]) - 1.0) > 1e-12:
        hard_failures.append("expansion_handle_integrity_failed")
    if budget_utilization > 1.0 + 1e-12:
        hard_failures.append("transport_exceeds_input_budget")
    gate = manifest.get("preservation_gate", {})
    if not bool(gate.get("transport_integrity")):
        hard_failures.append("transport_integrity_not_verified")
    if not bool(gate.get("source_freshness")):
        hard_failures.append("source_freshness_not_verified")
    cfg = _cfg(root)
    target_min = float(cfg.get("compression_target_min", 2.0) or 2.0)
    target_max = float(cfg.get("compression_target_max", 4.0) or 4.0)
    if ratio < target_min:
        warnings.append("compression_below_initial_target")
    if ratio > target_max:
        warnings.append("compression_above_stability_target_review_required")
    if not bool(budget.get("evidence_floor_satisfied", True)):
        warnings.append("evidence_floor_not_satisfied")
    if expansion_failure:
        warnings.append("expansion_failures_observed")

    status = "FAIL" if hard_failures else "WARN" if warnings else "PASS"
    result: dict[str, Any] = {
        "evaluation_version": EVALUATION_VERSION,
        "gate_status": status,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "raw_tokens": int(metrics.get("raw_tokens", 0) or 0),
        "transport_tokens": transport_tokens,
        "compression_ratio": ratio,
        "protected_requirement_count": int(metrics.get("protected_requirement_count", 0) or 0),
        "preserved_requirement_count": int(metrics.get("preserved_requirement_count", 0) or 0),
        "requirement_preservation_rate": preservation,
        "context_miss_count": int(accounting["unaccounted_candidate_count"]),
        "expansion_request_count": requested,
        "expansion_success_count": expansion_success,
        "expansion_failure_count": expansion_failure,
        "task_success_rate": task_success,
        "test_pass_rate": test_pass,
        "rework_count": rework,
        "tool_call_count": tool_call_count,
        "budget_utilization": budget_utilization,
        "budget_mode": str(budget.get("mode", "fixed")),
        "model_profile": manifest.get("model_profile"),
        "model_profile_hash": manifest.get("model_profile_hash"),
        "transport_hash": manifest.get("transport_hash"),
        **accounting,
    }
    eval_hash = _sha256_text(_canonical_json(result))
    result["evaluation_hash"] = eval_hash
    evaluation_id: int | None = None
    if persist:
        with connect(root, immediate=True) as c:
            c.execute(
                """
                INSERT OR IGNORE INTO context_compression_evaluation_runs(
                    transport_pack_id,task_id,transport_hash,evaluation_version,evaluation_hash,gate_status,
                    hard_failures_json,warnings_json,canonical_candidate_count,included_candidate_count,
                    expandable_candidate_count,accounted_candidate_count,unaccounted_candidate_count,
                    handle_integrity_rate,raw_tokens,transport_tokens,compression_ratio,requirement_preservation_rate,
                    context_miss_count,expansion_request_count,expansion_success_count,expansion_failure_count,
                    budget_utilization,metrics_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    pack["pack_id"], task_id, str(manifest.get("transport_hash") or ""), EVALUATION_VERSION,
                    eval_hash, status, _canonical_json(hard_failures), _canonical_json(warnings),
                    accounting["canonical_candidate_count"], accounting["included_candidate_count"],
                    accounting["expandable_candidate_count"], accounting["accounted_candidate_count"],
                    accounting["unaccounted_candidate_count"], accounting["handle_integrity_rate"],
                    result["raw_tokens"], result["transport_tokens"], result["compression_ratio"], preservation,
                    result["context_miss_count"], requested, expansion_success, expansion_failure,
                    budget_utilization, _canonical_json(result),
                ),
            )
            row = c.execute(
                "SELECT id FROM context_compression_evaluation_runs WHERE transport_pack_id=? AND evaluation_hash=?",
                (pack["pack_id"], eval_hash),
            ).fetchone()
            evaluation_id = int(row["id"]) if row else None
    return {
        "ok": status != "FAIL",
        "task_id": task_id,
        "transport_revision": pack["transport_revision"],
        "evaluation_id": evaluation_id,
        **result,
    }


def compression_evaluation_get(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Read the latest persisted evaluation, or compute a non-persisting current view."""
    root = root.resolve()
    pack = context_transport_get(root, task_id, revision, allow_historical=revision is not None)
    with connect(root) as c:
        row = c.execute(
            """
            SELECT id,metrics_json,gate_status,created_at FROM context_compression_evaluation_runs
             WHERE transport_pack_id=? ORDER BY id DESC LIMIT 1
            """,
            (pack["pack_id"],),
        ).fetchone()
    if not row:
        value = evaluate_compression(root, task_id, revision, persist=False)
        value["persisted"] = False
        return value
    metrics = json.loads(str(row["metrics_json"]))
    return {
        "ok": str(row["gate_status"]) != "FAIL" and not bool(pack.get("stale")),
        "stale": bool(pack.get("stale")),
        "stale_reasons": list(pack.get("stale_reasons", [])),
        "task_id": task_id,
        "transport_revision": pack["transport_revision"],
        "evaluation_id": int(row["id"]),
        "persisted": True,
        "created_at": row["created_at"],
        **metrics,
    }


def compression_evaluation_history_get(root: Path, task_id: str, limit: int = 20) -> dict[str, Any]:
    """Read bounded evaluation history without source or expanded content."""
    bounded = min(100, max(1, int(limit)))
    with connect(root.resolve()) as c:
        rows = [dict(row) for row in c.execute(
            """
            SELECT id,transport_pack_id,transport_hash,evaluation_version,evaluation_hash,gate_status,
                   compression_ratio,requirement_preservation_rate,context_miss_count,expansion_request_count,
                   expansion_success_count,expansion_failure_count,budget_utilization,created_at
              FROM context_compression_evaluation_runs
             WHERE task_id=? ORDER BY id DESC LIMIT ?
            """,
            (task_id, bounded),
        ).fetchall()]
    return {"ok": True, "task_id": task_id, "evaluations": rows, "count": len(rows)}


def expansion_history_get(root: Path, task_id: str, revision: int | None = None, limit: int = 50) -> dict[str, Any]:
    """Read expansion metadata only; excerpts are never persisted or returned here."""
    root = root.resolve()
    pack = context_transport_get(root, task_id, revision)
    bounded = min(200, max(1, int(limit)))
    with connect(root) as c:
        sessions = [dict(row) for row in c.execute(
            """
            SELECT id,request_hash,reason_code,requirement_ids_json,requested_handle_count,
                   expanded_handle_count,failed_handle_count,returned_tokens,status,created_at
              FROM context_expansion_sessions WHERE transport_pack_id=? ORDER BY id DESC LIMIT ?
            """,
            (pack["pack_id"], bounded),
        ).fetchall()]
        events = [dict(row) for row in c.execute(
            """
            SELECT id,session_id,handle_id,outcome,source_hash,request_hash,line_start,line_end,
                   returned_tokens,reason_code,requirement_ids_json,transport_hash,created_at
              FROM context_expansion_events WHERE transport_pack_id=? ORDER BY id DESC LIMIT ?
            """,
            (pack["pack_id"], bounded),
        ).fetchall()]
    return {
        "ok": True,
        "task_id": task_id,
        "transport_revision": pack["transport_revision"],
        "sessions": sessions,
        "events": events,
        "content_persisted": False,
    }


def compare_compression(
    root: Path,
    task_id: str,
    baseline_revision: int,
    candidate_revision: int,
    persist: bool = False,
) -> dict[str, Any]:
    """Compare two transport revisions using deterministic regression rules."""
    if int(baseline_revision) == int(candidate_revision):
        raise ContextEvaluationError("comparison_requires_distinct_revisions")
    baseline = evaluate_compression(root, task_id, int(baseline_revision), persist=False)
    candidate = evaluate_compression(root, task_id, int(candidate_revision), persist=False)
    flags: list[str] = []
    if candidate["requirement_preservation_rate"] < baseline["requirement_preservation_rate"]:
        flags.append("requirement_preservation_regressed")
    if candidate["context_miss_count"] > baseline["context_miss_count"]:
        flags.append("context_miss_count_increased")
    if candidate["expansion_failure_count"] > baseline["expansion_failure_count"]:
        flags.append("expansion_failures_increased")
    if candidate["budget_utilization"] > 1.0 + 1e-12:
        flags.append("candidate_budget_exceeded")
    if candidate["gate_status"] == "FAIL":
        flags.append("candidate_hard_gate_failed")
    for key in ("task_success_rate", "test_pass_rate"):
        left, right = baseline.get(key), candidate.get(key)
        if left is not None and right is not None and float(right) < float(left):
            flags.append(f"{key}_regressed")
    if baseline.get("rework_count") is not None and candidate.get("rework_count") is not None:
        if int(candidate["rework_count"]) > int(baseline["rework_count"]):
            flags.append("rework_count_increased")
    status = "REGRESSION" if flags else "NO_REGRESSION"
    result = {
        "task_id": task_id,
        "baseline_revision": int(baseline_revision),
        "candidate_revision": int(candidate_revision),
        "status": status,
        "regression_flags": flags,
        "deltas": {
            "compression_ratio": candidate["compression_ratio"] - baseline["compression_ratio"],
            "context_miss_count": candidate["context_miss_count"] - baseline["context_miss_count"],
            "expansion_request_count": candidate["expansion_request_count"] - baseline["expansion_request_count"],
            "budget_utilization": candidate["budget_utilization"] - baseline["budget_utilization"],
        },
        "baseline": baseline,
        "candidate": candidate,
    }
    compare_hash = _sha256_text(_canonical_json(result))
    result["comparison_hash"] = compare_hash
    comparison_id: int | None = None
    if persist:
        base_pack = context_transport_get(root, task_id, baseline_revision, allow_historical=True)
        cand_pack = context_transport_get(root, task_id, candidate_revision, allow_historical=True)
        with connect(root, immediate=True) as c:
            c.execute(
                """
                INSERT OR IGNORE INTO context_compression_comparisons(
                    task_id,baseline_pack_id,candidate_pack_id,comparison_hash,status,regression_flags_json,comparison_json
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    task_id, base_pack["pack_id"], cand_pack["pack_id"], compare_hash, status,
                    _canonical_json(flags), _canonical_json(result),
                ),
            )
            row = c.execute(
                "SELECT id FROM context_compression_comparisons WHERE comparison_hash=?",
                (compare_hash,),
            ).fetchone()
            comparison_id = int(row["id"]) if row else None
    return {"ok": not flags, "comparison_id": comparison_id, **result}


def sync_schema(root: Path) -> dict[str, Any]:
    """Apply migrations through schema 46 using the central db.connect() path."""
    with connect(root.resolve()) as c:
        version = int(c.execute("SELECT COALESCE(MAX(version),0) AS v FROM schema_migrations").fetchone()["v"])
        foreign_keys = int(c.execute("PRAGMA foreign_keys").fetchone()[0])
    return {"ok": version == MIGRATION_VERSION and foreign_keys == 1, "schema": version, "foreign_keys": foreign_keys}
