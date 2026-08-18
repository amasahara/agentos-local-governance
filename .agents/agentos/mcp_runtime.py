"""
File: .agents/agentos/mcp_runtime.py

Purpose:
    Serve the active cross-platform AgentOS MCP JSON-RPC runtime with feature
    handlers fully detached from historical MCP gateway modules.

Responsibilities:
    - Own JSON-RPC protocol handling only.
    - Dispatch read-only feature tools through mcp_feature_runtime.
    - Dispatch governed core tools through mcp_core_runtime and the trusted
      gateway_client/gatewayd enforcement boundary.
    - Never import mcp_server or mcp_*_gateway compatibility modules.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any

from .mcp_core_runtime import CORE_TOOLS, CORE_TOOL_NAMES, execute_core_tool
from .mcp_feature_runtime import (
    FEATURE_HANDLERS,
    FEATURE_TOOLS,
    FEATURE_TOOL_NAMES,
    dispatch_feature_tool,
    feature_runtime_health,
)
from . import __version__
from .schema_version import CURRENT_SCHEMA_VERSION
from .mcp_v0252 import TOOLS as V0252_TOOLS, TOOL_NAMES as V0252_TOOL_NAMES, dispatch as dispatch_v0252_tool
from .mcp_v0253 import TOOLS as V0253_TOOLS, TOOL_NAMES as V0253_TOOL_NAMES, dispatch as dispatch_v0253_tool
from .mcp_v0254 import TOOLS as V0254_TOOLS, TOOL_NAMES as V0254_TOOL_NAMES, dispatch as dispatch_v0254_tool
from .mcp_v0255 import TOOLS as V0255_TOOLS, TOOL_NAMES as V0255_TOOL_NAMES, dispatch as dispatch_v0255_tool
from .mcp_v0260 import TOOLS as V0260_TOOLS, TOOL_NAMES as V0260_TOOL_NAMES, dispatch as dispatch_v0260_tool
from .mcp_v0261 import TOOLS as V0261_TOOLS, TOOL_NAMES as V0261_TOOL_NAMES, dispatch as dispatch_v0261_tool
from .mcp_v0262 import TOOLS as V0262_TOOLS, TOOL_NAMES as V0262_TOOL_NAMES, dispatch as dispatch_v0262_tool
from .mcp_v0263 import TOOLS as V0263_TOOLS, TOOL_NAMES as V0263_TOOL_NAMES, dispatch as dispatch_v0263_tool
from .mcp_v0270 import TOOLS as V0270_TOOLS, TOOL_NAMES as V0270_TOOL_NAMES, dispatch as dispatch_v0270_tool

VERSION = __version__

HEALTH_TOOL = {
    "name": "agentos.mcp_health",
    "description": "Read active MCP runtime/catalog health without secrets or mutation.",
    "inputSchema": {"type": "object", "properties": {}},
}


def _merge_tools() -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Merge core, feature and health tool catalogs and reject duplicates."""
    tools: list[dict[str, Any]] = []
    names: set[str] = set()
    duplicates: set[str] = set()
    for definition in [*CORE_TOOLS, *FEATURE_TOOLS, *V0252_TOOLS, *V0253_TOOLS, *V0254_TOOLS, *V0255_TOOLS, *V0260_TOOLS, *V0261_TOOLS, *V0262_TOOLS, *V0263_TOOLS, *V0270_TOOLS, HEALTH_TOOL]:
        name = str(definition["name"])
        if name in names:
            duplicates.add(name)
            continue
        names.add(name)
        tools.append(definition)
    if duplicates:
        raise RuntimeError(f"duplicate MCP tool names: {sorted(duplicates)}")
    return tools, set(CORE_TOOL_NAMES), set(FEATURE_TOOL_NAMES)


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
    """Return privacy-safe current-release MCP feature-runtime health."""
    features = feature_runtime_health()
    return {
        "ok": bool(features["ok"]),
        "version": VERSION,
        "schema": CURRENT_SCHEMA_VERSION,
        "runtime": "mcp_feature_runtime_v1",
        "project_root_name": root.name,
        "tool_count": len(ALL_TOOLS),
        "core_proxy_tool_count": len(CORE_TOOLS),
        "extension_readonly_tool_count": len(FEATURE_TOOLS) + len(V0252_TOOLS) + len(V0253_TOOLS) + len(V0254_TOOLS) + len(V0255_TOOLS) + len(V0260_TOOLS) + len(V0261_TOOLS) + len(V0262_TOOLS) + len(V0263_TOOLS) + len(V0270_TOOLS) - 1,
        "monotonic_blocker_tool_count": 1,
        "duplicate_tools": [],
        "subprocess_forwarding": False,
        "legacy_gateway_active": False,
        "legacy_gateway_handler_count": features["legacy_gateway_handler_count"],
        "runtime_native_migrated_tool_count": features["runtime_native_migrated_tool_count"],
        "trusted_enforcement_gateway": True,
        "task_bound": bool(task_id),
        "session_bound": bool(session_id),
        "session_token_present": bool(os.environ.get("AGENTOS_SESSION_TOKEN")),
        "python": platform.python_version(),
        "platform": sys.platform,
    }


