"""Privacy-safe read-only v0.30.0 Context Authority MCP tools."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .context_authority_surface import (
    context_authority_explain,
    context_authority_findings_get,
    context_authority_status,
    context_provenance_get,
)
from .context_transport import ContextTransportError

TOOLS = [
    {"name":"agentos.context_authority_status_get","description":"Read privacy-safe Context Authority status and pinned hashes. Read-only.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"},"revision":{"type":"integer"}},"required":["task_id"],"additionalProperties":False}},
    {"name":"agentos.context_provenance_get","description":"Read hash/label context provenance records without raw content. Read-only.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"},"revision":{"type":"integer"},"trust_class":{"type":"string"},"authority_class":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":1000}},"required":["task_id"],"additionalProperties":False}},
    {"name":"agentos.context_authority_explain","description":"Explain origin-based authority classes, counts, pins and non-claims. Read-only.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"},"revision":{"type":"integer"}},"required":["task_id"],"additionalProperties":False}},
    {"name":"agentos.context_authority_findings_get","description":"Read hash-only context authority findings. Read-only.","inputSchema":{"type":"object","properties":{"task_id":{"type":"string"},"revision":{"type":"integer"}},"required":["task_id"],"additionalProperties":False}},
]
TOOL_NAMES = {item["name"] for item in TOOLS}


def dispatch(root: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        task_id = str(arguments.get("task_id") or "")
        if not task_id:
            return {"ok": False, "error": "task_id_required"}
        revision = int(arguments["revision"]) if arguments.get("revision") is not None else None
        if name == "agentos.context_authority_status_get":
            return context_authority_status(root, task_id, revision)
        if name == "agentos.context_provenance_get":
            return context_provenance_get(root, task_id, revision, trust_class=arguments.get("trust_class"), authority_class=arguments.get("authority_class"), limit=int(arguments.get("limit") or 200))
        if name == "agentos.context_authority_explain":
            return context_authority_explain(root, task_id, revision)
        if name == "agentos.context_authority_findings_get":
            return context_authority_findings_get(root, task_id, revision)
    except (ContextTransportError, KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    raise RuntimeError(f"unknown v0.30.0 MCP tool: {name}")
