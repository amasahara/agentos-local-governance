"""
Path: .agents/agentos/mcp_v0280.py
Purpose: Expose privacy-safe v0.28.0 Command Center projections through read-only MCP tools.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .command_center import command_center_human_actions, command_center_section, command_center_snapshot

TOOLS = [
    {
        "name": "agentos.command_center_snapshot_get",
        "description": "Read the privacy-safe Architecture & Agent Command Center snapshot. Read-only; no authority.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agentos.command_center_human_actions_get",
        "description": "Read pending human/operator action metadata without raw request/source content. Read-only.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agentos.command_center_section_get",
        "description": "Read one Command Center section. Read-only; never approves or mutates governance state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["architecture", "execution", "compliance", "human_actions", "authority"],
                }
            },
            "required": ["section"],
        },
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def dispatch(root: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one v0.28.0 read-only Command Center tool."""
    if name == "agentos.command_center_snapshot_get":
        return command_center_snapshot(root)
    if name == "agentos.command_center_human_actions_get":
        return command_center_human_actions(root)
    if name == "agentos.command_center_section_get":
        return command_center_section(root, str(arguments.get("section") or ""))
    raise RuntimeError(f"unknown v0.28.0 MCP tool: {name}")
