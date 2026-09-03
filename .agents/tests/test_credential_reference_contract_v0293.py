from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agentos.policy import load_policy
from agentos.proxy import _filtered_env
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.secret_lineage import (
    ALLOWED_SECRET_CAPABILITIES,
    PROVIDER_API_VERSION,
)
from agentos.tool_runtime_profiles import (
    PROCESS_CREDENTIAL_CAPABILITY,
    credential_bindings_for_profile,
    credential_reference_contract_from_policy,
    resolve_runtime_profile_from_policy,
    sandbox_configuration_from_policy,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0293_phase2_reference_contract_is_release_activated():
    policy = load_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]

    assert section["credential_reference_contract_enabled"] is True
    assert section["credential_reference_version"] == 1
    assert section["credential_reference_scheme"] == "secret"
    assert section["credential_resolver_contract"] == PROVIDER_API_VERSION == "secret-resolver-v1"
    assert section["credential_reference_secret_alias_only"] is True
    assert section["credential_reference_hash_required"] is True
    assert section["credential_raw_values_forbidden"] is True
    assert section["credential_values_persisted_forbidden"] is True
    assert section["credential_environment_projection_enabled"] is True
    assert section["credential_boundary_enabled"] is True
    assert section["credential_boundary_attested"] is True
    assert section["windows_file_secret_process_projection_attested"] is False

def test_v0293_phase2_default_profiles_have_empty_reference_bindings():
    policy = load_policy(ROOT)

    contract = credential_reference_contract_from_policy(
        policy
    )

    assert len(
        contract["credential_reference_hash"]
    ) == 64
    assert contract["credential_resolver_contract"] == "secret-resolver-v1"
    assert contract["process_credential_capability"] == (
        PROCESS_CREDENTIAL_CAPABILITY
    )

    assert contract["credential_bindings"] == {
        "build": [],
        "inspect": [],
        "test": [],
    }

    for name in ("inspect", "test", "build"):
        binding = credential_bindings_for_profile(
            name,
            policy,
        )
        assert binding["binding_count"] == 0
        assert len(binding["binding_hash"]) == 64
        assert binding["secret_values_included"] is False


def test_v0293_phase2_credential_references_are_configuration_hash_bound():
    policy = load_policy(ROOT)

    original = sandbox_configuration_from_policy(
        policy
    )

    modified = copy.deepcopy(policy)
    modified[
        "sandbox_workspace_runtime_profile_policy"
    ][
        "credential_bindings"
    ][
        "test"
    ] = [
        {
            "binding_id": "ci-token",
            "credential_ref": "secret://ci-token",
            "target_env": "CI_API_TOKEN",
            "secret_field": "token",
        }
    ]

    changed = sandbox_configuration_from_policy(
        modified
    )

    assert (
        original["configuration_hash"]
        != changed["configuration_hash"]
    )
    assert (
        original["credential_reference_hash"]
        != changed["credential_reference_hash"]
    )

    runtime = resolve_runtime_profile_from_policy(
        "test",
        modified,
    )
    assert runtime["credential_binding_count"] == 1
    assert len(runtime["credential_binding_hash"]) == 64
    assert runtime["credential_values_included"] is False


@pytest.mark.parametrize(
    ("binding", "match"),
    [
        (
            {
                "binding_id": "bad",
                "credential_ref": "env://TOKEN",
                "target_env": "CI_API_TOKEN",
                "secret_field": "token",
            },
            "secret_alias",
        ),
        (
            {
                "binding_id": "bad",
                "credential_ref": "secret://ci-token",
                "target_env": "PATH",
                "secret_field": "token",
            },
            "reserved",
        ),
        (
            {
                "binding_id": "bad",
                "credential_ref": "secret://ci-token",
                "target_env": "VISIBLE_SETTING",
                "secret_field": "token",
            },
            "secret_classified",
        ),
        (
            {
                "binding_id": "bad",
                "credential_ref": "secret://ci-token",
                "target_env": "CI_API_TOKEN",
                "secret_field": "token",
                "value": "raw-secret",
            },
            "unknown_fields",
        ),
    ],
)
def test_v0293_phase2_invalid_or_raw_binding_contract_fails_closed(
    binding,
    match,
):
    policy = copy.deepcopy(load_policy(ROOT))
    policy[
        "sandbox_workspace_runtime_profile_policy"
    ][
        "credential_bindings"
    ][
        "test"
    ] = [binding]

    with pytest.raises(
        RuntimeError,
        match=match,
    ):
        credential_reference_contract_from_policy(
            policy
        )


def test_v0293_phase2_duplicate_environment_projection_fails_closed():
    policy = copy.deepcopy(load_policy(ROOT))
    policy[
        "sandbox_workspace_runtime_profile_policy"
    ][
        "credential_bindings"
    ][
        "test"
    ] = [
        {
            "binding_id": "first",
            "credential_ref": "secret://one",
            "target_env": "CI_API_TOKEN",
            "secret_field": "token",
        },
        {
            "binding_id": "second",
            "credential_ref": "secret://two",
            "target_env": "CI_API_TOKEN",
            "secret_field": "token",
        },
    ]

    with pytest.raises(
        RuntimeError,
        match="target_env_duplicate",
    ):
        credential_reference_contract_from_policy(
            policy
        )


def test_v0293_phase2_raw_secret_like_caller_environment_remains_filtered():
    filtered = _filtered_env(
        {
            "CI_API_TOKEN": "raw-secret",
            "APP_PASSWORD": "raw-secret",
            "NORMAL_SETTING": "visible",
        }
    )

    assert "CI_API_TOKEN" not in filtered
    assert "APP_PASSWORD" not in filtered
    assert filtered["NORMAL_SETTING"] == "visible"


def test_v0293_phase2_declares_bounded_process_secret_capability():
    assert (
        PROCESS_CREDENTIAL_CAPABILITY
        == "process.exec.credential"
    )


def test_v0293_phase2_identity_and_nonclaims_are_preserved_under_successor():
    policy = load_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]
    current = (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()

    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 3)
    assert CURRENT_SCHEMA_VERSION >= 62
    assert section["sandbox_configuration_attested"] is True
    assert section["credential_boundary_enabled"] is True
    assert section["credential_boundary_attested"] is True

    for key in (
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    ):
        assert section[key] is False
