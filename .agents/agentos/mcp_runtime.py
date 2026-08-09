"""
File: .agents/agentos/mcp_runtime.py

Purpose:
    Serve one cross-platform AgentOS MCP JSON-RPC runtime without subprocess forwarding.

Responsibilities:
    - Advertise the governed core proxy tools and all read-only extension tools.
    - Dispatch extension tools by direct dictionary lookup.
    - Route governed core actions through the existing session gateway.
    - Return standards-shaped JSON-RPC errors for unknown methods/tools.
    - Expose runtime health without leaking credentials or session tokens.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import secrets
import sys
from typing import Any

from .gateway_client import request as gateway_request
from .mcp_catalog import FEATURE_HANDLERS, FEATURE_TOOLS
from .mcp_server import TOOLS as CORE_TOOLS
from .schema_version import CURRENT_SCHEMA_VERSION

VERSION = "0.22.6"
HEALTH_TOOL = {
    "name": "agentos.mcp_health",
    "description": "Read unified MCP runtime/catalog health without secrets or mutation.",
    "inputSchema": {"type": "object", "properties": {}},
}


def _merge_tools() -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Merge core and extension catalogs and reject duplicate names."""
    tools: list[dict[str, Any]] = []
    names: set[str] = set()
    duplicates: set[str] = set()
    for definition in [*CORE_TOOLS, *FEATURE_TOOLS, HEALTH_TOOL]:
        name = str(definition["name"])
        if name in names:
            duplicates.add(name)
            continue
        names.add(name)
        tools.append(definition)
    if duplicates:
        raise RuntimeError(f"duplicate MCP tool names: {sorted(duplicates)}")
    return tools, {item["name"] for item in CORE_TOOLS}, {item["name"] for item in FEATURE_TOOLS}


ALL_TOOLS, CORE_TOOL_NAMES, FEATURE_TOOL_NAMES = _merge_tools()
ALL_TOOL_NAMES = {item["name"] for item in ALL_TOOLS}


def _reply(identifier: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    """Write one JSON-RPC response line."""
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": identifier}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _tool_result(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, default=str)}],
        "isError": bool(is_error),
    }


def _health(root: Path, task_id: str | None, session_id: str | None) -> dict[str, Any]:
    """Return privacy-safe unified MCP runtime health."""
    return {
        "ok": True,
        "version": VERSION,
        "schema": CURRENT_SCHEMA_VERSION,
        "runtime": "unified_python_mcp",
        "project_root_name": root.name,
        "tool_count": len(ALL_TOOLS),
        "core_proxy_tool_count": len(CORE_TOOLS),
        "extension_readonly_tool_count": len(FEATURE_TOOLS),
        "duplicate_tools": [],
        "subprocess_forwarding": False,
        "legacy_gateway_active": False,
        "task_bound": bool(task_id),
        "session_bound": bool(session_id),
        "session_token_present": bool(os.environ.get("AGENTOS_SESSION_TOKEN")),
        "python": platform.python_version(),
        "platform": sys.platform,
    }


def _call_core(root: Path, task_id: str | None, session_id: str | None, name: str, arguments: dict[str, Any], sequence: int) -> dict[str, Any]:
    """Execute one governed core MCP proxy tool through the session gateway."""
    if not task_id or not session_id:
        raise RuntimeError("core MCP proxy tool requires --task-id and --session-id")
    session_token = os.environ.get("AGENTOS_SESSION_TOKEN")
    if not session_token:
        raise RuntimeError("AGENTOS_SESSION_TOKEN is required for governed core MCP tools")
    payload = dict(arguments)
    reason = payload.pop("reason_code", None)
    justification = payload.pop("justification", None)
    target = payload.get("url") if name == "agentos.http_request" else payload.get("path")
    return gateway_request(root, {
        "action": "execute",
        "task_id": task_id,
        "session_token": session_token,
        "tool_name": name,
        "args": payload,
        "reason_code": reason,
        "justification": justification,
        "target": target,
        "request_id": secrets.token_hex(16),
        "sequence": sequence,
    })


def serve(root: Path, task_id: str | None = None, session_id: str | None = None) -> None:
    """Serve unified MCP JSON-RPC messages from stdin.

    Args:
        root: Governed project root.
        task_id: Optional bound task for governed core tools.
        session_id: Optional bound session for governed core tools.

    Returns:
        None.
    """
    sequence = 0
    for line in sys.stdin:
        request: Any = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                _reply(None, error={"code": -32600, "message": "invalid request"})
                continue
            method = request.get("method")
            identifier = request.get("id")
            if method == "notifications/initialized":
                continue
            if method == "initialize":
                protocol = (request.get("params") or {}).get("protocolVersion") or "2025-03-26"
                _reply(identifier, {"protocolVersion": protocol, "capabilities": {"tools": {}}, "serverInfo": {"name": "agentos-local-governance", "version": VERSION}})
                continue
            if method == "ping":
                _reply(identifier, {})
                continue
            if method == "tools/list":
                _reply(identifier, {"tools": ALL_TOOLS})
                continue
            if method != "tools/call":
                _reply(identifier, error={"code": -32601, "message": f"method not found: {method}"})
                continue

            sequence += 1
            params = request.get("params") or {}
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                _reply(identifier, error={"code": -32602, "message": "tool arguments must be an object"})
                continue
            if name == HEALTH_TOOL["name"]:
                _reply(identifier, _tool_result(_health(root, task_id, session_id)))
                continue
            if name in FEATURE_TOOL_NAMES:
                value = FEATURE_HANDLERS[name](name, dict(arguments), root)
                _reply(identifier, _tool_result(value))
                continue
            if name in CORE_TOOL_NAMES:
                value = _call_core(root, task_id, session_id, name, arguments, sequence)
                _reply(identifier, _tool_result(value, is_error=not value.get("success", value.get("allowed", True))))
                continue
            _reply(identifier, error={"code": -32602, "message": f"unknown MCP tool: {name}"})
        except Exception as exc:
            identifier = request.get("id") if isinstance(request, dict) else None
            _reply(identifier, error={"code": -32000, "message": str(exc)})


def main(argv: list[str] | None = None) -> int:
    """Run the unified stdio MCP runtime."""
    parser = argparse.ArgumentParser(prog="agentos-mcp")
    parser.add_argument("--root", default=os.environ.get("AGENTOS_PROJECT_ROOT", "."))
    parser.add_argument("--task-id", default=os.environ.get("AGENTOS_TASK_ID"))
    parser.add_argument("--session-id", default=os.environ.get("AGENTOS_SESSION_ID"))
    args = parser.parse_args(argv)
    serve(Path(args.root).resolve(), args.task_id, args.session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
