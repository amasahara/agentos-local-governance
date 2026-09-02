from __future__ import annotations

from pathlib import Path

from agentos.release_integrity import (
    CORE_FILES,
    DOC_FILES,
    RELEASE_FILES,
    check_release_integrity,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0295_release_integrity_inventory_contains_physical_isolation_assets():
    for rel in (
        ".agents/agentos/windows_physical_isolation.py",
        ".agents/agentos/windows_physical_isolation_attestation.py",
    ):
        assert rel in CORE_FILES

    for rel in (
        ".agents/tests/test_windows_low_integrity_primitives_v0295.py",
        ".agents/tests/test_windows_sandbox_mandatory_label_v0295.py",
        ".agents/tests/test_windows_sandbox_dacl_access_v0295.py",
        ".agents/tests/test_windows_low_integrity_sync_v0295.py",
        ".agents/tests/test_windows_low_integrity_async_v0295.py",
        ".agents/tests/test_windows_physical_isolation_attestation_v0295.py",
        ".agents/tests/test_windows_physical_isolation_ci_gate_v0295.py",
        ".agents/tests/test_windows_physical_isolation_activation_v0295.py",
        ".agents/tests/test_windows_physical_isolation_release_integrity_v0295.py",
        ".agents/docs/WINDOWS_NATIVE_PHYSICAL_ISOLATION_V0295.md",
    ):
        assert rel in RELEASE_FILES

    assert (
        ".agents/docs/WINDOWS_NATIVE_PHYSICAL_ISOLATION_V0295.md"
        in DOC_FILES
    )


def test_v0295_release_integrity_source_has_scoped_physical_activation_gate():
    source = (
        ROOT / ".agents/agentos/release_integrity.py"
    ).read_text(encoding="utf-8")

    for marker in (
        'required_policy_sections.add("windows_physical_isolation_policy")',
        "windows_physical_isolation_attestation_failed",
        "windows_physical_isolation_scope_invalid",
        "windows_physical_isolation_activation_flags_invalid",
        "windows_physical_isolation_global_overclaim",
        '"windows_physical_isolation": attestation_report.get(',
    ):
        assert marker in source


def test_v0295_release_integrity_is_green_after_generated_artifact_rebuild():
    report = check_release_integrity(ROOT)

    assert report["ok"], report["findings"]

    physical = (
        report[
            "enforcement_attestation"
        ][
            "windows_physical_isolation"
        ]
    )

    assert physical["structurally_attested"] is True
    assert physical["policy_declared_attested"] is True
    assert physical["low_integrity_attested"] is True
    assert physical["sandbox_low_integrity_label_attested"] is True

    restricted = (
        report[
            "enforcement_attestation"
        ][
            "windows_restricted_execution"
        ]
    )

    assert restricted["restricted_token_attested"] is True
    assert restricted["low_integrity_attested"] is False
