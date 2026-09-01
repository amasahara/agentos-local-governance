from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agentos.policy import load_policy
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.tool_runtime_profiles import (
    SANDBOX_CONFIGURATION_VERSION,
    resolve_runtime_profile_from_policy,
    sandbox_configuration_from_policy,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0293_phase1_policy_configuration_contract_is_present():
    policy = load_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]

    assert section["sandbox_configuration_contract_enabled"] is True
    assert section["sandbox_configuration_version"] == 1
    assert section["sandbox_configuration_source"] == "effective_policy"
    assert section["sandbox_configuration_hash_required"] is True
    assert section["configured_profiles_must_match_known_profiles"] is True
    assert section["unknown_profile_fields_allowed"] is False
    assert section["security_invariants_runtime_enforced"] is True
    assert section["caller_configuration_override_allowed"] is False
    assert set(section["configured_profiles"]) == {
        "inspect",
        "test",
        "build",
    }


def test_v0293_phase1_configuration_hash_is_deterministic():
    policy = load_policy(ROOT)

    first = sandbox_configuration_from_policy(policy)
    second = sandbox_configuration_from_policy(copy.deepcopy(policy))

    assert first == second
    assert first["configuration_version"] == SANDBOX_CONFIGURATION_VERSION
    assert first["configuration_source"] == "effective_policy"
    assert len(first["configuration_hash"]) == 64


def test_v0293_phase1_policy_resolver_binds_profile_and_configuration_hash():
    policy = load_policy(ROOT)

    resolved = resolve_runtime_profile_from_policy(
        "test",
        policy,
    )

    assert resolved["name"] == "test"
    assert len(resolved["profile_hash"]) == 64
    assert len(resolved["configuration_hash"]) == 64
    assert resolved["configuration_version"] == 1
    assert resolved["configuration_source"] == "effective_policy"
    assert resolved["profile"]["network_policy"] == "none"
    assert resolved["profile"]["writable_scope"] == "sandbox_only"


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (
            lambda section: section["configured_profiles"]["test"].update(
                {"network_policy": "allow"}
            ),
            "invariant_mismatch",
        ),
        (
            lambda section: section["configured_profiles"]["test"].update(
                {"extra_field": True}
            ),
            "unknown_fields",
        ),
        (
            lambda section: section["configured_profiles"].pop("build"),
            "profile_set_mismatch",
        ),
        (
            lambda section: section.update(
                {"caller_configuration_override_allowed": True}
            ),
            "configuration_contract",
        ),
    ],
)
def test_v0293_phase1_weakened_or_ambiguous_configuration_fails_closed(
    mutation,
    match,
):
    policy = copy.deepcopy(load_policy(ROOT))
    section = policy["sandbox_workspace_runtime_profile_policy"]
    mutation(section)

    with pytest.raises(RuntimeError, match=match):
        sandbox_configuration_from_policy(policy)


def test_v0293_phase1_sync_proxy_binds_policy_configuration():
    source = (
        ROOT / ".agents/agentos/proxy.py"
    ).read_text(encoding="utf-8")

    assert "resolve_runtime_profile_from_policy" in source
    assert 'metadata["runtime_profile_configuration_hash"]' in source
    assert 'metadata["runtime_profile_configuration_version"]' in source
    assert 'metadata["runtime_profile_configuration_source"]' in source
    assert "resolved_runtime_profile=runtime_profile" in source
    assert "runtime_profile_configuration_drift" in source


def test_v0293_phase1_async_job_binds_and_revalidates_policy_configuration():
    source = (
        ROOT / ".agents/agentos/jobs.py"
    ).read_text(encoding="utf-8")

    assert "resolve_runtime_profile_from_policy" in source
    assert "def _assert_async_runtime_spec_current(" in source
    assert '"runtime_profile_configuration_hash"' in source
    assert '"runtime_profile_configuration_version"' in source
    assert '"runtime_profile_configuration_source"' in source
    assert "resolved_runtime_profile=runtime_profile" in source
    assert "runtime_profile_configuration_drift" in source



def test_v0293_phase1_contract_is_preserved_under_successor_release():
    policy = load_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]
    current = (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()

    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 3)
    assert CURRENT_SCHEMA_VERSION == 62
    assert section["sandbox_configuration_attested"] is True
    assert section["credential_boundary_enabled"] is True

    for key in (
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    ):
        assert section[key] is False

def test_v0293_phase1_legacy_policy_resolution_remains_compatible():
    minimal_policy = {
        "proxy_policy": {
            "process_exec": {}
        }
    }

    resolved = resolve_runtime_profile_from_policy(
        "test",
        minimal_policy,
    )

    assert resolved["name"] == "test"
    assert "configuration_hash" not in resolved
    assert "configuration_version" not in resolved
    assert "configuration_source" not in resolved


def test_v0293_phase1_inherited_v0292_structural_attestation_accepts_policy_resolver():
    from agentos.enforcement_attestation import attest_enforcement

    report = attest_enforcement(ROOT)

    assert report["checks"]["sandbox_sync_profile_bound"] is True
    assert report["checks"]["sandbox_async_profile_snapshot_bound"] is True
