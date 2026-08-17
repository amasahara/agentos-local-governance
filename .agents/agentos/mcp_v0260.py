"""Path: .agents/agentos/mcp_v0260.py
Purpose: Read-only MCP inspection for v0.26.0 Architecture-Aware Task Planning.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .architecture_planning import architecture_plan_get, architecture_plan_status
TOOLS=[
 {"name":"agentos.architecture_plan_get","description":"Read one architecture-aware task-plan binding.","inputSchema":{"type":"object","properties":{"plan_id":{"type":"integer"},"task_id":{"type":"string"}}}},
 {"name":"agentos.architecture_plan_status_get","description":"Read current task-plan architecture readiness and baseline pin.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"}},"required":["task_id"]}},
 {"name":"agentos.architecture_plan_impact_get","description":"Read persisted deterministic architecture impact for one plan; no analysis or mutation is executed.","inputSchema":{"type":"object","properties":{"plan_id":{"type":"integer"},"task_id":{"type":"string"}}}},
]
TOOL_NAMES={item["name"] for item in TOOLS}

def dispatch(name: str, arguments: dict[str,Any], root: Path, task_id: str|None=None, session_id: str|None=None) -> Any:
    del session_id
    if name=="agentos.architecture_plan_get" or name=="agentos.architecture_plan_impact_get":
        return architecture_plan_get(root,plan_id=arguments.get("plan_id"),task_id=arguments.get("task_id") or task_id)
    if name=="agentos.architecture_plan_status_get":
        selected=str(arguments.get("task_id") or task_id or "").strip()
        if not selected: raise RuntimeError("task_id_required")
        return architecture_plan_status(root,selected)
    raise RuntimeError(f"unknown_v0260_tool:{name}")
