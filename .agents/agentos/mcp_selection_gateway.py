"""
File: .agents/agentos/mcp_selection_gateway.py

Purpose:
    Add read-only v0.20.1 primary-selection intelligence to the existing
    v0.20.0 MCP gateway without exposing human approval mutations to LLMs.

Responsibilities:
    - Append read-only candidate/compatibility/recommendation/status tools.
    - Execute local read-only selection queries.
    - Forward all v0.20.0 identity and legacy AgentOS MCP traffic unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .project_selection import (
    get_candidate_set,
    get_primary_selection,
    recommend_primary,
)

TOOLS = [
    {
        "name": "agentos.project_candidate_set_get",
        "description": "Read a registered multi-project candidate set and its compatibility matrix. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_set_id": {"type": "integer"}},
            "required": ["candidate_set_id"],
        },
    },
    {
        "name": "agentos.project_domain_compatibility_get",
        "description": "Read deterministic business-domain and purpose compatibility evidence. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_set_id": {"type": "integer"}},
            "required": ["candidate_set_id"],
        },
    },
    {
        "name": "agentos.project_primary_recommend",
        "description": "Return an advisory primary-project ranking. Never selects or approves a primary project.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_set_id": {"type": "integer"}},
            "required": ["candidate_set_id"],
        },
    },
    {
        "name": "agentos.project_primary_selection_get",
        "description": "Read the human-selected primary project, if selection has been committed. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_set_id": {"type": "integer"}},
            "required": ["candidate_set_id"],
        },
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def project_root() -> Path:
    """Resolve the active AgentOS root for local selection state."""
    configured = os.environ.get("AGENTOS_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Execute one read-only local selection query."""
    candidate_set_id = int(arguments["candidate_set_id"])
    if name == "agentos.project_candidate_set_get":
        return get_candidate_set(root, candidate_set_id)
    if name == "agentos.project_domain_compatibility_get":
        state = get_candidate_set(root, candidate_set_id)
        return {
            "ok": True,
            "candidate_set_id": candidate_set_id,
            "compatibility": state["compatibility"],
        }
    if name == "agentos.project_primary_recommend":
        return recommend_primary(root, candidate_set_id)
    if name == "agentos.project_primary_selection_get":
        return get_primary_selection(root, candidate_set_id)
    raise RuntimeError(f"unknown v0.20.1 selection tool: {name}")


def _response(rid: Any, result: Any = None, error: str | None = None) -> str:
    """Build a compact JSON-RPC response line."""
    if error is not None:
        return json.dumps(
            {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": error}},
            ensure_ascii=False,
        )
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    """Run the v0.20.1 sidecar in front of the v0.20.0 MCP gateway."""
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = os.environ.get("AGENTOS_V0200_MCP")
    old = Path(launcher) if launcher else project_root() / ".agents/bin/agentos-mcp.v0200"
    if not old.exists():
        print(_response(None, error=f"v0.20.0 MCP backend not found: {old}"), flush=True)
        return 2
    child = subprocess.Popen(
        [str(old), *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
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
                print(_response(rid, error="v0.20.0 MCP backend terminated"), flush=True)
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
                    server["version"] = "0.20.1"
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
