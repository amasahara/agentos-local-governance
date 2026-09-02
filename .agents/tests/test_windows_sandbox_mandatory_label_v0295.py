
from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentos.tool_runtime_profiles import (
    cleanup_sandbox_workspace,
    create_sandbox_workspace,
)
from agentos.windows_physical_isolation import (
    CONTAINER_INHERIT_ACE,
    DESCRIPTOR,
    LABEL_SECURITY_INFORMATION,
    LOW_DIRECTORY_LABEL_SDDL,
    LOW_FILE_LABEL_SDDL,
    LOW_INTEGRITY_SID,
    OBJECT_INHERIT_ACE,
    SECURITY_MANDATORY_LOW_RID,
    SECURITY_MANDATORY_MEDIUM_RID,
    SYSTEM_MANDATORY_LABEL_ACE_TYPE,
    SYSTEM_MANDATORY_LABEL_NO_WRITE_UP,
    WindowsPhysicalIsolationUnavailable,
    apply_low_integrity_sandbox_boundary,
    inspect_path_mandatory_label,
    verify_low_mandatory_label,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0295_phase2_mandatory_label_constants_are_exact():
    assert LABEL_SECURITY_INFORMATION == 0x00000010
    assert SYSTEM_MANDATORY_LABEL_ACE_TYPE == 0x11
    assert SYSTEM_MANDATORY_LABEL_NO_WRITE_UP == 0x00000001
    assert OBJECT_INHERIT_ACE == 0x01
    assert CONTAINER_INHERIT_ACE == 0x02
    assert SECURITY_MANDATORY_LOW_RID == 0x00001000
    assert SECURITY_MANDATORY_MEDIUM_RID == 0x00002000
    assert LOW_INTEGRITY_SID == "S-1-16-4096"
    assert LOW_DIRECTORY_LABEL_SDDL == "S:(ML;OICI;NW;;;LW)"
    assert LOW_FILE_LABEL_SDDL == "S:(ML;;NW;;;LW)"



def test_v0295_phase2_descriptor_progresses_to_async_low_integrity():
    assert DESCRIPTOR.sandbox_mandatory_label_enforced is True
    assert DESCRIPTOR.sync_execution_enforced is True
    assert DESCRIPTOR.async_execution_enforced is True
    assert DESCRIPTOR.low_integrity_attested is True

@pytest.mark.skipif(
    os.name == "nt",
    reason="non-Windows fail-closed contract",
)
def test_v0295_phase2_non_windows_label_primitive_fails_closed(
    tmp_path,
):
    with pytest.raises(
        WindowsPhysicalIsolationUnavailable,
    ):
        apply_low_integrity_sandbox_boundary(
            tmp_path
        )


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows mandatory-label live probe",
)
def test_v0295_phase2_live_low_label_applies_to_existing_tree(
    tmp_path,
):
    root = tmp_path / "sandbox-label-probe"
    nested = root / "workspace" / "nested"
    nested.mkdir(parents=True)

    payload = nested / "payload.txt"
    payload.write_text(
        "phase2",
        encoding="utf-8",
    )

    boundary = (
        apply_low_integrity_sandbox_boundary(
            root
        )
    )

    assert boundary.low_integrity is True
    assert boundary.no_write_up is True
    assert (
        boundary.labeled_path_count
        == boundary.verified_path_count
    )
    assert boundary.labeled_path_count >= 4

    for path in (
        root,
        root / "workspace",
        nested,
        payload,
    ):
        evidence = verify_low_mandatory_label(
            path
        )
        assert evidence.sid == LOW_INTEGRITY_SID
        assert evidence.rid == SECURITY_MANDATORY_LOW_RID
        assert evidence.no_write_up is True


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows sandbox integration live probe",
)
def test_v0295_phase2_create_sandbox_workspace_returns_verified_low_boundary(
    tmp_path,
):
    primary = tmp_path / "primary"
    source = primary / "source"
    source.mkdir(parents=True)

    (
        source / "input.txt"
    ).write_text(
        "hello",
        encoding="utf-8",
    )

    sandbox = create_sandbox_workspace(
        primary_root=primary,
        source_root=source,
        task_id="T1",
        session_id="phase2",
        execution_id="E1",
        command_profile="test",
    )

    try:
        assert (
            sandbox[
                "mandatory_integrity_label"
            ]
            == "low"
        )
        assert (
            sandbox[
                "mandatory_integrity_sid"
            ]
            == LOW_INTEGRITY_SID
        )
        assert (
            sandbox[
                "mandatory_integrity_rid"
            ]
            == SECURITY_MANDATORY_LOW_RID
        )
        assert (
            sandbox[
                "mandatory_integrity_no_write_up"
            ]
            is True
        )

        for key in (
            "root",
            "workspace",
            "home",
            "temp",
            "cache",
            "logs",
        ):
            evidence = (
                verify_low_mandatory_label(
                    Path(
                        sandbox[key]
                    )
                )
            )
            assert evidence.low_integrity is True
            assert evidence.no_write_up is True

        copied = (
            Path(
                sandbox["workspace"]
            )
            / "input.txt"
        )
        assert (
            verify_low_mandatory_label(
                copied
            ).low_integrity
            is True
        )

        primary_evidence = (
            inspect_path_mandatory_label(
                primary
            )
        )
        assert (
            primary_evidence.rid
            >= SECURITY_MANDATORY_MEDIUM_RID
        )
        assert primary_evidence.low_integrity is False
    finally:
        cleanup_sandbox_workspace(
            primary,
            Path(
                sandbox["root"]
            ),
        )


def test_v0295_phase2_release_identity_and_schema_v0295():
    assert (ROOT / 'VERSION').read_text(encoding='utf-8').strip() == '0.29.5'
    from agentos import __version__
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    assert __version__ == '0.29.5'
    assert CURRENT_SCHEMA_VERSION == 62
