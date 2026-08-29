from __future__ import annotations

import json
from pathlib import Path

from agentos.enforcement_attestation import attest_enforcement
from agentos.release_integrity import check_release_integrity

ROOT = Path(__file__).resolve().parents[2]


def test_v0291_process_tree_attestation_structurally_green():
    report = attest_enforcement(ROOT)
    assert report["ok"], report["findings"]

    containment = report["windows_process_tree_containment"]
    for key in (
        "structurally_attested",
        "sync_enforced",
        "async_enforced",
        "assignment_before_resume",
        "timeout_tree_termination",
        "cancellation_tree_termination",
        "broker_fail_closed",
        "completion_evidence_bound",
        "broad_nonclaims_preserved",
        "windows_only",
    ):
        assert containment[key] is True, key

    assert containment["policy_scope"] == "agentos_mediated_process_execution"


def test_v0291_process_tree_policy_is_release_activated():
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

    assert item["enabled"] is True
    assert item["database_schema"] == 62
    assert item["scope"] == "agentos_mediated_process_execution"
    assert item["windows_only"] is True
    assert item["job_objects_required_on_windows"] is True
    assert item["root_created_suspended"] is True
    assert item["assignment_before_resume_required"] is True
    assert item["synchronous_exec_enforced"] is True
    assert item["async_job_enforced"] is True
    assert item["timeout_terminates_tree"] is True
    assert item["cancellation_terminates_tree"] is True
    assert item["broker_failure_terminates_tree"] is True
    assert item["completion_receipt_required"] is True
    assert item["windows_ci_required"] is True
    assert item["windows_ci_runner"] == "windows-latest"
    assert item["process_tree_containment_attested"] is True
    assert item["same_user_host_bypass_resistance_claimed"] is False
    assert item["general_os_process_isolation_attested"] is False
    assert item["arbitrary_host_process_containment_attested"] is False


def test_v0291_process_tree_release_integrity_is_activated():
    report = check_release_integrity(ROOT)
    assert report["ok"], report["findings"]

    containment = report[
        "enforcement_attestation"
    ][
        "windows_process_tree_containment"
    ]
    assert containment["structurally_attested"] is True
    assert containment["policy_declared_attested"] is True
    assert (
        containment["policy_scope"]
        == "agentos_mediated_process_execution"
    )


def test_v0291_release_integrity_contains_activation_gate():
    source = (ROOT / ".agents/agentos/release_integrity.py").read_text(
        encoding="utf-8"
    )
    assert "attested_release_version >= (0, 29, 1)" in source
    assert "windows_process_tree_policy_not_activated" in source
    assert "windows_process_tree_containment_policy" in source


def test_v0291_existing_broad_nonclaims_remain_false():
    non_claims = attest_enforcement(ROOT)["non_claims"]
    assert non_claims["same_user_host_bypass_resistance"] is False
    assert non_claims["os_level_process_isolation_attested"] is False
    assert non_claims["arbitrary_host_process_containment"] is False
