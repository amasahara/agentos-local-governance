"""
File: .agents/agentos/workflow.py

Purpose:
    Persist task heartbeat state and enforce workflow progress outside LLM context.

Responsibilities:
    - Manage current-task runtime state.
    - Seed and update workflow checklist rows.
    - Report task context, next required step, and final completion gates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect
from .policy import load_policy


def _current_path(root: Path) -> Path:
    path = root.resolve() / ".agents" / "runtime" / "current_task.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def set_current_task(root: Path, task_id: str, set_by: str) -> dict[str, Any]:
    """Persist the active task for later CLI commands.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        set_by: Command or actor that selected the task.

    Returns:
        Current-task metadata.
    """
    with connect(root) as c:
        row = c.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise RuntimeError(f"task not found: {task_id}")
    payload = {"task_id": task_id, "set_at": datetime.now(timezone.utc).isoformat(), "set_by": set_by}
    _current_path(root).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def current_task_id(root: Path) -> str | None:
    """Return the active task identifier when one is selected.

    Args:
        root: Project root.

    Returns:
        Active task identifier or None.
    """
    path = _current_path(root)
    if not path.exists():
        return None
    try:
        return str(json.loads(path.read_text(encoding="utf-8"))["task_id"])
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("current_task.json is invalid") from exc


def resolve_task_id(root: Path, task_id: str | None) -> str:
    """Resolve an explicit task ID or the persisted current task.

    Args:
        root: Project root.
        task_id: Optional explicit task identifier.

    Returns:
        Resolved task identifier.
    """
    resolved = task_id or current_task_id(root)
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
            c.execute(
                "INSERT OR IGNORE INTO workflow_steps(task_id,workflow_name,step_name,status,note) VALUES(?,?,?,?,?)",
                (task_id, workflow_name, step, status, "Task request recorded." if status == "done" else None),
            )


def mark_step(root: Path, task_id: str, step: str, status: str, note: str | None = None, workflow_name: str = "default") -> dict[str, Any]:
    """Mark a workflow step done or skipped with an auditable note.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        step: Workflow step name.
        status: Either done or skipped.
        note: Explanation; required for skipped steps.
        workflow_name: Workflow name.

    Returns:
        Updated step metadata.
    """
    if status not in {"done", "skipped"}:
        raise RuntimeError("status must be done or skipped")
    if status == "skipped" and not (note or "").strip():
        raise RuntimeError("note is required when status is skipped")
    seed_workflow(root, task_id, workflow_name)
    with connect(root) as c:
        cur = c.execute(
            "UPDATE workflow_steps SET status=?,skip_reason=?,note=?,recorded_at=CURRENT_TIMESTAMP WHERE task_id=? AND workflow_name=? AND step_name=?",
            (status, note if status == "skipped" else None, note, task_id, workflow_name, step),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"workflow step not found: {step}")
    return {"task_id": task_id, "workflow_name": workflow_name, "step_name": step, "status": status, "note": note}


def workflow_status(root: Path, task_id: str, workflow_name: str = "default") -> dict[str, Any]:
    """Return ordered workflow progress for a task.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        workflow_name: Workflow name.

    Returns:
        Checklist, pending steps, and completion state.
    """
    seed_workflow(root, task_id, workflow_name)
    order = load_policy(root)["workflows"][workflow_name]
    with connect(root) as c:
        rows = c.execute(
            "SELECT step_name,status,skip_reason,note,recorded_at FROM workflow_steps WHERE task_id=? AND workflow_name=?",
            (task_id, workflow_name),
        ).fetchall()
    by_name = {r["step_name"]: dict(r) for r in rows}
    steps = [by_name[name] for name in order]
    pending = [r["step_name"] for r in steps if r["status"] == "pending"]
    return {"task_id": task_id, "workflow_name": workflow_name, "steps": steps, "required_pending": pending, "complete": not pending}


def next_step(root: Path, task_id: str) -> dict[str, Any]:
    """Return the next pending workflow step and suggested command.

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
        "execute_guarded": "agentos record-tool --tool TOOL --success --output SUMMARY",
        "documentation_check": "agentos docs-scan --scope src",
        "tests": "agentos run-tests",
        "evidence_review": "agentos mark-step --step evidence_review --status done --note 'Evidence reviewed'",
        "egress_review": "agentos mark-step --step egress_review --status skipped --note 'No network calls'",
        "structural_review": "agentos mark-step --step structural_review --status done --note 'Structure reviewed'",
        "synchronize": "agentos sync-check",
        "report": "agentos report",
    }
    return {"task_id": task_id, "next_step": step, "suggested_command": commands.get(step), "why": "This is the first pending step in the configured workflow." if step else "Workflow is complete."}
