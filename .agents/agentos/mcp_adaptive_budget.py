"""
File: .agents/agentos/mcp_adaptive_budget.py

Purpose:
    Expose read-only v0.23.1 model-profile and adaptive-budget inspection over MCP.

Responsibilities:
    - List/read data-only model profiles and pinned profile hashes.
    - Inspect adaptive budget decision history and numeric calibration statistics.
    - Never expose token-observation mutation, profile mutation, or compiler authority.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .adaptive_budget import (
    AdaptiveBudgetError,
    budget_history_get,
    model_profiles_get,
    token_calibration_get,
)

TOOLS = [
    {
        "name": "agentos.context_model_profiles_get",
        "description": "Read local data-only model profiles and pinned profile hashes. No provider/network discovery.",
        "inputSchema": {
            "type": "object",
            "properties": {"model_profile": {"type": "string"}},
        },
    },
    {
        "name": "agentos.context_budget_history_get",
        "description": "Read deterministic adaptive token-budget decisions for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "agentos.context_token_calibration_get",
        "description": "Read numeric tokenizer calibration statistics without prompt or response content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_profile": {"type": "string"},
                "tokenizer_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["model_profile", "tokenizer_id"],
        },
    },
]


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch one read-only adaptive-budget MCP operation."""
    try:
        if name == "agentos.context_model_profiles_get":
            value = arguments.get("model_profile")
            return model_profiles_get(root, str(value) if value else None)
        if name == "agentos.context_budget_history_get":
            task_id = str(arguments.get("task_id") or "")
            if not task_id:
                raise AdaptiveBudgetError("task_id_required")
            return budget_history_get(root, task_id, int(arguments.get("limit", 20)))
        if name == "agentos.context_token_calibration_get":
            return token_calibration_get(
                root,
                str(arguments["model_profile"]),
                str(arguments["tokenizer_id"]),
                int(arguments.get("limit", 32)),
            )
    except (AdaptiveBudgetError, KeyError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "unknown v0.23.1 read-only adaptive-budget MCP tool"}
