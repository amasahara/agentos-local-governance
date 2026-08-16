"""Path: .agents/agentos/mcp_v0254.py
Purpose: Read-only MCP inspection tools for v0.25.4 Architecture Drift & Compliance.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .architecture_compliance import architecture_compliance_findings_get, architecture_compliance_get, architecture_compliance_status_get

TOOLS = [
    {"name":"agentos.architecture_compliance_get","description":"Read a persisted Architecture Compliance run and findings.","inputSchema":{"type":"object","properties":{"run_id":{"type":"integer"}},"additionalProperties":False}},
    {"name":"agentos.architecture_compliance_findings_get","description":"Read architecture compliance findings; no waiver or mutation authority is exposed.","inputSchema":{"type":"object","properties":{"run_id":{"type":"integer"},"severity":{"type":"string","enum":["info","warn","block"]}},"additionalProperties":False}},
    {"name":"agentos.architecture_compliance_status_get","description":"Read active-baseline enforcement readiness and latest compliance status.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
]
TOOL_NAMES = {tool["name"] for tool in TOOLS}

def dispatch(name: str, arguments: dict[str, Any], root: Path, task_id: str | None = None, session_id: str | None = None) -> Any:
    """Dispatch read-only v0.25.4 MCP inspection only."""
    del task_id, session_id
    if name == "agentos.architecture_compliance_get":
        return architecture_compliance_get(root, run_id=arguments.get("run_id"))
    if name == "agentos.architecture_compliance_findings_get":
        return architecture_compliance_findings_get(root, run_id=arguments.get("run_id"), severity=arguments.get("severity"))
    if name == "agentos.architecture_compliance_status_get":
        return architecture_compliance_status_get(root)
    raise KeyError(name)
