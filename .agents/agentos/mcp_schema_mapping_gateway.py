"""
File: .agents/agentos/mcp_schema_mapping_gateway.py

Purpose:
    Add read-only v0.21.1 target-contract and field-mapping visibility to MCP.

Responsibilities:
    - Let LLM agents inspect metadata-only schema snapshots and approved/draft contracts.
    - Let agents inspect field mappings and v0.21.2 readiness.
    - Let agents compute advisory lexical/type mapping suggestions without persisting state.
    - Keep snapshot registration, contract approval, and mapping confirmation outside MCP.
    - Forward older MCP methods to the v0.21.0 gateway.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .schema_mapping import (
    get_schema_snapshot,
    get_target_contract,
    list_field_mappings,
    mapping_readiness,
    suggest_field_mappings,
)

TOOLS = [
    {
        "name": "agentos.db_schema_snapshot_get",
        "description": "Read a metadata-only database schema snapshot. No record data or credentials are returned.",
        "inputSchema": {"type": "object", "properties": {"snapshot_id": {"type": "integer"}}, "required": ["snapshot_id"]},
    },
    {
        "name": "agentos.db_target_contract_get",
        "description": "Read a versioned target schema contract and its immutable hashes. Read-only.",
        "inputSchema": {"type": "object", "properties": {"contract_id": {"type": "integer"}}, "required": ["contract_id"]},
    },
    {
        "name": "agentos.db_field_mappings_get",
        "description": "List directional SOURCE-to-TARGET field mappings for one database consolidation. Read-only.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}, "status": {"type": "string"}}, "required": ["consolidation_id"]},
    },
    {
        "name": "agentos.db_field_mapping_suggest",
        "description": "Compute advisory local lexical/type mapping suggestions. Does not persist or confirm mappings.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}, "source_snapshot_id": {"type": "integer"}, "target_contract_id": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["consolidation_id", "source_snapshot_id", "target_contract_id"]},
    },
    {
        "name": "agentos.db_mapping_readiness_get",
        "description": "Read whether confirmed current mappings are ready for v0.21.2 extraction/validation. Does not extract data.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}, "target_contract_id": {"type": "integer"}}, "required": ["consolidation_id", "target_contract_id"]},
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


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
    """Dispatch read-only v0.21.1 tools locally."""
    if name == "agentos.db_schema_snapshot_get":
        return get_schema_snapshot(root, int(arguments["snapshot_id"]))
    if name == "agentos.db_target_contract_get":
        return get_target_contract(root, int(arguments["contract_id"]))
    if name == "agentos.db_field_mappings_get":
        return list_field_mappings(root, int(arguments["consolidation_id"]), status=arguments.get("status"))
    if name == "agentos.db_field_mapping_suggest":
        return suggest_field_mappings(root, consolidation_id=int(arguments["consolidation_id"]), source_snapshot_id=int(arguments["source_snapshot_id"]), target_contract_id=int(arguments["target_contract_id"]), limit=int(arguments.get("limit", 50)))
    if name == "agentos.db_mapping_readiness_get":
        return mapping_readiness(root, int(arguments["consolidation_id"]), int(arguments["target_contract_id"]))
    raise RuntimeError(f"unknown v0.21.1 schema-mapping tool: {name}")


def _response(rid: Any, result: Any = None, error: str | None = None) -> str:
    """Build one JSON-RPC response."""
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": error}}, ensure_ascii=False)
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    """Run wrapper MCP server and preserve v0.21.0 tools."""
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = os.environ.get("AGENTOS_V0210_MCP")
    old = Path(launcher) if launcher else project_root() / ".agents/bin/agentos-mcp.v0210"
    if not old.exists():
        print(_response(None, error=f"v0.21.0 MCP backend not found: {old}"), flush=True)
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
                print(_response(rid, error="v0.21.0 MCP backend terminated"), flush=True)
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
                    server["version"] = "0.21.1"
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
