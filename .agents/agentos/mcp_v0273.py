"""
File: .agents/agentos/mcp_v0273.py

Purpose:
    Provide the read-only MCP inspection surface for v0.27.3 isolated workspaces and controlled integration.

Responsibilities:
    - Expose redacted workspace status and diff summaries.
    - Expose controlled-integration proposal status and readiness.
    - Keep all workspace/integration mutation and approval authority out of MCP.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .multi_agent_workspace import integration_readiness, integration_status, workspace_status
TOOLS=[
 {"name":"agentos.multi_agent_workspace_status_get","description":"Get redacted isolated workspace state and diff hashes.","inputSchema":{"type":"object","properties":{"supervisor_id":{"type":"integer"},"worker_key":{"type":"string"}},"required":["supervisor_id","worker_key"],"additionalProperties":False}},
 {"name":"agentos.multi_agent_workspace_diff_summary_get","description":"Get redacted changed-file/hash summary for one worker workspace.","inputSchema":{"type":"object","properties":{"supervisor_id":{"type":"integer"},"worker_key":{"type":"string"}},"required":["supervisor_id","worker_key"],"additionalProperties":False}},
 {"name":"agentos.multi_agent_integration_proposal_get","description":"Get controlled integration proposal status without mutation authority.","inputSchema":{"type":"object","properties":{"proposal_id":{"type":"integer"}},"required":["proposal_id"],"additionalProperties":False}},
 {"name":"agentos.multi_agent_integration_readiness_get","description":"Get conflict/gate readiness for a controlled integration proposal.","inputSchema":{"type":"object","properties":{"proposal_id":{"type":"integer"}},"required":["proposal_id"],"additionalProperties":False}},
]
TOOL_NAMES={x["name"] for x in TOOLS}
def dispatch(root:Path,name:str,arguments:dict[str,Any])->Any:
    """Dispatch one read-only v0.27.3 MCP tool.

    Args:
        root: Primary governed repository root.
        name: MCP tool name.
        arguments: Validated tool arguments.
    Returns:
        Redacted workspace or integration state.
    """
    if name in {"agentos.multi_agent_workspace_status_get","agentos.multi_agent_workspace_diff_summary_get"}:
        return workspace_status(root,int(arguments["supervisor_id"]),str(arguments["worker_key"]))
    if name=="agentos.multi_agent_integration_proposal_get": return integration_status(root,int(arguments["proposal_id"]))
    if name=="agentos.multi_agent_integration_readiness_get": return integration_readiness(root,int(arguments["proposal_id"]))
    raise KeyError(name)
