"""
File: .agents/agentos/tooling.py

Purpose:
    Enforce a canonical guarded tool-execution lifecycle.

Responsibilities:
    - Derive tool classification from a conservative registry.
    - Issue single-use execution tokens after policy evaluation.
    - Complete guarded executions and create canonical evidence records.
    - Redact sensitive audit content and append hash-chained audit events.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect
from .policy import load_policy

LOCAL_TOOLS = {"bounded_file_read", "filesystem_read", "filesystem_write", "python", "pytest", "shell_local", "index_query", "docs_scan", "governed_operation"}
NETWORK_TOOLS = {"web", "http", "download", "api", "git_remote"}
_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization|api[_-]?key|password|cookie|secret|token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+\-/]+=*"),
]


def classify_tool(tool_name: str) -> dict[str, Any]:
    """Derive a tool classification from the built-in registry.

    Args:
        tool_name: Runtime tool identifier.

    Returns:
        Classification metadata.
    """
    normalized = tool_name.strip().lower()
    if normalized in LOCAL_TOOLS:
        return {"classification": "local", "known": True}
    if normalized in NETWORK_TOOLS:
        return {"classification": "network", "known": True}
    if normalized.startswith("dynamic:"):
        return {"classification": "dynamic", "known": True}
    return {"classification": "unknown", "known": False}


def redact_text(text: str) -> str:
    """Redact common secrets from free-form audit text.

    Args:
        text: Untrusted summary text.

    Returns:
        Redacted text bounded to 4000 characters.
    """
    value = text
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]" if m.lastindex and m.lastindex >= 1 else "[REDACTED]", value)
    return value[:4000]


def redact_value(value: Any) -> Any:
    """Recursively redact sensitive keys and strings.

    Args:
        value: Arbitrary JSON-compatible value.

    Returns:
        Redacted value.
    """
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("authorization", "password", "secret", "token", "cookie", "api_key", "apikey", "credential", "dsn", "connection_string")):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _args_hash(args: dict[str, Any]) -> str:
    payload = json.dumps(redact_value(args), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_audit_event(root: Path, event_type: str, payload: dict[str, Any], task_id: str | None = None, session_id: str | None = None) -> str:
    """Append one hash-chained audit event.

    Args:
        root: Project root.
        event_type: Stable event type.
        payload: Structured event payload.
        task_id: Optional task identifier.
        session_id: Optional session identifier.

    Returns:
        Event hash.
    """
    clean = redact_value(payload)
    body = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with connect(root) as c:
        row = c.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        previous = row["event_hash"] if row else None
        digest = hashlib.sha256(f"{previous or ''}|{event_type}|{task_id or ''}|{session_id or ''}|{body}".encode("utf-8")).hexdigest()
        c.execute("INSERT INTO audit_events(event_type,task_id,session_id,payload_json,previous_hash,event_hash) VALUES(?,?,?,?,?,?)", (event_type, task_id, session_id, body, previous, digest))
    return digest


def guard_tool(root: Path, task_id: str, session_id: str, tool_name: str, args: dict[str, Any], reason_code: str | None = None, justification: str | None = None, target: str | None = None, ttl_seconds: int = 900) -> dict[str, Any]:
    """Evaluate a tool call and issue a single-use execution token.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        session_id: Active session identifier.
        tool_name: Tool identifier.
        args: Structured arguments.
        reason_code: Required reason for network calls.
        justification: Required explanation for network calls.
        target: Optional network target.
        ttl_seconds: Token lifetime.

    Returns:
        Guard decision and execution token when allowed.
    """
    classification = classify_tool(tool_name)
    decision, reason = "allow", "local_tool"
    read_only_tools = {"bounded_file_read", "filesystem_read", "index_query", "docs_scan"}
    if tool_name not in read_only_tools and tool_name != "governed_operation":
        from .human_decision import clarity_gate_status, decision_gate_status
        clarity = clarity_gate_status(root, task_id)
        decisions = decision_gate_status(root, task_id)
        if decisions["blocked"]:
            decision, reason = "block", "human_decision_pending"
        elif not clarity["ready"]:
            decision, reason = "block", "clarity_gate_pending"
    if decision == "block":
        pass
    elif not classification["known"]:
        decision, reason = "block", "unknown_tool_fail_closed"
    elif classification["classification"] == "dynamic":
        decision, reason = "block", "dynamic_tool_requires_explicit_registry"
    elif classification["classification"] == "network":
        if not reason_code or not justification:
            decision, reason = "block", "network_reason_and_justification_required"
        else:
            with connect(root) as c:
                evidence = c.execute("SELECT COUNT(*) AS n FROM tool_calls WHERE task_id=? AND success=1 AND classification='local'", (task_id,)).fetchone()["n"]
            if evidence < 1:
                decision, reason = "block", "local_evidence_required_before_network"
            else:
                reason = "network_egress_authorized"
    token = secrets.token_urlsafe(32) if decision == "allow" else None
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    args_hash = _args_hash(args)
    with connect(root) as c:
        if not c.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise RuntimeError(f"task not found: {task_id}")
        c.execute("INSERT INTO tool_events(task_id,tool_name,event_type,classification_json,args_hash,decision,reason) VALUES(?,?,?,?,?,?,?)", (task_id, tool_name, "guard", json.dumps(classification), args_hash, decision, reason))
        if classification["classification"] == "network":
            c.execute("INSERT INTO egress_events(task_id,tool_name,target,reason_code,justification,decision) VALUES(?,?,?,?,?,?)", (task_id, tool_name, target, reason_code, redact_text(justification or ""), decision))
        if token:
            c.execute("""INSERT INTO guarded_executions(execution_token,task_id,session_id,tool_name,classification,args_hash,decision,reason,target,reason_code,justification,expires_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (token, task_id, session_id, tool_name, classification["classification"], args_hash, decision, reason, target, reason_code, redact_text(justification or ""), expires.isoformat()))
    append_audit_event(root, "tool_guard", {"tool_name": tool_name, "classification": classification["classification"], "args_hash": args_hash, "decision": decision, "reason": reason}, task_id, session_id)
    return {"allowed": decision == "allow", "decision": decision, "reason": reason, "execution_token": token, "expires_at": expires.isoformat() if token else None, **classification}



