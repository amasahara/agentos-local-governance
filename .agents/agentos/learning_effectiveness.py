"""
File: .agents/agentos/learning_effectiveness.py

Purpose:
    Measure comparative learning effectiveness and knowledge drift from existing
    AgentOS evidence without creating a parallel lifecycle or granting authority.

Responsibilities:
    - Use actual knowledge_usage context inclusion for treatment cohorts.
    - Build deterministic observational comparison cohorts from task outcomes.
    - Report Wilson intervals, z-test results, effect size, and small-sample limits.
    - Distinguish architecture review, stale evidence, and unresolved scope.
    - Open an existing Human Decision only on explicit review request.
    - Never deactivate, supersede, graduate, activate policy, or mutate architecture.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .db import connect_read_only
from .human_decision import request_human_decision
from .policy import load_policy

EFFECTIVENESS_VERSION = 1
SUPPORTED_KINDS = {"skill", "memory", "finding"}


class LearningEffectivenessError(RuntimeError):
    """Raised when a v0.31.3 effectiveness/drift invariant is not satisfied."""


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
    section = load_policy(root).get("governed_learning_policy")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        raise LearningEffectivenessError("governed_learning_policy_required")
    cfg = section.get("effectiveness")
    if not isinstance(cfg, dict):
        raise LearningEffectivenessError("learning_effectiveness_policy_required")

    required_true = (
        "comparative_effectiveness_enabled",
        "drift_detection_enabled",
        "actual_context_inclusion_required",
        "architecture_match_required",
        "human_review_required_for_state_change",
        "explicit_review_request_required",
    )
    for key in required_true:
        if cfg.get(key) is not True:
            raise LearningEffectivenessError(
                "effectiveness_required_invariant_disabled:" + key
            )

    required_false = (
        "automatic_review_request_creation",
        "automatic_deactivation_allowed",
        "automatic_supersede_allowed",
        "automatic_stale_status_mutation",
        "causal_effectiveness_claim_allowed",
        "provider_model_matching_required",
        "mcp_mutation_allowed",
    )
    for key in required_false:
        if cfg.get(key) is not False:
            raise LearningEffectivenessError(
                "effectiveness_authority_invariant_violated:" + key
            )

    for key in (
        "minimum_treatment_tasks",
        "minimum_control_tasks",
        "minimum_distinct_tasks",
        "window_days",
        "small_sample_warning_below",
    ):
        if int(cfg.get(key, 0)) <= 0:
            raise LearningEffectivenessError(
                "effectiveness_threshold_invalid:" + key
            )

    alpha = float(cfg.get("significance_alpha", 0.0))
    if not 0.0 < alpha < 1.0:
        raise LearningEffectivenessError("effectiveness_alpha_invalid")

    effect = float(cfg.get("minimum_effect_size", -1.0))
    if not 0.0 < effect <= 1.0:
        raise LearningEffectivenessError("effectiveness_effect_size_invalid")

    options = list(cfg.get("review_options") or [])
    if options != ["retain", "revise", "supersede", "deactivate"]:
        raise LearningEffectivenessError("effectiveness_review_options_invalid")
    return cfg


def _wilson(successes: int, n: int, z: float = 1.95996398454) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p = successes / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt(
        (p * (1 - p) + z * z / (4 * n)) / n
    ) / d
    return (
        max(0.0, center - margin),
        min(1.0, center + margin),
    )


def _z_compare(
    treatment_successes: int,
    treatment_n: int,
    control_successes: int,
    control_n: int,
) -> dict[str, Any]:
    treatment_rate = (
        treatment_successes / treatment_n
        if treatment_n
        else 0.0
    )
    control_rate = (
        control_successes / control_n
        if control_n
        else 0.0
    )
    if not treatment_n or not control_n:
        return {
            "z": 0.0,
            "p_value": 1.0,
            "effect_size": treatment_rate - control_rate,
        }

    pooled = (
        (treatment_successes + control_successes)
        / (treatment_n + control_n)
    )
    se = math.sqrt(
        pooled
        * (1 - pooled)
        * (1 / treatment_n + 1 / control_n)
    )
    z_value = (
        (treatment_rate - control_rate) / se
        if se
        else 0.0
    )
    p_value = (
        math.erfc(abs(z_value) / math.sqrt(2))
        if se
        else 1.0
    )
    return {
        "z": z_value,
        "p_value": p_value,
        "effect_size": treatment_rate - control_rate,
    }


def _classify_comparison(
    *,
    treatment_successes: int,
    treatment_n: int,
    control_successes: int,
    control_n: int,
    distinct_treatment_tasks: int,
    distinct_control_tasks: int,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    treatment_rate = (
        treatment_successes / treatment_n
        if treatment_n
        else 0.0
    )
    control_rate = (
        control_successes / control_n
        if control_n
        else 0.0
    )
    z_result = _z_compare(
        treatment_successes,
        treatment_n,
        control_successes,
        control_n,
    )

    warnings: list[str] = []
    sufficient = True
    if treatment_n < int(cfg["minimum_treatment_tasks"]):
        sufficient = False
        warnings.append("minimum_treatment_tasks_not_met")
    if control_n < int(cfg["minimum_control_tasks"]):
        sufficient = False
        warnings.append("minimum_control_tasks_not_met")
    if distinct_treatment_tasks < int(cfg["minimum_distinct_tasks"]):
        sufficient = False
        warnings.append("minimum_distinct_treatment_tasks_not_met")
    if distinct_control_tasks < int(cfg["minimum_distinct_tasks"]):
        sufficient = False
        warnings.append("minimum_distinct_control_tasks_not_met")
    if min(treatment_n, control_n) < int(cfg["small_sample_warning_below"]):
        warnings.append("small_sample_warning")

    verdict = "insufficient_evidence"
    if sufficient:
        effect = float(z_result["effect_size"])
        significant = (
            float(z_result["p_value"])
            < float(cfg["significance_alpha"])
        )
        threshold = float(cfg["minimum_effect_size"])
        if significant and effect <= -threshold:
            verdict = "possibly_ineffective"
        elif significant and effect >= threshold:
            verdict = "comparatively_better"
        else:
            verdict = "no_clear_difference"

    return {
        "verdict": verdict,
        "sufficient_evidence": sufficient,
        "treatment": {
            "n": treatment_n,
            "successes": treatment_successes,
            "success_rate": treatment_rate,
            "confidence_interval": _wilson(
                treatment_successes,
                treatment_n,
            ),
        },
        "control": {
            "n": control_n,
            "successes": control_successes,
            "success_rate": control_rate,
            "confidence_interval": _wilson(
                control_successes,
                control_n,
            ),
        },
        "comparison": z_result,
        "warnings": sorted(set(warnings)),
    }


def _latest_outcomes(
    root: Path,
    window_days: int,
) -> list[dict[str, Any]]:
    with connect_read_only(root) as c:
        rows = c.execute(
            """
            SELECT o.*,
                   ls.architecture_baseline_hash
            FROM task_outcomes o
            LEFT JOIN learning_signals ls
              ON ls.task_id=o.task_id
             AND ls.source_type='task_outcome'
             AND ls.source_id=CAST(o.id AS TEXT)
            WHERE o.created_at >= datetime('now', ?)
              AND o.id=(
                  SELECT MAX(o2.id)
                  FROM task_outcomes o2
                  WHERE o2.task_id=o.task_id
                    AND o2.created_at >= datetime('now', ?)
              )
            ORDER BY o.task_id,o.id
            """,
            (
                f"-{int(window_days)} days",
                f"-{int(window_days)} days",
            ),
        ).fetchall()
    return [dict(row) for row in rows]


def _cohort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("task_category") or ""),
        str(row.get("policy_revision") or ""),
        str(row.get("retrieval_backend") or ""),
        str(row.get("architecture_baseline_hash") or ""),
    )


def comparative_effectiveness(
    root: Path,
    knowledge_kind: str,
    knowledge_id: str | int,
) -> dict[str, Any]:
    """Compare actual-inclusion tasks with deterministic non-inclusion controls."""
    cfg = _policy(root)
    kind = str(knowledge_kind)
    kid = str(knowledge_id)
    if kind not in SUPPORTED_KINDS:
        raise LearningEffectivenessError("unsupported_knowledge_kind")
    if not kid:
        raise LearningEffectivenessError("knowledge_id_required")

    window_days = int(cfg["window_days"])
    with connect_read_only(root) as c:
        latest_hash_row = c.execute(
            """
            SELECT knowledge_hash,MAX(created_at) AS latest_at
            FROM knowledge_usage
            WHERE knowledge_kind=? AND knowledge_id=?
              AND created_at >= datetime('now', ?)
            GROUP BY knowledge_hash
            ORDER BY latest_at DESC,knowledge_hash
            LIMIT 1
            """,
            (kind, kid, f"-{window_days} days"),
        ).fetchone()
        if latest_hash_row:
            latest_hash = str(latest_hash_row["knowledge_hash"])
            treatment_rows = c.execute(
                """
                SELECT DISTINCT task_id
                FROM knowledge_usage
                WHERE knowledge_kind=? AND knowledge_id=?
                  AND knowledge_hash=?
                  AND created_at >= datetime('now', ?)
                ORDER BY task_id
                """,
                (
                    kind,
                    kid,
                    latest_hash,
                    f"-{window_days} days",
                ),
            ).fetchall()
        else:
            latest_hash = None
            treatment_rows = []

        any_usage_rows = c.execute(
            """
            SELECT DISTINCT task_id
            FROM knowledge_usage
            WHERE knowledge_kind=? AND knowledge_id=?
              AND created_at >= datetime('now', ?)
            ORDER BY task_id
            """,
            (kind, kid, f"-{window_days} days"),
        ).fetchall()

    treatment_task_ids = {
        str(row["task_id"])
        for row in treatment_rows
    }
    any_usage_task_ids = {
        str(row["task_id"])
        for row in any_usage_rows
    }

    outcomes = _latest_outcomes(root, window_days)
    treatment = [
        row
        for row in outcomes
        if str(row["task_id"]) in treatment_task_ids
        and str(row.get("architecture_baseline_hash") or "")
    ]
    treatment_keys = {
        _cohort_key(row)
        for row in treatment
    }
    control = [
        row
        for row in outcomes
        if str(row["task_id"]) not in any_usage_task_ids
        and str(row.get("architecture_baseline_hash") or "")
        and _cohort_key(row) in treatment_keys
    ]

    treatment_successes = sum(
        1 for row in treatment
        if str(row.get("outcome") or "") == "success"
    )
    control_successes = sum(
        1 for row in control
        if str(row.get("outcome") or "") == "success"
    )

    stats = _classify_comparison(
        treatment_successes=treatment_successes,
        treatment_n=len(treatment),
        control_successes=control_successes,
        control_n=len(control),
        distinct_treatment_tasks=len(
            {str(row["task_id"]) for row in treatment}
        ),
        distinct_control_tasks=len(
            {str(row["task_id"]) for row in control}
        ),
        cfg=cfg,
    )

    limitations = [
        "observational_comparison_not_causal",
        "provider_model_provenance_incomplete_before_v0.32.0",
        "controls_exact_match_available_task_category_policy_retrieval_architecture",
    ]
    if latest_hash is None:
        limitations.append("artifact_not_observed_in_context_window")
    if len(treatment) < len(treatment_task_ids):
        limitations.append(
            "treatment_rows_without_architecture_bound_outcome_excluded"
        )

    return {
        "ok": True,
        "effectiveness_version": EFFECTIVENESS_VERSION,
        "knowledge_kind": kind,
        "knowledge_id": kid,
        "knowledge_hash": latest_hash,
        "window_days": window_days,
        **stats,
        "treatment_task_ids": sorted(
            str(row["task_id"]) for row in treatment
        ),
        "control_task_ids": sorted(
            str(row["task_id"]) for row in control
        ),
        "cohort_dimensions": [
            "task_category",
            "policy_revision",
            "retrieval_backend",
            "architecture_baseline_hash",
        ],
        "limitations": limitations,
        "comparative_not_causal": True,
        "automatic_deactivation": False,
        "instruction_authority": False,
    }


def _active_architecture(c: Any) -> dict[str, Any] | None:
    row = c.execute(
        """
        SELECT *
        FROM architecture_baselines
        WHERE status='active'
        ORDER BY activated_at DESC,rowid DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def _baseline_sections(
    c: Any,
    baseline_id: int,
) -> dict[str, dict[str, Any]]:
    rows = c.execute(
        """
        SELECT bs.section_id,bs.section_hash,
               sr.applicability,sr.revision
        FROM architecture_baseline_sections bs
        JOIN architecture_section_revisions sr
          ON sr.id=bs.section_revision_id
        WHERE bs.baseline_id=?
        ORDER BY bs.section_id
        """,
        (int(baseline_id),),
    ).fetchall()
    return {
        str(row["section_id"]): dict(row)
        for row in rows
    }


