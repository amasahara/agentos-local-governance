"""Path: .agents/agentos/mcp_v0253.py
Purpose: Read-only MCP inspection tools for v0.25.3 architecture discovery/evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .architecture_discovery import (
    architecture_discrepancies_get,
    architecture_evidence_get,
    architecture_observations_get,
    architecture_scan_get,
)

TOOLS = [
    {"name": "agentos.architecture_scan_get", "description": "Read a persisted architecture discovery scan summary.", "inputSchema": {"type": "object", "properties": {"scan_id": {"type": "integer"}}, "additionalProperties": False}},
    {"name": "agentos.architecture_observations_get", "description": "Read deterministic observations from a completed scan.", "inputSchema": {"type": "object", "properties": {"scan_id": {"type": "integer"}, "section_id": {"type": "string"}}, "required": ["scan_id"], "additionalProperties": False}},
    {"name": "agentos.architecture_evidence_get", "description": "Read evidence paths, hashes and locators; source contents are not exposed.", "inputSchema": {"type": "object", "properties": {"scan_id": {"type": "integer"}, "section_id": {"type": "string"}}, "required": ["scan_id"], "additionalProperties": False}},
    {"name": "agentos.architecture_discrepancies_get", "description": "Read advisory discovery discrepancies. v0.25.3 does not enforce architecture drift.", "inputSchema": {"type": "object", "properties": {"scan_id": {"type": "integer"}, "section_id": {"type": "string"}}, "required": ["scan_id"], "additionalProperties": False}},
]

TOOL_NAMES = {tool["name"] for tool in TOOLS}


def dispatch(name: str, arguments: dict[str, Any], root: Path, task_id: str | None = None, session_id: str | None = None) -> Any:
    """Dispatch one read-only v0.25.3 MCP tool; task/session do not grant mutation."""
    del task_id, session_id
    if name == "agentos.architecture_scan_get":
        return architecture_scan_get(root, scan_id=arguments.get("scan_id"))
    if name == "agentos.architecture_observations_get":
        return architecture_observations_get(root, scan_id=int(arguments["scan_id"]), section_id=arguments.get("section_id"))
    if name == "agentos.architecture_evidence_get":
        return architecture_evidence_get(root, scan_id=int(arguments["scan_id"]), section_id=arguments.get("section_id"))
    if name == "agentos.architecture_discrepancies_get":
        return architecture_discrepancies_get(root, scan_id=int(arguments["scan_id"]), section_id=arguments.get("section_id"))
    raise KeyError(name)
