"""
File: .agents/tests/test_enforcement_attestation_v0284.py

Purpose:
    Protect v0.28.4 deterministic enforcement attestation.
"""
from __future__ import annotations

from pathlib import Path

from agentos.cli_runtime import (
    agent_command_registry,
    privileged_command_registry,
)
from agentos.enforcement_attestation import (
    ATTESTATION_SCOPE,
    attest_enforcement,
)


ROOT = Path(__file__).resolve().parents[2]


def _report() -> dict:
    return attest_enforcement(ROOT)


def test_enforcement_attestation_passes() -> None:
    report = _report()

    assert report["ok"], report["findings"]
    assert report["tool_exclusivity"] is True
    assert report["attestation_ready"] is True


def test_attestation_scope_is_explicit() -> None:
    report = _report()

    assert (
        report["scope"]
        == "agentos_mediated_agent_execution"
        == ATTESTATION_SCOPE
    )


def test_attestation_does_not_overclaim_os_isolation() -> None:
    report = _report()
    claims = report["non_claims"]

    assert (
        claims[
            "same_user_host_bypass_resistance"
        ]
        is False
    )
    assert (
        claims[
            "os_level_process_isolation_attested"
        ]
        is False
    )
    assert (
        claims[
            "arbitrary_host_process_containment"
        ]
        is False
    )


def test_process_primitives_have_no_unexpected_sites() -> None:
    report = _report()

    assert (
        report["process_execution"][
            "unexpected"
        ]
        == []
    )

    assert (
        report["process_execution"][
            "canonical_primitive_site_count"
        ]
        >= 2
    )


def test_mcp_active_runtime_is_exclusive() -> None:
    report = _report()
    mcp = report["mcp"]

    assert mcp["ok"] is True
    assert (
        mcp[
            "trusted_enforcement_gateway"
        ]
        is True
    )
    assert (
        mcp["subprocess_forwarding"]
        is False
    )
    assert (
        mcp["legacy_gateway_active"]
        is False
    )
    assert (
        mcp[
            "legacy_gateway_handler_count"
        ]
        == 0
    )
    assert (
        mcp["legacy_runtime_imports"]
        == []
    )


def test_enforcement_attest_is_agent_read_only_command() -> None:
    agent = agent_command_registry()
    privileged = privileged_command_registry()

    assert "enforcement-attest" in agent
    assert "enforcement-attest" not in privileged


def test_policy_activation_is_reported_separately() -> None:
    report = _report()

    assert isinstance(
        report["policy_declared_attested"],
        bool,
    )

    # Structural attestation must not depend on the release
    # declaration flag. Phase 4 activates that policy flag only
    # after this report is independently green.
    assert report["attestation_ready"] is True


def test_runtime_health_is_attestation_gated() -> None:
    from agentos.cli_runtime import _runtime_health

    result = _runtime_health(ROOT)
    attestation = result["enforcement_attestation"]

    assert result["ok"] is True
    assert attestation["ok"] is True
    assert attestation["attestation_ready"] is True
    assert attestation["tool_exclusivity"] is True
    assert (
        attestation["scope"]
        == "agentos_mediated_agent_execution"
    )


def test_release_integrity_requires_attestation_artifacts() -> None:
    import inspect

    from agentos import release_integrity

    assert (
        ".agents/agentos/enforcement_attestation.py"
        in release_integrity.CORE_FILES
    )

    assert (
        ".agents/tests/test_tool_exclusivity_v0284.py"
        in release_integrity.RELEASE_FILES
    )

    assert (
        ".agents/tests/test_enforcement_attestation_v0284.py"
        in release_integrity.RELEASE_FILES
    )

    source = inspect.getsource(
        release_integrity.check_release_integrity
    )

    assert "attest_enforcement(" in source
    assert "enforcement_attestation_failed" in source
    assert "tool_exclusivity_policy_not_activated" in source


def test_doctor_contains_enforcement_attestation_gate() -> None:
    import inspect

    import agentos.cli as core_cli

    source = inspect.getsource(
        core_cli._doctor
    )

    assert "attest_enforcement(" in source
    assert '"enforcement_attestation"' in source
    assert '"tool_exclusivity"' in source


def _v0284_policy_candidate() -> dict:
    import copy

    from agentos.policy import load_release_policy

    policy = copy.deepcopy(
        load_release_policy(ROOT)
    )

    policy["version"] = "0.28.4"

    control = policy[
        "privileged_control_plane_policy"
    ]

    control.update(
        {
            "hard_anti_bypass_reserved_for_v0284": False,
            "tool_exclusivity_attested": True,
            "tool_exclusivity_scope": (
                "agentos_mediated_agent_execution"
            ),
            "enforcement_attestation_version": 1,
            "same_user_host_bypass_resistance_claimed": False,
            "os_level_process_isolation_attested": False,
            "arbitrary_host_process_containment_attested": False,
        }
    )

    policy["web_control_plane_policy"]["database_schema"] = 61
    policy["privileged_control_plane_policy"]["database_schema"] = 61
    policy.pop("completion_verification_policy", None)
    return policy


def test_v0284_policy_contract_accepts_scoped_attestation() -> None:
    from agentos.policy import validate_policy

    validate_policy(
        _v0284_policy_candidate()
    )


def test_v0284_policy_contract_rejects_security_overclaim() -> None:
    import pytest

    from agentos.policy import validate_policy

    policy = _v0284_policy_candidate()

    policy[
        "privileged_control_plane_policy"
    ][
        "same_user_host_bypass_resistance_claimed"
    ] = True

    with pytest.raises(
        RuntimeError,
        match="scope overclaim",
    ):
        validate_policy(policy)
