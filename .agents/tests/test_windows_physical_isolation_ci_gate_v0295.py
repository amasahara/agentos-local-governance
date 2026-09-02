from __future__ import annotations

from pathlib import Path

from agentos.windows_physical_isolation_attestation import (
    attest_windows_physical_isolation,
)


ROOT = Path(
    __file__
).resolve().parents[2]


def test_v0295_phase5_windows_ci_contract_is_complete():
    report = (
        attest_windows_physical_isolation(
            ROOT
        )
    )

    ci = report[
        "windows_ci"
    ]

    assert (
        ci[
            "ok"
        ]
    ), ci[
        "missing_markers"
    ]

    assert (
        ci[
            "runner"
        ]
        == "windows-latest"
    )
    assert (
        ci[
            "focused_suite"
        ]
        is True
    )
    assert (
        ci[
            "full_regression_suite"
        ]
        is True
    )


def test_v0295_phase5_windows_ci_has_complete_physical_isolation_suite():
    text = (ROOT / '.github/workflows/agentos-release-validation.yml').read_text(encoding='utf-8')
    start = text.index('- name: Windows physical isolation v0.29.5')
    end = text.index('\n      - name:', start + 1)
    step = text[start:end]
    for test in ('test_windows_low_integrity_primitives_v0295.py', 'test_windows_sandbox_mandatory_label_v0295.py', 'test_windows_sandbox_dacl_access_v0295.py', 'test_windows_low_integrity_sync_v0295.py', 'test_windows_low_integrity_async_v0295.py', 'test_windows_physical_isolation_attestation_v0295.py', 'test_windows_physical_isolation_ci_gate_v0295.py', 'test_windows_physical_isolation_activation_v0295.py', 'test_windows_physical_isolation_release_integrity_v0295.py'):
        assert test in step
