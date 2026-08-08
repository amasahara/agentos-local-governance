"""
File: .agents/agentos/mcp_database_boundary_gateway.py

Purpose:
    Add read-only v0.21.0 database-boundary visibility to MCP.

Responsibilities:
    - Let LLM agents inspect connection/consolidation metadata with credentials redacted.
    - Let agents ask for abstract allow/deny boundary decisions.
    - Keep connection registration, SOURCE verification, and consolidation mutation outside MCP.
    - Forward older MCP methods to the v0.20.2 gateway.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .database_boundary import authorize_operation, get_connection, get_consolidation

TOOLS = [
    {
        "name": "agentos.db_connection_get",
        "description": "Read redacted SOURCE/TARGET connection metadata. Read-only; credentials are never returned.",
        "inputSchema": {"type": "object", "properties": {"connection_id": {"type": "integer"}}, "required": ["connection_id"]},
    },
    {
        "name": "agentos.db_consolidation_get",
        "description": "Read a one-target database consolidation and its verified SOURCE connections. Read-only.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}}, "required": ["consolidation_id"]},
    },
    {
        "name": "agentos.db_boundary_check",
        "description": "Check whether an abstract database operation is allowed by v0.21.0 boundary policy. Does not execute SQL.",
        "inputSchema": {"type": "object", "properties": {"connection_id": {"type": "integer"}, "operation": {"type": "string"}}, "required": ["connection_id", "operation"]},
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def project_root() -> Path:
    configured = os.environ.get("AGENTOS_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name == "agentos.db_connection_get":
        return get_connection(root, int(arguments["connection_id"]))
    if name == "agentos.db_consolidation_get":
        return get_consolidation(root, int(arguments["consolidation_id"]))
    if name == "agentos.db_boundary_check":
        return authorize_operation(root, int(arguments["connection_id"]), str(arguments["operation"]))
    raise RuntimeError(f"unknown v0.21.0 database-boundary tool: {name}")


def _response(rid: Any, result: Any = None, error: str | None = None) -> str:
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": error}}, ensure_ascii=False)
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = os.environ.get("AGENTOS_V0202_MCP")
    old = Path(launcher) if launcher else project_root() / ".agents/bin/agentos-mcp.v0202"
    if not old.exists():
        print(_response(None, error=f"v0.20.2 MCP backend not found: {old}"), flush=True)
        return 2
    child = subprocess.Popen([str(old), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1)
    assert child.stdin is not None and child.stdout is not None
    root = project_root()
    for line in sys.stdin:
        req: dict[str, Any] | None = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            method = req.get("method")
            if method == "tools/call":
                params = req.get("params") or {}
                name = params.get("name")
                if name in TOOL_NAMES:
                    value = _local_call(name, params.get("arguments") or {}, root)
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
                    print(_response(rid, result=result), flush=True)
                    continue
            child.stdin.write(line)
            child.stdin.flush()
            forwarded = child.stdout.readline()
            if not forwarded:
                print(_response(rid, error="v0.20.2 MCP backend terminated"), flush=True)
                return 3
            if method == "tools/list":
                resp = json.loads(forwarded)
                result = resp.get("result")
                if isinstance(result, dict):
                    existing = result.setdefault("tools", [])
                    names = {item.get("name") for item in existing if isinstance(item, dict)}
                    existing.extend(item for item in TOOLS if item["name"] not in names)
                forwarded = json.dumps(resp, ensure_ascii=False) + "\n"
            elif method == "initialize":
                resp = json.loads(forwarded)
                server = (resp.get("result") or {}).get("serverInfo")
                if isinstance(server, dict):
                    server["version"] = "0.21.0"
                forwarded = json.dumps(resp, ensure_ascii=False) + "\n"
            sys.stdout.write(forwarded)
            sys.stdout.flush()
        except Exception as exc:
            rid = req.get("id") if isinstance(req, dict) else None
            print(_response(rid, error=str(exc)), flush=True)
    try:
        child.stdin.close()
    except Exception:
        pass
    return child.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
