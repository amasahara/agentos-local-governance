"""
File: .agents/agentos/memory_promotion.py

Purpose:
    Promote repeated verified project findings into existing project-memory
    candidates without creating a parallel lesson or feedback subsystem.

Responsibilities:
    - Require occurrence, distinct verified-task, freshness, architecture, and cooldown gates.
    - Reuse project_memory status='candidate' as the non-active promotion state.
    - Link candidates to existing learning signals without copying raw signal content.
    - Require an existing explicit Human Decision before activation or rejection.
    - Keep candidate flagging degraded-safe while activation remains fail-closed.
    - Preserve Context Authority: promoted memory remains project evidence, not instruction authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .db import connect, connect_read_only
from .human_decision import request_human_decision
from .learning_signals import link_learning_signal, revalidate_learning_signal
from .memory import remember_candidate
from .policy import load_policy

MEMORY_PROMOTION_VERSION = 1
_SHA256 = set("0123456789abcdef")


class MemoryPromotionError(RuntimeError):
    """Raised when a governed memory-promotion invariant is not satisfied."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_sha(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and set(text) <= _SHA256


def _policy(root: Path) -> dict[str, Any]:
    section = load_policy(root).get("governed_learning_policy")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        raise MemoryPromotionError("governed_learning_policy_required")
    promotion = section.get("promotion")
    if not isinstance(promotion, dict):
        raise MemoryPromotionError("learning_promotion_policy_required")
    for key in (
        "automatic_memory_candidate_flagging",
        "distinct_completed_tasks_required",
        "source_signal_revalidation_required",
        "architecture_baseline_revalidation_required",
        "human_decision_required_for_memory_activation",
    ):
        if promotion.get(key) is not True:
            raise MemoryPromotionError("memory_promotion_required_invariant_disabled:" + key)
    for key in (
        "automatic_memory_activation",
        "automatic_memory_authority_promotion",
        "automatic_skill_graduation",
        "automatic_policy_activation",
        "automatic_architecture_mutation",
    ):
        if promotion.get(key) is not False:
            raise MemoryPromotionError("memory_promotion_authority_invariant_violated:" + key)
    for key in ("minimum_occurrences", "minimum_distinct_tasks", "window_days", "promotion_cooldown_days"):
        if int(promotion.get(key, 0)) <= 0:
            raise MemoryPromotionError("invalid_learning_promotion_threshold:" + key)
    if promotion.get("candidate_status") != "candidate":
        raise MemoryPromotionError("memory_candidate_status_invalid")
    if promotion.get("active_status") != "active":
        raise MemoryPromotionError("memory_active_status_invalid")
    if promotion.get("rejected_status") != "rejected":
        raise MemoryPromotionError("memory_rejected_status_invalid")
    return promotion


def _active_architecture_hash(c: Any) -> str | None:
    row = c.execute(
        "SELECT baseline_hash FROM architecture_baselines WHERE status='active' ORDER BY activated_at DESC,rowid DESC LIMIT 1"
    ).fetchone()
    value = str(row["baseline_hash"] or "") if row else ""
    return value if _valid_sha(value) else None


def _finding(c: Any, finding_id: int | str) -> dict[str, Any]:
    row = c.execute("SELECT * FROM project_findings WHERE id=?", (str(finding_id),)).fetchone()
    if not row:
        raise MemoryPromotionError("project_finding_missing")
    value = dict(row)
    if str(value.get("status") or "") != "active":
        raise MemoryPromotionError("project_finding_not_active")
    return value


def _candidate_hash(memory: dict[str, Any]) -> str:
    return _sha({
        "memory_promotion_version": MEMORY_PROMOTION_VERSION,
        "memory_id": int(memory["id"]),
        "kind": memory["kind"],
        "statement": memory["statement"],
        "source_hash": memory["source_hash"],
        "evidence_hash": memory["evidence_hash"],
        "owner_scope": memory["owner_scope"],
    })


def _decision_question(memory_id: int, finding_id: int | str, evidence_hash: str) -> str:
    return (
        "Approve activation of governed project memory candidate "
        f"{int(memory_id)} derived from recurring finding {finding_id} "
        f"with evidence hash {evidence_hash}?"
    )


