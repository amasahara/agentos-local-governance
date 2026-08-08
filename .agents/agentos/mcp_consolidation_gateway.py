"""
File: .agents/agentos/mcp_consolidation_gateway.py

Purpose:
    Add read-only v0.20.2 consolidation visibility to MCP while keeping all
    human review, approval, execution, and rollback mutations outside LLM MCP.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .project_consolidation import get_consolidation

TOOLS = [
    {
        "name": "agentos.project_consolidation_get",
        "description": "Read a Primary-Project Consolidation, its sources, mappings, approval state and provenance. Read-only.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}}, "required": ["consolidation_id"]},
    },
    {
        "name": "agentos.project_consolidation_plan_get",
        "description": "Read the current consolidation plan and plan hash. Read-only; cannot review or approve.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}}, "required": ["consolidation_id"]},
    },
    {
        "name": "agentos.project_consolidation_provenance_get",
        "description": "Read per-component consolidation provenance and rollback state. Read-only.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}}, "required": ["consolidation_id"]},
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
    state = get_consolidation(root, int(arguments["consolidation_id"]))
    if name == "agentos.project_consolidation_get":
        return state
    if name == "agentos.project_consolidation_plan_get":
        return {
            "ok": True,
            "consolidation": state["consolidation"],
            "sources": state["sources"],
            "mappings": state["mappings"],
            "review": state["review"],
            "approval": state["approval"],
            "current_plan_hash": state["current_plan_hash"],
        }
    if name == "agentos.project_consolidation_provenance_get":
        return {"ok": True, "consolidation_id": arguments["consolidation_id"], "provenance": state["provenance"]}
    raise RuntimeError(f"unknown v0.20.2 consolidation tool: {name}")


def _response(rid: Any, result: Any = None, error: str | None = None) -> str:
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": error}}, ensure_ascii=False)
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = os.environ.get("AGENTOS_V0201_MCP")
    old = Path(launcher) if launcher else project_root() / ".agents/bin/agentos-mcp.v0201"
    if not old.exists():
        print(_response(None, error=f"v0.20.1 MCP backend not found: {old}"), flush=True)
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
                print(_response(rid, error="v0.20.1 MCP backend terminated"), flush=True)
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
                    server["version"] = "0.20.2"
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
