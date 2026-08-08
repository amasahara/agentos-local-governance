"""
File: .agents/agentos/mcp_identity_gateway.py

Purpose:
    Add read-only project identity and purpose tools to an existing AgentOS MCP
    gateway while preserving the v0.19.5 gateway as the execution backend.

Responsibilities:
    - Append three read-only v0.20.0 tools to `tools/list`.
    - Handle identity reads locally without exposing mutation over MCP.
    - Forward every pre-existing request unchanged to the v0.19.5 MCP process.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .project_identity import ensure_instance_id, ensure_project_id, load_purpose, verify_identity

TOOLS = [
    {
        "name": "agentos.project_identity_get",
        "description": "Read the stable project UUID and local instance UUID. Read-only.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agentos.project_identity_verify",
        "description": "Verify stable identity, purpose completeness, relocation, and clone collision state. Read-only.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agentos.project_purpose_get",
        "description": "Read the human-confirmed business domain, purpose, capabilities, and role. Read-only.",
        "inputSchema": {"type": "object", "properties": {}},
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


def _local_call(name: str, root: Path) -> dict[str, Any]:
    if name == "agentos.project_identity_get":
        return {
            "project": ensure_project_id(root),
            "instance": ensure_instance_id(root),
        }
    if name == "agentos.project_identity_verify":
        return verify_identity(root)
    if name == "agentos.project_purpose_get":
        return {"purpose": load_purpose(root)}
    raise RuntimeError(f"unknown v0.20.0 identity tool: {name}")


def _response(rid: Any, result: Any = None, error: str | None = None) -> str:
    if error is not None:
        return json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": error}}, ensure_ascii=False)
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    launcher = os.environ.get("AGENTOS_V0195_MCP")
    if launcher:
        old = Path(launcher)
    else:
        old = project_root() / ".agents/bin/agentos-mcp.v0195"
    if not old.exists():
        print(_response(None, error=f"v0.19.5 MCP backend not found: {old}"), flush=True)
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
        try:
            req = json.loads(line)
            rid = req.get("id")
            method = req.get("method")
            if method == "tools/call":
                params = req.get("params") or {}
                name = params.get("name")
                if name in TOOL_NAMES:
                    value = _local_call(name, root)
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
                    print(_response(rid, result=result), flush=True)
                    continue
            child.stdin.write(line)
            child.stdin.flush()
            forwarded = child.stdout.readline()
            if not forwarded:
                print(_response(rid, error="v0.19.5 MCP backend terminated"), flush=True)
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
                    server["version"] = "0.20.0"
                forwarded = json.dumps(resp, ensure_ascii=False) + "\n"
            sys.stdout.write(forwarded)
            sys.stdout.flush()
        except Exception as exc:
            rid = req.get("id") if isinstance(locals().get("req"), dict) else None
            print(_response(rid, error=str(exc)), flush=True)
    try:
        child.stdin.close()
    except Exception:
        pass
    return child.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
