"""
File: .agents/agentos/mcp_identity_resolution_gateway.py

Purpose:
    Add read-only v0.22.1 identity/dedup/lineage visibility to MCP.

Responsibilities:
    - Let LLM agents inspect policies, candidates, readiness, and pseudonymous lineage.
    - Never expose raw identity values, policy approval, candidate decisions, resolution execution, or writes.
    - Preserve the merged read-only MCP catalog from v0.22.0 and older nodes.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .identity_resolution import get_entity_lineage, get_identity_policy, get_identity_readiness, get_identity_resolution_run, list_identity_candidates
from .mcp_controlled_target_insert_gateway import ALL_TOOLS as V0220_TOOLS, _local_call as _v0220_call

TOOLS = [
    {"name":"agentos.db_identity_policy_get","description":"Read an approved/draft deterministic identity policy. No business values are returned.","inputSchema":{"type":"object","properties":{"policy_id":{"type":"integer"}},"required":["policy_id"]}},
    {"name":"agentos.db_identity_resolution_get","description":"Read v0.22.1 identity-resolution status, counts, and hashes only.","inputSchema":{"type":"object","properties":{"resolution_run_id":{"type":"integer"}},"required":["resolution_run_id"]}},
    {"name":"agentos.db_identity_candidates_get","description":"Read privacy-safe strong-match candidates. LLM cannot confirm/reject identity candidates.","inputSchema":{"type":"object","properties":{"resolution_run_id":{"type":"integer"}},"required":["resolution_run_id"]}},
    {"name":"agentos.db_identity_readiness_get","description":"Read whether an extraction batch has completed human-governed identity/dedup resolution before TARGET INSERT.","inputSchema":{"type":"object","properties":{"extraction_batch_id":{"type":"integer"}},"required":["extraction_batch_id"]}},
    {"name":"agentos.db_entity_lineage_get","description":"Read pseudonymous source-to-target lineage for a canonical entity UUID. No raw identity values are returned.","inputSchema":{"type":"object","properties":{"entity_uuid":{"type":"string"}},"required":["entity_uuid"]}},
]


def _merge_tools(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge MCP catalogs by first-seen tool name."""
    seen=set(); out=[]
    for group in groups:
        for item in group:
            name=str(item.get("name",""))
            if name and name not in seen: seen.add(name); out.append(item)
    return out

ALL_TOOLS=_merge_tools(V0220_TOOLS,TOOLS); ALL_TOOL_NAMES={x["name"] for x in ALL_TOOLS}; V0220_NAMES={x["name"] for x in V0220_TOOLS}


def project_root() -> Path:
    """Resolve active AgentOS project root."""
    if os.environ.get("AGENTOS_PROJECT_ROOT"): return Path(os.environ["AGENTOS_PROJECT_ROOT"]).resolve()
    cur=Path.cwd().resolve()
    for c in (cur,*cur.parents):
        if (c/".agents").is_dir(): return c
    return cur


def _local_call(name: str, args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch local v0.22.1 and older read-only MCP tools."""
    if name=="agentos.db_identity_policy_get": return get_identity_policy(root,int(args["policy_id"]))
    if name=="agentos.db_identity_resolution_get": return get_identity_resolution_run(root,int(args["resolution_run_id"]))
    if name=="agentos.db_identity_candidates_get": return list_identity_candidates(root,int(args["resolution_run_id"]))
    if name=="agentos.db_identity_readiness_get": return get_identity_readiness(root,int(args["extraction_batch_id"]))
    if name=="agentos.db_entity_lineage_get": return get_entity_lineage(root,str(args["entity_uuid"]))
    if name in V0220_NAMES: return _v0220_call(name,args,root)
    raise RuntimeError(f"unknown AgentOS MCP tool: {name}")


def _response(rid: Any, result: Any=None, error: str|None=None) -> str:
    """Build JSON-RPC response."""
    if error is not None: return json.dumps({"jsonrpc":"2.0","id":rid,"error":{"code":-32000,"message":error}},ensure_ascii=False)
    return json.dumps({"jsonrpc":"2.0","id":rid,"result":result},ensure_ascii=False)


def main(argv: list[str]|None=None) -> int:
    """Run v0.22.1 MCP with local read-only discovery and legacy forwarding."""
    args=list(sys.argv[1:] if argv is None else argv); root=project_root(); child=None
    launcher=os.environ.get("AGENTOS_V0220_MCP"); old=Path(launcher) if launcher else root/".agents/bin/agentos-mcp.v0220"
    for line in sys.stdin:
        req=None
        try:
            req=json.loads(line); rid=req.get("id"); method=req.get("method")
            if method=="initialize":
                protocol=(req.get("params") or {}).get("protocolVersion") or "2024-11-05"
                print(_response(rid,{"protocolVersion":protocol,"capabilities":{"tools":{}},"serverInfo":{"name":"agentos-local-governance","version":"0.22.1"}}),flush=True); continue
            if method=="tools/list": print(_response(rid,{"tools":ALL_TOOLS}),flush=True); continue
            if method=="tools/call":
                params=req.get("params") or {}; name=params.get("name")
                if name in ALL_TOOL_NAMES:
                    value=_local_call(str(name),params.get("arguments") or {},root)
                    print(_response(rid,{"content":[{"type":"text","text":json.dumps(value,ensure_ascii=False,default=str)}]}),flush=True); continue
            if not old.exists(): print(_response(rid,error=f"v0.22.0 MCP backend not found: {old}"),flush=True); continue
            if child is None: child=subprocess.Popen([str(old),*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr,text=True,bufsize=1)
            assert child.stdin and child.stdout; child.stdin.write(line); child.stdin.flush(); forwarded=child.stdout.readline()
            if not forwarded: print(_response(rid,error="v0.22.0 MCP backend terminated"),flush=True); return 3
            sys.stdout.write(forwarded); sys.stdout.flush()
        except Exception as exc:
            rid=req.get("id") if isinstance(req,dict) else None; print(_response(rid,error=str(exc)),flush=True)
    if child is not None:
        try:
            assert child.stdin; child.stdin.close()
        except Exception: pass
        return child.wait(timeout=5)
    return 0

if __name__=="__main__": raise SystemExit(main())
