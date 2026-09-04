"""Focused v0.32.1 Runtime Coherence & Provenance Ergonomics tests."""
from __future__ import annotations

import json
from pathlib import Path

from agentos import cli_runtime, mcp_runtime
from agentos import execution_provenance as ep
from agentos import mcp_execution_provenance as mcp_ep
from agentos.schema_version import CURRENT_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_v0321_schema_stays_65() -> None:
    assert CURRENT_SCHEMA_VERSION == 65
    db = (ROOT / ".agents/agentos/db.py").read_text(encoding="utf-8")
    assert "migration_65" in db
    assert "migration_66" not in db


def test_mcp_safe_projection_excludes_sensitive_correlation_fields() -> None:
    row = {
        "provenance_id": "EP-1",
        "provenance_version": 1,
        "task_id": "T1",
        "session_id": "S1",
        "execution_ref_type": "async_job",
        "execution_ref_id": "PRIVATE-REF",
        "execution_ref_hash": "a" * 64,
        "provider_id": "provider",
        "model_id": "model",
        "model_revision": "r1",
        "deployment_id": "private-deployment",
        "provider_request_id_hash": "b" * 64,
        "agent_id": "agent",
        "runtime_id": "runtime",
        "runtime_version": "1",
        "endpoint_class": "remote_api",
        "recorded_by": "operator",
        "source_class": "immutable_runtime_spec",
        "verification_class": "runtime_bound",
        "context_revision": 1,
        "context_authority_hash": "c" * 64,
        "provenance_manifest_hash": "d" * 64,
        "architecture_baseline_hash": "e" * 64,
        "plan_hash": "f" * 64,
        "policy_revision": "0.32.1",
        "declaration_hash": "1" * 64,
        "binding_hash": "2" * 64,
        "secrets_included": 0,
        "created_at": "2026-09-04 00:00:00",
    }
    safe = ep._mcp_safe_projection(row)
    for key in (
        "execution_ref_id",
        "provider_request_id_hash",
        "deployment_id",
        "recorded_by",
        "secrets_included",
    ):
        assert key not in safe
    assert safe["instruction_authority"] is False
    assert safe["context_authority_affected"] is False
    assert safe["remote_provider_cryptographic_attestation"] is False
    assert safe["mutable_via_mcp"] is False


def test_exact_two_execution_provenance_mcp_tools() -> None:
    assert mcp_ep.TOOL_NAMES == {
        "agentos.execution_provenance_get",
        "agentos.execution_provenance_list",
    }
    assert len(mcp_ep.TOOLS) == 2
    source = (ROOT / ".agents/agentos/mcp_execution_provenance.py").read_text(
        encoding="utf-8"
    )
    assert "register_execution_provenance" not in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source


def test_mcp_runtime_registration_and_exact_surface() -> None:
    feature = (ROOT / ".agents/agentos/mcp_feature_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "mcp_execution_provenance" in feature
    assert len(mcp_runtime.ALL_TOOLS) == 134
    assert "agentos.execution_provenance_get" in mcp_runtime.ALL_TOOL_NAMES
    assert "agentos.execution_provenance_list" in mcp_runtime.ALL_TOOL_NAMES
    assert "agentos.execution_provenance_register" not in mcp_runtime.ALL_TOOL_NAMES


def test_cli_list_is_agent_plane_and_registration_stays_privileged() -> None:
    registry = cli_runtime.command_registry()
    agent = cli_runtime.agent_command_registry()
    privileged = cli_runtime.privileged_command_registry()
    assert "execution-provenance-list" in registry
    assert "execution-provenance-list" in agent
    assert "execution-provenance-list" not in privileged
    assert "execution-provenance-register" in privileged
    assert "execution-provenance-register" not in agent
    assert len(registry) == 368
    assert len(agent) == 270
    assert len(privileged) == 100


def test_learning_usage_savepoint_policy_and_source() -> None:
    source = (ROOT / ".agents/agentos/context_runtime.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        "SAVEPOINT context_learning_usage",
        "ROLLBACK TO SAVEPOINT context_learning_usage",
        "learning_usage_degraded",
        "learning_usage_error",
        "learning_usage_recorded",
    ):
        assert marker in source
    policy = json.loads(
        (ROOT / ".agents/config/policy/learning.json").read_text(encoding="utf-8")
    )["governed_learning_policy"]["degraded_safe"]
    assert policy["knowledge_usage_savepoint_required"] is True
    assert policy["knowledge_usage_failure_must_be_surfaced"] is True
    assert policy["knowledge_usage_failure_must_not_fabricate_usage"] is True


def test_execution_identity_policy_mcp_projection() -> None:
    policy = json.loads(
        (ROOT / ".agents/config/policy/execution_identity.json").read_text(
            encoding="utf-8"
        )
    )["execution_identity_policy"]
    assert policy["mcp_mutation_allowed"] is False
    assert policy["mcp_read_only"] is True
    assert policy["mcp_safe_projection_required"] is True
    assert policy["mcp_read_tools"] == [
        "agentos.execution_provenance_get",
        "agentos.execution_provenance_list",
    ]
    assert policy["mcp_provider_request_id_hash_exposed"] is False
    assert policy["mcp_recorded_by_exposed"] is False
    assert policy["mcp_execution_ref_id_exposed"] is False


def test_mcp_feature_runtime_metadata_semantics() -> None:
    governance = json.loads(
        (ROOT / ".agents/config/governance.json").read_text(encoding="utf-8")
    )
    policy = governance["mcp_feature_runtime_policy"]
    assert policy["database_schema"] == 49
    assert policy["feature_tool_count"] == 63
    assert policy["total_tool_count_with_health"] == 78
    assert policy["feature_tool_count_semantics"] == "historical_activation_snapshot_v0243"
    assert policy["total_tool_count_semantics"] == "historical_activation_snapshot_v0243"
    assert policy["current_catalog_count_source"] == "runtime_catalog"
    assert policy["current_catalog_release_validation_required"] is True

def test_v0321_base_governance_version_remains_historical_overlay_boundary() -> None:
    base = json.loads(
        (ROOT / ".agents/config/governance.json").read_text(encoding="utf-8")
    )
    release = json.loads(
        (ROOT / ".agents/config/release_policy.json").read_text(encoding="utf-8")
    )
    assert base["version"] == "0.26.3"
    assert release["version"] == "0.32.1"
    assert "windows_process_tree_containment_policy" not in base
    assert "windows_process_tree_containment_policy" in release


def test_v0321_exact_feature_mcp_surface() -> None:
    assert len(mcp_runtime.FEATURE_TOOL_NAMES) == 65
    assert len(mcp_runtime.ALL_TOOLS) == 134
