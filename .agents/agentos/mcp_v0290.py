"""Path: .agents/agentos/mcp_v0290.py
Purpose: Privacy-safe read-only v0.29.0 completion status MCP tool.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .completion_surface import completion_public_status

TOOLS = [
    {
        "name": "agentos.completion_status_get",
        "description": "Read privacy-safe independent completion verification status. Read-only; never requests, verifies, approves, or terminalizes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "subject_type": {"type": "string", "enum": ["workflow", "multi_agent_worker"]},
                "task_id": {"type": "string"},
                "workflow_name": {"type": "string"},
                "supervisor_id": {"type": "integer"},
                "worker_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def dispatch(root: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name != "agentos.completion_status_get":
        raise RuntimeError(f"unknown v0.29.0 MCP tool: {name}")
    return completion_public_status(
        root,
        request_id=arguments.get("request_id"),
        subject_type=arguments.get("subject_type"),
        task_id=arguments.get("task_id"),
        workflow_name=str(arguments.get("workflow_name") or "default"),
        supervisor_id=(int(arguments["supervisor_id"]) if arguments.get("supervisor_id") is not None else None),
        worker_key=arguments.get("worker_key"),
    )
