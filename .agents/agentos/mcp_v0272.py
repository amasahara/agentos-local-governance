"""Path: .agents/agentos/mcp_v0272.py
Purpose: Read-only MCP inspection surface for v0.27.2 Multi-Agent Worker Supervisor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .multi_agent_supervisor import supervisor_readiness, supervisor_status, supervisor_workers

TOOLS = [
    {
        "name": "agentos.multi_agent_supervisor_status_get",
        "description": "Get redacted multi-agent supervisor status and effective freshness state.",
        "inputSchema": {"type": "object", "properties": {"supervisor_id": {"type": "integer"}}, "required": ["supervisor_id"], "additionalProperties": False},
    },
    {
        "name": "agentos.multi_agent_supervisor_workers_get",
        "description": "List redacted worker assignments and DAG dependencies for a supervisor.",
        "inputSchema": {"type": "object", "properties": {"supervisor_id": {"type": "integer"}}, "required": ["supervisor_id"], "additionalProperties": False},
    },
    {
        "name": "agentos.multi_agent_supervisor_readiness_get",
        "description": "Get supervisor readiness, worker freshness, overlaps, and runnable worker keys.",
        "inputSchema": {"type": "object", "properties": {"supervisor_id": {"type": "integer"}}, "required": ["supervisor_id"], "additionalProperties": False},
    },
]

TOOL_NAMES = {tool["name"] for tool in TOOLS}


def dispatch(root: Path, name: str, arguments: dict[str, Any]) -> Any:
    """Dispatch one read-only v0.27.2 MCP method.

    Input: project root, MCP tool name, validated argument object.
    Output: JSON-compatible supervisor inspection result.
    """
    supervisor_id = int(arguments["supervisor_id"])
    if name == "agentos.multi_agent_supervisor_status_get":
        return supervisor_status(root, supervisor_id)
    if name == "agentos.multi_agent_supervisor_workers_get":
        return supervisor_workers(root, supervisor_id)
    if name == "agentos.multi_agent_supervisor_readiness_get":
        return supervisor_readiness(root, supervisor_id)
    raise KeyError(name)