def _scope_resolves(root: Path, value: str) -> bool:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        return True
    if any(ch in text for ch in "*?["):
        try:
            return any(root.glob(text))
        except (OSError, ValueError):
            return False
    return (root / text).exists()


def _skill_drift(
    root: Path,
    skill_id: int,
    active: dict[str, Any] | None,
) -> dict[str, Any]:
    with connect_read_only(root) as c:
        skill = c.execute(
            "SELECT * FROM promoted_skills WHERE id=?",
            (int(skill_id),),
        ).fetchone()
        contract_row = c.execute(
            "SELECT * FROM skill_contracts WHERE skill_id=?",
            (int(skill_id),),
        ).fetchone()
        if not skill:
            raise LearningEffectivenessError("skill_not_found")
        skill = dict(skill)
        contract_row = (
            dict(contract_row)
            if contract_row
            else None
        )

        if contract_row:
            try:
                contract = json.loads(
                    str(contract_row["contract_json"])
                )
            except json.JSONDecodeError:
                contract = {}
        else:
            contract = {}

        pinned_id = (
            int(contract_row["architecture_baseline_id"])
            if contract_row
            and contract_row.get("architecture_baseline_id")
            else (
                int(skill["architecture_baseline_id"])
                if skill.get("architecture_baseline_id")
                else None
            )
        )
        pinned_hash = (
            str(
                (
                    contract_row.get("architecture_baseline_hash")
                    if contract_row
                    else None
                )
                or skill.get("architecture_baseline_hash")
                or ""
            )
            or None
        )

        pinned_sections = (
            _baseline_sections(c, pinned_id)
            if pinned_id
            else {}
        )
        active_sections = (
            _baseline_sections(c, int(active["id"]))
            if active
            else {}
        )

    scopes = [
        str(x)
        for field in (
            "allowed_read_scope",
            "allowed_write_scope",
        )
        for x in (
            contract.get(field)
            if isinstance(contract.get(field), list)
            else []
        )
    ]
    unresolved_scopes = sorted(
        scope
        for scope in scopes
        if not _scope_resolves(root, scope)
    )
    if unresolved_scopes:
        return {
            "state": "scope_unresolved",
            "reason": "declared_skill_scope_no_longer_resolves",
            "unresolved_scopes": unresolved_scopes,
        }

    if str(skill.get("status") or "") == "revoked":
        return {
            "state": "stale",
            "reason": "skill_revoked",
        }

    graduated_path = str(
        skill.get("graduated_path") or ""
    )
    if graduated_path:
        path = root / graduated_path
        if not path.is_file():
            return {
                "state": "stale",
                "reason": "graduated_skill_artifact_missing",
                "path": graduated_path,
            }

    if not active:
        return {
            "state": "review_required_architecture_change",
            "reason": "active_architecture_baseline_missing",
        }

    if pinned_hash and pinned_hash == str(active["baseline_hash"]):
        return {
            "state": "current",
            "reason": "pinned_architecture_baseline_current",
        }

    required = [
        str(x)
        for x in (
            contract.get("required_architecture_sections")
            if isinstance(
                contract.get("required_architecture_sections"),
                list,
            )
            else []
        )
    ]
    architecture_bound = bool(
        required
        or contract.get("allowed_dependencies")
        or contract.get("allowed_external_services")
        or contract.get("architecture_constraints")
    )

    if not pinned_id:
        return {
            "state": (
                "review_required_architecture_change"
                if architecture_bound
                else "current"
            ),
            "reason": (
                "architecture_bound_skill_has_no_pinned_baseline"
                if architecture_bound
                else "skill_not_architecture_bound"
            ),
        }

    if required:
        changed: list[str] = []
        for section_id in required:
            before = pinned_sections.get(section_id)
            current = active_sections.get(section_id)
            if not current:
                return {
                    "state": "stale",
                    "reason": "required_architecture_section_missing",
                    "section_id": section_id,
                }
            if current.get("applicability") == "unresolved":
                return {
                    "state": "review_required_architecture_change",
                    "reason": "required_architecture_section_unresolved",
                    "section_id": section_id,
                }
            if (
                before
                and before.get("applicability") == "applicable"
                and current.get("applicability") == "not_applicable"
            ):
                return {
                    "state": "stale",
                    "reason": "required_architecture_section_became_not_applicable",
                    "section_id": section_id,
                }
            if (
                not before
                or str(before.get("section_hash") or "")
                != str(current.get("section_hash") or "")
            ):
                changed.append(section_id)

        if not changed:
            return {
                "state": "current",
                "reason": "unrelated_architecture_sections_changed_only",
                "required_sections": required,
            }
        return {
            "state": "review_required_architecture_change",
            "reason": "required_architecture_sections_changed",
            "changed_sections": changed,
        }

    if architecture_bound:
        return {
            "state": "review_required_architecture_change",
            "reason": "architecture_bound_skill_baseline_changed_without_section_proof",
        }

    return {
        "state": "current",
        "reason": "baseline_changed_but_skill_not_architecture_bound",
    }


