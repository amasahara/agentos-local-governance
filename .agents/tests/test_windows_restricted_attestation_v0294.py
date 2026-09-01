
from __future__ import annotations

from pathlib import Path

from agentos.enforcement_attestation import (
    attest_enforcement,
)
from agentos.windows_restricted_attestation import (
    ATTESTATION_SCOPE,
    attest_windows_restricted_execution,
)


ROOT = Path(__file__).resolve().parents[2]



def test_v0294_phase5_structural_readiness_progresses_to_release_activation():
    report = attest_windows_restricted_execution(ROOT)

    assert (
        report["scope"]
        == ATTESTATION_SCOPE
        == "agentos_mediated_process_execution"
    )

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


def test_v0294_phase5_enforcement_attestation_embeds_activated_restricted_report():
    report = attest_enforcement(ROOT)
    assert report["ok"], report["findings"]

    restricted = report["windows_restricted_execution"]

    for key in (
        "structurally_attested",
        "sync_enforced",
        "async_enforced",
        "windows_ci_covered",
        "policy_declared_attested",
        "restricted_token_attested",
    ):
        assert restricted[key] is True, key

    for name, value in restricted["checks"].items():
        assert value is True, name

def test_v0294_phase5_global_nonclaims_remain_narrow():
    report = attest_enforcement(
        ROOT
    )

    nonclaims = report[
        "non_claims"
    ]

    assert nonclaims[
        "restricted_token_attested"
    ] is False
    assert nonclaims[
        "low_integrity_attested"
    ] is False
    assert nonclaims[
        "host_filesystem_isolation_attested"
    ] is False
    assert nonclaims[
        "os_write_confinement_attested"
    ] is False
    assert nonclaims[
        "same_user_host_bypass_resistance"
    ] is False
