"""
File: .agents/agentos/proxy.py

Purpose:
    Enforce AgentOS policy at the actual tool invocation boundary.

Responsibilities:
    - Normalize agent-facing tool names into stable capabilities.
    - Evaluate task, workflow, drift, scope, and egress policy before execution.
    - Invoke tightly bounded filesystem, shell, and HTTP adapters.
    - Produce canonical execution evidence and signed external audit records.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from .core import check_write
from .db import connect
from .drift import drift_check
from .external_audit import append_signed_event
from .policy import load_policy, local_override_status
from .tooling import append_audit_event, complete_tool, guard_tool, redact_value
from .workflow import workflow_status

CAPABILITIES = {
    "agentos.read_file": "filesystem.read",
    "agentos.write_file": "filesystem.write",
    "agentos.run_command": "process.exec",
    "agentos.http_request": "network.http",
    "filesystem_read": "filesystem.read",
    "filesystem_write": "filesystem.write",
    "shell_local": "process.exec",
    "http": "network.http",
}
TOOL_NAMES = {
    "filesystem.read": "filesystem_read",
    "filesystem.write": "filesystem_write",
    "process.exec": "shell_local",
    "network.http": "http",
}


def normalize_capability(tool_name: str) -> str:
    """Map a concrete tool name to one stable capability.

    Args:
        tool_name: Agent-facing tool name.

    Returns:
        Stable capability identifier.
    """
    if tool_name not in CAPABILITIES:
        raise RuntimeError(f"tool is not exposed by AgentOS proxy: {tool_name}")
    return CAPABILITIES[tool_name]


def _preflight(root: Path, task_id: str, capability: str, args: dict[str, Any]) -> None:
    drift = drift_check(root, task_id=task_id)
    override = local_override_status(root)
    policy = load_policy(root)
    if policy.get("proxy_policy", {}).get("block_on_uninitialized_baseline", True) and drift["baseline_state"] != "initialized":
        raise RuntimeError("proxy blocked: governance baseline is not initialized")
    if policy.get("proxy_policy", {}).get("block_on_drift", True) and drift["drift_detected"]:
        raise RuntimeError("proxy blocked: unacknowledged governance drift")
    if override.get("sensitive") and override.get("status") != "approved":
        raise RuntimeError("proxy blocked: sensitive local override is pending approval")
    status = workflow_status(root, task_id)
    if capability in {"filesystem.write", "process.exec", "network.http"}:
        steps = {item["step_name"]: item["status"] for item in status["steps"]}
        if steps.get("approve_task") != "done":
            raise RuntimeError("proxy blocked: task is not approved")
        if steps.get("prepare_change") != "done" and capability == "filesystem.write":
            raise RuntimeError("proxy blocked: prepare_change is incomplete")
    if capability == "filesystem.write":
        target = str(args.get("path", ""))
        decision = check_write(root, task_id, target)
        if not decision["allowed"]:
            raise RuntimeError(f"proxy blocked: {decision['reason']}")


def _execute_adapter(root: Path, capability: str, args: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if capability == "filesystem.read":
        path = (root / str(args["path"])).resolve()
        path.relative_to(root.resolve())
        content = path.read_text(encoding=str(args.get("encoding", "utf-8")))
        start = int(args.get("start", 1)); end = int(args.get("end", 0))
        if end:
            content = "\n".join(content.splitlines()[start - 1:end])
        return True, {"content": content, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
    if capability == "filesystem.write":
        path = (root / str(args["path"])).resolve(); path.relative_to(root.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        text = str(args.get("content", "")); path.write_text(text, encoding=str(args.get("encoding", "utf-8")))
        return True, {"path": path.relative_to(root).as_posix(), "bytes_written": len(text.encode("utf-8")), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    if capability == "process.exec":
        command = args.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise RuntimeError("command must be a non-empty JSON array of strings")
        timeout = min(int(args.get("timeout", 120)), 600)
        proc = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=timeout, shell=False)
        return proc.returncode == 0, {"exit_code": proc.returncode, "stdout": proc.stdout[:8000], "stderr": proc.stderr[:8000]}
    if capability == "network.http":
        method = str(args.get("method", "GET")).upper()
        data = args.get("body")
        body = data.encode("utf-8") if isinstance(data, str) else None
        request = urllib.request.Request(str(args["url"]), data=body, method=method, headers={str(k): str(v) for k, v in args.get("headers", {}).items()})
        with urllib.request.urlopen(request, timeout=min(int(args.get("timeout", 30)), 120)) as response:
            payload = response.read(min(int(args.get("max_bytes", 1048576)), 1048576))
            return True, {"status": response.status, "headers": dict(response.headers.items()), "body": payload.decode("utf-8", errors="replace")}
    raise RuntimeError(f"unsupported capability: {capability}")


def proxy_execute(root: Path, task_id: str, session_id: str, tool_name: str, args: dict[str, Any], reason_code: str | None = None, justification: str | None = None, target: str | None = None) -> dict[str, Any]:
    """Evaluate and execute one tool request through the enforced proxy.

    Args:
        root: Project root.
        task_id: Existing approved task.
        session_id: Transport-bound session identifier.
        tool_name: Agent-facing proxy tool name.
        args: Structured tool arguments.
        reason_code: Required reason code for network access.
        justification: Required network justification.
        target: Optional network target.

    Returns:
        Canonical execution result and evidence identifiers.
    """
    capability = normalize_capability(tool_name)
    _preflight(root, task_id, capability, args)
    canonical_tool = TOOL_NAMES[capability]
    clean_args = redact_value(args)
    requested = {"tool": tool_name, "capability": capability, "args": clean_args}
    append_audit_event(root, "proxy.request", requested, task_id, session_id)
    append_signed_event(root, "proxy.request", requested, task_id, session_id)
    guard = guard_tool(root, task_id, session_id, canonical_tool, args, reason_code, justification, target)
    if not guard["allowed"]:
        denied = {"allowed": False, "reason": guard["reason"], "capability": capability}
        append_signed_event(root, "proxy.denied", denied, task_id, session_id)
        return denied
    try:
        success, output = _execute_adapter(root, capability, args)
    except Exception as exc:
        success, output = False, {"error": type(exc).__name__, "message": str(exc)}
    summary = json.dumps(redact_value(output), sort_keys=True, ensure_ascii=False)
    canonical = complete_tool(root, guard["execution_token"], args, success, summary, session_id)
    event = {"allowed": True, "success": success, "capability": capability, "tool_call_id": canonical["tool_call_id"], "output": redact_value(output)}
    append_audit_event(root, "proxy.completed", event, task_id, session_id)
    signed = append_signed_event(root, "proxy.completed", event, task_id, session_id)
    with connect(root) as c:
        c.execute("INSERT INTO proxy_executions(task_id,session_id,tool_name,capability,decision,success,tool_call_id,external_event_hash) VALUES(?,?,?,?,?,?,?,?)", (task_id, session_id, tool_name, capability, "allowed", int(success), canonical["tool_call_id"], signed["event_hash"]))
    return {**event, "external_audit": signed}
