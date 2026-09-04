"""
File: .agents/agentos/mcp_execution_provenance.py

Purpose:
    Expose a minimal privacy-safe read-only MCP view of execution provenance.

Responsibilities:
    - Publish exactly two read-only tools: get and list.
    - Return sanitized execution evidence only.
    - Never expose provenance registration or any mutation path.
    - Never expose provider request hashes, recorded_by, deployment_id,
      execution_ref_id, credentials, raw prompts, or raw responses.
    - Preserve explicit authority and remote-attestation non-claims.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .execution_provenance import (
    ExecutionProvenanceError,
    get_execution_provenance_for_mcp,
    list_execution_provenance,
)

TOOLS = [
    {
        "name": "agentos.execution_provenance_get",
        "description": (
            "Read one sanitized execution provenance record. "
            "Read-only evidence; no instruction authority."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"provenance_id": {"type": "string"}},
            "required": ["provenance_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "agentos.execution_provenance_list",
        "description": (
            "List sanitized execution provenance records with bounded filters. "
            "Read-only evidence; no instruction authority."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "session_id": {"type": "string"},
                "provider_id": {"type": "string"},
                "model_id": {"type": "string"},
                "verification_class": {
                    "type": "string",
                    "enum": ["declared", "runtime_bound"],
                },
                "created_after": {"type": "string"},
                "created_before": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    },
]

TOOL_NAMES = {item["name"] for item in TOOLS}


def _local_call(
    name: str,
    arguments: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    """Dispatch one read-only execution-provenance MCP tool."""
    try:
        if name == "agentos.execution_provenance_get":
            return get_execution_provenance_for_mcp(
                root,
                str(arguments["provenance_id"]),
            )
        if name == "agentos.execution_provenance_list":
            return list_execution_provenance(
                root,
                task_id=arguments.get("task_id"),
                session_id=arguments.get("session_id"),
                provider_id=arguments.get("provider_id"),
                model_id=arguments.get("model_id"),
                verification_class=arguments.get("verification_class"),
                created_after=arguments.get("created_after"),
                created_before=arguments.get("created_before"),
                limit=int(arguments.get("limit") or 50),
            )
    except (ExecutionProvenanceError, KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    raise RuntimeError(f"unknown execution provenance MCP tool: {name}")
