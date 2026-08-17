"""Path: .agents/agentos/mcp_v0262.py
Purpose: Read-only MCP inspection for v0.26.2 Runtime/Data/API & Business Boundary Enforcement.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .architecture_runtime import (
    architecture_runtime_findings,
    architecture_runtime_status,
    architecture_runtime_target_check,
)

TOOLS = [
    {
        "name": "agentos.architecture_runtime_status_get",
        "description": "Read current runtime/data/API/business boundary enforcement state and active Architecture Baseline.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agentos.architecture_runtime_findings_get",
        "description": "Read persisted v0.26.2 boundary findings; no enforcement run is executed.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "integer"}, "task_id": {"type": "string"}, "limit": {"type": "integer"}},
        },
    },
    {
        "name": "agentos.architecture_runtime_target_get",
        "description": "Read target-only ARCH-09/14 boundary compatibility for one project-relative path.",
        "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
    },
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def dispatch(name: str, arguments: dict[str, Any], root: Path, task_id: str | None = None, session_id: str | None = None) -> Any:
    del session_id
    if name == "agentos.architecture_runtime_status_get":
        return architecture_runtime_status(root)
    if name == "agentos.architecture_runtime_findings_get":
        return architecture_runtime_findings(
            root,
            run_id=arguments.get("run_id"),
            task_id=arguments.get("task_id") or task_id,
            limit=int(arguments.get("limit", 100)),
        )
    if name == "agentos.architecture_runtime_target_get":
        target = str(arguments.get("target") or "").strip()
        if not target:
            raise RuntimeError("target_required")
        return architecture_runtime_target_check(root, target)
    raise RuntimeError(f"unknown_v0262_tool:{name}")
