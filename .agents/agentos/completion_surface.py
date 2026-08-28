"""
Path: .agents/agentos/completion_surface.py
Purpose: Canonical v0.29.0 CLI/MCP-facing completion surface.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .completion_verification import completion_status
from .db import connect_read_only

SUBJECT_WORKFLOW = "workflow"
SUBJECT_WORKER = "multi_agent_worker"
SUBJECT_TYPES = {SUBJECT_WORKFLOW, SUBJECT_WORKER}


def _verification_tables_available(root: Path) -> bool:
    with connect_read_only(root) as c:
        return bool(
            c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='completion_verification_requests'").fetchone()
            and c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='completion_verification_attempts'").fetchone()
        )


def _require_candidate_schema(root: Path) -> None:
    if not _verification_tables_available(root):
        raise PermissionError("independent_completion_verification_schema_required")


def _actor(task_id: str | None = None, session_id: str | None = None) -> tuple[str, str]:
    task = str(task_id or os.environ.get("AGENTOS_TASK_ID") or "").strip()
    session = str(session_id or os.environ.get("AGENTOS_SESSION_ID") or "").strip()
    if not task or not session:
        raise PermissionError("completion_task_and_session_required")
    return task, session


def _request_row(root: Path, request_id: str) -> dict[str, Any]:
    _require_candidate_schema(root)
    with connect_read_only(root) as c:
        row = c.execute(
            """SELECT request_id,subject_type,subject_id,task_id,status,subject_hash,
                      required_checks_json,created_at,resolved_at
                 FROM completion_verification_requests WHERE request_id=?""",
            (str(request_id),),
        ).fetchone()
    if not row:
        raise ValueError("completion_verification_request_not_found")
    return dict(row)


def _safe_request(request: dict[str, Any] | None) -> dict[str, Any] | None:
    if not request:
        return None
    return {
        "request_id": request.get("request_id"),
        "status": request.get("status"),
        "subject_hash": request.get("subject_hash"),
        "required_checks": list(request.get("required_checks") or []),
        "created_at": request.get("created_at"),
        "resolved_at": request.get("resolved_at"),
    }


def _safe_attempt(attempt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not attempt:
        return None
    return {
        "attempt_id": attempt.get("id"),
        "verifier_role": attempt.get("verifier_role"),
        "observed_subject_hash": attempt.get("observed_subject_hash"),
        "verdict": attempt.get("verdict"),
        "result_hash": attempt.get("result_hash"),
        "created_at": attempt.get("created_at"),
    }


def _public_status_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "subject_type": raw.get("subject_type"),
        "subject_id": raw.get("subject_id"),
        "schema_available": bool(raw.get("schema_available")),
        "accepted": bool(raw.get("accepted")),
        "current": bool(raw.get("current")),
        "reason": raw.get("reason"),
        "request": _safe_request(raw.get("request")),
        "attempt": _safe_attempt(raw.get("attempt")),
    }


def completion_request(
    root: Path,
    *,
    subject_type: str,
    task_id: str | None = None,
    session_id: str | None = None,
    workflow_name: str = "default",
    supervisor_id: int | None = None,
    worker_key: str | None = None,
) -> dict[str, Any]:
    _require_candidate_schema(root)
    kind = str(subject_type)
    if kind not in SUBJECT_TYPES:
        raise ValueError("unsupported_completion_subject_type")
    actor_task, actor_session = _actor(task_id, session_id)
    if kind == SUBJECT_WORKFLOW:
        from .workflow import workflow_completion_request
        value = workflow_completion_request(root, actor_task, actor_session, str(workflow_name))
    else:
        if supervisor_id is None or not str(worker_key or "").strip():
            raise ValueError("supervisor_id_and_worker_key_required")
        from .multi_agent_supervisor import worker_completion_request
        value = worker_completion_request(
            root, int(supervisor_id), str(worker_key), actor_task, actor_session
        )
    return {
        "ok": True,
        "request_id": value.get("request_id"),
        "subject_type": value.get("subject_type"),
        "subject_id": value.get("subject_id"),
        "task_id": value.get("task_id"),
        "subject_hash": value.get("subject_hash"),
        "required_checks": list(value.get("required_checks") or []),
        "status": value.get("status"),
    }


def completion_verify(
    root: Path,
    *,
    request_id: str,
    verdict: str,
    checks: dict[str, Any],
    evidence: dict[str, Any],
    verifier_task_id: str | None = None,
    verifier_session_id: str | None = None,
) -> dict[str, Any]:
    actor_task, actor_session = _actor(verifier_task_id, verifier_session_id)
    request = _request_row(root, request_id)
    kind = str(request["subject_type"])
    if kind == SUBJECT_WORKFLOW:
        from .workflow import workflow_completion_verify
        value = workflow_completion_verify(
            root, str(request_id), actor_task, actor_session,
            verdict=str(verdict), checks=checks, evidence=evidence,
        )
    elif kind == SUBJECT_WORKER:
        from .multi_agent_supervisor import worker_completion_verify
        value = worker_completion_verify(
            root, str(request_id), actor_task, actor_session,
            verdict=str(verdict), checks=checks, evidence=evidence,
        )
    else:
        raise RuntimeError("unsupported_completion_request_subject_type")
    result = {
        "ok": True,
        "request_id": str(request_id),
        "subject_type": kind,
        "subject_id": request["subject_id"],
        "verdict": value.get("verdict"),
        "request_status": value.get("request_status"),
        "result_hash": value.get("result_hash"),
    }
    if "worker_status" in value:
        result["worker_status"] = value.get("worker_status")
    if "supervisor_completed" in value:
        result["supervisor_completed"] = bool(value.get("supervisor_completed"))
    return result


def _workflow_status_raw(root: Path, task_id: str, workflow_name: str) -> dict[str, Any]:
    from .workflow import workflow_completion_verification_status
    return workflow_completion_verification_status(
        root, str(task_id), str(workflow_name), read_only=True
    )


def _worker_status_raw(root: Path, supervisor_id: int, worker_key: str) -> dict[str, Any]:
    from .multi_agent_supervisor import worker_completion_subject
    subject = worker_completion_subject(root, int(supervisor_id), str(worker_key))
    return completion_status(
        root,
        subject_type=SUBJECT_WORKER,
        subject_id=f"{int(supervisor_id)}:{worker_key}",
        current_subject_payload=subject,
    )


def completion_public_status(
    root: Path,
    *,
    request_id: str | None = None,
    subject_type: str | None = None,
    task_id: str | None = None,
    workflow_name: str = "default",
    supervisor_id: int | None = None,
    worker_key: str | None = None,
) -> dict[str, Any]:
    kind = str(subject_type) if subject_type is not None else None
    if request_id:
        if not _verification_tables_available(root):
            return {
                "ok": True,
                "subject_type": kind,
                "subject_id": None,
                "schema_available": False,
                "accepted": False,
                "current": False,
                "reason": "completion_verification_schema_unavailable",
                "request": None,
                "attempt": None,
            }
        request = _request_row(root, str(request_id))
        kind = str(request["subject_type"])
        subject_id = str(request["subject_id"])
        if kind == SUBJECT_WORKFLOW:
            try:
                selected_task, selected_workflow = subject_id.split(":", 1)
            except ValueError as exc:
                raise RuntimeError("invalid_workflow_completion_subject_id") from exc
            from .workflow import workflow_completion_subject

            raw = completion_status(
                root,
                subject_type=SUBJECT_WORKFLOW,
                subject_id=subject_id,
                current_subject_payload=workflow_completion_subject(
                    root,
                    selected_task,
                    selected_workflow,
                    read_only=True,
                ),
                request_id=str(request_id),
            )
        elif kind == SUBJECT_WORKER:
            try:
                supervisor_text, selected_worker = subject_id.split(":", 1)
                selected_supervisor = int(supervisor_text)
            except Exception as exc:
                raise RuntimeError("invalid_worker_completion_subject_id") from exc
            from .multi_agent_supervisor import (
                worker_completion_subject,
            )

            raw = completion_status(
                root,
                subject_type=SUBJECT_WORKER,
                subject_id=subject_id,
                current_subject_payload=worker_completion_subject(
                    root,
                    selected_supervisor,
                    selected_worker,
                ),
                request_id=str(request_id),
            )
        else:
            raise RuntimeError("unsupported_completion_request_subject_type")
        return _public_status_from_raw(raw)

    if kind is None:
        kind = SUBJECT_WORKFLOW
    if kind == SUBJECT_WORKFLOW:
        selected_task = str(task_id or os.environ.get("AGENTOS_TASK_ID") or "").strip()
        if not selected_task:
            raise ValueError("task_id_required_for_workflow_completion_status")
        try:
            raw = _workflow_status_raw(root, selected_task, str(workflow_name))
        except RuntimeError as exc:
            if str(exc).startswith("workflow_not_seeded:"):
                return {
                    "ok": True,
                    "subject_type": SUBJECT_WORKFLOW,
                    "subject_id": f"{selected_task}:{workflow_name}",
                    "schema_available": _verification_tables_available(root),
                    "accepted": False,
                    "current": False,
                    "reason": "workflow_not_seeded",
                    "request": None,
                    "attempt": None,
                }
            raise
        return _public_status_from_raw(raw)
    if kind == SUBJECT_WORKER:
        if supervisor_id is None or not str(worker_key or "").strip():
            raise ValueError("supervisor_id_and_worker_key_required")
        return _public_status_from_raw(
            _worker_status_raw(root, int(supervisor_id), str(worker_key))
        )
    raise ValueError("unsupported_completion_subject_type")
