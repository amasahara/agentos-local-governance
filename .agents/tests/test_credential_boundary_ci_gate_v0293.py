from __future__ import annotations

from pathlib import Path

from agentos.release_integrity import (
    _credential_boundary_ci_contract_v0293,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0293_credential_boundary_ci_contract_is_green():
    report = (
        _credential_boundary_ci_contract_v0293(
            ROOT
        )
    )

    assert report["ok"], report[
        "missing_markers"
    ]
    assert report["ubuntu_focused_suite"] is True
    assert report["windows_focused_suite"] is True
    assert report["v0291_containment_regression"] is True
    assert report["v0292_sandbox_regression"] is True
    assert report["full_regression_suite"] is True
