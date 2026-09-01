
from __future__ import annotations

from pathlib import Path

from agentos.windows_restricted_attestation import (
    attest_windows_restricted_execution,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0294_phase5_windows_ci_contract_is_complete():
    report = (
        attest_windows_restricted_execution(
            ROOT
        )
    )

    ci = report[
        "windows_ci"
    ]

    assert ci["ok"], ci[
        "missing_markers"
    ]
    assert (
        ci["runner"]
        == "windows-latest"
    )
    assert (
        ci["focused_suite"]
        is True
    )
    assert (
        ci[
            "full_regression_suite"
        ]
        is True
    )


def test_v0294_phase5_windows_ci_has_all_restricted_execution_tests():
    text = (
        ROOT
        / ".github/workflows/agentos-release-validation.yml"
    ).read_text(
        encoding="utf-8"
    )

    start = text.index(
        "- name: Windows restricted execution v0.29.4"
    )
    end = text.index(
        "\n      - name:",
        start + 1,
    )
    step = text[
        start:end
    ]

    for test in (
        "test_windows_restricted_execution_v0294.py",
        "test_windows_restricted_sync_v0294.py",
        "test_windows_restricted_async_v0294.py",
        "test_windows_restricted_fail_closed_v0294.py",
        "test_windows_restricted_attestation_v0294.py",
        "test_windows_restricted_ci_gate_v0294.py",
        'test_windows_restricted_activation_v0294.py',
        'test_successor_policy_activation_v0294.py',
        'test_windows_restricted_release_integrity_v0294.py',
    ):
        assert test in step
