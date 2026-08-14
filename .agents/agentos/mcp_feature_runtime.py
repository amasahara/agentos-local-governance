"""
File: .agents/agentos/mcp_feature_runtime.py

Purpose:
    Build and dispatch the active MCP feature runtime independently of historical
    version-forwarding gateway modules.

Responsibilities:
    - Register runtime-native handlers migrated from mcp_*_gateway modules.
    - Register modern read-only feature modules directly.
    - Reject duplicate tool names fail-closed.
    - Expose handler provenance so release integrity can prove no legacy gateway
      owns an active feature handler.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .mcp_feature_handlers import REGISTRATIONS as RUNTIME_NATIVE_REGISTRATIONS
from . import mcp_secret_lineage as secret_lineage
from . import mcp_data_subject_rights as data_subject_rights
from . import mcp_context_transport as context_transport
from . import mcp_adaptive_budget as adaptive_budget
from . import mcp_context_evaluation as context_evaluation
from . import mcp_consolidation_cockpit as consolidation_cockpit
from . import mcp_risk_tiered_batch_review as risk_tiered_batch_review
from . import mcp_db_aware_context_projection as db_aware_projection

FeatureHandler = Callable[[str, dict[str, Any], Path], dict[str, Any]]

LEGACY_GATEWAY_MODULES = (
    "agentos.mcp_identity_gateway",
    "agentos.mcp_selection_gateway",
    "agentos.mcp_consolidation_gateway",
    "agentos.mcp_database_boundary_gateway",
    "agentos.mcp_schema_mapping_gateway",
    "agentos.mcp_read_only_extraction_gateway",
    "agentos.mcp_controlled_target_insert_gateway",
    "agentos.mcp_identity_resolution_gateway",
    "agentos.mcp_reconciliation_recovery_gateway",
    "agentos.mcp_server",
)

MODERN_REGISTRATIONS: tuple[tuple[list[dict[str, Any]], FeatureHandler], ...] = (
    (secret_lineage.TOOLS, secret_lineage._local_call),
    (data_subject_rights.TOOLS, data_subject_rights._local_call),
    (context_transport.TOOLS, context_transport._local_call),
    (adaptive_budget.TOOLS, adaptive_budget._local_call),
    (context_evaluation.TOOLS, context_evaluation._local_call),
    (consolidation_cockpit.TOOLS, consolidation_cockpit._local_call),
    (risk_tiered_batch_review.TOOLS, risk_tiered_batch_review._local_call),
    (db_aware_projection.TOOLS, db_aware_projection._local_call),
)

REGISTRATIONS = (*RUNTIME_NATIVE_REGISTRATIONS, *MODERN_REGISTRATIONS)


def build_feature_catalog() -> tuple[list[dict[str, Any]], dict[str, FeatureHandler]]:
    """Return active feature tools and direct handler mapping."""
    tools: list[dict[str, Any]] = []
    handlers: dict[str, FeatureHandler] = {}
    duplicates: list[str] = []
    for definitions, handler in REGISTRATIONS:
        for definition in definitions:
            name = str(definition["name"])
            if name in handlers:
                duplicates.append(name)
                continue
            tools.append(definition)
            handlers[name] = handler
    if duplicates:
        raise RuntimeError(f"duplicate extension MCP tools: {sorted(set(duplicates))}")
    return tools, handlers


FEATURE_TOOLS, FEATURE_HANDLERS = build_feature_catalog()
FEATURE_TOOL_NAMES = {item["name"] for item in FEATURE_TOOLS}
HANDLER_SOURCES = {name: handler.__module__ for name, handler in FEATURE_HANDLERS.items()}
LEGACY_GATEWAY_HANDLER_NAMES = sorted(
    name for name, module in HANDLER_SOURCES.items()
    if module in LEGACY_GATEWAY_MODULES or "_gateway" in module or module.endswith(".mcp_server")
)


def dispatch_feature_tool(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch one active feature tool directly in-process."""
    handler = FEATURE_HANDLERS.get(name)
    if handler is None:
        raise RuntimeError(f"unknown MCP feature tool: {name}")
    return handler(name, dict(arguments), root)


def feature_runtime_health() -> dict[str, Any]:
    """Return static handler-provenance health for the active feature runtime."""
    return {
        "ok": not LEGACY_GATEWAY_HANDLER_NAMES,
        "feature_tool_count": len(FEATURE_TOOLS),
        "runtime_native_migrated_tool_count": sum(
            len(definitions) for definitions, _ in RUNTIME_NATIVE_REGISTRATIONS
        ),
        "modern_feature_tool_count": sum(
            len(definitions) for definitions, _ in MODERN_REGISTRATIONS
        ),
        "legacy_gateway_handler_names": LEGACY_GATEWAY_HANDLER_NAMES,
        "legacy_gateway_handler_count": len(LEGACY_GATEWAY_HANDLER_NAMES),
        "active_handler_modules": sorted(set(HANDLER_SOURCES.values())),
    }
