"""
File: .agents/agentos/mcp_context_transport.py

Purpose:
    Expose read-only v0.23.0 context transport inspection through MCP.

Responsibilities:
    - Allow LLMs to inspect READY transport packs and token reports.
    - Allow read-only, hash-pinned expansion of omission handles.
    - Never expose compile, evaluation persistence, requirement mutation, or authority mutation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .context_transport import (
    ContextTransportError,
    context_expand,
    context_requirement_get,
    context_token_report,
    context_transport_explain,
    context_transport_get,
)

TOOLS = [
    {
        "name": "agentos.context_transport_get",
        "description": "Read a verified READY requirement-preserving context transport pack.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "revision": {"type": "integer"}}, "required": ["task_id"]},
    },
    {
        "name": "agentos.context_transport_explain",
        "description": "Explain preservation gates, deterministic codecs, omissions, and freshness for a READY transport pack.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "revision": {"type": "integer"}}, "required": ["task_id"]},
    },
    {
        "name": "agentos.context_expand",
        "description": "Read-only expansion of a hash-pinned omission handle. Does not mutate project or authority state.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "handle_id": {"type": "string"}, "revision": {"type": "integer"}, "max_lines": {"type": "integer"}}, "required": ["task_id", "handle_id"]},
    },
    {
        "name": "agentos.context_requirement_get",
        "description": "Read exact protected Requirement Ledger entries with stable requirement IDs.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "requirement_id": {"type": "string"}, "context_revision": {"type": "integer"}}, "required": ["task_id"]},
    },
    {
        "name": "agentos.context_token_report",
        "description": "Read tokenizer, model budget, raw/used/saved tokens, and compression ratio for a READY transport pack.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "revision": {"type": "integer"}}, "required": ["task_id"]},
    },
]


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch one read-only context transport MCP operation."""
    try:
        task_id = str(arguments.get("task_id") or "")
        if not task_id:
            raise ContextTransportError("task_id_required")
        revision = int(arguments["revision"]) if arguments.get("revision") is not None else None
        if name == "agentos.context_transport_get":
            return context_transport_get(root, task_id, revision)
        if name == "agentos.context_transport_explain":
            return context_transport_explain(root, task_id, revision)
        if name == "agentos.context_expand":
            return context_expand(root, task_id, str(arguments["handle_id"]), revision, int(arguments.get("max_lines", 240)), record_event=False)
        if name == "agentos.context_requirement_get":
            context_revision = int(arguments["context_revision"]) if arguments.get("context_revision") is not None else None
            return context_requirement_get(root, task_id, arguments.get("requirement_id"), context_revision)
        if name == "agentos.context_token_report":
            return context_token_report(root, task_id, revision)
    except (ContextTransportError, KeyError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "unknown v0.23.0 read-only MCP tool"}
