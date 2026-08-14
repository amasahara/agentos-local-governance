"""
File: .agents/agentos/mcp_risk_tiered_batch_review.py

Purpose:
    Expose read-only v0.24.1 risk-review inspection over MCP.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .risk_tiered_batch_review import get_batch_bundle, get_risk_review_status

TOOLS = [
    {
        "name": "agentos.project_consolidation_risk_review_get",
        "description": "Read current risk tiers, review coverage, and signed-bundle summaries for one consolidation.",
        "inputSchema": {"type": "object", "properties": {"consolidation_id": {"type": "integer"}}, "required": ["consolidation_id"]},
    },
    {
        "name": "agentos.project_consolidation_batch_bundle_get",
        "description": "Read one immutable low-risk review bundle and its external signature metadata.",
        "inputSchema": {"type": "object", "properties": {"bundle_id": {"type": "string"}}, "required": ["bundle_id"]},
    },
]

def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name == "agentos.project_consolidation_risk_review_get":
        return get_risk_review_status(root, int(arguments["consolidation_id"]))
    if name == "agentos.project_consolidation_batch_bundle_get":
        return get_batch_bundle(root, str(arguments["bundle_id"]))
    raise RuntimeError(f"unknown v0.24.1 read-only MCP tool: {name}")
