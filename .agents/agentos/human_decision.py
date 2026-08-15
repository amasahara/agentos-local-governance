"""
File: .agents/agentos/human_decision.py

Purpose:
    Enforce v0.25.2 requirement-clarification and runtime human-decision gates.

Responsibilities:
    - Persist structured clarity assessments before task approval.
    - Prevent silent material assumptions from becoming implementation authority.
    - Let an AI/session open a blocking decision but never resolve it.
    - Require explicit human confirmation for resolution.
    - Pin local human answers losslessly while external audit stores only hashes/metadata.
    - Revoke task approval when a resolution changes requirements, scope, or architecture.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .db import connect, connect_read_only
from .external_audit import append_signed_event
from .governance_enforcement import governed_mutation

DECISION_TYPES = {
    "requirement_ambiguity", "conflicting_requirements", "acceptance_criterion", "business_rule",
    "architecture_choice", "technology", "dependency", "external_service", "authentication",
    "authorization", "database_schema", "api_contract", "data_migration", "destructive_operation",
    "security_privacy", "scope_change", "undefined_behavior", "unexpected_condition", "other",
}
SEVERITIES = {"normal", "high", "critical"}
IMPACTS = {"none", "requirement_change", "scope_change", "architecture_change"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event(root: Path, decision_id: int | None, event_type: str, payload: dict[str, Any], task_id: str, session_id: str | None = None) -> str:
    body = _canonical(payload)
    digest = _sha(body)
    signed = append_signed_event(root, event_type, {**payload, "event_hash": digest}, task_id, session_id)
    with connect(root) as c:
        c.execute("INSERT INTO human_decision_events(decision_id,event_type,event_json,event_hash,external_event_hash) VALUES(?,?,?,?,?)", (decision_id, event_type, body, digest, signed["event_hash"]))
    return signed["event_hash"]


def record_clarity_assessment(
    root: Path,
    task_id: str,
    assessed_by: str,
    *,
    objective_understood: bool,
    scope_understood: bool,
    constraints_understood: bool,
    acceptance_understood: bool,
    assumptions: list[str] | None = None,
    ambiguities: list[str] | None = None,
    decisions_required: list[str] | None = None,
) -> dict[str, Any]:
    """Persist one structured clarity assessment; any stated assumption is blocking."""
    assumptions = [str(x).strip() for x in (assumptions or []) if str(x).strip()]
    ambiguities = [str(x).strip() for x in (ambiguities or []) if str(x).strip()]
    decisions_required = [str(x).strip() for x in (decisions_required or []) if str(x).strip()]
    understood = all((objective_understood, scope_understood, constraints_understood, acceptance_understood))
    blocking_count = len(assumptions) + len(ambiguities) + len(decisions_required)
    if not understood and blocking_count == 0:
        raise RuntimeError("blocking_question_required_when_clarity_incomplete")
    status = "clear" if understood and blocking_count == 0 else "needs_clarification"
    payload = {
        "task_id": task_id, "status": status,
        "objective_understood": bool(objective_understood), "scope_understood": bool(scope_understood),
        "constraints_understood": bool(constraints_understood), "acceptance_understood": bool(acceptance_understood),
        "assumptions": assumptions, "ambiguities": ambiguities, "decisions_required": decisions_required,
        "blocking_question_count": blocking_count, "assessed_by": assessed_by,
    }
    digest = _sha(_canonical(payload))
    assessment_uuid = str(uuid.uuid4())
    with connect(root, immediate=True) as c:
        if not c.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise RuntimeError(f"task not found: {task_id}")
        c.execute(
            """INSERT INTO task_clarity_assessments(assessment_uuid,task_id,status,objective_understood,scope_understood,constraints_understood,acceptance_understood,assumptions_json,ambiguities_json,decisions_required_json,blocking_question_count,assessed_by,assessment_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (assessment_uuid, task_id, status, int(objective_understood), int(scope_understood), int(constraints_understood), int(acceptance_understood), _canonical(assumptions), _canonical(ambiguities), _canonical(decisions_required), blocking_count, assessed_by, digest),
        )
    signed = append_signed_event(root, "human.clarity_assessed", {"assessment_uuid": assessment_uuid, "task_id": task_id, "status": status, "blocking_question_count": blocking_count, "assessment_hash": digest}, task_id, None)
    if status != "clear":
        questions = []
        questions.extend(("Confirm or correct this material assumption: " + value, "requirement_ambiguity") for value in assumptions)
        questions.extend((value, "requirement_ambiguity") for value in ambiguities)
        questions.extend((value, "requirement_ambiguity") for value in decisions_required)
        for question, decision_type in questions:
            request_human_decision(root, task_id, "pre_execution", decision_type, "normal", question, raised_by_session=assessed_by, blocking=True)
    # Bind the clarity assessment to the existing workflow without allowing manual self-attestation.
    try:
        from .workflow import complete_automated_step, mark_step, seed_workflow
        seed_workflow(root, task_id)
        complete_automated_step(root, task_id, "assess_requirement_clarity", "clarity-assess", {"assessment_uuid": assessment_uuid, "status": status, "assessment_hash": digest})
        if status == "clear":
            with connect(root) as c:
                c.execute(
                    """UPDATE workflow_steps SET status='skipped',skip_reason='Structured clarity assessment is clear.',note='No clarification required.',recorded_at=CURRENT_TIMESTAMP,completion_source='system',evidence_type='clarity_assessment',evidence_id=?,result_hash=?,command_name='clarity-assess',exit_code=0 WHERE task_id=? AND workflow_name='default' AND step_name='clarify_if_needed'""",
                    (assessment_uuid, digest, task_id),
                )
            skip_payload = {
                "task_id": task_id,
                "workflow_name": "default",
                "step_name": "clarify_if_needed",
                "status": "skipped",
                "completion_source": "system",
                "command_name": "clarity-assess",
                "result_hash": digest,
                "evidence_type": "clarity_assessment",
                "evidence_id": assessment_uuid,
            }
            skip_event = append_signed_event(
                root,
                "governance.workflow_step_skipped",
                skip_payload,
                task_id,
                None,
            )
            from .security import link_signed_state
            row_key = f"{task_id}:default:clarify_if_needed"
            with connect(root) as c:
                c.execute(
                    """UPDATE workflow_steps
                       SET external_event_hash=?,verification_status='verified'
                       WHERE task_id=? AND workflow_name='default'
                         AND step_name='clarify_if_needed'""",
                    (skip_event["event_hash"], task_id),
                )
            link_signed_state(
                root,
                "workflow_steps",
                row_key,
                skip_event["event_hash"],
            )
    except Exception:
        # Schema-level clarity authority remains valid even for minimal library-style roots without workflow state.
        pass
    return {**payload, "assessment_uuid": assessment_uuid, "assessment_hash": digest, "external_event_hash": signed["event_hash"]}


