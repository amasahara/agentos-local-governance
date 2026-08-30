from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agentos.enforcement_attestation import attest_enforcement
from agentos.policy import load_release_policy, validate_policy


ROOT = Path(__file__).resolve().parents[2]


def test_v0292_sandbox_policy_is_activated():
    policy = load_release_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]

    assert policy["version"] == "0.29.2"
    assert section["runtime_profile_sandbox_attested"] is True
    assert section["scope"] == "agentos_mediated_process_execution"


def test_v0292_structural_attestation_green_after_activation():
    report = attest_enforcement(ROOT)
    assert report["ok"], report["findings"]

    item = report["sandbox_workspace_runtime_profiles"]
    for key in (
        "structurally_attested",
        "policy_declared_attested",
        "sync_enforced",
        "async_enforced",
        "snapshot_hash_bound",
        "mutable_state_redirected",
        "terminal_cleanup_guarded",
        "windows_process_tree_containment_preserved",
        "broad_nonclaims_preserved",
    ):
        assert item[key] is True

    assert item["policy_scope"] == "agentos_mediated_process_execution"


def test_v0292_attestation_keeps_future_security_claims_false():
    policy = load_release_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]

    for key in (
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    ):
        assert section[key] is False


def test_v0292_active_activation_policy_validates():
    policy = copy.deepcopy(load_release_policy(ROOT))
    assert policy["version"] == "0.29.2"
    assert (
        policy["sandbox_workspace_runtime_profile_policy"][
            "runtime_profile_sandbox_attested"
        ]
        is True
    )
    validate_policy(policy)


@pytest.mark.parametrize(
    "key",
    [
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "credential_isolation_attested",
        "same_user_host_bypass_resistance_claimed",
    ],
)
def test_v0292_activation_policy_rejects_security_overclaim(key: str):
    policy = copy.deepcopy(load_release_policy(ROOT))
    policy["sandbox_workspace_runtime_profile_policy"][key] = True

    with pytest.raises(RuntimeError):
        validate_policy(policy)


def test_v0292_activation_requires_attestation_declaration():
    policy = copy.deepcopy(load_release_policy(ROOT))
    policy["sandbox_workspace_runtime_profile_policy"][
        "runtime_profile_sandbox_attested"
    ] = False

    with pytest.raises(RuntimeError):
        validate_policy(policy)
