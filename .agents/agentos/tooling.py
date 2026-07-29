"""
File: .agents/agentos/tooling.py

Purpose:
    Enforce local-first tool policy and persist tool and egress audit events.

Responsibilities:
    - Classify tool execution as local, network, dynamic, or unknown.
    - Fail closed for unknown tools and unauthorized network egress.
    - Record guard decisions without duplicating canonical tool-call storage.
    - Produce task-scoped egress reports.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .db import connect
from .policy import load_policy

LOCAL_TOOLS = {
    "bounded_file_read",
    "filesystem_read",
    "filesystem_write",
    "python",
    "pytest",
    "shell_local",
    "index_query",
}
NETWORK_TOOLS = {"web", "http", "download", "api", "git_remote"}


def classify_tool(tool_name: str) -> dict[str, Any]:
    """Classify a tool name using the built-in conservative registry.

    Args:
        tool_name: Runtime tool identifier.

    Returns:
        Classification metadata with a stable category and known flag.
    """
    normalized = tool_name.strip().lower()
    if normalized in LOCAL_TOOLS:
        return {"classification": "local", "known": True}
    if normalized in NETWORK_TOOLS:
        return {"classification": "network", "known": True}
    if normalized.startswith("dynamic:"):
        return {"classification": "dynamic", "known": True}
    return {"classification": "unknown", "known": False}


def _args_hash(args: dict[str, Any]) -> str:
    payload = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def guard_tool(
    root: Path,
    task_id: str,
    tool_name: str,
    args: dict[str, Any],
    reason_code: str | None = None,
    justification: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Evaluate and audit whether a tool call may proceed.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        tool_name: Tool identifier.
        args: Redacted structured arguments.
        reason_code: Required reason code for network calls.
        justification: Required explanation for network calls.
        target: Optional network target or destination.

    Returns:
        Guard decision, reason, and classification metadata.
    """
    policy = load_policy(root)
    classification = classify_tool(tool_name)
    decision = "allow"
    reason = "local_tool"
    if not classification["known"]:
        decision, reason = "block", "unknown_tool_fail_closed"
    elif classification["classification"] == "network":
        if not reason_code or not justification:
            decision, reason = "block", "network_reason_and_justification_required"
        else:
            with connect(root) as c:
                evidence = c.execute(
                    "SELECT COUNT(*) AS n FROM tool_calls WHERE task_id=? AND success=1 AND classification='local'",
                    (task_id,),
                ).fetchone()["n"]
            if evidence < 1:
                decision, reason = "block", "local_evidence_required_before_network"
            else:
                reason = "network_egress_authorized"
    with connect(root) as c:
        if not c.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise RuntimeError(f"task not found: {task_id}")
        c.execute(
            "INSERT INTO tool_events(task_id,tool_name,event_type,classification_json,args_hash,decision,reason) VALUES(?,?,?,?,?,?,?)",
            (task_id, tool_name, "guard", json.dumps(classification), _args_hash(args), decision, reason),
        )
        if classification["classification"] == "network":
            c.execute(
                "INSERT INTO egress_events(task_id,tool_name,target,reason_code,justification,decision) VALUES(?,?,?,?,?,?)",
                (task_id, tool_name, target, reason_code, justification, decision),
            )
    return {"allowed": decision == "allow", "decision": decision, "reason": reason, **classification}


def record_guard_result(root: Path, task_id: str, tool_name: str, args: dict[str, Any], success: bool) -> dict[str, Any]:
    """Record the observed result of a previously guarded tool execution.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        tool_name: Tool identifier.
        args: Redacted structured arguments.
        success: Whether the actual tool execution succeeded.

    Returns:
        Audit acknowledgement.
    """
    classification = classify_tool(tool_name)
    with connect(root) as c:
        if not c.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise RuntimeError(f"task not found: {task_id}")
        c.execute(
            "INSERT INTO tool_events(task_id,tool_name,event_type,classification_json,args_hash,decision,reason,success) VALUES(?,?,?,?,?,?,?,?)",
            (task_id, tool_name, "result", json.dumps(classification), _args_hash(args), "observed", "execution_result", int(success)),
        )
        if classification["classification"] == "network":
            row = c.execute(
                "SELECT id FROM egress_events WHERE task_id=? AND tool_name=? ORDER BY id DESC LIMIT 1",
                (task_id, tool_name),
            ).fetchone()
            if row:
                c.execute("UPDATE egress_events SET success=? WHERE id=?", (int(success), row["id"]))
    return {"recorded": True, "success": success}


def egress_report(root: Path, task_id: str) -> list[dict[str, Any]]:
    """Return all network-egress audit entries for a task.

    Args:
        root: Project root.
        task_id: Existing task identifier.

    Returns:
        Ordered egress event dictionaries.
    """
    with connect(root) as c:
        rows = c.execute("SELECT * FROM egress_events WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
    return [dict(row) for row in rows]
