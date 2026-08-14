"""
File: .agents/agentos/mcp_db_aware_context_projection.py

Purpose:
    Expose hash/count-only v0.24.2 DB-aware projection telemetry over read-only MCP.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from .db_aware_context_projection import projection_status

TOOLS = [
    {
        "name": "agentos.context_db_projection_get",
        "description": "Read DB-aware context projection hashes, codecs, and compression counters without raw projected content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "revision": {"type": "integer"},
            },
            "required": ["task_id"],
        },
    }
]


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name != "agentos.context_db_projection_get":
        raise RuntimeError(f"unknown v0.24.2 read-only MCP tool: {name}")
    revision = arguments.get("revision")
    return projection_status(root, str(arguments["task_id"]), int(revision) if revision is not None else None)
