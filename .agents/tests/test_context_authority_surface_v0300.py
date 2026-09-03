"""Focused v0.30.0 Phase 4 tests for read-only surfaces and attestation."""
from __future__ import annotations
import ast
from pathlib import Path
from agentos.cli_runtime import CONTROL_PLANE_COMMANDS, agent_command_registry, command_registry
from agentos.enforcement_attestation import attest_enforcement
from agentos.mcp_runtime import ALL_TOOLS
from agentos.mcp_v0300 import TOOL_NAMES, dispatch
from agentos.policy import load_release_policy

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_CLI = {"context-authority-status","context-provenance-show","context-authority-explain","context-authority-findings"}
EXPECTED_MCP = {"agentos.context_authority_status_get","agentos.context_provenance_get","agentos.context_authority_explain","agentos.context_authority_findings_get"}


def test_context_authority_cli_is_agent_plane_read_only() -> None:
    registry = command_registry(); agent = agent_command_registry()
    assert EXPECTED_CLI <= set(registry)
    assert EXPECTED_CLI <= set(agent)
    assert not (EXPECTED_CLI & set(CONTROL_PLANE_COMMANDS))
    assert all(registry[name] == "context_authority_cli" for name in EXPECTED_CLI)


def test_context_authority_mcp_is_read_only_and_unique() -> None:
    assert TOOL_NAMES == EXPECTED_MCP
    names = [item["name"] for item in ALL_TOOLS]
    assert len(names) == len(set(names))
    assert EXPECTED_MCP <= set(names)


def test_mcp_missing_task_fails_without_mutation() -> None:
    assert dispatch(ROOT, "agentos.context_authority_status_get", {}) == {"ok": False, "error": "task_id_required"}


def test_context_authority_attestation_is_active() -> None:
    report = attest_enforcement(ROOT)
    assert report["ok"] is True, report["findings"]
    context = report["context_authority"]
    assert context["structurally_attested"] is True
    assert context["origin_classification"] is True
    assert context["authority_promotion_forbidden"] is True
    assert context["hash_only_persistence"] is True
    assert context["transport_pinned"] is True
    assert context["cli_read_only"] is True
    assert context["mcp_read_only"] is True
    assert context["policy_scope"] == "agentos_context_assembly"
    assert context["broad_nonclaims_preserved"] is True


def test_context_authority_surfaces_add_no_process_primitives() -> None:
    for rel in (".agents/agentos/context_authority.py",".agents/agentos/context_authority_surface.py",".agents/agentos/context_authority_cli.py",".agents/agentos/mcp_v0300.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        imports = set(); process_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module: imports.add(node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess": process_calls.append(node.func.attr)
        assert "subprocess" not in imports, rel
        assert process_calls == [], rel


def test_policy_declares_exact_read_only_surfaces() -> None:
    policy = load_release_policy(ROOT)["context_authority_policy"]
    assert set(policy["mcp_read_tools"]) == EXPECTED_MCP
    assert set(policy["cli_read_commands"]) == EXPECTED_CLI
    assert policy["mcp_mutation_allowed"] is False
