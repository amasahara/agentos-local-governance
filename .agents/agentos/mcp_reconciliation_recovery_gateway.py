"""
File: .agents/agentos/mcp_reconciliation_recovery_gateway.py

Purpose:
    Expose v0.22.2 reconciliation/recovery evidence through read-only MCP tools.

Responsibilities:
    - Aggregate the v0.22.1 read-only MCP catalog.
    - Expose reconciliation summaries, specs, recovery readiness, cases, and checkpoints.
    - Keep reconciliation execution and every recovery mutation outside MCP.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .mcp_identity_resolution_gateway import ALL_TOOLS as V0221_TOOLS, _local_call as _v0221_call
from .reconciliation_recovery import (
    build_reconciliation_spec,
    get_reconciliation_run,
    get_reconciliation_summary,
    get_recovery_readiness,
    list_recovery_cases,
    list_recovery_checkpoints,
)

LOCAL_TOOLS = [
    {"name": "agentos.db_reconciliation_get", "description": "Read one privacy-safe TARGET reconciliation result.",
     "inputSchema": {"type": "object", "properties": {"reconciliation_run_id": {"type": "integer"}}, "required": ["reconciliation_run_id"]}},
    {"name": "agentos.db_reconciliation_summary_get", "description": "Read extraction→identity→insert→lineage reconciliation counts.",
     "inputSchema": {"type": "object", "properties": {"reconciliation_run_id": {"type": "integer"}}, "required": ["reconciliation_run_id"]}},
    {"name": "agentos.db_reconciliation_spec_get", "description": "Read the SELECT-only reconciliation query shape without parameters or values.",
     "inputSchema": {"type": "object", "properties": {"reconciliation_run_id": {"type": "integer"}}, "required": ["reconciliation_run_id"]}},
    {"name": "agentos.db_recovery_cases_get", "description": "List privacy-safe recovery cases; no recovery mutation is available over MCP.",
     "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}}}},
    {"name": "agentos.db_recovery_readiness_get", "description": "Read fail-closed recovery readiness for one insert run.",
     "inputSchema": {"type": "object", "properties": {"insert_run_id": {"type": "integer"}}, "required": ["insert_run_id"]}},
    {"name": "agentos.db_recovery_checkpoints_get", "description": "Read privacy-safe recovery checkpoint hashes for one insert run.",
     "inputSchema": {"type": "object", "properties": {"insert_run_id": {"type": "integer"}}, "required": ["insert_run_id"]}},
]
ALL_TOOLS = [*V0221_TOOLS, *LOCAL_TOOLS]
ALL_TOOL_NAMES = {item["name"] for item in ALL_TOOLS}
V0221_NAMES = {item["name"] for item in V0221_TOOLS}


def project_root() -> Path:
    """Resolve the active AgentOS project root."""
    if os.environ.get("AGENTOS_PROJECT_ROOT"):
        return Path(os.environ["AGENTOS_PROJECT_ROOT"]).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _local_call(name: str, args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch local v0.22.2 and inherited v0.22.1 read-only MCP tools."""
    if name == "agentos.db_reconciliation_get":
        return get_reconciliation_run(root, int(args["reconciliation_run_id"]))
    if name == "agentos.db_reconciliation_summary_get":
        return get_reconciliation_summary(root, int(args["reconciliation_run_id"]))
    if name == "agentos.db_reconciliation_spec_get":
        return build_reconciliation_spec(root, int(args["reconciliation_run_id"]))
    if name == "agentos.db_recovery_cases_get":
        return list_recovery_cases(root, status=args.get("status"))
    if name == "agentos.db_recovery_readiness_get":
        return get_recovery_readiness(root, int(args["insert_run_id"]))
    if name == "agentos.db_recovery_checkpoints_get":
        return list_recovery_checkpoints(root, int(args["insert_run_id"]))
    if name in V0221_NAMES:
        return _v0221_call(name, args, root)
    raise RuntimeError(f"unknown AgentOS MCP tool: {name}")


def _response(request_id: Any, result: Any = None, error: str | None = None) -> str:
    """Build one JSON-RPC response."""
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": error}}, ensure_ascii=False)
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    """Run v0.22.2 MCP with local read-only discovery and legacy forwarding."""
    args = list(sys.argv[1:] if argv is None else argv)
    root = project_root()
    child = None
    launcher = os.environ.get("AGENTOS_V0221_MCP")
    old = Path(launcher) if launcher else root / ".agents/bin/agentos-mcp.v0221"
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method")
            if method == "initialize":
                protocol = (request.get("params") or {}).get("protocolVersion") or "2024-11-05"
                print(_response(request_id, {"protocolVersion": protocol, "capabilities": {"tools": {}},
                                             "serverInfo": {"name": "agentos-local-governance", "version": "0.22.2"}}), flush=True)
                continue
            if method == "tools/list":
                print(_response(request_id, {"tools": ALL_TOOLS}), flush=True)
                continue
            if method == "tools/call":
                params = request.get("params") or {}
                name = params.get("name")
                if name in ALL_TOOL_NAMES:
                    value = _local_call(str(name), params.get("arguments") or {}, root)
                    print(_response(request_id, {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, default=str)}]}), flush=True)
                    continue
            if not old.exists():
                print(_response(request_id, error=f"v0.22.1 MCP backend not found: {old}"), flush=True)
                continue
            if child is None:
                child = subprocess.Popen([str(old), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1)
            assert child.stdin and child.stdout
            child.stdin.write(line)
            child.stdin.flush()
            forwarded = child.stdout.readline()
            if not forwarded:
                print(_response(request_id, error="v0.22.1 MCP backend terminated"), flush=True)
                return 3
            sys.stdout.write(forwarded)
            sys.stdout.flush()
        except Exception as exc:
            request_id = request.get("id") if isinstance(request, dict) else None
            print(_response(request_id, error=str(exc)), flush=True)
    if child is not None:
        try:
            assert child.stdin
            child.stdin.close()
        except Exception:
            pass
        return child.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
