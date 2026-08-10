"""
File: .agents/agentos/mcp_consolidation_cockpit.py

Purpose:
    Expose privacy-safe v0.23.3 cockpit inspection through read-only MCP tools.

Responsibilities:
    - Expose complete consolidation status without mutation or raw business data.
    - Expose the checked-in performance baseline without executing benchmarks.
    - Keep benchmark execution at the explicit CLI/operator boundary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .consolidation_cockpit import consolidation_status
from .performance_baseline import load_baseline

TOOLS = [
    {
        "name": "agentos.consolidation_status_get",
        "description": "Read the aggregated project/database consolidation cockpit. No mutation or raw row values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "consolidation_id": {"type": "integer"},
                "candidate_set_id": {"type": "integer"},
                "project_consolidation_id": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agentos.performance_baseline_get",
        "description": "Read the checked-in v0.23.3 performance baseline artifact. Does not execute benchmarks.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch one v0.23.3 read-only MCP operation."""
    if name == "agentos.consolidation_status_get":
        db_value = arguments.get("consolidation_id")
        candidate_value = arguments.get("candidate_set_id")
        project_value = arguments.get("project_consolidation_id")
        return consolidation_status(
            root,
            int(db_value) if db_value is not None else None,
            candidate_set_id=int(candidate_value) if candidate_value is not None else None,
            project_consolidation_id=int(project_value) if project_value is not None else None,
        )
    if name == "agentos.performance_baseline_get":
        return load_baseline(root)
    raise RuntimeError(f"unknown v0.23.3 cockpit MCP tool: {name}")