def _linked_learning_architecture(
    c: Any,
    *,
    relation_type: str,
    target_type: str,
    target_id: str,
) -> str | None:
    rows = c.execute(
        """
        SELECT DISTINCT ls.architecture_baseline_hash
        FROM learning_signal_links l
        JOIN learning_signals ls
          ON ls.signal_id=l.signal_id
        WHERE l.relation_type=?
          AND l.target_type=?
          AND l.target_id=?
          AND ls.architecture_baseline_hash IS NOT NULL
        ORDER BY ls.architecture_baseline_hash
        """,
        (relation_type, target_type, target_id),
    ).fetchall()
    values = [
        str(row["architecture_baseline_hash"])
        for row in rows
        if row["architecture_baseline_hash"]
    ]
    return values[0] if len(values) == 1 else None


def _memory_drift(
    root: Path,
    memory_id: int,
    active: dict[str, Any] | None,
) -> dict[str, Any]:
    with connect_read_only(root) as c:
        row = c.execute(
            "SELECT * FROM project_memory WHERE id=?",
            (int(memory_id),),
        ).fetchone()
        if not row:
            raise LearningEffectivenessError("memory_not_found")
        memory = dict(row)

        pinned_hash = _linked_learning_architecture(
            c,
            relation_type="memory_candidate",
            target_type="project_memory",
            target_id=str(int(memory_id)),
        )
        finding_paths = c.execute(
            """
            SELECT DISTINCT pf.path
            FROM learning_signal_links l
            JOIN learning_signals ls
              ON ls.signal_id=l.signal_id
            JOIN project_findings pf
              ON CAST(pf.id AS TEXT)=ls.source_id
            WHERE l.relation_type='memory_candidate'
              AND l.target_type='project_memory'
              AND l.target_id=?
              AND ls.source_type='project_finding'
              AND pf.path IS NOT NULL
              AND pf.path<>''
            ORDER BY pf.path
            """,
            (str(int(memory_id)),),
        ).fetchall()

    if str(memory.get("status") or "") in {"revoked", "stale"}:
        return {
            "state": "stale",
            "reason": "memory_lifecycle_not_active",
            "memory_status": str(memory.get("status") or ""),
        }

    source_path = str(memory.get("source_path") or "")
    paths = [source_path] if source_path else []
    paths.extend(
        str(row["path"])
        for row in finding_paths
        if row["path"]
    )
    missing = sorted(
        {
            path
            for path in paths
            if path and not (root / path).exists()
        }
    )
    if missing:
        return {
            "state": "stale",
            "reason": "referenced_project_artifact_missing",
            "missing_paths": missing,
        }

    if not active:
        return {
            "state": "review_required_architecture_change",
            "reason": "active_architecture_baseline_missing",
        }
    if not pinned_hash:
        return {
            "state": "review_required_architecture_change",
            "reason": "memory_architecture_scope_not_precisely_bound",
        }
    if pinned_hash == str(active["baseline_hash"]):
        return {
            "state": "current",
            "reason": "pinned_architecture_baseline_current",
        }
    return {
        "state": "review_required_architecture_change",
        "reason": "memory_baseline_changed_without_section_level_applicability_proof",
        "pinned_architecture_baseline_hash": pinned_hash,
        "current_architecture_baseline_hash": str(active["baseline_hash"]),
    }