def _linked_memories(c: Any, finding_id: int | str) -> list[dict[str, Any]]:
    rows = c.execute(
        """
        SELECT pm.id AS memory_id,pm.status AS memory_status,pm.evidence_hash,
               pm.source_hash,MAX(lsl.created_at) AS latest_link_at
        FROM learning_signals ls
        JOIN learning_signal_links lsl
          ON lsl.signal_id=ls.signal_id
         AND lsl.relation_type='memory_candidate'
         AND lsl.target_type='project_memory'
        JOIN project_memory pm ON CAST(pm.id AS TEXT)=lsl.target_id
        WHERE ls.source_type='project_finding' AND ls.source_id=?
        GROUP BY pm.id,pm.status,pm.evidence_hash,pm.source_hash
        ORDER BY pm.id DESC
        """,
        (str(finding_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def evaluate_memory_promotion(
    root: Path,
    finding_id: int | str,
    *,
    persist_signal_eligibility: bool = False,
) -> dict[str, Any]:
    """Evaluate one recurring finding against governed v0.31.1 promotion gates."""
    promotion = _policy(root)
    minimum_occurrences = int(promotion["minimum_occurrences"])
    minimum_distinct_tasks = int(promotion["minimum_distinct_tasks"])
    window_days = int(promotion["window_days"])
    cooldown_days = int(promotion["promotion_cooldown_days"])

    with connect_read_only(root) as c:
        finding = _finding(c, finding_id)
        architecture_hash = _active_architecture_hash(c)
        signals = c.execute(
            """
            SELECT signal_id
            FROM learning_signals
            WHERE source_type='project_finding' AND source_id=?
              AND created_at >= datetime('now', ?)
            ORDER BY created_at,signal_sequence_number
            """,
            (str(finding_id), f"-{window_days} days"),
        ).fetchall()
        linked = _linked_memories(c, finding_id)

    reports = []
    for row in signals:
        report = dict(revalidate_learning_signal(
            root,
            str(row["signal_id"]),
            persist_eligibility=persist_signal_eligibility,
        ))
        report["architecture_match"] = bool(
            architecture_hash
            and str(report.get("architecture_baseline_hash") or "") == architecture_hash
        )
        reports.append(report)

    valid = [
        report for report in reports
        if report["source_current"]
        and report["cross_task_eligible"]
        and report["architecture_match"]
    ]
    tasks = sorted({str(report["task_id"]) for report in valid})
    source_hashes = sorted({str(report["source_hash"]) for report in valid})
    stable_source_hash = source_hashes[0] if len(source_hashes) == 1 else None

    existing = next(
        (row for row in linked if str(row["memory_status"]) in {"candidate", "active"}),
        None,
    )
    cooldown_active = False
    if not existing:
        previous = next((row for row in linked if str(row["memory_status"]) in {"rejected", "stale"}), None)
        if previous and previous.get("latest_link_at"):
            with connect_read_only(root) as c:
                check = c.execute(
                    "SELECT CASE WHEN datetime(?) >= datetime('now', ?) THEN 1 ELSE 0 END AS active",
                    (str(previous["latest_link_at"]), f"-{cooldown_days} days"),
                ).fetchone()
                cooldown_active = bool(check and int(check["active"] or 0))

    reasons = []
    if int(finding["occurrences"]) < minimum_occurrences:
        reasons.append("occurrence_threshold_not_met")
    if len(tasks) < minimum_distinct_tasks:
        reasons.append("distinct_verified_task_threshold_not_met")
    if not architecture_hash:
        reasons.append("active_architecture_baseline_required")
    if not reports:
        reasons.append("finding_learning_signals_missing")
    elif not valid:
        reasons.append("no_current_architecture_matched_verified_signal")
    if stable_source_hash is None:
        reasons.append("stable_current_source_hash_required")
    if cooldown_active:
        reasons.append("promotion_cooldown_active")

    evidence_hash = None
    if stable_source_hash and architecture_hash and valid:
        evidence_hash = _sha({
            "memory_promotion_version": MEMORY_PROMOTION_VERSION,
            "finding_id": int(finding["id"]),
            "finding_key": finding["finding_key"],
            "finding_source_hash": stable_source_hash,
            "architecture_baseline_hash": architecture_hash,
            "signal_ids": sorted(str(item["signal_id"]) for item in valid),
            "distinct_task_ids": tasks,
            "minimum_occurrences": minimum_occurrences,
            "minimum_distinct_tasks": minimum_distinct_tasks,
            "window_days": window_days,
        })

    return {
        "ok": True,
        "finding_id": int(finding["id"]),
        "finding_key": finding["finding_key"],
        "occurrences": int(finding["occurrences"]),
        "minimum_occurrences": minimum_occurrences,
        "distinct_verified_task_count": len(tasks),
        "minimum_distinct_tasks": minimum_distinct_tasks,
        "distinct_task_ids": tasks,
        "window_days": window_days,
        "promotion_cooldown_days": cooldown_days,
        "current_architecture_baseline_hash": architecture_hash,
        "valid_signal_count": len(valid),
        "valid_signals": valid,
        "source_hash": stable_source_hash,
        "evidence_hash": evidence_hash,
        "existing_candidate": existing,
        "cooldown_active": cooldown_active,
        "eligible": bool(not reasons and existing is None),
        "reasons": reasons,
        "trust_class": "project_evidence",
        "authority_class": "none",
        "instruction_authority": False,
    }


def _request_decision(
    root: Path,
    *,
    memory_id: int,
    finding_id: int,
    evidence_hash: str,
    task_id: str,
    raised_by_session: str | None,
) -> dict[str, Any]:
    return request_human_decision(
        root,
        task_id,
        "post_execution",
        "other",
        "normal",
        _decision_question(memory_id, finding_id, evidence_hash),
        options=["approve", "reject"],
        raised_by_session=raised_by_session,
        blocking=False,
    )


def create_memory_promotion_candidate(
    root: Path,
    finding_id: int | str,
    *,
    raised_by_session: str | None = None,
    open_human_decision: bool = True,
) -> dict[str, Any]:
    """Create or reuse a non-active project_memory candidate; never activate it."""
    evaluation = evaluate_memory_promotion(root, finding_id, persist_signal_eligibility=True)
    existing = evaluation.get("existing_candidate")
    if existing:
        result = {
            "ok": True,
            "created": False,
            "existing": True,
            "memory_id": int(existing["memory_id"]),
            "status": str(existing["memory_status"]),
            "evaluation": evaluation,
        }
        if open_human_decision and result["status"] == "candidate":
            evidence = str(existing.get("evidence_hash") or evaluation.get("evidence_hash") or "")
            if not _valid_sha(evidence):
                raise MemoryPromotionError("memory_candidate_evidence_hash_invalid")
            result["human_decision"] = _request_decision(
                root,
                memory_id=result["memory_id"],
                finding_id=int(finding_id),
                evidence_hash=evidence,
                task_id=str(evaluation["distinct_task_ids"][-1]),
                raised_by_session=raised_by_session,
            )
        return result

    if not evaluation["eligible"]:
        return {
            "ok": True,
            "created": False,
            "existing": False,
            "memory_id": None,
            "status": "not_eligible",
            "evaluation": evaluation,
        }

    with connect_read_only(root) as c:
        finding = _finding(c, finding_id)

    tasks = list(evaluation["distinct_task_ids"])
    memory = remember_candidate(
        root,
        str(_policy(root).get("candidate_memory_kind", "procedural")),
        "Recurring verified project evidence: " + str(finding["message"]),
        source_hash=str(evaluation["source_hash"]),
        task_id=str(tasks[0]),
        last_confirmed_task_id=str(tasks[-1]),
        confidence=min(0.99, 0.65 + 0.05 * min(len(tasks), 4)),
        evidence_hash=str(evaluation["evidence_hash"]),
        owner_scope="project",
        sensitivity="normal",
    )
    memory_id = int(memory["memory_id"])
    with connect_read_only(root) as c:
        row = c.execute("SELECT * FROM project_memory WHERE id=?", (memory_id,)).fetchone()
        if not row:
            raise MemoryPromotionError("memory_candidate_insert_missing")
        target_hash = _candidate_hash(dict(row))

    linked = 0
    try:
        for signal in evaluation["valid_signals"]:
            link_learning_signal(
                root,
                signal_id=str(signal["signal_id"]),
                relation_type="memory_candidate",
                target_type="project_memory",
                target_id=str(memory_id),
                target_hash=target_hash,
            )
            linked += 1
    except Exception:
        with connect(root, immediate=True) as c:
            c.execute(
                "UPDATE project_memory SET status='stale' WHERE id=? AND status='candidate'",
                (memory_id,),
            )
        raise

    decision = None
    if open_human_decision:
        decision = _request_decision(
            root,
            memory_id=memory_id,
            finding_id=int(finding_id),
            evidence_hash=str(evaluation["evidence_hash"]),
            task_id=str(tasks[-1]),
            raised_by_session=raised_by_session,
        )
    return {
        "ok": True,
        "created": True,
        "existing": False,
        "memory_id": memory_id,
        "status": "candidate",
        "candidate_hash": target_hash,
        "linked_signal_count": linked,
        "human_decision": decision,
        "evaluation": evaluation,
        "instruction_authority": False,
    }


def flag_memory_promotion_candidates_for_task(
    root: Path,
    task_id: str,
    *,
    raised_by_session: str | None = None,
) -> dict[str, Any]:
    """Re-evaluate project findings observed by one just-verified task."""
    with connect_read_only(root) as c:
        rows = c.execute(
            """
            SELECT DISTINCT source_id
            FROM learning_signals
            WHERE task_id=? AND source_type='project_finding'
            ORDER BY source_id
            """,
            (str(task_id),),
        ).fetchall()
    results = []
    degraded = []
    for row in rows:
        try:
            results.append(create_memory_promotion_candidate(
                root,
                str(row["source_id"]),
                raised_by_session=raised_by_session,
                open_human_decision=True,
            ))
        except Exception as exc:
            degraded.append({
                "finding_id": int(row["source_id"]),
                "error": f"{type(exc).__name__}:{exc}",
            })
    return {
        "ok": True,
        "task_id": str(task_id),
        "results": results,
        "degraded": degraded,
        "automatic_activation": False,
        "instruction_authority": False,
    }


def _linked_candidate(root: Path, memory_id: int) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    with connect_read_only(root) as c:
        memory = c.execute("SELECT * FROM project_memory WHERE id=?", (int(memory_id),)).fetchone()
        if not memory:
            raise MemoryPromotionError("memory_candidate_missing")
        rows = c.execute(
            """
            SELECT lsl.target_hash,ls.signal_id,ls.task_id,ls.source_id AS finding_id
            FROM learning_signal_links lsl
            JOIN learning_signals ls ON ls.signal_id=lsl.signal_id
            WHERE lsl.relation_type='memory_candidate'
              AND lsl.target_type='project_memory'
              AND lsl.target_id=?
              AND ls.source_type='project_finding'
            ORDER BY ls.task_id,ls.signal_id
            """,
            (str(int(memory_id)),),
        ).fetchall()
    links = [dict(row) for row in rows]
    if not links:
        raise MemoryPromotionError("memory_candidate_signal_links_missing")
    finding_ids = {int(row["finding_id"]) for row in links}
    if len(finding_ids) != 1:
        raise MemoryPromotionError("memory_candidate_finding_identity_ambiguous")
    return dict(memory), links, next(iter(finding_ids))


def finalize_memory_promotion_candidate(
    root: Path,
    memory_id: int,
    decision_uuid: str,
    *,
    expected_task_id: str | None = None,
) -> dict[str, Any]:
    """Finalize candidate only from an explicit resolved Human Decision."""
    promotion = _policy(root)
    memory, links, finding_id = _linked_candidate(root, int(memory_id))
    if str(memory["status"]) == "active":
        return {"ok": True, "memory_id": int(memory_id), "status": "active", "existing": True}
    if str(memory["status"]) != "candidate":
        raise MemoryPromotionError("memory_candidate_not_pending")
    expected_target_hash = _candidate_hash(memory)
    if any(str(link["target_hash"]) != expected_target_hash for link in links):
        raise MemoryPromotionError("memory_candidate_target_hash_mismatch")

    with connect_read_only(root) as c:
        architecture_hash = _active_architecture_hash(c)
        request = c.execute(
            "SELECT * FROM human_decision_requests WHERE decision_uuid=?",
            (str(decision_uuid),),
        ).fetchone()
        if not request:
            raise MemoryPromotionError("memory_promotion_human_decision_missing")
        request = dict(request)
        resolution = c.execute(
            """
            SELECT selected_option,answer_hash,resolved_by,human_confirmed,
                   impact_classification,created_at
            FROM human_decision_resolutions WHERE decision_id=?
            """,
            (int(request["id"]),),
        ).fetchone()
        resolution = dict(resolution) if resolution else None

    linked_task_ids = {str(link["task_id"]) for link in links}
    if str(request["task_id"]) not in linked_task_ids:
        raise MemoryPromotionError("memory_promotion_decision_task_mismatch")
    if expected_task_id and str(request["task_id"]) != str(expected_task_id):
        raise MemoryPromotionError("memory_promotion_decision_task_mismatch")
    if str(request["question_hash"]) != _sha(
        _decision_question(int(memory_id), finding_id, str(memory["evidence_hash"]))
    ):
        raise MemoryPromotionError("memory_promotion_decision_identity_mismatch")
    if str(request["status"]) != "resolved" or resolution is None:
        raise MemoryPromotionError("memory_promotion_human_decision_unresolved")
    if int(resolution.get("human_confirmed") or 0) != 1:
        raise MemoryPromotionError("memory_promotion_explicit_human_confirmation_required")
    if str(resolution.get("impact_classification") or "") != "none":
        raise MemoryPromotionError("memory_promotion_decision_impact_must_be_none")
    option = str(resolution.get("selected_option") or "").strip().lower()
    if option not in {"approve", "reject"}:
        raise MemoryPromotionError("memory_promotion_decision_option_invalid")

    if option == "reject":
        with connect(root, immediate=True) as c:
            c.execute(
                "UPDATE project_memory SET status=? WHERE id=? AND status='candidate'",
                (str(promotion["rejected_status"]), int(memory_id)),
            )
        return {
            "ok": True,
            "memory_id": int(memory_id),
            "status": str(promotion["rejected_status"]),
            "activated": False,
            "human_confirmed": True,
            "instruction_authority": False,
        }

    if not architecture_hash:
        raise MemoryPromotionError("active_architecture_baseline_required")
    if str(request.get("architecture_baseline_hash") or "") != architecture_hash:
        raise MemoryPromotionError("memory_promotion_decision_architecture_stale")

    reports = []
    for link in links:
        report = revalidate_learning_signal(root, str(link["signal_id"]), persist_eligibility=True)
        if not report["source_current"]:
            raise MemoryPromotionError("memory_promotion_source_hash_stale")
        if not report["cross_task_eligible"]:
            raise MemoryPromotionError("memory_promotion_source_task_not_verified")
        if str(report.get("architecture_baseline_hash") or "") != architecture_hash:
            raise MemoryPromotionError("memory_promotion_architecture_baseline_changed")
        if str(report["source_hash"]) != str(memory["source_hash"]):
            raise MemoryPromotionError("memory_promotion_memory_source_hash_mismatch")
        reports.append(report)

    tasks = sorted({str(report["task_id"]) for report in reports})
    if len(tasks) < int(promotion["minimum_distinct_tasks"]):
        raise MemoryPromotionError("memory_promotion_distinct_task_threshold_regressed")
    with connect_read_only(root) as c:
        finding = _finding(c, finding_id)
    if int(finding["occurrences"]) < int(promotion["minimum_occurrences"]):
        raise MemoryPromotionError("memory_promotion_occurrence_threshold_regressed")

    with connect(root, immediate=True) as c:
        cur = c.execute(
            "UPDATE project_memory SET status='active',last_confirmed_task_id=? WHERE id=? AND status='candidate'",
            (str(request["task_id"]), int(memory_id)),
        )
        if int(cur.rowcount) != 1:
            raise MemoryPromotionError("memory_promotion_activation_race")
    closed_loop_skill_candidate = None
    closed_loop_skill_candidate_error = None
    try:
        from .closed_loop_improvement import create_skill_candidate_from_memory
        closed_loop_skill_candidate = create_skill_candidate_from_memory(
            root,
            int(memory_id),
        )
    except Exception as exc:
        # Candidate creation is non-active/degraded-safe; memory activation remains authoritative.
        closed_loop_skill_candidate_error = f"{type(exc).__name__}:{exc}"

    return {
        "ok": True,
        "memory_id": int(memory_id),
        "status": "active",
        "activated": True,
        "human_confirmed": True,
        "verified_distinct_task_count": len(tasks),
        "architecture_baseline_hash": architecture_hash,
        "closed_loop_skill_candidate": closed_loop_skill_candidate,
        "closed_loop_skill_candidate_error": closed_loop_skill_candidate_error,
        "trust_class": "project_evidence",
        "authority_class": "none",
        "instruction_authority": False,
    }


def memory_promotion_status(root: Path, *, finding_id: int | str | None = None) -> dict[str, Any]:
    """Return privacy-safe governed memory-promotion state."""
    if finding_id is not None:
        return evaluate_memory_promotion(root, finding_id)
    with connect_read_only(root) as c:
        candidates = int(c.execute(
            "SELECT COUNT(*) AS n FROM project_memory WHERE status='candidate'"
        ).fetchone()["n"])
        active = int(c.execute(
            """
            SELECT COUNT(DISTINCT pm.id) AS n
            FROM project_memory pm
            JOIN learning_signal_links l
              ON l.target_type='project_memory'
             AND l.target_id=CAST(pm.id AS TEXT)
             AND l.relation_type='memory_candidate'
            WHERE pm.status='active'
            """
        ).fetchone()["n"])
    return {
        "ok": True,
        "memory_promotion_version": MEMORY_PROMOTION_VERSION,
        "schema": 64,
        "candidate_count": candidates,
        "active_promoted_memory_count": active,
        "automatic_candidate_flagging": True,
        "automatic_activation": False,
        "human_decision_required_for_activation": True,
        "mcp_mutation_allowed": False,
        "instruction_authority": False,
    }
