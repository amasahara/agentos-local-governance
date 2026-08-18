"""
File: .agents/agentos/mcp_v0270.py
Purpose: Expose read-only Governed Skill Contract v2 inspection over MCP.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .skill_contract_v2 import list_skill_contracts, skill_contract_get, skill_contract_status

TOOLS = [
    {"name":"agentos.skill_contract_get","description":"Read one governed Skill Contract v2 or legacy-v1 marker.","inputSchema":{"type":"object","properties":{"skill_id":{"type":"integer"}},"required":["skill_id"]}},
    {"name":"agentos.skill_contract_status_get","description":"Read governed Skill Contract v2 coverage and authority status.","inputSchema":{"type":"object","properties":{"skill_id":{"type":"integer"}}}},
    {"name":"agentos.skill_contracts_list","description":"List skill contract metadata without mutation or approval authority.","inputSchema":{"type":"object","properties":{}}},
]
TOOL_NAMES = {item["name"] for item in TOOLS}

def dispatch(root: Path, name: str, arguments: dict[str, Any]) -> Any:
    if name == "agentos.skill_contract_get":
        return skill_contract_get(root, int(arguments["skill_id"]), read_only=True)
    if name == "agentos.skill_contract_status_get":
        raw = arguments.get("skill_id")
        return skill_contract_status(root, int(raw) if raw is not None else None, read_only=True)
    if name == "agentos.skill_contracts_list":
        return list_skill_contracts(root, read_only=True)
    raise KeyError(name)
