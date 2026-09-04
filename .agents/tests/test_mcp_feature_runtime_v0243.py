"""
File: .agents/tests/test_mcp_feature_runtime_v0243.py

Purpose:
    Verify v0.24.3 MCP Feature Runtime Refactor contracts.

Responsibilities:
    - Preserve the public MCP tool surface.
    - Prove active feature handlers are not owned by legacy gateway modules.
    - Prove mcp_runtime/catalog/core runtime do not import legacy MCP gateways.
    - Preserve the trusted gatewayd enforcement boundary for governed core tools.
    - Keep extension mutation authority unchanged.
"""
from __future__ import annotations

import ast
from pathlib import Path

import agentos.mcp_core_runtime as core_runtime
from agentos.mcp_feature_handlers import MIGRATED_TOOL_COUNT
from agentos.mcp_feature_runtime import (
    FEATURE_HANDLERS,
    FEATURE_TOOLS,
    LEGACY_GATEWAY_HANDLER_NAMES,
    feature_runtime_health,
)
from agentos.mcp_runtime import ALL_TOOLS, CORE_TOOL_NAMES, FEATURE_TOOL_NAMES

ROOT = Path(__file__).resolve().parents[2]

LEGACY_MODULE_NAMES = {
    "mcp_identity_gateway",
    "mcp_selection_gateway",
    "mcp_consolidation_gateway",
    "mcp_database_boundary_gateway",
    "mcp_schema_mapping_gateway",
    "mcp_read_only_extraction_gateway",
    "mcp_controlled_target_insert_gateway",
    "mcp_identity_resolution_gateway",
    "mcp_reconciliation_recovery_gateway",
    "mcp_server",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[-1] for alias in node.names)
    return modules


def test_public_mcp_tool_surface_is_preserved() -> None:
    names = [item["name"] for item in ALL_TOOLS]
    assert len(names) == len(set(names))
    assert len(CORE_TOOL_NAMES) == 14
    # Historical v0.24.3 feature-tool floor; successor releases may add read-only feature tools.
    assert len(FEATURE_TOOL_NAMES) >= 63
    from agentos.mcp_runtime import V0252_TOOL_NAMES
    assert len(V0252_TOOL_NAMES) == 6
    assert len(ALL_TOOLS) >= 84  # historical v0.24.3 public surface is a monotonic floor
    assert "agentos.mcp_health" in names
    assert "agentos.read_file" in names
    assert "agentos.db_reconciliation_get" in names
    assert "agentos.context_db_projection_get" in names


def test_37_gateway_embedded_handlers_are_now_runtime_native() -> None:
    assert MIGRATED_TOOL_COUNT == 37
    assert LEGACY_GATEWAY_HANDLER_NAMES == []
    health = feature_runtime_health()
    assert health["ok"] is True
    assert health["runtime_native_migrated_tool_count"] == 37
    assert health["legacy_gateway_handler_count"] == 0
    assert all("_gateway" not in handler.__module__ for handler in FEATURE_HANDLERS.values())


def test_active_mcp_import_graph_excludes_legacy_gateways() -> None:
    for rel in (
        ".agents/agentos/mcp_runtime.py",
        ".agents/agentos/mcp_core_runtime.py",
        ".agents/agentos/mcp_feature_runtime.py",
        ".agents/agentos/mcp_feature_handlers.py",
        ".agents/agentos/mcp_catalog.py",
    ):
        path = ROOT / rel
        imports = _imported_modules(path)
        assert not (imports & LEGACY_MODULE_NAMES), (rel, imports & LEGACY_MODULE_NAMES)
        assert "subprocess" not in imports, rel


def test_mcp_catalog_is_compatibility_facade_not_gateway_registry() -> None:
    text = (ROOT / ".agents/agentos/mcp_catalog.py").read_text(encoding="utf-8")
    assert "mcp_feature_runtime" in text
    assert "_gateway" not in text
    assert "subprocess" not in text


def test_governed_core_runtime_keeps_trusted_enforcement_gateway(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_request(root: Path, payload: dict):
        captured["root"] = root
        captured["payload"] = payload
        return {"success": True, "tool": payload["tool_name"]}

    monkeypatch.setattr(core_runtime, "gateway_request", fake_request)
    monkeypatch.setenv("AGENTOS_SESSION_TOKEN", "test-session-token")
    result = core_runtime.execute_core_tool(
        tmp_path,
        "task-1",
        "session-1",
        "agentos.read_file",
        {"path": "README.md"},
        7,
    )
    assert result["success"] is True
    assert captured["payload"]["action"] == "execute"
    assert captured["payload"]["task_id"] == "task-1"
    assert captured["payload"]["tool_name"] == "agentos.read_file"
    assert captured["payload"]["sequence"] == 7


def test_feature_mutation_surface_remains_forbidden() -> None:
    names = {item["name"] for item in FEATURE_TOOLS}
    forbidden = {
        "agentos.db_target_insert_execute",
        "agentos.db_identity_candidate_decide",
        "agentos.db_recovery_commit_decide",
        "agentos.db_reconciliation_run",
        "agentos.db_connection_register",
        "agentos.project_consolidation_batch_review",
    }
    assert not (names & forbidden)
