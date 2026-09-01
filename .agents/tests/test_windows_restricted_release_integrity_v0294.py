
from __future__ import annotations

from pathlib import Path

from agentos.release_integrity import (
    CORE_FILES,
    DOC_FILES,
    RELEASE_FILES,
    check_release_integrity,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0294_release_integrity_inventory_contains_restricted_execution_assets():
    for rel in (
        ".agents/agentos/windows_restricted_execution.py",
        ".agents/agentos/windows_restricted_attestation.py",
    ):
        assert rel in CORE_FILES

    for rel in (
        ".agents/tests/test_windows_restricted_execution_v0294.py",
        ".agents/tests/test_windows_restricted_sync_v0294.py",
        ".agents/tests/test_windows_restricted_async_v0294.py",
        ".agents/tests/test_windows_restricted_fail_closed_v0294.py",
        ".agents/tests/test_windows_restricted_attestation_v0294.py",
        ".agents/tests/test_windows_restricted_ci_gate_v0294.py",
        ".agents/tests/test_windows_restricted_activation_v0294.py",
        ".agents/tests/test_successor_policy_activation_v0294.py",
        ".agents/tests/test_windows_restricted_release_integrity_v0294.py",
        ".agents/docs/WINDOWS_RESTRICTED_EXECUTION_V0294.md",
    ):
        assert rel in RELEASE_FILES

    assert (
        ".agents/docs/WINDOWS_RESTRICTED_EXECUTION_V0294.md"
        in DOC_FILES
    )


def test_v0294_release_integrity_source_has_scoped_activation_gate():
    source = (
        ROOT
        / ".agents/agentos/release_integrity.py"
    ).read_text(
        encoding="utf-8"
    )

    for marker in (
        'required_policy_sections.add("windows_restricted_execution_policy")',
        "windows_restricted_execution_attestation_failed",
        "windows_restricted_execution_scope_invalid",
        "windows_restricted_execution_activation_flags_invalid",
        "windows_restricted_execution_global_overclaim",
        '"windows_restricted_execution": attestation_report.get(',
    ):
        assert marker in source


def test_v0294_release_integrity_is_green_after_generated_artifact_rebuild():
    report = check_release_integrity(
        ROOT
    )
    assert report["ok"], report[
        "findings"
    ]

    restricted = (
        report[
            "enforcement_attestation"
        ][
            "windows_restricted_execution"
        ]
    )

    assert restricted[
        "structurally_attested"
    ] is True
    assert restricted[
        "policy_declared_attested"
    ] is True
    assert restricted[
        "restricted_token_attested"
    ] is True
    assert restricted[
        "low_integrity_attested"
    ] is False
