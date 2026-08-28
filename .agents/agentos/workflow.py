"""
File: .agents/agentos/workflow.py

Purpose:
    Persist session-scoped task state and enforce workflow provenance.

Responsibilities:
    - Isolate current-task state per session.
    - Seed and update workflow checklist rows.
    - Prevent manual self-attestation for automated gates.
    - Preserve command evidence used by the final report gate.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect, connect_read_only
from .external_audit import append_signed_event
from .security import link_signed_state
from .policy import load_policy

AUTOMATED_ONLY_STEPS = {
    "assess_requirement_clarity",
    "approve_task",
    "build_or_update_local_index",
    "prepare_change",
    "execute_guarded",
    "documentation_check",
    "tests",
    "evidence_review",
    "synchronize",
}


def normalize_session_id(session_id: str | None = None) -> str:
    """Return a filesystem-safe session identifier.

    Args:
        session_id: Optional caller supplied session identifier.

    Returns:
        Stable session identifier.
    """
    raw = session_id or os.environ.get("AGENTOS_SESSION_ID") or "default"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw.strip())
    if not safe:
        raise RuntimeError("session_id must not be empty")
    return safe[:128]


def _current_path(root: Path, session_id: str | None = None) -> Path:
    session = normalize_session_id(session_id)
    path = root.resolve() / ".agents" / "runtime" / "sessions" / session / "current_task.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def set_current_task(root: Path, task_id: str, set_by: str, session_id: str | None = None) -> dict[str, Any]:
    """Persist the active task for one session.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        set_by: Command or actor that selected the task.
        session_id: Optional session identifier.

    Returns:
        Current-task metadata.
    """
    with connect(root) as c:
        row = c.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise RuntimeError(f"task not found: {task_id}")
    session = normalize_session_id(session_id)
    payload = {"task_id": task_id, "session_id": session, "set_at": datetime.now(timezone.utc).isoformat(), "set_by": set_by}
    _current_path(root, session).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def current_task_id(root: Path, session_id: str | None = None) -> str | None:
    """Return the active task identifier for one session.

    Args:
        root: Project root.
        session_id: Optional session identifier.

    Returns:
        Active task identifier or None.
    """
    path = _current_path(root, session_id)
    if not path.exists():
        return None
    try:
        return str(json.loads(path.read_text(encoding="utf-8"))["task_id"])
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("current_task.json is invalid") from exc


def resolve_task_id(root: Path, task_id: str | None, session_id: str | None = None) -> str:
    """Resolve an explicit task ID or session-scoped current task.

    Args:
        root: Project root.
        task_id: Optional explicit task identifier.
        session_id: Optional session identifier.

    Returns:
        Resolved task identifier.
    """
    resolved = task_id or current_task_id(root, session_id)
    if not resolved:
        raise RuntimeError("no task selected; pass --task-id or run use-task")
    return resolved


def seed_workflow(root: Path, task_id: str, workflow_name: str = "default") -> None:
    """Seed workflow checklist rows for a task.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        workflow_name: Workflow key in governance policy.

    Returns:
        None.
    """
    steps = load_policy(root)["workflows"][workflow_name]
    with connect(root) as c:
        for step in steps:
            status = "done" if step == "receive_request" else "pending"
            source = "system" if status == "done" else "none"
            c.execute(
                "INSERT OR IGNORE INTO workflow_steps(task_id,workflow_name,step_name,status,note,completion_source,command_name) VALUES(?,?,?,?,?,?,?)",
                (task_id, workflow_name, step, status, "Task request recorded." if status == "done" else None, source, "start-task" if status == "done" else None),
            )


def _result_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def complete_automated_step(
    root: Path,
    task_id: str,
    step: str,
    command_name: str,
    result: Any,
    exit_code: int = 0,
    evidence_type: str = "command_result",
    evidence_id: str | None = None,
    workflow_name: str = "default",
) -> dict[str, Any]:
    """Complete an automated step with verifiable command provenance.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        step: Automated workflow step.
        command_name: Command that produced the result.
        result: Structured command result.
        exit_code: Process exit code.
        evidence_type: Evidence category.
        evidence_id: Optional linked record identifier.
        workflow_name: Workflow name.

    Returns:
        Updated step metadata.
    """
    if step not in AUTOMATED_ONLY_STEPS:
        raise RuntimeError(f"step is not automated-only: {step}")
    if exit_code != 0:
        raise RuntimeError(f"cannot complete {step}: command failed")
    seed_workflow(root, task_id, workflow_name)
    digest = _result_hash(result)
    with connect(root) as c:
        cur = c.execute(
            """UPDATE workflow_steps
               SET status='done',skip_reason=NULL,note=?,recorded_at=CURRENT_TIMESTAMP,
                   completion_source='auto',evidence_type=?,evidence_id=?,result_hash=?,command_name=?,exit_code=?
               WHERE task_id=? AND workflow_name=? AND step_name=?""",
            (f"Completed by {command_name}.", evidence_type, evidence_id, digest, command_name, exit_code, task_id, workflow_name, step),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"workflow step not found: {step}")
    payload = {"task_id": task_id, "workflow_name": workflow_name, "step_name": step, "status": "done", "completion_source": "auto", "command_name": command_name, "result_hash": digest}
    event = append_signed_event(root, "governance.workflow_step_completed", payload, task_id, None)
    row_key = f"{task_id}:{workflow_name}:{step}"
    with connect(root) as c:
        c.execute("UPDATE workflow_steps SET external_event_hash=?,verification_status='verified' WHERE task_id=? AND workflow_name=? AND step_name=?", (event["event_hash"], task_id, workflow_name, step))
    link_signed_state(root, "workflow_steps", row_key, event["event_hash"])
    return {**payload, "external_event_hash": event["event_hash"], "verification_status": "verified"}


def mark_step(root: Path, task_id: str, step: str, status: str, note: str | None = None, workflow_name: str = "default") -> dict[str, Any]:
    """Mark a manual workflow step done or any permitted step skipped.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        step: Workflow step name.
        status: Either done or skipped.
        note: Required explanation.
        workflow_name: Workflow name.

    Returns:
        Updated step metadata.
    """
    if status not in {"done", "skipped"}:
        raise RuntimeError("status must be done or skipped")
    if not (note or "").strip():
        raise RuntimeError("note is required for manual workflow updates")
    if status == "done" and step in AUTOMATED_ONLY_STEPS:
        raise RuntimeError(f"step {step} can only be completed by its canonical AgentOS command")
    seed_workflow(root, task_id, workflow_name)
    with connect(root) as c:
        cur = c.execute(
            """UPDATE workflow_steps
               SET status=?,skip_reason=?,note=?,recorded_at=CURRENT_TIMESTAMP,
                   completion_source='manual',evidence_type='manual_note',evidence_id=NULL,
                   result_hash=?,command_name='mark-step',exit_code=0
               WHERE task_id=? AND workflow_name=? AND step_name=?""",
            (status, note if status == "skipped" else None, note, _result_hash({"status": status, "note": note}), task_id, workflow_name, step),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"workflow step not found: {step}")
    return {"task_id": task_id, "workflow_name": workflow_name, "step_name": step, "status": status, "note": note, "completion_source": "manual"}



def _table_exists(c, name: str) -> bool:
    return bool(c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (str(name),),
    ).fetchone())


def _workflow_rows(
    root: Path,
    task_id: str,
    workflow_name: str,
    *,
    seed: bool = True,
):
    if seed:
        seed_workflow(root, task_id, workflow_name)
    order = load_policy(root)["workflows"][workflow_name]
    connector = connect if seed else connect_read_only
    with connector(root) as c:
        rows = c.execute(
            """SELECT step_name,status,skip_reason,note,recorded_at,completion_source,
                      evidence_type,evidence_id,result_hash,command_name,exit_code,
                      verification_status,external_event_hash
               FROM workflow_steps WHERE task_id=? AND workflow_name=?""",
            (task_id, workflow_name),
        ).fetchall()
    by_name = {r["step_name"]: dict(r) for r in rows}
    missing = [name for name in order if name not in by_name]
    if missing:
        if not seed:
            raise RuntimeError("workflow_not_seeded:" + ",".join(missing))
        raise RuntimeError("workflow_seed_incomplete:" + ",".join(missing))
    steps = [by_name[name] for name in order]
    pending = [r["step_name"] for r in steps if r["status"] == "pending"]
    invalid = [
        r["step_name"] for r in steps
        if r["step_name"] in AUTOMATED_ONLY_STEPS
        and r["status"] == "done"
        and (r["completion_source"] != "auto" or not r["result_hash"])
    ]
    return steps, pending, invalid


def workflow_completion_subject(
    root: Path,
    task_id: str,
    workflow_name: str = "default",
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    """Build a deterministic pre-report completion subject."""
    steps, _, _ = _workflow_rows(
        root,
        task_id,
        workflow_name,
        seed=not read_only,
    )
    pre_report = []
    for row in steps:
        if row["step_name"] == "report":
            continue
        pre_report.append({
            "step_name": row["step_name"],
            "status": row["status"],
            "skip_reason": row["skip_reason"],
            "note_hash": _result_hash(row["note"]) if row["note"] is not None else None,
            "completion_source": row["completion_source"],
            "evidence_type": row["evidence_type"],
            "evidence_id": row["evidence_id"],
            "result_hash": row["result_hash"],
            "command_name": row["command_name"],
            "exit_code": row["exit_code"],
            "verification_status": row["verification_status"],
            "external_event_hash": row["external_event_hash"],
        })
    connector = connect_read_only if read_only else connect
    with connector(root) as c:
        task = c.execute(
            "SELECT id,request,approved,approved_scope,owner_session_id,task_state FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        if not task:
            raise RuntimeError("task not found")
        active_plan = None
        if _table_exists(c, "task_plans"):
            row = c.execute(
                "SELECT id,revision,status,plan_hash FROM task_plans WHERE task_id=? AND status='active' ORDER BY revision DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            active_plan = dict(row) if row else None
        claims = []
        if _table_exists(c, "claims") and _table_exists(c, "claim_evidence") and _table_exists(c, "tool_calls"):
            for claim in c.execute(
                "SELECT id,claim_text,claim_type,risk,created_at FROM claims WHERE task_id=? ORDER BY id",
                (task_id,),
            ).fetchall():
                evidence = [
                    _result_hash(dict(e))
                    for e in c.execute(
                        """SELECT ce.tool_call_id,ce.evidence_role,tc.tool_name,tc.classification,
                                  tc.input_json,tc.success,tc.output_summary,tc.created_at
                           FROM claim_evidence ce JOIN tool_calls tc ON tc.id=ce.tool_call_id
                           WHERE ce.claim_id=? ORDER BY ce.tool_call_id,ce.evidence_role""",
                        (int(claim["id"]),),
                    ).fetchall()
                ]
                claims.append({
                    "claim_id": int(claim["id"]),
                    "claim_hash": _result_hash({
                        "claim_text": claim["claim_text"],
                        "claim_type": claim["claim_type"],
                        "risk": claim["risk"],
                        "created_at": claim["created_at"],
                        "evidence": evidence,
                    }),
                })
        tools = []
        if _table_exists(c, "tool_calls"):
            tools = [
                {"id": int(r["id"]), "hash": _result_hash(dict(r))}
                for r in c.execute(
                    "SELECT id,tool_name,classification,input_json,success,output_summary,created_at FROM tool_calls WHERE task_id=? ORDER BY id",
                    (task_id,),
                ).fetchall()
            ]
        egress = []
        if _table_exists(c, "egress_events"):
            egress = [
                {"id": int(r["id"]), "hash": _result_hash(dict(r))}
                for r in c.execute("SELECT * FROM egress_events WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
            ]
        files = []
        if _table_exists(c, "file_versions"):
            files = [
                {"id": int(r["id"]), "hash": _result_hash(dict(r))}
                for r in c.execute(
                    """SELECT id,path,version,content_hash,previous_hash,session_id,created_at
                       FROM file_versions WHERE task_id=? ORDER BY id""",
                    (task_id,),
                ).fetchall()
            ]
    return {
        "workflow_name": workflow_name,
        "task_hash": _result_hash(dict(task)),
        "pre_report_steps": pre_report,
        "active_plan": active_plan,
        "claims": claims,
        "tool_calls": tools,
        "egress_events": egress,
        "file_versions": files,
    }


def workflow_completion_verification_status(
    root: Path,
    task_id: str,
    workflow_name: str = "default",
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    from .completion_verification import completion_status
    return completion_status(
        root,
        subject_type="workflow",
        subject_id=f"{task_id}:{workflow_name}",
        current_subject_payload=workflow_completion_subject(
            root,
            task_id,
            workflow_name,
            read_only=read_only,
        ),
    )


def workflow_completion_request(root: Path, task_id: str, producer_session_id: str, workflow_name: str = "default") -> dict[str, Any]:
    _, pending, invalid = _workflow_rows(root, task_id, workflow_name)
    if [x for x in pending if x != "report"] or invalid:
        raise PermissionError("workflow_completion_candidate_not_ready")
    from .completion_verification import request_completion
    return request_completion(
        root,
        subject_type="workflow",
        subject_id=f"{task_id}:{workflow_name}",
        task_id=task_id,
        producer_task_id=task_id,
        producer_session_id=producer_session_id,
        subject_payload=workflow_completion_subject(root, task_id, workflow_name),
        required_checks=["evidence", "requirements", "tests"],
    )


def workflow_completion_verify(root: Path, request_id: str, verifier_task_id: str, verifier_session_id: str, *, verdict: str, checks: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    from .completion_verification import verify_completion
    with connect(root) as c:
        request = c.execute(
            "SELECT subject_type,subject_id FROM completion_verification_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if not request:
            raise ValueError("completion_verification_request_not_found")
        if request["subject_type"] != "workflow":
            raise PermissionError("workflow_completion_request_type_required")
        task_id, workflow_name = str(request["subject_id"]).rsplit(":", 1)
    return verify_completion(
        root,
        request_id=request_id,
        verifier_task_id=verifier_task_id,
        verifier_session_id=verifier_session_id,
        observed_subject_payload=workflow_completion_subject(root, task_id, workflow_name),
        verdict=verdict,
        checks=checks,
        evidence=evidence,
    )


def bind_workflow_report_verification(root: Path, task_id: str, workflow_name: str = "default") -> dict[str, Any]:
    verification = workflow_completion_verification_status(root, task_id, workflow_name)
    if not verification.get("schema_available"):
        raise PermissionError("independent_completion_verification_schema_required")
    if not verification.get("accepted"):
        raise PermissionError(str(verification.get("reason") or "independent_completion_verification_required"))
    request_id = str(verification["request"]["request_id"])
    result_hash = str(verification["attempt"]["result_hash"])
    with connect(root, immediate=True) as c:
        columns = {str(r["name"]) for r in c.execute("PRAGMA table_info(workflow_steps)").fetchall()}
        if not {"completion_verification_request_id", "completion_verification_result_hash"} <= columns:
            raise PermissionError("independent_completion_verification_schema_required")
        cur = c.execute(
            """UPDATE workflow_steps
               SET completion_verification_request_id=?,completion_verification_result_hash=?
               WHERE task_id=? AND workflow_name=? AND step_name='report' AND status='done'""",
            (request_id, result_hash, task_id, workflow_name),
        )
        if cur.rowcount != 1:
            raise PermissionError("report_step_must_be_done_before_verification_binding")
    return {
        "completion_verification_request_id": request_id,
        "completion_verification_result_hash": result_hash,
    }


def workflow_status(root: Path, task_id: str, workflow_name: str = "default") -> dict[str, Any]:
    """Return workflow progress plus independent completion state."""
    steps, pending, invalid = _workflow_rows(root, task_id, workflow_name)
    pending_before_report = [x for x in pending if x != "report"]
    candidate_ready = not pending_before_report and not invalid
    verification = workflow_completion_verification_status(root, task_id, workflow_name)
    enforced = bool(verification.get("schema_available"))
    report_request_id = None
    report_result_hash = None
    report_binding_current = False
    if enforced:
        with connect(root) as c:
            columns = {str(r["name"]) for r in c.execute("PRAGMA table_info(workflow_steps)").fetchall()}
            if {"completion_verification_request_id", "completion_verification_result_hash"} <= columns:
                pin = c.execute(
                    """SELECT completion_verification_request_id,completion_verification_result_hash
                       FROM workflow_steps WHERE task_id=? AND workflow_name=? AND step_name='report'""",
                    (task_id, workflow_name),
                ).fetchone()
                if pin:
                    report_request_id = pin["completion_verification_request_id"]
                    report_result_hash = pin["completion_verification_result_hash"]
        if verification.get("accepted") and verification.get("request") and verification.get("attempt"):
            report_binding_current = (
                str(report_request_id or "") == str(verification["request"]["request_id"])
                and str(report_result_hash or "") == str(verification["attempt"]["result_hash"])
            )
    legacy_complete = not pending and not invalid
    independent_complete = legacy_complete and bool(verification.get("accepted")) and report_binding_current
    return {
        "task_id": task_id,
        "workflow_name": workflow_name,
        "steps": steps,
        "required_pending": pending,
        "required_pending_before_report": pending_before_report,
        "invalid_provenance": invalid,
        "steps_complete": not pending,
        "provenance_valid": not invalid,
        "completion_candidate_ready": candidate_ready,
        "independent_completion_enforced": enforced,
        "completion_verification": {
            "schema_available": bool(verification.get("schema_available")),
            "accepted": bool(verification.get("accepted")),
            "current": bool(verification.get("current")),
            "reason": verification.get("reason"),
            "request_id": verification["request"]["request_id"] if verification.get("request") else None,
            "verdict": verification["attempt"]["verdict"] if verification.get("attempt") else None,
            "result_hash": verification["attempt"]["result_hash"] if verification.get("attempt") else None,
        },
        "report_completion_verification": {
            "request_id": report_request_id,
            "result_hash": report_result_hash,
            "current": report_binding_current,
        },
        "complete": independent_complete if enforced else legacy_complete,
    }

def next_step(root: Path, task_id: str) -> dict[str, Any]:
    """Return the next pending workflow step and canonical command.

    Args:
        root: Project root.
        task_id: Existing task identifier.

    Returns:
        Next-step guidance.
    """
    status = workflow_status(root, task_id)
    step = status["required_pending"][0] if status["required_pending"] else None
    if status["independent_completion_enforced"] and status["completion_candidate_ready"] and not status["completion_verification"]["accepted"]:
        return {"task_id": task_id, "next_step": "completion_verification", "suggested_command": "agentos completion-request", "why": "Independent completion verification is required before the terminal report."}
    if status["independent_completion_enforced"] and not step and not status["complete"]:
        if status["completion_verification"]["accepted"]:
            return {"task_id": task_id, "next_step": "report", "suggested_command": "agentos report", "why": "The current independent verification receipt must be consumed and pinned by the terminal report."}
        return {"task_id": task_id, "next_step": "completion_verification", "suggested_command": "agentos completion-request", "why": "Completion verification is missing or stale."}
    commands = {
        "assess_requirement_clarity": "agentos clarity-assess --objective-understood --scope-understood --constraints-understood --acceptance-understood --assessed-by HUMAN_OR_AGENT",
        "clarify_if_needed": "agentos grill-me",
        "approve_task": "agentos approve-task --scope '[\"src\",\"tests\"]'",
        "detect_environment": "agentos mark-step --step detect_environment --status done --note 'Environment detected'",
        "build_or_update_local_index": "agentos index-build src",
        "prepare_change": "agentos prepare-change --operation modify --target PATH --intent INTENT",
        "execute_guarded": "agentos guard-tool --tool TOOL --args '{}' then agentos complete-tool --execution-token TOKEN",
        "documentation_check": "agentos docs-scan --scope src",
        "tests": "agentos run-tests",
        "evidence_review": "agentos record-claim ...",
        "egress_review": "agentos mark-step --step egress_review --status skipped --note 'No network calls'",
        "structural_review": "agentos mark-step --step structural_review --status done --note 'Structure reviewed'",
        "synchronize": "agentos sync-check",
        "report": "agentos report",
    }
    return {"task_id": task_id, "next_step": step, "suggested_command": commands.get(step), "why": "This is the first pending step in the configured workflow." if step else "Workflow is complete."}