def _finding_drift(
    root: Path,
    finding_id: int,
    active: dict[str, Any] | None,
) -> dict[str, Any]:
    with connect_read_only(root) as c:
        row = c.execute(
            "SELECT * FROM project_findings WHERE id=?",
            (int(finding_id),),
        ).fetchone()
        if not row:
            raise LearningEffectivenessError("finding_not_found")
        finding = dict(row)
        signal_rows = c.execute(
            """
            SELECT DISTINCT architecture_baseline_hash
            FROM learning_signals
            WHERE source_type='project_finding'
              AND source_id=?
              AND architecture_baseline_hash IS NOT NULL
            ORDER BY architecture_baseline_hash
            """,
            (str(int(finding_id)),),
        ).fetchall()

    path = str(finding.get("path") or "")
    if path and not (root / path).exists():
        return {
            "state": "stale",
            "reason": "finding_project_artifact_missing",
            "path": path,
        }

    pinned = [
        str(row["architecture_baseline_hash"])
        for row in signal_rows
        if row["architecture_baseline_hash"]
    ]
    pinned_hash = pinned[0] if len(set(pinned)) == 1 else None
    if not active:
        return {
            "state": "review_required_architecture_change",
            "reason": "active_architecture_baseline_missing",
        }
    if pinned_hash and pinned_hash == str(active["baseline_hash"]):
        return {
            "state": "current",
            "reason": "finding_architecture_baseline_current",
        }
    return {
        "state": "review_required_architecture_change",
        "reason": "finding_architecture_scope_not_precisely_bound",
    }


