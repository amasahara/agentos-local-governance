"""
File: .agents/agentos/mcp_v0271.py
Purpose: Expose read-only Architecture-Aware Skill Selection & Evaluation inspection over MCP.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .skill_selection import skill_evaluation_get, skill_selection_candidates_get, skill_selection_status

TOOLS = [
    {"name":"agentos.skill_selection_status_get","description":"Read the latest or identified advisory architecture-aware skill selection status.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"},"run_id":{"type":"integer"}}}},
    {"name":"agentos.skill_selection_candidates_get","description":"Read persisted candidate ranking/evidence metadata for one selection run.","inputSchema":{"type":"object","properties":{"run_id":{"type":"integer"},"eligible_only":{"type":"boolean"}},"required":["run_id"]}},
    {"name":"agentos.skill_evaluation_get","description":"Read observational skill evaluation metadata without lifecycle or ranking mutation.","inputSchema":{"type":"object","properties":{"evaluation_id":{"type":"integer"},"selection_run_id":{"type":"integer"},"task_id":{"type":"string"}}}},
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def dispatch(root: Path, name: str, arguments: dict[str, Any]) -> Any:
    if name == "agentos.skill_selection_status_get":
        raw = arguments.get("run_id")
        return skill_selection_status(root, task_id=arguments.get("task_id"), run_id=int(raw) if raw is not None else None)
    if name == "agentos.skill_selection_candidates_get":
        return skill_selection_candidates_get(root, int(arguments["run_id"]), eligible_only=bool(arguments.get("eligible_only", False)))
    if name == "agentos.skill_evaluation_get":
        raw_eval = arguments.get("evaluation_id")
        raw_run = arguments.get("selection_run_id")
        return skill_evaluation_get(
            root,
            evaluation_id=int(raw_eval) if raw_eval is not None else None,
            selection_run_id=int(raw_run) if raw_run is not None else None,
            task_id=arguments.get("task_id"),
        )
    raise KeyError(name)
