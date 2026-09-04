"""
File: .agents/agentos/closed_loop_improvement.py

Purpose:
    Close the governed learning loop from human-approved project memory through
    reusable skill candidates and evidence-backed policy improvement proposals.

Responsibilities:
    - Reuse project_memory, promoted_skills, skill_evaluation_runs,
      evolution_proposals, and schema-64 learning_signal_links.
    - Create only non-active skill candidates from current learning-linked memory.
    - Revalidate learning evidence before closed-loop skill graduation.
    - Require repeated adverse skill evaluations before policy-proposal readiness.
    - Require an explicit caller-supplied policy patch; never synthesize policy authority.
    - Create/simulate draft evolution proposals without automatic policy activation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .db import connect_read_only
from .evolution import create_proposal, simulate_proposal
from .learning_signals import link_learning_signal, revalidate_learning_signal
from .policy import load_policy
from .skills import promote_skill_candidate

CLOSED_LOOP_VERSION = 1
CLOSED_LOOP_PROMOTER = "system:closed-loop-v0312"


class ClosedLoopImprovementError(RuntimeError):
    """Raised when a v0.31.2 closed-loop governance invariant is not satisfied."""


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _policy(root: Path) -> dict[str, Any]:
    policy = load_policy(root)
    learning = policy.get("governed_learning_policy")
    if not isinstance(learning, dict) or learning.get("enabled") is not True:
        raise ClosedLoopImprovementError("governed_learning_policy_required")
    cfg = learning.get("closed_loop")
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        raise ClosedLoopImprovementError("closed_loop_policy_required")

    required_true = (
        "automatic_skill_candidate_creation",
        "policy_patch_must_be_explicit",
        "automatic_policy_simulation_after_explicit_draft",
        "skill_candidate_requires_learning_links",
        "source_signal_revalidation_required",
        "architecture_baseline_revalidation_required",
        "human_skill_graduation_required",
        "human_policy_transition_required",
        "policy_activation_via_existing_evolution_only",
    )
    for key in required_true:
        if cfg.get(key) is not True:
            raise ClosedLoopImprovementError(
                "closed_loop_required_invariant_disabled:" + key
            )

    required_false = (
        "automatic_skill_graduation",
        "automatic_policy_proposal_creation",
        "automatic_policy_transition",
        "automatic_policy_activation",
        "automatic_architecture_mutation",
        "mcp_mutation_allowed",
    )
    for key in required_false:
        if cfg.get(key) is not False:
            raise ClosedLoopImprovementError(
                "closed_loop_authority_invariant_violated:" + key
            )

    for key in (
        "minimum_adverse_evaluations",
        "minimum_negative_evaluations",
        "minimum_distinct_evaluation_tasks",
        "evaluation_window_days",
    ):
        if int(cfg.get(key, 0)) <= 0:
            raise ClosedLoopImprovementError(
                "closed_loop_threshold_invalid:" + key
            )

    if set(str(x) for x in cfg.get("adverse_evaluation_statuses", [])) != {
        "negative",
        "mixed",
    }:
        raise ClosedLoopImprovementError(
            "closed_loop_adverse_status_registry_invalid"
        )
    return cfg


def _active_architecture_hash(root: Path) -> str | None:
    with connect_read_only(root) as c:
        row = c.execute(
            "SELECT baseline_hash FROM architecture_baselines "
            "WHERE status='active' "
            "ORDER BY activated_at DESC,rowid DESC LIMIT 1"
        ).fetchone()
    value = str(row["baseline_hash"] or "") if row else ""
    return value or None


def _existing_skill_for_memory(
    root: Path,
    memory_id: int,
) -> dict[str, Any] | None:
    with connect_read_only(root) as c:
        row = c.execute(
            """
            SELECT *
            FROM promoted_skills
            WHERE memory_id=? AND status IN ('candidate','graduated')
            ORDER BY id DESC LIMIT 1
            """,
            (int(memory_id),),
        ).fetchone()
    return dict(row) if row else None


def _memory_support_links(
    root: Path,
    memory_id: int,
) -> list[dict[str, Any]]:
    with connect_read_only(root) as c:
        rows = c.execute(
            """
            SELECT l.target_hash,ls.*
            FROM learning_signal_links l
            JOIN learning_signals ls ON ls.signal_id=l.signal_id
            WHERE l.relation_type='memory_candidate'
              AND l.target_type='project_memory'
              AND l.target_id=?
            ORDER BY ls.task_id,ls.signal_sequence_number
            """,
            (str(int(memory_id)),),
        ).fetchall()
    return [dict(row) for row in rows]


def _revalidated_support(
    root: Path,
    rows: list[dict[str, Any]],
    *,
    architecture_hash: str,
) -> list[dict[str, Any]]:
    reports = []
    for row in rows:
        report = revalidate_learning_signal(
            root,
            str(row["signal_id"]),
            persist_eligibility=True,
        )
        if not report["source_current"]:
            raise ClosedLoopImprovementError(
                "closed_loop_source_hash_stale"
            )
        if not report["cross_task_eligible"]:
            raise ClosedLoopImprovementError(
                "closed_loop_source_task_not_verified"
            )
        if str(report.get("architecture_baseline_hash") or "") != str(
            architecture_hash
        ):
            raise ClosedLoopImprovementError(
                "closed_loop_architecture_baseline_mismatch"
            )
        reports.append(report)
    return reports


def skill_candidate_readiness(
    root: Path,
    memory_id: int,
) -> dict[str, Any]:
    """Evaluate whether active procedural memory can become a skill candidate."""
    _policy(root)
    architecture_hash = _active_architecture_hash(root)
    policy = load_policy(root)

    with connect_read_only(root) as c:
        memory = c.execute(
            "SELECT * FROM project_memory WHERE id=?",
            (int(memory_id),),
        ).fetchone()
    if not memory:
        raise ClosedLoopImprovementError("closed_loop_memory_missing")
    memory = dict(memory)

    reasons: list[str] = []
    if str(memory.get("kind") or "") != "procedural":
        reasons.append("procedural_memory_required")
    if str(memory.get("status") or "") != "active":
        reasons.append("active_memory_required")
    if not architecture_hash:
        reasons.append("active_architecture_baseline_required")

    skill_cfg = policy.get("knowledge_runtime", {}).get(
        "skill_policy",
        {},
    )
    threshold = float(
        skill_cfg.get("candidate_confidence_threshold", 0.8)
    )
    if float(memory.get("confidence") or 0.0) < threshold:
        reasons.append("memory_confidence_below_skill_threshold")

    existing = _existing_skill_for_memory(root, int(memory_id))
    links = _memory_support_links(root, int(memory_id))
    if not links:
        reasons.append("memory_learning_links_required")

    reports: list[dict[str, Any]] = []
    if architecture_hash and links:
        try:
            reports = _revalidated_support(
                root,
                links,
                architecture_hash=architecture_hash,
            )
        except ClosedLoopImprovementError as exc:
            reasons.append(str(exc))

    required_tasks = int(
        (
            policy.get(
                "governed_learning_policy",
                {},
            ).get("promotion", {})
            or {}
        ).get("minimum_distinct_tasks", 2)
    )
    distinct_tasks = sorted(
        {str(item["task_id"]) for item in reports}
    )
    if len(distinct_tasks) < required_tasks:
        reasons.append(
            "distinct_verified_task_threshold_not_met"
        )

    return {
        "ok": True,
        "memory_id": int(memory_id),
        "memory_status": str(memory.get("status") or ""),
        "memory_kind": str(memory.get("kind") or ""),
        "memory_confidence": float(
            memory.get("confidence") or 0.0
        ),
        "candidate_confidence_threshold": threshold,
        "architecture_baseline_hash": architecture_hash,
        "support_signal_count": len(reports),
        "distinct_verified_task_count": len(distinct_tasks),
        "minimum_distinct_tasks": required_tasks,
        "existing_skill": existing,
        "ready": bool(not reasons and existing is None),
        "reasons": sorted(set(reasons)),
        "automatic_graduation": False,
        "instruction_authority": False,
        "authority_class": "none",
        "trust_class": "project_evidence",
    }


def create_skill_candidate_from_memory(
    root: Path,
    memory_id: int,
    *,
    promoted_by: str = CLOSED_LOOP_PROMOTER,
) -> dict[str, Any]:
    """Create one non-active skill candidate from governed active memory."""
    existing = _existing_skill_for_memory(
        root,
        int(memory_id),
    )
    if existing:
        return {
            "ok": True,
            "created": False,
            "existing": True,
            "memory_id": int(memory_id),
            "skill_id": int(existing["id"]),
            "skill_status": str(existing["status"]),
            "promoted_by": str(
                existing.get("promoted_by") or ""
            ),
            "automatic_graduation": False,
        }

    readiness = skill_candidate_readiness(
        root,
        int(memory_id),
    )
    if not readiness["ready"]:
        raise ClosedLoopImprovementError(
            "closed_loop_skill_candidate_not_ready:"
            + ",".join(readiness["reasons"])
        )

    candidate = promote_skill_candidate(
        root,
        int(memory_id),
        str(promoted_by or CLOSED_LOOP_PROMOTER),
    )

    linked = 0
    for row in _memory_support_links(
        root,
        int(memory_id),
    ):
        report = revalidate_learning_signal(
            root,
            str(row["signal_id"]),
            persist_eligibility=True,
        )
        if (
            not report["source_current"]
            or not report["cross_task_eligible"]
        ):
            raise ClosedLoopImprovementError(
                "closed_loop_skill_link_source_invalid"
            )
        if str(
            report.get(
                "architecture_baseline_hash"
            )
            or ""
        ) != str(
            readiness["architecture_baseline_hash"]
        ):
            raise ClosedLoopImprovementError(
                "closed_loop_skill_link_architecture_stale"
            )
        link_learning_signal(
            root,
            signal_id=str(report["signal_id"]),
            relation_type="skill_candidate",
            target_type="promoted_skill",
            target_id=str(candidate["skill_id"]),
            target_hash=str(candidate["content_hash"]),
        )
        linked += 1

    return {
        "ok": True,
        "created": True,
        "existing": False,
        "memory_id": int(memory_id),
        "skill_id": int(candidate["skill_id"]),
        "skill_key": candidate["skill_key"],
        "skill_status": candidate["status"],
        "content_hash": candidate["content_hash"],
        "linked_signal_count": linked,
        "automatic_graduation": False,
        "human_graduation_required": True,
        "instruction_authority": False,
    }


def validate_closed_loop_skill_candidate(
    root: Path,
    skill_id: int,
) -> dict[str, Any]:
    """Revalidate linked learning evidence immediately before graduation."""
    _policy(root)
    with connect_read_only(root) as c:
        skill = c.execute(
            "SELECT * FROM promoted_skills WHERE id=?",
            (int(skill_id),),
        ).fetchone()
        if not skill:
            raise ClosedLoopImprovementError(
                "closed_loop_skill_missing"
            )
        skill = dict(skill)

        if str(
            skill.get("promoted_by") or ""
        ) != CLOSED_LOOP_PROMOTER:
            return {
                "ok": True,
                "applies": False,
                "skill_id": int(skill_id),
            }

        rows = c.execute(
            """
            SELECT l.target_hash,ls.signal_id
            FROM learning_signal_links l
            JOIN learning_signals ls
              ON ls.signal_id=l.signal_id
            WHERE l.relation_type='skill_candidate'
              AND l.target_type='promoted_skill'
              AND l.target_id=?
            ORDER BY ls.task_id,ls.signal_sequence_number
            """,
            (str(int(skill_id)),),
        ).fetchall()

    if str(skill.get("status") or "") != "candidate":
        raise ClosedLoopImprovementError(
            "closed_loop_skill_not_candidate"
        )
    if not rows:
        raise ClosedLoopImprovementError(
            "closed_loop_skill_learning_links_missing"
        )

    expected_hash = str(
        skill.get("content_hash") or ""
    )
    if any(
        str(row["target_hash"]) != expected_hash
        for row in rows
    ):
        raise ClosedLoopImprovementError(
            "closed_loop_skill_target_hash_mismatch"
        )

    architecture_hash = _active_architecture_hash(root)
    if not architecture_hash:
        raise ClosedLoopImprovementError(
            "active_architecture_baseline_required"
        )

    reports = []
    for row in rows:
        report = revalidate_learning_signal(
            root,
            str(row["signal_id"]),
            persist_eligibility=True,
        )
        if not report["source_current"]:
            raise ClosedLoopImprovementError(
                "closed_loop_skill_source_stale"
            )
        if not report["cross_task_eligible"]:
            raise ClosedLoopImprovementError(
                "closed_loop_skill_source_not_verified"
            )
        if str(
            report.get("architecture_baseline_hash") or ""
        ) != architecture_hash:
            raise ClosedLoopImprovementError(
                "closed_loop_skill_architecture_stale"
            )
        reports.append(report)

    policy = load_policy(root)
    required_tasks = int(
        (
            policy.get(
                "governed_learning_policy",
                {},
            ).get("promotion", {})
            or {}
        ).get("minimum_distinct_tasks", 2)
    )
    distinct_tasks = sorted(
        {str(item["task_id"]) for item in reports}
    )
    if len(distinct_tasks) < required_tasks:
        raise ClosedLoopImprovementError(
            "closed_loop_skill_distinct_task_threshold_regressed"
        )

    return {
        "ok": True,
        "applies": True,
        "skill_id": int(skill_id),
        "support_signal_count": len(reports),
        "distinct_verified_task_count": len(
            distinct_tasks
        ),
        "architecture_baseline_hash": architecture_hash,
        "instruction_authority": False,
    }


def _policy_evaluation_rows(
    root: Path,
    skill_id: int,
    window_days: int,
) -> list[dict[str, Any]]:
    with connect_read_only(root) as c:
        rows = c.execute(
            """
            SELECT e.*,s.architecture_baseline_hash
            FROM skill_evaluation_runs e
            JOIN skill_selection_runs s
              ON s.id=e.selection_run_id
            WHERE e.skill_id=?
              AND e.created_at >= datetime('now', ?)
            ORDER BY e.created_at,e.id
            """,
            (
                int(skill_id),
                f"-{int(window_days)} days",
            ),
        ).fetchall()
    return [dict(row) for row in rows]


def policy_improvement_readiness(
    root: Path,
    skill_id: int,
) -> dict[str, Any]:
    """Evaluate evidence readiness for an explicit policy-improvement proposal."""
    cfg = _policy(root)
    architecture_hash = _active_architecture_hash(root)

    with connect_read_only(root) as c:
        skill = c.execute(
            "SELECT * FROM promoted_skills WHERE id=?",
            (int(skill_id),),
        ).fetchone()
        baseline = c.execute(
            "SELECT id FROM evaluation_runs "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not skill:
        raise ClosedLoopImprovementError(
            "closed_loop_policy_skill_missing"
        )
    skill = dict(skill)

    adverse_statuses = set(
        str(x)
        for x in cfg[
            "adverse_evaluation_statuses"
        ]
    )
    rows = _policy_evaluation_rows(
        root,
        int(skill_id),
        int(cfg["evaluation_window_days"]),
    )
    adverse_rows = [
        row
        for row in rows
        if str(
            row["evaluation_status"]
        )
        in adverse_statuses
    ]

    valid = []
    missing_signals = 0
    for row in adverse_rows:
        with connect_read_only(root) as c:
            signal = c.execute(
                """
                SELECT signal_id
                FROM learning_signals
                WHERE task_id=?
                  AND source_type='task_outcome'
                  AND source_id=?
                ORDER BY signal_sequence_number DESC
                LIMIT 1
                """,
                (
                    str(row["task_id"]),
                    str(row["outcome_id"]),
                ),
            ).fetchone()

        if not signal:
            missing_signals += 1
            continue

        report = revalidate_learning_signal(
            root,
            str(signal["signal_id"]),
            persist_eligibility=True,
        )
        if (
            not report["source_current"]
            or not report["cross_task_eligible"]
        ):
            continue
        if not architecture_hash:
            continue
        if str(
            row.get(
                "architecture_baseline_hash"
            )
            or ""
        ) != architecture_hash:
            continue
        if str(
            report.get(
                "architecture_baseline_hash"
            )
            or ""
        ) != architecture_hash:
            continue

        valid.append(
            {
                "evaluation_id": int(row["id"]),
                "evaluation_status": str(
                    row["evaluation_status"]
                ),
                "task_id": str(row["task_id"]),
                "outcome_id": int(row["outcome_id"]),
                "signal_id": str(
                    report["signal_id"]
                ),
                "source_hash": str(
                    report["source_hash"]
                ),
            }
        )

    adverse_count = len(valid)
    negative_count = sum(
        1
        for row in valid
        if row["evaluation_status"] == "negative"
    )
    distinct_tasks = sorted(
        {row["task_id"] for row in valid}
    )

    reasons = []
    if str(skill.get("status") or "") != "graduated":
        reasons.append("graduated_skill_required")
    if not architecture_hash:
        reasons.append(
            "active_architecture_baseline_required"
        )
    if baseline is None:
        reasons.append("evaluation_baseline_required")
    if adverse_count < int(
        cfg["minimum_adverse_evaluations"]
    ):
        reasons.append(
            "minimum_adverse_evaluations_not_met"
        )
    if negative_count < int(
        cfg["minimum_negative_evaluations"]
    ):
        reasons.append(
            "minimum_negative_evaluations_not_met"
        )
    if len(distinct_tasks) < int(
        cfg["minimum_distinct_evaluation_tasks"]
    ):
        reasons.append(
            "minimum_distinct_evaluation_tasks_not_met"
        )
    if missing_signals:
        reasons.append(
            "adverse_evaluation_learning_signal_missing"
        )

    with connect_read_only(root) as c:
        finding_rows = c.execute(
            """
            SELECT DISTINCT ls.source_id
            FROM promoted_skills ps
            JOIN learning_signal_links l
              ON l.relation_type='skill_candidate'
             AND l.target_type='promoted_skill'
             AND l.target_id=CAST(ps.id AS TEXT)
            JOIN learning_signals ls
              ON ls.signal_id=l.signal_id
            WHERE ps.id=?
              AND ls.source_type='project_finding'
            ORDER BY ls.source_id
            """,
            (int(skill_id),),
        ).fetchall()

    trigger_findings = [
        int(row["source_id"])
        for row in finding_rows
        if str(row["source_id"]).isdigit()
    ]

    return {
        "ok": True,
        "skill_id": int(skill_id),
        "skill_status": str(
            skill.get("status") or ""
        ),
        "architecture_baseline_hash": architecture_hash,
        "evaluation_window_days": int(
            cfg["evaluation_window_days"]
        ),
        "adverse_evaluation_count": adverse_count,
        "negative_evaluation_count": negative_count,
        "distinct_evaluation_task_count": len(
            distinct_tasks
        ),
        "minimum_adverse_evaluations": int(
            cfg["minimum_adverse_evaluations"]
        ),
        "minimum_negative_evaluations": int(
            cfg["minimum_negative_evaluations"]
        ),
        "minimum_distinct_evaluation_tasks": int(
            cfg["minimum_distinct_evaluation_tasks"]
        ),
        "support_evaluations": valid,
        "trigger_findings": trigger_findings,
        "latest_evaluation_baseline_id": (
            int(baseline["id"])
            if baseline
            else None
        ),
        "ready": bool(not reasons),
        "reasons": sorted(set(reasons)),
        "policy_patch_must_be_explicit": True,
        "automatic_policy_activation": False,
        "instruction_authority": False,
    }


def _proposal_hash(
    *,
    title: str,
    trigger_findings: list[int],
    policy_patch: dict[str, Any],
    expected_benefit: str,
    risks: list[str],
    rollback_plan: dict[str, Any],
) -> str:
    return _sha(
        {
            "title": title,
            "trigger_findings": trigger_findings,
            "policy_patch": policy_patch,
            "expected_benefit": expected_benefit,
            "risks": risks,
            "rollback_plan": rollback_plan,
        }
    )


def create_policy_improvement_proposal(
    root: Path,
    *,
    skill_id: int,
    title: str,
    policy_patch: dict[str, Any],
    expected_benefit: str,
    risks: list[str],
    rollback_plan: dict[str, Any],
    created_by: str,
) -> dict[str, Any]:
    """Create/simulate a proposal from an explicit caller-supplied patch."""
    cfg = _policy(root)

    if (
        not isinstance(policy_patch, dict)
        or not policy_patch
    ):
        raise ClosedLoopImprovementError(
            "explicit_nonempty_policy_patch_required"
        )
    if not str(title or "").strip():
        raise ClosedLoopImprovementError(
            "policy_proposal_title_required"
        )
    if not str(created_by or "").strip():
        raise ClosedLoopImprovementError(
            "policy_proposal_creator_required"
        )

    readiness = policy_improvement_readiness(
        root,
        int(skill_id),
    )
    if not readiness["ready"]:
        raise ClosedLoopImprovementError(
            "closed_loop_policy_proposal_not_ready:"
            + ",".join(readiness["reasons"])
        )

    trigger_findings = list(
        readiness["trigger_findings"]
    )
    expected_hash = _proposal_hash(
        title=str(title),
        trigger_findings=trigger_findings,
        policy_patch=policy_patch,
        expected_benefit=str(expected_benefit),
        risks=[str(item) for item in risks],
        rollback_plan=rollback_plan,
    )

    with connect_read_only(root) as c:
        existing = c.execute(
            "SELECT * FROM evolution_proposals "
            "WHERE proposal_hash=? "
            "ORDER BY id DESC LIMIT 1",
            (expected_hash,),
        ).fetchone()

    if existing:
        row = dict(existing)
        return {
            "ok": True,
            "created": False,
            "existing": True,
            "proposal_id": int(row["id"]),
            "status": str(row["status"]),
            "proposal_hash": str(
                row["proposal_hash"]
            ),
            "automatic_policy_activation": False,
        }

    proposal = create_proposal(
        root,
        str(title),
        trigger_findings,
        policy_patch,
        str(expected_benefit),
        [str(item) for item in risks],
        rollback_plan,
        str(created_by),
    )
    if str(
        proposal["proposal_hash"]
    ) != expected_hash:
        raise ClosedLoopImprovementError(
            "evolution_proposal_hash_mismatch"
        )

    linked = 0
    for support in readiness[
        "support_evaluations"
    ]:
        link_learning_signal(
            root,
            signal_id=str(
                support["signal_id"]
            ),
            relation_type="evolution_proposal",
            target_type="evolution_proposal",
            target_id=str(
                proposal["proposal_id"]
            ),
            target_hash=str(
                proposal["proposal_hash"]
            ),
        )
        linked += 1

    status = str(proposal["status"])
    simulation = None
    if cfg.get(
        "automatic_policy_simulation_after_explicit_draft"
    ) is True:
        simulation = simulate_proposal(
            root,
            int(proposal["proposal_id"]),
        )
        status = str(simulation["status"])

    return {
        "ok": True,
        "created": True,
        "existing": False,
        "proposal_id": int(
            proposal["proposal_id"]
        ),
        "proposal_hash": str(
            proposal["proposal_hash"]
        ),
        "status": status,
        "linked_signal_count": linked,
        "simulation": simulation,
        "policy_patch_was_explicit": True,
        "automatic_policy_transition": False,
        "automatic_policy_activation": False,
        "human_policy_transition_required": True,
        "instruction_authority": False,
    }


def closed_loop_status(
    root: Path,
) -> dict[str, Any]:
    """Return privacy-safe v0.31.2 closed-loop state and non-claims."""
    _policy(root)
    with connect_read_only(root) as c:
        skill_candidates = int(
            c.execute(
                "SELECT COUNT(*) AS n "
                "FROM promoted_skills "
                "WHERE promoted_by=? "
                "AND status='candidate'",
                (CLOSED_LOOP_PROMOTER,),
            ).fetchone()["n"]
        )
        linked_proposals = int(
            c.execute(
                "SELECT COUNT(DISTINCT target_id) AS n "
                "FROM learning_signal_links "
                "WHERE relation_type='evolution_proposal' "
                "AND target_type='evolution_proposal'"
            ).fetchone()["n"]
        )

    return {
        "ok": True,
        "closed_loop_version": CLOSED_LOOP_VERSION,
        "schema": 64,
        "closed_loop_skill_candidate_count": (
            skill_candidates
        ),
        "evidence_linked_policy_proposal_count": (
            linked_proposals
        ),
        "automatic_skill_graduation": False,
        "automatic_policy_proposal_creation": False,
        "automatic_policy_activation": False,
        "automatic_architecture_mutation": False,
        "mcp_mutation_allowed": False,
        "instruction_authority": False,
        "authority_class": "none",
        "trust_class": "project_evidence",
    }
