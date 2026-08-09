"""
File: .agents/agentos/mcp_context_evaluation.py

Purpose:
    Expose read-only v0.23.2 context expansion and compression-evaluation APIs.

Responsibilities:
    - Provide bounded hash-pinned batch expansion without telemetry mutation.
    - Explain expansion coverage and inspect evaluation results.
    - Compare transport revisions without persisting comparison state.
    - Never expose evaluation persistence, compile authority, or context mutation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .context_evaluation import (
    ContextEvaluationError,
    compare_compression,
    compression_evaluation_get,
    expansion_history_get,
)
from .context_transport import (
    ContextTransportError,
    context_expand_batch,
    context_expansion_explain,
)

TOOLS = [
    {
        "name": "agentos.context_expansion_explain",
        "description": "Read omission-handle coverage and expandability metadata for a READY transport pack.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "revision": {"type": "integer"}}, "required": ["task_id"]},
    },
    {
        "name": "agentos.context_expand_batch",
        "description": "Read-only bounded expansion of multiple hash-pinned omission handles. Expanded content is not persisted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"}, "revision": {"type": "integer"},
                "requests": {"type": "array", "items": {"type": "object"}},
                "max_total_tokens": {"type": "integer"}, "reason_code": {"type": "string"},
                "requirement_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task_id", "requests"],
        },
    },
    {
        "name": "agentos.context_expansion_history_get",
        "description": "Read expansion metadata history only; no excerpt or raw source content is stored or returned.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "revision": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["task_id"]},
    },
    {
        "name": "agentos.context_compression_evaluation_get",
        "description": "Read or non-persistently compute deterministic compression safety/effectiveness metrics for a transport pack.",
        "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}, "revision": {"type": "integer"}}, "required": ["task_id"]},
    },
    {
        "name": "agentos.context_compression_compare",
        "description": "Read-only shadow comparison of two transport revisions using deterministic regression gates.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}, "baseline_revision": {"type": "integer"}, "candidate_revision": {"type": "integer"}},
            "required": ["task_id", "baseline_revision", "candidate_revision"],
        },
    },
]


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch one read-only v0.23.2 MCP operation."""
    try:
        task_id = str(arguments.get("task_id") or "")
        if not task_id:
            raise ContextEvaluationError("task_id_required")
        revision = int(arguments["revision"]) if arguments.get("revision") is not None else None
        if name == "agentos.context_expansion_explain":
            return context_expansion_explain(root, task_id, revision)
        if name == "agentos.context_expand_batch":
            requests = arguments.get("requests")
            if not isinstance(requests, list):
                raise ContextEvaluationError("requests_must_be_array")
            return context_expand_batch(
                root, task_id, requests, revision,
                int(arguments["max_total_tokens"]) if arguments.get("max_total_tokens") is not None else None,
                str(arguments.get("reason_code") or "inspection"),
                arguments.get("requirement_ids") if isinstance(arguments.get("requirement_ids"), list) else None,
                record_event=False,
            )
        if name == "agentos.context_expansion_history_get":
            return expansion_history_get(root, task_id, revision, int(arguments.get("limit", 50)))
        if name == "agentos.context_compression_evaluation_get":
            return compression_evaluation_get(root, task_id, revision)
        if name == "agentos.context_compression_compare":
            return compare_compression(
                root, task_id, int(arguments["baseline_revision"]), int(arguments["candidate_revision"]), persist=False,
            )
    except (ContextEvaluationError, ContextTransportError, KeyError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "unknown v0.23.2 read-only context evaluation MCP tool"}