def knowledge_drift(
    root: Path,
    knowledge_kind: str,
    knowledge_id: str | int,
) -> dict[str, Any]:
    """Evaluate knowledge drift without mutating the artifact lifecycle."""
    _policy(root)
    kind = str(knowledge_kind)
    kid = str(knowledge_id)
    if kind not in SUPPORTED_KINDS:
        raise LearningEffectivenessError("unsupported_knowledge_kind")
    if not kid.isdigit():
        raise LearningEffectivenessError("numeric_knowledge_id_required")

    with connect_read_only(root) as c:
        active = _active_architecture(c)

    if kind == "skill":
        detail = _skill_drift(root, int(kid), active)
    elif kind == "memory":
        detail = _memory_drift(root, int(kid), active)
    else:
        detail = _finding_drift(root, int(kid), active)

    return {
        "ok": True,
        "effectiveness_version": EFFECTIVENESS_VERSION,
        "knowledge_kind": kind,
        "knowledge_id": kid,
        **detail,
        "review_required": detail["state"] != "current",
        "automatic_deactivation": False,
        "automatic_supersede": False,
        "instruction_authority": False,
    }


def learning_assessment(
    root: Path,
    knowledge_kind: str,
    knowledge_id: str | int,
) -> dict[str, Any]:
    """Combine comparative effectiveness and drift into one review-bound assessment."""
    effectiveness = comparative_effectiveness(
        root,
        knowledge_kind,
        knowledge_id,
    )
    drift = knowledge_drift(
        root,
        knowledge_kind,
        knowledge_id,
    )
    review_recommended = bool(
        drift["review_required"]
        or effectiveness["verdict"] == "possibly_ineffective"
    )
    body = {
        "effectiveness_version": EFFECTIVENESS_VERSION,
        "knowledge_kind": str(knowledge_kind),
        "knowledge_id": str(knowledge_id),
        "effectiveness": effectiveness,
        "drift": drift,
        "review_recommended": review_recommended,
        "comparative_not_causal": True,
        "automatic_state_change": False,
        "instruction_authority": False,
    }
    return {
        "ok": True,
        **body,
        "assessment_hash": _sha(body),
    }


