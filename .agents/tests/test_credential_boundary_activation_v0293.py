from __future__ import annotations

import json
from pathlib import Path

from agentos import __version__
from agentos.enforcement_attestation import attest_enforcement
from agentos.policy import load_policy, validate_policy
from agentos.release_integrity import _credential_boundary_ci_contract_v0293
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.tool_runtime_profiles import (
    credential_reference_contract_from_policy,
    sandbox_configuration_from_policy,
)

ROOT = Path(__file__).resolve().parents[2]



def test_v0293_release_identity_and_schema_are_preserved_under_successor():
    current = (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()

    assert __version__ == current
    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 3)
    assert CURRENT_SCHEMA_VERSION == 62

    metadata = json.loads(
        (ROOT / ".agents/distribution/metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["agentos_version"] == current
    assert metadata["schema_version"] == 62


def test_v0293_policy_guarantees_are_preserved_under_successor():
    policy = load_policy(ROOT)
    validate_policy(policy)

    assert tuple(
        int(part)
        for part in policy["version"].split(".")
    ) >= (0, 29, 3)

    section = policy["sandbox_workspace_runtime_profile_policy"]

    assert (
        section["release_focus"]
        == "sandbox_configuration_and_credential_boundary"
    )

    for key in (
        "sandbox_configuration_attested",
        "credential_environment_projection_enabled",
        "credential_boundary_enabled",
        "credential_boundary_attested",
        "sync_credential_boundary_attested",
        "async_credential_boundary_attested",
    ):
        assert section[key] is True

    assert len(
        sandbox_configuration_from_policy(policy)["configuration_hash"]
    ) == 64
    assert len(
        credential_reference_contract_from_policy(policy)[
            "credential_reference_hash"
        ]
    ) == 64

def test_v0293_structural_attestation_is_policy_activated():
    report = attest_enforcement(ROOT)
    assert report["ok"], report["findings"]
    item = report["credential_boundary"]
    for key in (
        "structurally_attested",
        "sync_enforced",
        "async_enforced",
        "reference_hash_bound",
        "launch_time_resolution",
        "provider_approval_revalidated",
        "secret_values_not_persisted",
        "credentialed_output_safe",
        "windows_file_secret_blocked",
        "broad_nonclaims_preserved",
        "policy_declared_attested",
    ):
        assert item[key] is True
    assert item["credential_isolation_attested"] is False


def test_v0293_activation_preserves_broad_nonclaims():
    section = load_policy(ROOT)["sandbox_workspace_runtime_profile_policy"]
    for key in (
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
        "windows_file_secret_process_projection_attested",
    ):
        assert section[key] is False


def test_v0293_ci_contract_includes_activation_suite():
    report = _credential_boundary_ci_contract_v0293(ROOT)
    assert report["ok"], report["missing_markers"]
    workflow = (
        ROOT / ".github/workflows/agentos-release-validation.yml"
    ).read_text(encoding="utf-8")
    assert "test_credential_boundary_activation_v0293.py" in workflow
