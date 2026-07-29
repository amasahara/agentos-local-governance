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

from .db import connect
from .policy import load_policy

AUTOMATED_ONLY_STEPS = {
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
    return {"task_id": task_id, "step_name": step, "status": "done", "completion_source": "auto", "command_name": command_name, "result_hash": digest}


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


def workflow_status(root: Path, task_id: str, workflow_name: str = "default") -> dict[str, Any]:
    """Return ordered workflow progress and provenance validity.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        workflow_name: Workflow name.

    Returns:
        Checklist, pending steps, invalid provenance, and completion state.
    """
    seed_workflow(root, task_id, workflow_name)
    order = load_policy(root)["workflows"][workflow_name]
    with connect(root) as c:
        rows = c.execute(
            """SELECT step_name,status,skip_reason,note,recorded_at,completion_source,
                      evidence_type,evidence_id,result_hash,command_name,exit_code
               FROM workflow_steps WHERE task_id=? AND workflow_name=?""",
            (task_id, workflow_name),
        ).fetchall()
    by_name = {r["step_name"]: dict(r) for r in rows}
    steps = [by_name[name] for name in order]
    pending = [r["step_name"] for r in steps if r["status"] == "pending"]
    invalid = [r["step_name"] for r in steps if r["step_name"] in AUTOMATED_ONLY_STEPS and r["status"] == "done" and (r["completion_source"] != "auto" or not r["result_hash"])]
    return {"task_id": task_id, "workflow_name": workflow_name, "steps": steps, "required_pending": pending, "invalid_provenance": invalid, "complete": not pending and not invalid}


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
    commands = {
        "assess_requirement_clarity": "agentos mark-step --step assess_requirement_clarity --status done --note 'Requirements assessed'",
        "clarify_if_needed": "agentos mark-step --step clarify_if_needed --status skipped --note 'No clarification required'",
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
