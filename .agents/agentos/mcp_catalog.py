"""
File: .agents/agentos/mcp_catalog.py

Purpose:
    Build one flat read-only extension MCP catalog with direct in-process handlers.

Responsibilities:
    - Merge extension tool definitions without version forwarding.
    - Bind each tool name directly to the module that owns the tool.
    - Reject duplicate tool names fail-closed.
    - Keep database/identity/recovery mutation tools outside MCP.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import mcp_identity_gateway as identity
from . import mcp_selection_gateway as selection
from . import mcp_consolidation_gateway as consolidation
from . import mcp_database_boundary_gateway as boundary
from . import mcp_schema_mapping_gateway as mapping
from . import mcp_read_only_extraction_gateway as extraction
from . import mcp_controlled_target_insert_gateway as target_insert
from . import mcp_identity_resolution_gateway as identity_resolution
from . import mcp_reconciliation_recovery_gateway as recovery
from . import mcp_secret_lineage as secret_lineage
from . import mcp_data_subject_rights as data_subject_rights

FeatureHandler = Callable[[str, dict[str, Any], Path], dict[str, Any]]


def _identity_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    del arguments
    return identity._local_call(name, root)


REGISTRATIONS: tuple[tuple[list[dict[str, Any]], FeatureHandler], ...] = (
    (identity.TOOLS, _identity_call),
    (selection.TOOLS, selection._local_call),
    (consolidation.TOOLS, consolidation._local_call),
    (boundary.TOOLS, boundary._local_call),
    (mapping.TOOLS, mapping._local_call),
    (extraction.TOOLS, extraction._local_call),
    (target_insert.TOOLS, target_insert._local_call),
    (identity_resolution.TOOLS, identity_resolution._local_call),
    (recovery.LOCAL_TOOLS, recovery._local_call),
    (secret_lineage.TOOLS, secret_lineage._local_call),
    (data_subject_rights.TOOLS, data_subject_rights._local_call),
)


def build_feature_catalog() -> tuple[list[dict[str, Any]], dict[str, FeatureHandler]]:
    """Return the flat extension tool catalog and direct handlers.

    Returns:
        Tuple containing ordered tool definitions and name-to-handler mapping.

    Raises:
        RuntimeError: When duplicate extension MCP tool names are detected.
    """
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
