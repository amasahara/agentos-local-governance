"""Path: .agents/agentos/mcp_v0255.py
Purpose: Read-only MCP inspection for v0.25.5 Architecture Change Proposal & ADR lifecycle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .architecture_change import (
    architecture_adr_get,
    architecture_change_proposal_get,
    architecture_change_proposals_list,
    architecture_change_status,
)

TOOLS = [
    {
        "name": "agentos.architecture_change_proposal_get",
        "description": "Read one latest/selected Architecture Change Proposal and linked ADR; no approval authority.",
        "inputSchema": {"type": "object", "properties": {"proposal_id": {"type": "integer"}}, "additionalProperties": False},
    },
    {
        "name": "agentos.architecture_change_proposals_list",
        "description": "List Architecture Change Proposal summaries read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft","submitted","reviewed","approved","rejected","withdrawn"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agentos.architecture_adr_get",
        "description": "Read one linked ADR and stable Markdown rendering; no accept/reject authority.",
        "inputSchema": {"type": "object", "properties": {"adr_id": {"type": "integer"}, "proposal_id": {"type": "integer"}}, "additionalProperties": False},
    },
    {
        "name": "agentos.architecture_change_status_get",
        "description": "Read proposal/ADR lifecycle status and explicit human authority boundaries.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
TOOL_NAMES = {tool["name"] for tool in TOOLS}


def dispatch(name: str, arguments: dict[str, Any], root: Path, task_id: str | None = None, session_id: str | None = None) -> Any:
    """Dispatch read-only v0.25.5 MCP tools only."""
    del task_id, session_id
    if name == "agentos.architecture_change_proposal_get":
        return architecture_change_proposal_get(root, proposal_id=arguments.get("proposal_id"))
    if name == "agentos.architecture_change_proposals_list":
        return architecture_change_proposals_list(root, status=arguments.get("status"), limit=int(arguments.get("limit", 100)))
    if name == "agentos.architecture_adr_get":
        return architecture_adr_get(root, adr_id=arguments.get("adr_id"), proposal_id=arguments.get("proposal_id"))
    if name == "agentos.architecture_change_status_get":
        return architecture_change_status(root)
    raise KeyError(name)
