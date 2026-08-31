from __future__ import annotations

import json
from pathlib import Path

from agentos import __version__
from agentos.enforcement_attestation import attest_enforcement
from agentos.release_integrity import _windows_sandbox_ci_contract_v0292
from agentos.schema_version import CURRENT_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_v0292_schema_and_distribution_invariants_are_preserved():
    current = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert current == __version__
    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 2)
    assert CURRENT_SCHEMA_VERSION == 62
    metadata = json.loads((ROOT / ".agents/distribution/metadata.json").read_text(encoding="utf-8"))
    assert metadata["agentos_version"] == current
    assert metadata["schema_version"] == 62

def test_v0292_release_policy_guarantees_are_preserved():
    policy = json.loads((ROOT / ".agents/config/release_policy.json").read_text(encoding="utf-8"))
    assert tuple(int(part) for part in policy["version"].split(".")) >= (0, 29, 2)
    item = policy["sandbox_workspace_runtime_profile_policy"]
    assert item["runtime_profile_sandbox_attested"] is True
    assert item["scope"] == "agentos_mediated_process_execution"
    assert item["windows_ci_required"] is True
    assert item["windows_ci_runner"] == "windows-latest"
    assert item["windows_ci_activation_suite_required"] is True
    for key in ("credential_isolation_attested","restricted_token_attested","low_integrity_attested","host_filesystem_isolation_attested","os_write_confinement_attested","same_user_host_bypass_resistance_claimed"):
        assert item[key] is False

def test_v0292_structural_attestation_is_release_ready():
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


def test_v0292_windows_ci_activation_contract_is_complete():
    report = _windows_sandbox_ci_contract_v0292(ROOT)

    assert report["ok"], report
    assert report["runner"] == "windows-latest"
    assert report["v0291_containment_regression"] is True
    assert report["focused_runtime_profile_suite"] is True
    assert report["activation_suite"] is True
    assert report["full_regression_suite"] is True
    assert report["missing_markers"] == []


def test_v0292_release_docs_are_preserved_as_historical_contract():
    historical = (ROOT / ".agents/docs/WINDOWS_SANDBOX_WORKSPACE_TOOL_RUNTIME_PROFILES_V0292.md").read_text(encoding="utf-8")
    assert "v0.29.2" in historical
    assert "Windows Sandbox Workspace & Tool Runtime Profiles" in historical
    for marker in ("runtime_profile_sandbox_attested = true","restricted_token_attested = false","low_integrity_attested = false","same_user_host_bypass_resistance_claimed = false"):
        assert marker in historical
    history = (ROOT / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v0.29.2 — Windows Sandbox Workspace & Tool Runtime Profiles" in history
    current_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "v0.29.3" in current_notes
    assert "Sandbox Configuration & Credential Boundary" in current_notes

def test_v0292_generated_release_artifacts_are_deferred_to_finalization():
    # Phase 6 activates authoritative source identity only. MANIFEST,
    # CHECKSUMS, package completeness, and generated governance are rebuilt
    # in the final release gate and are intentionally not made green here.
    source = (
        ROOT / ".agents/agentos/release_coherence.py"
    ).read_text(encoding="utf-8")

    for marker in (
        'repo / "MANIFEST.json"',
        'repo / "PACKAGE_COMPLETENESS.json"',
        "manifest_release_mismatch",
        "package_release_mismatch",
    ):
        assert marker in source
