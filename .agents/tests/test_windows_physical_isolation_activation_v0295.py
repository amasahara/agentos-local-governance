from __future__ import annotations

import json
from pathlib import Path

from agentos import __version__
from agentos.enforcement_attestation import attest_enforcement
from agentos.policy import load_policy, validate_policy
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.windows_physical_isolation import DESCRIPTOR
from agentos.windows_physical_isolation_attestation import attest_windows_physical_isolation

ROOT = Path(__file__).resolve().parents[2]


def test_v0295_release_identity_and_schema():
    current = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 5)
    assert __version__ == current
    assert CURRENT_SCHEMA_VERSION >= 62
    metadata = json.loads(
        (ROOT / ".agents/distribution/metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["agentos_version"] == current
    assert metadata["schema_version"] == CURRENT_SCHEMA_VERSION


def test_v0295_activation_policy_is_bounded():
    policy = load_policy(ROOT)
    validate_policy(policy)
    assert tuple(int(part) for part in policy["version"].split(".")) >= (0, 29, 5)
    current_release_name = policy["documentation_policy"]["current_release_name"]
    assert isinstance(current_release_name, str)
    assert current_release_name.strip()
    assert policy["documentation_policy"]["current_schema"] == CURRENT_SCHEMA_VERSION

    item = policy["windows_physical_isolation_policy"]
    assert item["enabled"] is True
    assert item["scope"] == "agentos_mediated_process_execution"
    assert item["release_focus"] == "native_physical_isolation_extensions"
    assert item["sync_execution_enforced"] is True
    assert item["async_execution_enforced"] is True
    assert item["sandbox_mandatory_label_enforced"] is True
    assert item["low_integrity_attested"] is True
    assert item["sandbox_low_integrity_label_attested"] is True
    assert item["production_activation_deferred"] is False
    assert item["release_activation_deferred_until_phase6"] is False
    assert item["activation_complete"] is True
    assert item["activation_version"] == "0.29.5"
    assert item["primary_root_write_up_prevention_attested"] is False

    for key in (
        "desktop_isolation_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    ):
        assert item[key] is False

    predecessor = policy["windows_restricted_execution_policy"]
    assert predecessor["restricted_token_attested"] is True
    assert predecessor["low_integrity_attested"] is False


def test_v0295_descriptor_activation_is_scoped():
    assert DESCRIPTOR.restricted_token_preserved is True
    assert DESCRIPTOR.sandbox_mandatory_label_enforced is True
    assert DESCRIPTOR.sync_execution_enforced is True
    assert DESCRIPTOR.async_execution_enforced is True
    assert DESCRIPTOR.low_integrity_attested is True
    assert DESCRIPTOR.host_filesystem_isolation_attested is False
    assert DESCRIPTOR.os_write_confinement_attested is False
    assert DESCRIPTOR.same_user_host_bypass_resistance_claimed is False
    assert DESCRIPTOR.desktop_isolation_attested is False


def test_v0295_physical_attestation_is_activated():
    report = attest_windows_physical_isolation(ROOT)
    for key in (
        "structurally_attested",
        "sync_enforced",
        "async_enforced",
        "restricted_token_preserved",
        "low_integrity_token_verified",
        "sandbox_low_integrity_boundary_verified",
        "production_controlled_ancestry_verified",
        "assignment_before_resume",
        "windows_ci_covered",
        "broad_nonclaims_preserved",
        "policy_declared_attested",
        "low_integrity_attested",
        "sandbox_low_integrity_label_attested",
    ):
        assert report[key] is True, key
    assert report["release_activation_deferred"] is False
    assert report["host_filesystem_isolation_attested"] is False
    assert report["os_write_confinement_attested"] is False
    assert report["same_user_host_bypass_resistance_claimed"] is False
    assert report["desktop_isolation_attested"] is False


def test_v0295_global_attestation_keeps_legacy_nonclaims_conservative():
    report = attest_enforcement(ROOT)
    assert report["ok"], report["findings"]

    item = report["windows_physical_isolation"]
    assert item["structurally_attested"] is True
    assert item["policy_declared_attested"] is True
    assert item["low_integrity_attested"] is True
    assert item["sandbox_low_integrity_label_attested"] is True

    restricted = report["windows_restricted_execution"]
    assert restricted["restricted_token_attested"] is True
    assert restricted["low_integrity_attested"] is False

    nonclaims = report["non_claims"]
    assert nonclaims["low_integrity_attested"] is False
    assert nonclaims["host_filesystem_isolation_attested"] is False
    assert nonclaims["os_write_confinement_attested"] is False
    assert nonclaims["same_user_host_bypass_resistance"] is False
    assert nonclaims["credential_isolation_attested"] is False


def test_v0295_windows_ci_includes_activation_suite():
    workflow = (
        ROOT / ".github/workflows/agentos-release-validation.yml"
    ).read_text(encoding="utf-8")
    assert "Windows physical isolation v0.29.5" in workflow
    assert "test_windows_physical_isolation_activation_v0295.py" in workflow
