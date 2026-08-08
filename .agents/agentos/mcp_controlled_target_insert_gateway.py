"""
File: .agents/agentos/mcp_controlled_target_insert_gateway.py

Purpose:
    Add read-only v0.22.0 controlled-target-insert visibility to MCP.

Responsibilities:
    - Let LLM agents inspect immutable insert plans, readiness, generated prepared INSERT shape, and receipts.
    - Never expose staged row contents, credentials, human approval mutation, or external write execution.
    - Preserve the merged read-only MCP catalog from v0.21.2 and older nodes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .controlled_target_insert import (
    build_insert_spec,
    get_target_insert_plan,
    get_target_insert_readiness,
    get_target_insert_receipt,
)
from .mcp_read_only_extraction_gateway import ALL_TOOLS as V0212_TOOLS, _local_call as _v0212_call

TOOLS = [
    {
        "name": "agentos.db_target_insert_plan_get",
        "description": "Read v0.22.0 immutable controlled TARGET INSERT plan metadata and hashes. No row values or credentials are returned.",
        "inputSchema": {"type": "object", "properties": {"insert_run_id": {"type": "integer"}}, "required": ["insert_run_id"]},
    },
    {
        "name": "agentos.db_target_insert_readiness_get",
        "description": "Read current human-approval, staging-integrity, and contract readiness for a controlled TARGET INSERT run.",
        "inputSchema": {"type": "object", "properties": {"insert_run_id": {"type": "integer"}}, "required": ["insert_run_id"]},
    },
    {
        "name": "agentos.db_target_insert_spec_get",
        "description": "Read the generated parameterized INSERT-only statement shape. No parameter values are returned and raw SQL execution is not exposed.",
        "inputSchema": {"type": "object", "properties": {"insert_run_id": {"type": "integer"}}, "required": ["insert_run_id"]},
    },
    {
        "name": "agentos.db_target_insert_receipt_get",
        "description": "Read privacy-safe TARGET insert status/receipt hashes and row counts. No inserted business values are returned.",
        "inputSchema": {"type": "object", "properties": {"insert_run_id": {"type": "integer"}}, "required": ["insert_run_id"]},
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def _merge_tools(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge MCP tool catalogs by first-seen name."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            name = str(item.get("name", ""))
            if name and name not in seen:
                merged.append(item)
                seen.add(name)
    return merged


ALL_TOOLS = _merge_tools(V0212_TOOLS, TOOLS)
ALL_TOOL_NAMES = {item["name"] for item in ALL_TOOLS}


def project_root() -> Path:
    """Resolve active AgentOS root."""
    configured = os.environ.get("AGENTOS_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch v0.22.0 and all known older read-only AgentOS tools locally."""
    if name == "agentos.db_target_insert_plan_get":
        return get_target_insert_plan(root, int(arguments["insert_run_id"]))
    if name == "agentos.db_target_insert_readiness_get":
        return get_target_insert_readiness(root, int(arguments["insert_run_id"]))
    if name == "agentos.db_target_insert_spec_get":
        return build_insert_spec(root, int(arguments["insert_run_id"]))
    if name == "agentos.db_target_insert_receipt_get":
        return get_target_insert_receipt(root, int(arguments["insert_run_id"]))
    if name in {item["name"] for item in V0212_TOOLS}:
        return _v0212_call(name, arguments, root)
    raise RuntimeError(f"unknown AgentOS MCP tool: {name}")


def _response(rid: Any, result: Any = None, error: str | None = None) -> str:
    """Build one JSON-RPC response."""
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": error}}, ensure_ascii=False)
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    """Run v0.22.0 MCP with local read-only discovery and legacy forwarding."""
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = os.environ.get("AGENTOS_V0212_MCP")
    old = Path(launcher) if launcher else project_root() / ".agents/bin/agentos-mcp.v0212"
    child = None
    root = project_root()
    for line in sys.stdin:
        req: dict[str, Any] | None = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            method = req.get("method")
            if method == "initialize":
                protocol = (req.get("params") or {}).get("protocolVersion") or "2024-11-05"
                result = {
                    "protocolVersion": protocol,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "agentos-local-governance", "version": "0.22.0"},
                }
                print(_response(rid, result=result), flush=True)
                continue
            if method == "tools/list":
                print(_response(rid, result={"tools": ALL_TOOLS}), flush=True)
                continue
            if method == "tools/call":
                params = req.get("params") or {}
                name = params.get("name")
                if name in ALL_TOOL_NAMES:
                    value = _local_call(str(name), params.get("arguments") or {}, root)
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, default=str)}]}
                    print(_response(rid, result=result), flush=True)
                    continue
            if not old.exists():
                print(_response(rid, error=f"v0.21.2 MCP backend not found: {old}"), flush=True)
                continue
            if child is None:
                child = subprocess.Popen([str(old), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1)
            assert child.stdin is not None and child.stdout is not None
            child.stdin.write(line); child.stdin.flush()
            forwarded = child.stdout.readline()
            if not forwarded:
                print(_response(rid, error="v0.21.2 MCP backend terminated"), flush=True)
                return 3
            sys.stdout.write(forwarded); sys.stdout.flush()
        except Exception as exc:
            rid = req.get("id") if isinstance(req, dict) else None
            print(_response(rid, error=str(exc)), flush=True)
    if child is not None:
        try:
            assert child.stdin is not None
            child.stdin.close()
        except Exception:
            pass
        return child.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
