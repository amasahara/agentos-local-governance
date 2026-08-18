"""Path: .agents/agentos/mcp_v0263.py
Purpose: Read-only MCP inspection surface for v0.26.3 quality/operational enforcement.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .architecture_quality import architecture_quality_findings, architecture_quality_status, architecture_quality_target_check

TOOLS = [
    {"name": "agentos.architecture_quality_status_get", "description": "Read v0.26.3 quality/operational enforcement status.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "agentos.architecture_quality_findings_get", "description": "Read persisted quality/operational findings without running a scan.", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "integer"}, "task_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000}}, "additionalProperties": False}},
    {"name": "agentos.architecture_quality_target_get", "description": "Read target-only quality/operational write-boundary decision.", "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"], "additionalProperties": False}},
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def dispatch(name: str, arguments: dict[str, Any], root: Path, task_id: str | None = None, session_id: str | None = None) -> Any:
    del session_id
    if name == "agentos.architecture_quality_status_get":
        return architecture_quality_status(root)
    if name == "agentos.architecture_quality_findings_get":
        return architecture_quality_findings(root, run_id=arguments.get("run_id"), task_id=arguments.get("task_id") or task_id, limit=int(arguments.get("limit", 100)))
    if name == "agentos.architecture_quality_target_get":
        target = str(arguments.get("target") or "").strip()
        if not target:
            raise RuntimeError("target_required")
        return architecture_quality_target_check(root, target)
    raise RuntimeError(f"unknown_v0263_tool:{name}")
