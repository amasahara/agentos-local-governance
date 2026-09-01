from __future__ import annotations

from pathlib import Path

from agentos.enforcement_attestation import (
    attest_enforcement,
)
from agentos.policy import load_policy
from agentos.schema_version import CURRENT_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_v0293_credential_structural_attestation_is_green():
    report = attest_enforcement(ROOT)

    assert report["ok"], report["findings"]

    credential = report["credential_boundary"]

    assert credential["structurally_attested"] is True
    assert credential["sync_enforced"] is True
    assert credential["async_enforced"] is True
    assert credential["reference_hash_bound"] is True
    assert credential["launch_time_resolution"] is True
    assert credential["provider_approval_revalidated"] is True
    assert credential["secret_values_not_persisted"] is True
    assert credential["credentialed_output_safe"] is True
    assert credential["windows_file_secret_blocked"] is True
    assert credential["broad_nonclaims_preserved"] is True


def test_v0293_credential_structural_checks_are_all_true():
    report = attest_enforcement(ROOT)

    required = (
        "credential_policy_contract_enabled",
        "credential_reference_hash_bound",
        "credential_secret_resolver_reused",
        "credential_sync_launch_time_resolution",
        "credential_sync_output_redacted",
        "credential_async_spec_hash_only",
        "credential_async_launch_time_resolution",
        "credential_async_output_not_persisted",
        "credential_provider_approval_revalidated",
        "credential_values_not_persisted",
        "credential_windows_file_secret_blocked",
        "credential_broad_nonclaims_preserved",
    )

    for key in required:
        assert report["checks"][key] is True, key



def test_v0293_phase5_attestation_is_preserved_under_successor_without_overclaim():
    policy = load_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]
    report = attest_enforcement(ROOT)
    credential = report["credential_boundary"]

    assert section["credential_structural_attestation_required"] is True
    assert section["credential_ci_validation_required"] is True
    assert section["credential_boundary_attested"] is True
    assert credential["policy_declared_attested"] is True
    assert credential["credential_isolation_attested"] is False

    for key in (
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    ):
        assert section[key] is False

    current = (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()
    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 3)
    assert CURRENT_SCHEMA_VERSION == 62
