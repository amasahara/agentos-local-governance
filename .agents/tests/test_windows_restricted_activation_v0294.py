from __future__ import annotations

import json
from pathlib import Path

from agentos import __version__
from agentos.enforcement_attestation import attest_enforcement
from agentos.policy import load_policy, validate_policy
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.windows_restricted_attestation import (
    attest_windows_restricted_execution,
)

ROOT = Path(__file__).resolve().parents[2]


def test_v0294_release_identity_and_schema():
    current = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 5)
    assert __version__ == current
    assert CURRENT_SCHEMA_VERSION >= 62
    metadata = json.loads((ROOT / '.agents/distribution/metadata.json').read_text(encoding='utf-8'))
    assert metadata['agentos_version'] == current
    assert metadata["schema_version"] == CURRENT_SCHEMA_VERSION

def test_v0294_activation_policy_is_bounded():
    policy = load_policy(ROOT)
    validate_policy(policy)
    assert tuple(int(part) for part in policy["version"].split(".")) >= (0, 29, 5)
    current_release_name = policy["documentation_policy"]["current_release_name"]
    assert isinstance(current_release_name, str)
    assert current_release_name.strip()
    assert policy["documentation_policy"]["current_schema"] == CURRENT_SCHEMA_VERSION
    item = policy['windows_restricted_execution_policy']
    assert item['enabled'] is True
    assert item['scope'] == 'agentos_mediated_process_execution'
    assert item['release_focus'] == 'windows_restricted_execution'
    assert item['restricted_token_attested'] is True
    assert item['activation_complete'] is True
    assert item['activation_version'] == '0.29.4'
    assert item['release_activation_deferred_until_phase6'] is False
    for key in ('low_integrity_attested', 'desktop_isolation_attested', 'host_filesystem_isolation_attested', 'os_write_confinement_attested', 'same_user_host_bypass_resistance_claimed'):
        assert item[key] is False
    predecessor = policy['sandbox_workspace_runtime_profile_policy']
    assert predecessor['restricted_token_attested'] is False
    assert predecessor['credential_isolation_attested'] is False

def test_v0294_restricted_attestation_is_policy_activated():
    report = attest_windows_restricted_execution(ROOT)
    assert report["scope"] == "agentos_mediated_process_execution"

    for key in (
        "structurally_attested",
        "sync_enforced",
        "async_enforced",
        "source_token_verified",
        "child_token_verified",
        "assignment_before_resume",
        "fail_closed",
        "unrestricted_fallback_forbidden",
        "sandbox_inert_forbidden",
        "privilege_allowlist_enforced",
        "windows_ci_covered",
        "broad_nonclaims_preserved",
        "policy_declared_attested",
        "restricted_token_attested",
    ):
        assert report[key] is True, key

    assert report["low_integrity_attested"] is False


def test_v0294_global_attestation_embeds_scoped_activation():
    report = attest_enforcement(ROOT)
    assert report["ok"], report["findings"]

    item = report["windows_restricted_execution"]
    assert item["structurally_attested"] is True
    assert item["policy_declared_attested"] is True
    assert item["restricted_token_attested"] is True

    # Keep the legacy/global projection conservative: the v0.29.4 claim is
    # scoped, not a claim of general OS isolation.
    nonclaims = report["non_claims"]
    assert nonclaims["restricted_token_attested"] is False
    assert nonclaims["low_integrity_attested"] is False
    assert nonclaims["host_filesystem_isolation_attested"] is False
    assert nonclaims["os_write_confinement_attested"] is False
    assert nonclaims["same_user_host_bypass_resistance"] is False


def test_v0294_windows_ci_includes_activation_suite():
    workflow = (
        ROOT / ".github/workflows/agentos-release-validation.yml"
    ).read_text(encoding="utf-8")
    assert "Windows restricted execution v0.29.4" in workflow
    assert "test_windows_restricted_activation_v0294.py" in workflow

def test_v0294_release_documents_preserve_predecessor_contract_under_v0295():
    notes = (
        ROOT
        / "RELEASE_NOTES.md"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "v0.29.5 — Native Physical Isolation Extensions"
        in notes
    )
    assert (
        "v0.29.4 Restricted Token"
        in notes
    )
    assert (
        "restricted_token_attested = true"
        in notes
    )
    assert (
        "low_integrity_attested = true"
        in notes
    )
    assert (
        "host_filesystem_isolation_attested = false"
        in notes
    )

    for rel in (
        "README.md",
        "README.vi.md",
        "README.en.md",
    ):
        text = (
            ROOT
            / rel
        ).read_text(
            encoding="utf-8"
        )

        assert "v0.29.5" in text
        assert (
            "Native Physical Isolation Extensions"
            in text
        )

    # Historical v0.29.4 node documentation remains the authoritative
    # predecessor contract: Restricted Token was attested there; Low
    # Integrity belongs to the successor physical-isolation policy.
    node = (
        ROOT
        / ".agents/docs/WINDOWS_RESTRICTED_EXECUTION_V0294.md"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "restricted_token_attested = true"
        in node
    )
    assert (
        "low_integrity_attested = false"
        in node
    )