def request_learning_review(
    root: Path,
    *,
    knowledge_kind: str,
    knowledge_id: str | int,
    expected_assessment_hash: str,
    task_id: str,
    raised_by_session: str | None = None,
) -> dict[str, Any]:
    """Open an existing Human Decision for one exact current assessment."""
    cfg = _policy(root)
    assessment = learning_assessment(
        root,
        knowledge_kind,
        knowledge_id,
    )
    expected = str(expected_assessment_hash or "").strip().lower()
    if expected != str(assessment["assessment_hash"]):
        raise LearningEffectivenessError(
            "learning_assessment_hash_mismatch"
        )
    if not assessment["review_recommended"]:
        raise LearningEffectivenessError(
            "learning_review_not_required"
        )

    question = (
        "Review governed learning artifact "
        f"{knowledge_kind}:{knowledge_id} for assessment "
        f"{assessment['assessment_hash']} with effectiveness verdict "
        f"{assessment['effectiveness']['verdict']} and drift state "
        f"{assessment['drift']['state']}."
    )
    decision = request_human_decision(
        root,
        str(task_id),
        "post_execution",
        "other",
        "normal",
        question,
        options=list(cfg["review_options"]),
        raised_by_session=raised_by_session,
        blocking=False,
    )
    return {
        "ok": True,
        "review_requested": True,
        "assessment_hash": assessment["assessment_hash"],
        "assessment": assessment,
        "human_decision": decision,
        "automatic_state_change": False,
        "decision_resolution_requires_existing_governance_path": True,
        "instruction_authority": False,
    }


