"""
File: .agents/agentos/collaboration.py

Purpose:
    Provide capability-, role-, and context-isolated multi-agent collaboration.

Responsibilities:
    - Verify collaboration readiness before messaging is enabled.
    - Assign constrained task roles to authenticated sessions.
    - Enforce message-type permissions and context disclosure levels.
    - Preserve signed, correlated message provenance.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context_runtime import context_status
from .db import connect
from .external_audit import append_signed_event

ROLE_PERMISSIONS = {
    "executor": {"review_response", "evidence_response", "handoff_offer", "conflict_notice", "decision_proposal"},
    "reviewer": {"review_request", "review_response", "evidence_request", "decision_ack", "conflict_notice"},
    "planner": {"review_request", "scope_request", "decision_proposal", "handoff_offer"},
    "observer": set(),
}
DISCLOSURE_LEVELS = {"metadata-only", "summary", "selected-artifacts", "full-task-context"}


def collaboration_readiness(root: Path, task_id: str) -> dict[str, Any]:
    """Verify capability sessions, active roles, and fresh context isolation."""
    context = context_status(root, task_id)
    with connect(root) as c:
        active_tokens = c.execute("SELECT COUNT(*) AS n FROM session_tokens WHERE task_id=? AND revoked_at IS NULL AND expires_at>CURRENT_TIMESTAMP", (task_id,)).fetchone()["n"]
        roles = c.execute("SELECT COUNT(*) AS n FROM task_role_assignments WHERE task_id=? AND status='active'", (task_id,)).fetchone()["n"]
    checks = {
        "capability_sessions_stable": active_tokens > 0,
        "roles_stable": roles > 0,
        "context_isolation_stable": bool(context.get("exists") and not context.get("stale")),
    }
    return {"ok": all(checks.values()), "task_id": task_id, "checks": checks, "active_session_count": active_tokens, "active_role_count": roles, "context_revision": context.get("revision")}


def assign_role(root: Path, task_id: str, session_id: str, role: str, assigned_by: str) -> dict[str, Any]:
    """Assign a constrained role to an authenticated task session."""
    if role not in ROLE_PERMISSIONS:
        raise RuntimeError("invalid_collaboration_role")
    with connect(root, immediate=True) as c:
        token = c.execute("SELECT token_id FROM session_tokens WHERE task_id=? AND session_id=? AND revoked_at IS NULL AND expires_at>CURRENT_TIMESTAMP ORDER BY issued_at DESC LIMIT 1", (task_id, session_id)).fetchone()
        if not token:
            raise RuntimeError("active_capability_session_required")
        c.execute("UPDATE task_role_assignments SET status='superseded' WHERE task_id=? AND session_id=? AND status='active'", (task_id, session_id))
        cur = c.execute("INSERT INTO task_role_assignments(task_id,session_id,token_id,role,permissions_json,assigned_by,status) VALUES(?,?,?,?,?,?, 'active')", (task_id, session_id, token["token_id"], role, json.dumps(sorted(ROLE_PERMISSIONS[role])), assigned_by))
    event = append_signed_event(root, "collaboration.role_assigned", {"assignment_id": cur.lastrowid, "task_id": task_id, "session_id": session_id, "role": role}, task_id, assigned_by)
    return {"assignment_id": cur.lastrowid, "task_id": task_id, "session_id": session_id, "role": role, "external_event_hash": event["event_hash"]}


def _filter_payload(disclosure_level: str, payload: dict[str, Any], artifact_refs: list[str]) -> dict[str, Any]:
    """Return only content allowed by the declared disclosure level."""
    if disclosure_level == "metadata-only":
        allowed = {"title", "status", "kind", "summary_length", "content_hash"}
        return {k: v for k, v in payload.items() if k in allowed}
    if disclosure_level == "summary":
        summary = payload.get("summary")
        return {"summary": summary} if isinstance(summary, str) else {}
    if disclosure_level == "selected-artifacts":
        return {"artifact_refs": artifact_refs, "summary": payload.get("summary", "")}
    return payload


def send_message(root: Path, task_id: str, from_session: str, to_session: str, kind: str, payload: dict[str, Any], disclosure_level: str = "metadata-only", artifact_refs: list[str] | None = None, correlation_id: str | None = None, causation_id: str | None = None) -> dict[str, Any]:
    """Send a structured message while enforcing role and disclosure constraints."""
    readiness = collaboration_readiness(root, task_id)
    if not readiness["ok"]:
        raise RuntimeError("collaboration_prerequisites_not_stable")
    if disclosure_level not in DISCLOSURE_LEVELS:
        raise RuntimeError("invalid_disclosure_level")
    refs = artifact_refs or []
    filtered_payload = _filter_payload(disclosure_level, payload, refs)
    if disclosure_level == "selected-artifacts" and not refs:
        raise RuntimeError("selected_artifacts_required")
    with connect(root) as c:
        sender = c.execute("SELECT role,permissions_json FROM task_role_assignments WHERE task_id=? AND session_id=? AND status='active' ORDER BY id DESC LIMIT 1", (task_id, from_session)).fetchone()
        recipient = c.execute("SELECT 1 FROM task_role_assignments WHERE task_id=? AND session_id=? AND status='active'", (task_id, to_session)).fetchone()
        if not sender or not recipient:
            raise RuntimeError("active_role_assignment_required")
        if kind not in set(json.loads(sender["permissions_json"])):
            raise RuntimeError("role_message_permission_denied")
        message_id = secrets.token_hex(16)
        corr = correlation_id or message_id
        c.execute("INSERT INTO task_messages(message_id,correlation_id,causation_id,task_id,from_session,to_session,kind,payload_json,payload_schema_version,disclosure_level,artifact_refs_json,status) VALUES(?,?,?,?,?,?,?,?,1,?,?, 'sent')", (message_id, corr, causation_id, task_id, from_session, to_session, kind, json.dumps(filtered_payload, sort_keys=True), disclosure_level, json.dumps(refs)))
    event = append_signed_event(root, "collaboration.message_sent", {"message_id": message_id, "task_id": task_id, "from_session": from_session, "to_session": to_session, "kind": kind, "disclosure_level": disclosure_level, "artifact_refs": refs}, task_id, from_session)
    with connect(root) as c:
        c.execute("UPDATE task_messages SET external_event_hash=? WHERE message_id=?", (event["event_hash"], message_id))
    return {"message_id": message_id, "correlation_id": corr, "status": "sent", "disclosure_level": disclosure_level, "external_event_hash": event["event_hash"]}


def list_messages(root: Path, task_id: str, session_id: str) -> list[dict[str, Any]]:
    """List messages visible to a task session."""
    with connect(root) as c:
        rows = c.execute("SELECT * FROM task_messages WHERE task_id=? AND (from_session=? OR to_session=?) ORDER BY created_at,id", (task_id, session_id, session_id)).fetchall()
    result = []
    for row in rows:
        item = dict(row); item["payload"] = json.loads(item.pop("payload_json")); item["artifact_refs"] = json.loads(item.pop("artifact_refs_json")); result.append(item)
    return result
