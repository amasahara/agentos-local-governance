from __future__ import annotations

from pathlib import Path

from agentos.enforcement_attestation import (
    attest_enforcement,
)
from agentos.windows_physical_isolation_attestation import (
    ATTESTATION_SCOPE,
    attest_windows_physical_isolation,
)


ROOT = Path(
    __file__
).resolve().parents[2]


def test_v0295_phase5_physical_isolation_structural_attestation_is_green():
    report = attest_windows_physical_isolation(
        ROOT
    )

    assert (
        report[
            "scope"
        ]
        == ATTESTATION_SCOPE
        == "agentos_mediated_process_execution"
    )

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
        assert (
            report[
                key
            ]
            is True
        ), key

    assert (
        report[
            "release_activation_deferred"
        ]
        is False
    )

    for name, value in (
        report[
            "checks"
        ].items()
    ):
        assert (
            value
            is True
        ), name

def test_v0295_phase5_enforcement_attestation_embeds_activated_physical_report():
    report = attest_enforcement(
        ROOT
    )

    assert (
        report[
            "ok"
        ]
    ), report[
        "findings"
    ]

    physical = report[
        "windows_physical_isolation"
    ]

    assert (
        physical[
            "structurally_attested"
        ]
        is True
    )
    assert (
        physical[
            "sync_enforced"
        ]
        is True
    )
    assert (
        physical[
            "async_enforced"
        ]
        is True
    )
    assert (
        physical[
            "windows_ci_covered"
        ]
        is True
    )
    assert (
        physical[
            "release_activation_deferred"
        ]
        is False
    )
    assert (
        physical[
            "policy_declared_attested"
        ]
        is True
    )
    assert (
        physical[
            "low_integrity_attested"
        ]
        is True
    )
    assert (
        physical[
            "sandbox_low_integrity_label_attested"
        ]
        is True
    )

    for name, value in (
        physical[
            "checks"
        ].items()
    ):
        assert (
            value
            is True
        ), name

def test_v0295_phase5_global_nonclaims_remain_conservative():
    report = (
        attest_enforcement(
            ROOT
        )
    )

    nonclaims = (
        report[
            "non_claims"
        ]
    )

    assert (
        nonclaims[
            "low_integrity_attested"
        ]
        is False
    )
    assert (
        nonclaims[
            "host_filesystem_isolation_attested"
        ]
        is False
    )
    assert (
        nonclaims[
            "os_write_confinement_attested"
        ]
        is False
    )
    assert (
        nonclaims[
            "same_user_host_bypass_resistance"
        ]
        is False
    )
