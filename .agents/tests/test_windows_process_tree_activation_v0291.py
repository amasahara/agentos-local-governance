from __future__ import annotations

import json
from pathlib import Path

from agentos import __version__
from agentos.enforcement_attestation import attest_enforcement
from agentos.release_integrity import (
    _windows_ci_contract,
    check_release_integrity,
)
from agentos.schema_version import CURRENT_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_v0291_release_identity_and_schema():
    version = (
        ROOT
        / "VERSION"
    ).read_text(
        encoding="utf-8"
    ).strip()

    assert version == "0.29.1"
    assert __version__ == "0.29.1"
    assert CURRENT_SCHEMA_VERSION == 62


def test_v0291_release_policy_activation_is_bounded():
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

    assert item["process_tree_containment_attested"] is True
    assert item["scope"] == "agentos_mediated_process_execution"
    assert item["windows_only"] is True
    assert item["same_user_host_bypass_resistance_claimed"] is False
    assert item["general_os_process_isolation_attested"] is False
    assert item["arbitrary_host_process_containment_attested"] is False


def test_v0291_enforcement_attestation_is_release_ready():
    report = attest_enforcement(ROOT)
    assert report["ok"], report["findings"]

    item = report[
        "windows_process_tree_containment"
    ]
    assert item["structurally_attested"] is True
    assert item["policy_declared_attested"] is True
    assert item["sync_enforced"] is True
    assert item["async_enforced"] is True
    assert item["assignment_before_resume"] is True
    assert item["timeout_tree_termination"] is True
    assert item["cancellation_tree_termination"] is True
    assert item["broker_fail_closed"] is True
    assert item["completion_evidence_bound"] is True
    assert item["broad_nonclaims_preserved"] is True


def test_v0291_windows_ci_activation_contract_is_complete():
    report = _windows_ci_contract(ROOT)
    assert report["ok"], report
    assert report["runner"] == "windows-latest"
    assert report["focused_containment_suite"] is True
    assert report["activation_suite"] is True
    assert report["full_regression_suite"] is True


def test_v0291_release_integrity_is_green_after_artifact_rebuild():
    report = check_release_integrity(ROOT)
    assert report["ok"], report["findings"]
    assert report["version"] == "0.29.1"
    assert report["schema"] == 62

    attestation = report[
        "enforcement_attestation"
    ]
    assert (
        attestation[
            "windows_process_tree_containment"
        ][
            "policy_declared_attested"
        ]
        is True
    )
    assert (
        attestation[
            "windows_ci_validation"
        ][
            "ok"
        ]
        is True
    )
