from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agentos.policy import load_release_policy, validate_policy
from agentos.release_integrity import (
    CORE_FILES,
    DOC_FILES,
    RELEASE_FILES,
    _windows_sandbox_ci_contract_v0292,
)


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/agentos-release-validation.yml"


def test_v0292_windows_sandbox_ci_contract_is_configured():
    report = _windows_sandbox_ci_contract_v0292(ROOT)

    assert report["ok"], report
    assert report["runner"] == "windows-latest"
    assert report["v0291_containment_regression"] is True
    assert report["focused_runtime_profile_suite"] is True
    assert report["activation_suite"] is True
    assert report["full_regression_suite"] is True
    assert report["missing_markers"] == []


def test_v0292_windows_ci_preserves_v0291_containment_activation():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "validate-windows:" in text
    assert "runs-on: windows-latest" in text
    assert "test_windows_process_tree_activation_v0291.py" in text


def test_v0292_windows_ci_runs_complete_runtime_profile_and_activation_suite():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "Windows sandbox workspace and runtime profiles" in text

    for marker in (
        "test_tool_runtime_profiles_v0292.py",
        "test_sync_tool_runtime_profiles_v0292.py",
        "test_async_tool_runtime_profiles_v0292.py",
        "test_async_sandbox_lifecycle_v0292.py",
        "test_sandbox_runtime_attestation_v0292.py",
        "test_windows_sandbox_activation_v0292.py",
    ):
        assert marker in text

    assert "python -m pytest -q .agents/tests -rs" in text


def test_v0292_ci_policy_and_attestation_are_activated():
    policy = load_release_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]

    assert policy["version"] == "0.29.2"
    assert section["windows_ci_required"] is True
    assert section["windows_ci_runner"] == "windows-latest"
    assert section["windows_ci_runtime_profile_suite_required"] is True
    assert (
        section["windows_ci_v0291_containment_regression_required"]
        is True
    )
    assert section["windows_ci_full_regression_required"] is True
    assert section["windows_ci_activation_suite_required"] is True
    assert section["runtime_profile_sandbox_attested"] is True


def test_v0292_active_policy_rejects_disabled_ci_contract():
    policy = copy.deepcopy(load_release_policy(ROOT))
    validate_policy(policy)

    for key in (
        "windows_ci_required",
        "windows_ci_runtime_profile_suite_required",
        "windows_ci_v0291_containment_regression_required",
        "windows_ci_full_regression_required",
        "windows_ci_activation_suite_required",
    ):
        candidate = copy.deepcopy(policy)
        candidate["sandbox_workspace_runtime_profile_policy"][key] = False

        with pytest.raises(RuntimeError):
            validate_policy(candidate)

    bad_runner = copy.deepcopy(policy)
    bad_runner["sandbox_workspace_runtime_profile_policy"][
        "windows_ci_runner"
    ] = "ubuntu-latest"

    with pytest.raises(RuntimeError):
        validate_policy(bad_runner)


def test_v0292_release_integrity_source_has_activation_gates():
    source = (
        ROOT / ".agents/agentos/release_integrity.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "_windows_sandbox_ci_contract_v0292",
        "test_windows_sandbox_activation_v0292.py",
        "windows_sandbox_ci_validation_missing",
        "sandbox_runtime_profile_attestation_failed",
        "sandbox_runtime_profile_policy_not_activated",
        "sandbox_runtime_profile_scope_mismatch",
        "sandbox_runtime_profile_overclaim",
        ">= (0, 29, 2)",
    ):
        assert marker in source


def test_v0292_release_inventory_covers_runtime_profile_activation_artifacts():
    assert ".agents/agentos/tool_runtime_profiles.py" in CORE_FILES

    for rel in (
        ".agents/tests/test_tool_runtime_profiles_v0292.py",
        ".agents/tests/test_sync_tool_runtime_profiles_v0292.py",
        ".agents/tests/test_async_tool_runtime_profiles_v0292.py",
        ".agents/tests/test_async_sandbox_lifecycle_v0292.py",
        ".agents/tests/test_sandbox_runtime_attestation_v0292.py",
        ".agents/tests/test_windows_sandbox_ci_gate_v0292.py",
        ".agents/tests/test_windows_sandbox_activation_v0292.py",
    ):
        assert rel in RELEASE_FILES

    assert (
        ".agents/docs/WINDOWS_SANDBOX_WORKSPACE_TOOL_RUNTIME_PROFILES_V0292.md"
        in DOC_FILES
    )