def _call_core(
    root: Path,
    task_id: str | None,
    session_id: str | None,
    name: str,
    arguments: dict[str, Any],
    sequence: int,
) -> dict[str, Any]:
    """Backward-compatible core dispatch wrapper."""
    return execute_core_tool(root, task_id, session_id, name, arguments, sequence)


def serve(root: Path, task_id: str | None = None, session_id: str | None = None) -> None:
    """Serve active MCP JSON-RPC messages from stdin."""
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
                _reply(
                    identifier,
                    {
                        "protocolVersion": protocol,
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "agentos-local-governance",
                            "version": VERSION,
                        },
                    },
                )
                continue
            if method == "ping":
                _reply(identifier, {})
                continue
            if method == "tools/list":
                _reply(identifier, {"tools": ALL_TOOLS})
                continue
            if method != "tools/call":
                _reply(
                    identifier,
                    error={"code": -32601, "message": f"method not found: {method}"},
                )
                continue
            sequence += 1
            params = request.get("params") or {}
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                _reply(
                    identifier,
                    error={"code": -32602, "message": "tool arguments must be an object"},
                )
                continue
            if name == HEALTH_TOOL["name"]:
                _reply(identifier, _tool_result(_health(root, task_id, session_id)))
                continue
            if name in V0270_TOOL_NAMES:
                value = dispatch_v0270_tool(root, name, arguments)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0263_TOOL_NAMES:
                value = dispatch_v0263_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0262_TOOL_NAMES:
                value = dispatch_v0262_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0261_TOOL_NAMES:
                value = dispatch_v0261_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0260_TOOL_NAMES:
                value = dispatch_v0260_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0255_TOOL_NAMES:
                value = dispatch_v0255_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0254_TOOL_NAMES:
                value = dispatch_v0254_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0253_TOOL_NAMES:
                value = dispatch_v0253_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in V0252_TOOL_NAMES:
                value = dispatch_v0252_tool(name, arguments, root, task_id, session_id)
                _reply(identifier, _tool_result(value))
                continue
            if name in FEATURE_TOOL_NAMES:
                value = dispatch_feature_tool(name, arguments, root)
                _reply(identifier, _tool_result(value))
                continue
            if name in CORE_TOOL_NAMES:
                value = execute_core_tool(
                    root, task_id, session_id, name, arguments, sequence
                )
                _reply(
                    identifier,
                    _tool_result(
                        value,
                        is_error=not value.get("success", value.get("allowed", True)),
                    ),
                )
                continue
            _reply(
                identifier,
                error={"code": -32602, "message": f"unknown MCP tool: {name}"},
            )
        except Exception as exc:
            identifier = request.get("id") if isinstance(request, dict) else None
            _reply(identifier, error={"code": -32000, "message": str(exc)})


def main(argv: list[str] | None = None) -> int:
    """Run the active stdio MCP runtime."""
    parser = argparse.ArgumentParser(prog="agentos-mcp")
    parser.add_argument("--root", default=os.environ.get("AGENTOS_PROJECT_ROOT", "."))
    parser.add_argument("--task-id", default=os.environ.get("AGENTOS_TASK_ID"))
    parser.add_argument("--session-id", default=os.environ.get("AGENTOS_SESSION_ID"))
    args = parser.parse_args(argv)
    serve(Path(args.root).resolve(), args.task_id, args.session_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
