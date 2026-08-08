"""
File: .agents/agentos/mcp_read_only_extraction_gateway.py

Purpose:
    Add read-only v0.21.2 extraction/validation visibility to MCP.

Responsibilities:
    - Let LLM agents inspect extraction batch metadata, validation summaries, findings, and staging integrity.
    - Never return staged business-record contents or raw quarantine values.
    - Never expose batch creation, SOURCE execution, raw SQL, secret resolution, or TARGET writes.
    - Forward older MCP methods to the v0.21.1 gateway.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .read_only_extraction import (
    get_extraction_batch,
    get_extraction_summary,
    get_validation_findings,
    verify_staging_artifact,
)
from .mcp_identity_gateway import TOOLS as IDENTITY_TOOLS, _local_call as _identity_call
from .mcp_selection_gateway import TOOLS as SELECTION_TOOLS, _local_call as _selection_call
from .mcp_consolidation_gateway import TOOLS as CONSOLIDATION_TOOLS, _local_call as _consolidation_call
from .mcp_database_boundary_gateway import TOOLS as BOUNDARY_TOOLS, _local_call as _boundary_call
from .mcp_schema_mapping_gateway import TOOLS as SCHEMA_MAPPING_TOOLS, _local_call as _schema_mapping_call

TOOLS = [
    {
        "name": "agentos.db_extraction_batch_get",
        "description": "Read v0.21.2 extraction batch metadata and immutable hashes. Does not return record values.",
        "inputSchema": {"type": "object", "properties": {"batch_id": {"type": "integer"}}, "required": ["batch_id"]},
    },
    {
        "name": "agentos.db_extraction_summary_get",
        "description": "Read privacy-safe extraction/validation counts, artifact hashes, and v0.22.0 readiness.",
        "inputSchema": {"type": "object", "properties": {"batch_id": {"type": "integer"}}, "required": ["batch_id"]},
    },
    {
        "name": "agentos.db_validation_findings_get",
        "description": "Read validation issues with value hashes only; raw business values are never returned.",
        "inputSchema": {"type": "object", "properties": {"batch_id": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["batch_id"]},
    },
    {
        "name": "agentos.db_staging_integrity_get",
        "description": "Verify staging/quarantine/manifest artifact hashes without returning artifact contents.",
        "inputSchema": {"type": "object", "properties": {"batch_id": {"type": "integer"}}, "required": ["batch_id"]},
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def _merge_tools(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge tool catalogs by name while preserving first definition order."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            name = str(item.get("name", ""))
            if name and name not in seen:
                merged.append(item)
                seen.add(name)
    return merged


ALL_TOOLS = _merge_tools(IDENTITY_TOOLS, SELECTION_TOOLS, CONSOLIDATION_TOOLS, BOUNDARY_TOOLS, SCHEMA_MAPPING_TOOLS, TOOLS)
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
    """Dispatch all known AgentOS read-only MCP tools locally.

    This bypasses the historical cat-style compatibility stub for discovery and
    keeps tools/list deterministic in v0.21.2. Unknown methods may still be
    forwarded to the older backend for compatibility.
    """
    if name in {item["name"] for item in TOOLS}:
        if name == "agentos.db_extraction_batch_get":
            return get_extraction_batch(root, int(arguments["batch_id"]))
        if name == "agentos.db_extraction_summary_get":
            return get_extraction_summary(root, int(arguments["batch_id"]))
        if name == "agentos.db_validation_findings_get":
            return get_validation_findings(root, int(arguments["batch_id"]), limit=int(arguments.get("limit", 1000)))
        if name == "agentos.db_staging_integrity_get":
            return verify_staging_artifact(root, int(arguments["batch_id"]))
    if name in {item["name"] for item in IDENTITY_TOOLS}:
        return _identity_call(name, root)
    if name in {item["name"] for item in SELECTION_TOOLS}:
        return _selection_call(name, arguments, root)
    if name in {item["name"] for item in CONSOLIDATION_TOOLS}:
        return _consolidation_call(name, arguments, root)
    if name in {item["name"] for item in BOUNDARY_TOOLS}:
        return _boundary_call(name, arguments, root)
    if name in {item["name"] for item in SCHEMA_MAPPING_TOOLS}:
        return _schema_mapping_call(name, arguments, root)
    raise RuntimeError(f"unknown AgentOS MCP tool: {name}")

def _response(rid: Any, result: Any = None, error: str | None = None) -> str:
    """Build one JSON-RPC response."""
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": error}}, ensure_ascii=False)
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    """Run MCP server with local discovery and read-only AgentOS dispatch.

    Known AgentOS tools are served locally. Unknown methods/calls are forwarded
    to the v0.21.1 compatibility backend.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = os.environ.get("AGENTOS_V0211_MCP")
    old = Path(launcher) if launcher else project_root() / ".agents/bin/agentos-mcp.v0211"
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
                    "serverInfo": {"name": "agentos-local-governance", "version": "0.21.2"},
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
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
                    print(_response(rid, result=result), flush=True)
                    continue
            # Compatibility forwarding for non-AgentOS/legacy methods.
            if not old.exists():
                print(_response(rid, error=f"v0.21.1 MCP backend not found: {old}"), flush=True)
                continue
            if child is None:
                child = subprocess.Popen([str(old), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1)
            assert child.stdin is not None and child.stdout is not None
            child.stdin.write(line); child.stdin.flush()
            forwarded = child.stdout.readline()
            if not forwarded:
                print(_response(rid, error="v0.21.1 MCP backend terminated"), flush=True)
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