def clarity_gate_status(root: Path, task_id: str, read_only: bool = False) -> dict[str, Any]:
    """Return whether a task has clear requirements and no open blockers.

    Args:
        root: Project root.
        task_id: Governed task identifier.
        read_only: Use strict read-only database access when true.

    Returns:
        Gate readiness, latest assessment, and open-blocker count.
    """
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        row = c.execute("SELECT * FROM task_clarity_assessments WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
        open_count = int(c.execute("SELECT COUNT(*) AS n FROM human_decision_requests WHERE task_id=? AND status='open' AND blocking=1", (task_id,)).fetchone()["n"])
    latest = dict(row) if row else None
    ready = bool(latest and latest["status"] == "clear" and int(latest["blocking_question_count"]) == 0 and open_count == 0)
    return {"ok": True, "task_id": task_id, "ready": ready, "latest_assessment": latest, "open_blocking_decisions": open_count, "reason": "clear" if ready else "clarity_or_human_decision_pending"}


def decision_gate_status(root: Path, task_id: str, read_only: bool = False) -> dict[str, Any]:
    """Read unresolved blocking human decisions for a task.

    Args:
        root: Project root.
        task_id: Governed task identifier.
        read_only: Use strict read-only database access when true.

    Returns:
        Blocked state and privacy-safe decision metadata.
    """
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        rows = c.execute("SELECT decision_uuid,phase,decision_type,severity,question_hash,architecture_section_ids_json,created_at FROM human_decision_requests WHERE task_id=? AND status='open' AND blocking=1 ORDER BY id", (task_id,)).fetchall()
    return {"ok": True, "task_id": task_id, "blocked": bool(rows), "open_blocking_count": len(rows), "decisions": [dict(r) for r in rows]}


def request_human_decision(
    root: Path,
    task_id: str,
    phase: str,
    decision_type: str,
    severity: str,
    question: str,
    *,
    options: list[str] | None = None,
    recommendation: str | None = None,
    recommendation_rationale: str | None = None,
    requirement_ids: list[str] | None = None,
    architecture_section_ids: list[str] | None = None,
    raised_by_session: str | None = None,
    blocking: bool = True,
) -> dict[str, Any]:
    """Open a monotonic human-decision blocker; callers cannot resolve it here."""
    if decision_type not in DECISION_TYPES:
        raise RuntimeError("invalid_human_decision_type")
    if severity not in SEVERITIES:
        raise RuntimeError("invalid_human_decision_severity")
    question = question.strip()
    if not question:
        raise RuntimeError("human_decision_question_required")
    architecture_section_ids = list(architecture_section_ids or [])
    from .architecture_contract import SECTION_BY_ID
    unknown = sorted(set(architecture_section_ids) - set(SECTION_BY_ID))
    if unknown:
        raise RuntimeError(f"unknown_architecture_sections:{unknown}")
    with connect(root, immediate=True) as c:
        task = c.execute("SELECT request FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise RuntimeError(f"task not found: {task_id}")
        plan = c.execute("SELECT plan_hash FROM task_plans WHERE task_id=? AND status='active' ORDER BY revision DESC LIMIT 1", (task_id,)).fetchone()
        arch = c.execute("SELECT baseline_hash FROM architecture_baselines WHERE status='active' LIMIT 1").fetchone()
        decision_uuid = str(uuid.uuid4())
        qhash = _sha(question)
        duplicate = c.execute("SELECT id,decision_uuid FROM human_decision_requests WHERE task_id=? AND question_hash=? AND status='open' AND blocking=? ORDER BY id DESC LIMIT 1", (task_id, qhash, int(blocking))).fetchone()
        if duplicate:
            return {"ok": True, "existing": True, "decision_id": int(duplicate["id"]), "decision_uuid": duplicate["decision_uuid"], "task_id": task_id, "status": "open", "blocking": bool(blocking), "question_hash": qhash}
        open_count = int(c.execute("SELECT COUNT(*) AS n FROM human_decision_requests WHERE task_id=? AND status='open' AND blocking=1", (task_id,)).fetchone()["n"])
        if blocking and open_count >= 32:
            raise RuntimeError("human_decision_open_limit_exceeded")
        cur = c.execute(
            """INSERT INTO human_decision_requests(decision_uuid,task_id,phase,decision_type,severity,blocking,question,question_hash,options_json,recommendation,recommendation_rationale,requirement_ids_json,architecture_section_ids_json,task_request_hash,plan_hash,architecture_baseline_hash,raised_by_session)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (decision_uuid, task_id, phase, decision_type, severity, int(blocking), question, qhash, _canonical(options or []), recommendation, recommendation_rationale, _canonical(requirement_ids or []), _canonical(architecture_section_ids), _sha(str(task["request"])), plan["plan_hash"] if plan else None, arch["baseline_hash"] if arch else None, raised_by_session),
        )
        decision_id = int(cur.lastrowid)
    external = _event(root, decision_id, "human.decision_requested", {"decision_uuid": decision_uuid, "task_id": task_id, "phase": phase, "decision_type": decision_type, "severity": severity, "blocking": bool(blocking), "question_hash": qhash, "architecture_sections": architecture_section_ids}, task_id, raised_by_session)
    return {"ok": True, "decision_id": decision_id, "decision_uuid": decision_uuid, "task_id": task_id, "status": "open", "blocking": bool(blocking), "question_hash": qhash, "external_event_hash": external}


@governed_mutation("human.decision.resolve")
def resolve_human_decision(
    root: Path,
    decision_uuid: str,
    answer_text: str,
    resolved_by: str,
    impact_classification: str,
    *,
    selected_option: str | None = None,
    human_confirmed: bool = False,
) -> dict[str, Any]:
    """Resolve one decision with explicit human authority and revalidation impact."""
    if not human_confirmed:
        raise RuntimeError("explicit_human_confirmation_required")
    if impact_classification not in IMPACTS:
        raise RuntimeError("invalid_decision_impact_classification")
    answer_text = answer_text.strip()
    if not answer_text:
        raise RuntimeError("human_decision_answer_required")
    answer_hash = _sha(answer_text)
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM human_decision_requests WHERE decision_uuid=?", (decision_uuid,)).fetchone()
        if not row:
            raise RuntimeError("human_decision_not_found")
        if row["status"] != "open":
            raise RuntimeError("human_decision_not_open")
        c.execute("INSERT INTO human_decision_resolutions(decision_id,selected_option,answer_text,answer_hash,resolved_by,human_confirmed,impact_classification) VALUES(?,?,?,?,?,1,?)", (row["id"], selected_option, answer_text, answer_hash, resolved_by, impact_classification))
        c.execute("UPDATE human_decision_requests SET status='resolved',resolved_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
        if impact_classification != "none":
            c.execute("UPDATE tasks SET approved=0 WHERE id=?", (row["task_id"],))
            c.execute("UPDATE task_plans SET status='superseded' WHERE task_id=? AND status IN ('submitted','active')", (row["task_id"],))
    external = _event(root, int(row["id"]), "human.decision_resolved", {"decision_uuid": decision_uuid, "task_id": row["task_id"], "answer_hash": answer_hash, "resolved_by": resolved_by, "impact_classification": impact_classification}, row["task_id"], None)
    action = {"none": "resume_after_revalidation", "requirement_change": "requirement_revision_and_reapproval_required", "scope_change": "task_reapproval_required", "architecture_change": "architecture_change_and_reapproval_required"}[impact_classification]
    return {"ok": True, "decision_uuid": decision_uuid, "status": "resolved", "answer_hash": answer_hash, "impact_classification": impact_classification, "resume_action": action, "task_approval_revoked": impact_classification != "none", "external_event_hash": external}


def decision_list(root: Path, task_id: str, read_only: bool = False) -> list[dict[str, Any]]:
    """List privacy-safe decision metadata for one task.

    Args:
        root: Project root.
        task_id: Governed task identifier.
        read_only: Use strict read-only database access when true.

    Returns:
        Ordered decision summaries without raw question/answer text.
    """
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        rows = c.execute("SELECT decision_uuid,task_id,phase,decision_type,severity,blocking,question_hash,status,created_at,resolved_at FROM human_decision_requests WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
    return [dict(r) for r in rows]


def decision_show(root: Path, decision_uuid: str, read_only: bool = False) -> dict[str, Any]:
    """Read one local human-decision record including its exact human answer.

    Args:
        root: Project root.
        decision_uuid: Stable decision UUID.
        read_only: Use strict read-only database access when true.

    Returns:
        Local decision request and optional human resolution.

    Raises:
        RuntimeError: When the decision does not exist.
    """
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        row = c.execute("SELECT * FROM human_decision_requests WHERE decision_uuid=?", (decision_uuid,)).fetchone()
        if not row:
            raise RuntimeError("human_decision_not_found")
        resolution = c.execute("SELECT selected_option,answer_text,answer_hash,resolved_by,impact_classification,created_at FROM human_decision_resolutions WHERE decision_id=?", (row["id"],)).fetchone()
    result = dict(row)
    for key in ("options_json", "requirement_ids_json", "architecture_section_ids_json"):
        result[key[:-5] if key.endswith("_json") else key] = json.loads(result.pop(key))
    result["resolution"] = dict(resolution) if resolution else None
    return result


def grill_me(root: Path, task_id: str, read_only: bool = False) -> dict[str, Any]:
    """Return all unresolved human questions plus the latest structured clarity state."""
    gate = clarity_gate_status(root, task_id, read_only=read_only)
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        rows = c.execute("SELECT decision_uuid,phase,decision_type,severity,question,options_json,recommendation,recommendation_rationale,architecture_section_ids_json,created_at FROM human_decision_requests WHERE task_id=? AND status='open' AND blocking=1 ORDER BY id", (task_id,)).fetchall()
    questions=[]
    for r in rows:
        x=dict(r); x["options"]=json.loads(x.pop("options_json")); x["architecture_section_ids"]=json.loads(x.pop("architecture_section_ids_json")); questions.append(x)
    return {"ok": True, "task_id": task_id, "ready": gate["ready"], "clarity": gate["latest_assessment"], "questions": questions, "open_blocking_count": len(questions)}
