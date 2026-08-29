from __future__ import annotations

import json
from pathlib import Path

from agentos.release_integrity import (
    _windows_ci_contract,
)


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (
    ROOT
    / ".github/workflows/agentos-release-validation.yml"
)


def test_v0291_windows_ci_contract_is_configured():
    report = _windows_ci_contract(ROOT)

    assert report["ok"], report
    assert report["runner"] == "windows-latest"
    assert report["focused_containment_suite"] is True
    assert report["full_regression_suite"] is True
    assert report["missing_markers"] == []


def test_v0291_windows_ci_workflow_has_separate_windows_job():
    text = WORKFLOW.read_text(
        encoding="utf-8"
    )

    assert "validate:" in text
    assert "runs-on: ubuntu-latest" in text

    assert "validate-windows:" in text
    assert "runs-on: windows-latest" in text

    assert (
        text.index("validate-windows:")
        > text.index("validate:")
    )


def test_v0291_windows_ci_runs_containment_and_full_regression():
    text = WORKFLOW.read_text(
        encoding="utf-8"
    )

    for marker in (
        "test_windows_process_tree_v0291.py",
        "test_windows_process_exec_containment_v0291.py",
        "test_windows_job_broker_v0291.py",
        "test_windows_async_job_containment_v0291.py",
        "test_windows_async_timeout_v0291.py",
        "test_windows_process_tree_attestation_v0291.py",
        "python -m pytest -q .agents/tests -rs",
    ):
        assert marker in text


def test_v0291_windows_ci_policy_is_required_and_release_activated():
    policy = json.loads(
        (
            ROOT
            / ".agents/config/release_policy.json"
        ).read_text(
            encoding="utf-8"
        )
    )
    item = policy[
        "windows_process_tree_containment_policy"
    ]

    assert item["windows_ci_required"] is True
    assert item["windows_ci_runner"] == "windows-latest"
    assert item["windows_ci_containment_suite_required"] is True
    assert item["windows_ci_full_regression_required"] is True
    assert item["process_tree_containment_attested"] is True


def test_v0291_release_integrity_has_windows_ci_activation_gate():
    source = (
        ROOT
        / ".agents/agentos/release_integrity.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "windows_ci_validation_missing"
        in source
    )
    assert (
        "attested_release_version"
        in source
    )
    assert (
        ">= (0, 29, 1)"
        in source
    )
