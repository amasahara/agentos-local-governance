"""
File: .agents/agentos/mcp_data_subject_rights.py

Purpose:
    Expose v0.22.7 data-subject rights inspection through read-only MCP tools.

Responsibilities:
    - Return privacy-safe erasure request/plan/status evidence.
    - Never expose raw subject identifiers or erasure review/approval/execution mutation.
    - Never add TARGET UPDATE/DELETE authority.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .data_subject_rights import DataSubjectRightsError, erasure_request_get, erasure_plan_get, erasure_status_get

TOOLS=[
 {"name":"agentos.data_subject_erasure_request_get","description":"Read one immutable erasure request; no raw subject identifier.","inputSchema":{"type":"object","properties":{"request_id":{"type":"integer"}},"required":["request_id"]}},
 {"name":"agentos.data_subject_erasure_plan_get","description":"Read one immutable erasure plan and local/external erasure status.","inputSchema":{"type":"object","properties":{"plan_id":{"type":"integer"}},"required":["plan_id"]}},
 {"name":"agentos.data_subject_erasure_status_get","description":"Read tombstone and erasure status for a canonical entity UUID.","inputSchema":{"type":"object","properties":{"entity_uuid":{"type":"string"}},"required":["entity_uuid"]}},
]


def _local_call(name:str, arguments:dict[str,Any], root:Path)->dict[str,Any]:
    """Dispatch read-only privacy inspection."""
    try:
        if name=="agentos.data_subject_erasure_request_get": return erasure_request_get(root,int(arguments["request_id"]))
        if name=="agentos.data_subject_erasure_plan_get": return erasure_plan_get(root,int(arguments["plan_id"]))
        if name=="agentos.data_subject_erasure_status_get": return erasure_status_get(root,str(arguments["entity_uuid"]))
    except (DataSubjectRightsError,KeyError,ValueError) as exc:
        return {"ok":False,"error":str(exc)}
    return {"ok":False,"error":"unknown v0.22.7 read-only MCP tool"}
