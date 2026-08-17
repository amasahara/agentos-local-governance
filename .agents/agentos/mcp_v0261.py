"""Path: .agents/agentos/mcp_v0261.py
Purpose: Read-only MCP inspection for v0.26.1 Structural Enforcement.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .architecture_structural import (
    architecture_structural_findings,
    architecture_structural_status,
    architecture_structural_target_check,
)

TOOLS = [
    {
        "name": "agentos.architecture_structural_status_get",
        "description": "Read current structural enforcement state and active Architecture Baseline.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agentos.architecture_structural_findings_get",
        "description": "Read persisted structural findings; no enforcement run is executed.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "integer"}, "task_id": {"type": "string"}, "limit": {"type": "integer"}},
        },
    },
    {
        "name": "agentos.architecture_structural_target_get",
        "description": "Read whether one project-relative target satisfies the active structural contract.",
        "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def dispatch(name: str, arguments: dict[str, Any], root: Path, task_id: str | None = None, session_id: str | None = None) -> Any:
    del session_id
    if name == "agentos.architecture_structural_status_get":
        return architecture_structural_status(root)
    if name == "agentos.architecture_structural_findings_get":
        return architecture_structural_findings(root, run_id=arguments.get("run_id"), task_id=arguments.get("task_id") or task_id, limit=int(arguments.get("limit", 100)))
    if name == "agentos.architecture_structural_target_get":
        target = str(arguments.get("target") or "").strip()
        if not target:
            raise RuntimeError("target_required")
        return architecture_structural_target_check(root, target)
    raise RuntimeError(f"unknown_v0261_tool:{name}")
