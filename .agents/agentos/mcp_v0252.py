"""File: .agents/agentos/mcp_v0252.py

Purpose:
    Define v0.25.2 Architecture Contract reads and monotonic human-decision request MCP tools.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .architecture_contract import architecture_get,architecture_section_get,architecture_status
from .human_decision import decision_show,grill_me,request_human_decision

TOOLS=[
 {"name":"agentos.architecture_get","description":"Read the active/latest human-authorized Architecture Contract baseline.","inputSchema":{"type":"object","properties":{"baseline_id":{"type":"integer"}}}},
 {"name":"agentos.architecture_section_get","description":"Read one ARCH-01..ARCH-27 baseline section.","inputSchema":{"type":"object","properties":{"section_id":{"type":"string"},"baseline_id":{"type":"integer"}},"required":["section_id"]}},
 {"name":"agentos.architecture_status_get","description":"Read active Architecture Contract and working-copy match status.","inputSchema":{"type":"object","properties":{}}},
 {"name":"agentos.human_decision_status","description":"Read unresolved Grill Me/human-decision blockers for the bound task.","inputSchema":{"type":"object","properties":{}}},
 {"name":"agentos.human_decision_get","description":"Read one local human-decision request/resolution by ID.","inputSchema":{"type":"object","properties":{"decision_id":{"type":"string"}},"required":["decision_id"]}},
 {"name":"agentos.human_decision_request","description":"Open a blocking human decision. This tool can only make execution more restrictive; it cannot resolve, waive, approve, or activate authority.","inputSchema":{"type":"object","properties":{"phase":{"type":"string"},"decision_type":{"type":"string"},"severity":{"type":"string"},"question":{"type":"string"},"options":{"type":"array","items":{"type":"string"}},"recommendation":{"type":"string"},"recommendation_rationale":{"type":"string"},"requirement_ids":{"type":"array","items":{"type":"string"}},"architecture_section_ids":{"type":"array","items":{"type":"string"}}},"required":["phase","decision_type","severity","question"]}},
]
TOOL_NAMES={x["name"] for x in TOOLS}

def dispatch(name:str,args:dict[str,Any],root:Path,task_id:str|None,session_id:str|None)->dict[str,Any]:
    """Dispatch one v0.25.2 MCP tool.

    Args:
        name: Registered MCP tool name.
        args: Tool arguments.
        root: Governed project root.
        task_id: Optional MCP-bound task identifier.
        session_id: Optional MCP-bound session identifier.

    Returns:
        JSON-compatible tool result.
    """
    if name=="agentos.architecture_get": return architecture_get(root,args.get("baseline_id"),read_only=True)
    if name=="agentos.architecture_section_get": return architecture_section_get(root,str(args["section_id"]),args.get("baseline_id"),read_only=True)
    if name=="agentos.architecture_status_get": return architecture_status(root,read_only=True)
    if name=="agentos.human_decision_status":
        if not task_id: raise RuntimeError("task_id_required")
        return grill_me(root,task_id,read_only=True)
    if name=="agentos.human_decision_get": return {"ok":True,"decision":decision_show(root,str(args["decision_id"]),read_only=True)}
    if name=="agentos.human_decision_request":
        if not task_id: raise RuntimeError("task_id_required")
        return request_human_decision(root,task_id,str(args["phase"]),str(args["decision_type"]),str(args["severity"]),str(args["question"]),options=list(args.get("options") or []),recommendation=args.get("recommendation"),recommendation_rationale=args.get("recommendation_rationale"),requirement_ids=list(args.get("requirement_ids") or []),architecture_section_ids=list(args.get("architecture_section_ids") or []),raised_by_session=session_id,blocking=True)
    raise RuntimeError(f"unknown_v0252_mcp_tool:{name}")