def effectiveness_status(root: Path) -> dict[str, Any]:
    """Return v0.31.3 policy/state summary without lifecycle mutation."""
    cfg = _policy(root)
    with connect_read_only(root) as c:
        usage_count = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM knowledge_usage"
            ).fetchone()["n"]
        )
        outcome_count = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM task_outcomes"
            ).fetchone()["n"]
        )
        skill_evaluation_count = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM skill_evaluation_runs"
            ).fetchone()["n"]
        )
    return {
        "ok": True,
        "effectiveness_version": EFFECTIVENESS_VERSION,
        "schema": 64,
        "knowledge_usage_count": usage_count,
        "task_outcome_count": outcome_count,
        "skill_evaluation_count": skill_evaluation_count,
        "window_days": int(cfg["window_days"]),
        "minimum_treatment_tasks": int(cfg["minimum_treatment_tasks"]),
        "minimum_control_tasks": int(cfg["minimum_control_tasks"]),
        "minimum_effect_size": float(cfg["minimum_effect_size"]),
        "comparative_not_causal": True,
        "automatic_review_request_creation": False,
        "automatic_deactivation": False,
        "automatic_supersede": False,
        "automatic_architecture_mutation": False,
        "mcp_mutation_allowed": False,
        "instruction_authority": False,
        "authority_class": "none",
        "trust_class": "project_evidence",
    }