def validate_execution_token(
    root: Path,
    execution_token: str,
    task_id: str,
    session_id: str,
    tool_name: str,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    """Validate one guarded execution token without consuming it.

    This is used by execution adapters immediately before the
    actual side effect. complete_tool() remains responsible for
    consuming the single-use token and materializing canonical
    completion evidence.
    """
    actual_hash = _args_hash(input_data)
    now = datetime.now(timezone.utc)

    with connect(root) as c:
        row = c.execute(
            "SELECT * FROM guarded_executions "
            "WHERE execution_token=?",
            (execution_token,),
        ).fetchone()

    if not row:
        raise RuntimeError("execution token not found")

    if row["task_id"] != task_id:
        raise RuntimeError(
            "execution token belongs to another task"
        )

    if row["session_id"] != session_id:
        raise RuntimeError(
            "execution token belongs to another session"
        )

    if row["tool_name"] != tool_name:
        raise RuntimeError(
            "execution token belongs to another tool"
        )

    if row["decision"] != "allow":
        raise RuntimeError(
            "execution token was not allowed"
        )

    if row["completed_at"] is not None:
        raise RuntimeError(
            "execution token has already been used"
        )

    if datetime.fromisoformat(row["expires_at"]) < now:
        raise RuntimeError(
            "execution token has expired"
        )

    if row["args_hash"] != actual_hash:
        raise RuntimeError(
            "execution arguments do not match guarded arguments"
        )

    return dict(row)

def complete_tool(root: Path, execution_token: str, input_data: dict[str, Any], success: bool, output_summary: str, session_id: str) -> dict[str, Any]:
    """Complete a guarded execution and create canonical evidence.

    Args:
        root: Project root.
        execution_token: Single-use token returned by guard_tool.
        input_data: Actual structured input metadata.
        success: Whether execution succeeded.
        output_summary: Bounded execution summary.
        session_id: Active session identifier.

    Returns:
        Canonical tool-call metadata.
    """
    actual_hash = _args_hash(input_data)
    now = datetime.now(timezone.utc)
    with connect(root) as c:
        row = c.execute("SELECT * FROM guarded_executions WHERE execution_token=?", (execution_token,)).fetchone()
        if not row:
            raise RuntimeError("execution token not found")
        if row["session_id"] != session_id:
            raise RuntimeError("execution token belongs to another session")
        if row["decision"] != "allow":
            raise RuntimeError("execution token was not allowed")
        if row["completed_at"] is not None:
            raise RuntimeError("execution token has already been used")
        if datetime.fromisoformat(row["expires_at"]) < now:
            raise RuntimeError("execution token has expired")
        if row["args_hash"] != actual_hash:
            raise RuntimeError("execution arguments do not match guarded arguments")
        summary = redact_text(output_summary)
        cur = c.execute("INSERT INTO tool_calls(task_id,tool_name,classification,input_json,success,output_summary) VALUES(?,?,?,?,?,?)", (row["task_id"], row["tool_name"], row["classification"], json.dumps(redact_value(input_data), ensure_ascii=False), int(success), summary))
        call_id = int(cur.lastrowid)
        c.execute("UPDATE guarded_executions SET completed_at=CURRENT_TIMESTAMP,success=?,tool_call_id=? WHERE id=?", (int(success), call_id, row["id"]))
        c.execute("INSERT INTO tool_events(task_id,tool_name,event_type,classification_json,args_hash,decision,reason,success) VALUES(?,?,?,?,?,?,?,?)", (row["task_id"], row["tool_name"], "result", json.dumps({"classification": row["classification"], "known": True}), actual_hash, "observed", "guarded_execution_completed", int(success)))
        if row["classification"] == "network":
            e = c.execute("SELECT id FROM egress_events WHERE task_id=? AND tool_name=? AND success IS NULL ORDER BY id DESC LIMIT 1", (row["task_id"], row["tool_name"])).fetchone()
            if e:
                c.execute("UPDATE egress_events SET success=? WHERE id=?", (int(success), e["id"]))
    append_audit_event(root, "tool_complete", {"tool_call_id": call_id, "tool_name": row["tool_name"], "classification": row["classification"], "success": success, "args_hash": actual_hash}, row["task_id"], session_id)
    return {"tool_call_id": call_id, "task_id": row["task_id"], "tool_name": row["tool_name"], "classification": row["classification"], "success": success}


def egress_report(root: Path, task_id: str) -> list[dict[str, Any]]:
    """Return all network-egress audit entries for a task."""
    with connect(root) as c:
        rows = c.execute("SELECT * FROM egress_events WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
    return [dict(row) for row in rows]
