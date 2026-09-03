"""
File: .agents/agentos/mcp_v0310.py

Purpose:
    Expose privacy-safe read-only governed-learning MCP inspection tools.

Responsibilities:
    - Publish exactly four read-only governed-learning MCP tools.
    - Return hash-only linkage and status data without raw project content.
    - Keep learning mutation, approval, promotion, and activation outside MCP.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .learning_signals import LearningSignalError, knowledge_usage_get, learning_signal_links_get, learning_signals_get, learning_status
TOOLS=[
 {"name":"agentos.learning_signals_get","description":"Read hash-only governed learning signals. Read-only.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"},"signature_hash":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":1000}},"additionalProperties":False}},
 {"name":"agentos.learning_signal_links_get","description":"Read learning signal links. Read-only.","inputSchema":{"type":"object","properties":{"signal_id":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":1000}},"additionalProperties":False}},
 {"name":"agentos.knowledge_usage_get","description":"Read hash-only actual context knowledge usage. Read-only.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"},"knowledge_kind":{"type":"string","enum":["skill","memory","finding"]},"limit":{"type":"integer","minimum":1,"maximum":1000}},"additionalProperties":False}},
 {"name":"agentos.learning_status_get","description":"Read governed learning status/non-claims. Read-only.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
]
TOOL_NAMES={x["name"] for x in TOOLS}
def dispatch(root: Path,name: str,arguments: dict[str,Any]) -> dict[str,Any]:
    """Dispatch one read-only v0.31.0 governed-learning MCP tool."""
    try:
        if name=="agentos.learning_signals_get": return learning_signals_get(root,task_id=arguments.get("task_id"),signature_hash=arguments.get("signature_hash"),limit=int(arguments.get("limit") or 100))
        if name=="agentos.learning_signal_links_get": return learning_signal_links_get(root,signal_id=arguments.get("signal_id"),limit=int(arguments.get("limit") or 100))
        if name=="agentos.knowledge_usage_get": return knowledge_usage_get(root,task_id=arguments.get("task_id"),knowledge_kind=arguments.get("knowledge_kind"),limit=int(arguments.get("limit") or 100))
        if name=="agentos.learning_status_get": return learning_status(root)
    except (LearningSignalError,KeyError,TypeError,ValueError) as exc: return {"ok":False,"error":str(exc)}
    raise RuntimeError(f"unknown v0.31.0 MCP tool: {name}")
