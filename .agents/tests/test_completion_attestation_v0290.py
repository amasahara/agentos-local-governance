"""Phase 5 tests for v0.29.0 independent-completion attestation."""
from __future__ import annotations
import ast

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from agentos.cli_runtime import _runtime_health
from agentos.enforcement_attestation import (
    ATTESTATION_SCOPE,
    ATTESTATION_VERSION,
    attest_enforcement,
)


def report():
    return attest_enforcement(ROOT)


def test_completion_structural_attestation_passes():
    value = report()
    completion = value["completion_verification"]
    assert value["ok"], value["findings"]
    assert value["attestation_ready"] is True
    assert value["tool_exclusivity"] is True
    assert completion["structurally_attested"] is True


def test_completion_claim_is_producer_independent_and_evidence_bound():
    completion = report()["completion_verification"]
    assert completion["producer_independent"] is True
    assert completion["evidence_bound"] is True
    assert completion["freshness_bound"] is True


def test_completion_enforcement_covers_acceptance_boundaries():
    completion = report()["completion_verification"]
    assert completion["workflow_enforced"] is True
    assert completion["worker_enforced"] is True
    assert completion["integration_enforced"] is True


def test_completion_surfaces_preserve_agent_and_mcp_boundaries():
    completion = report()["completion_verification"]
    assert completion["cli_agent_plane_only"] is True
    assert completion["mcp_read_only"] is True


def test_completion_policy_is_activated_in_v0290():
    completion = report()["completion_verification"]

    assert completion["policy_declared_attested"] is True
    assert (
        completion["policy_scope"]
        == "agentos_mediated_agent_execution"
    )


def test_completion_nonclaims_are_explicit():
    non_claims = report()["non_claims"]
    assert non_claims["semantic_correctness_guaranteed"] is False
    assert non_claims["model_provider_independence_attested"] is False
    assert non_claims["human_review_replaced"] is False
    assert non_claims["human_approval_replaced"] is False
    assert non_claims["same_user_host_bypass_resistance"] is False
    assert non_claims["os_level_process_isolation_attested"] is False
    assert non_claims["arbitrary_host_process_containment"] is False


def test_attestation_scope_and_version_remain_backward_compatible():
    value = report()
    assert ATTESTATION_VERSION == 1
    assert value["scope"] == ATTESTATION_SCOPE == "agentos_mediated_agent_execution"


def test_runtime_health_is_completion_attestation_gated():
    health = _runtime_health(ROOT)
    assert health["ok"] is True
    assert health["enforcement_attestation"]["attestation_ready"] is True


def test_release_integrity_has_v0290_completion_gate():
    from agentos import release_integrity
    source = inspect.getsource(release_integrity.check_release_integrity)
    assert "completion_attestation_failed" in source
    assert "completion_attestation_policy_not_activated" in source
    assert "completion_attestation_overclaim" in source
    assert "(0, 29, 0)" in source


def test_completion_attestation_adds_no_process_primitive():
    path = ROOT / ".agents/agentos/enforcement_attestation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    process_calls = []

    for item in ast.walk(tree):
        if not isinstance(item, ast.Call):
            continue

        func = item.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
            and func.attr
            in {
                "run",
                "Popen",
                "call",
                "check_call",
                "check_output",
            }
        ):
            process_calls.append(
                {
                    "line": item.lineno,
                    "primitive": func.attr,
                }
            )

    assert process_calls == []
