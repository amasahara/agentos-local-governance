
from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentos.tool_runtime_profiles import (
    cleanup_sandbox_workspace,
    create_sandbox_workspace,
)
from agentos.windows_physical_isolation import (
    SANDBOX_ANCESTRY_TRAVERSE_MASK,
    SANDBOX_CURRENT_USER_ACCESS_MASK,
    _sandbox_controlled_ancestry,
    verify_current_user_access_ace,
)


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows Restricted/LUA DACL live probe",
)
def test_v0295_phase3_sandbox_has_current_user_dacl_for_restricted_token(
    tmp_path,
):
    primary = (
        tmp_path
        / "primary"
    )
    source = (
        primary
        / "source"
    )
    source.mkdir(
        parents=True
    )

    (
        source
        / "input.py"
    ).write_text(
        "print('ok')\n",
        encoding="utf-8",
        newline="\n",
    )

    sandbox = (
        create_sandbox_workspace(
            primary_root=primary,
            source_root=source,
            task_id="dacl",
            session_id="restricted",
            execution_id="E1",
            command_profile="test",
        )
    )

    try:
        root = Path(
            sandbox[
                "root"
            ]
        )

        ancestry = (
            _sandbox_controlled_ancestry(
                root
            )
        )

        assert ancestry

        for directory in ancestry:
            assert (
                verify_current_user_access_ace(
                    directory,
                    SANDBOX_ANCESTRY_TRAVERSE_MASK,
                )
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
            assert (
                verify_current_user_access_ace(
                    Path(
                        sandbox[
                            key
                        ]
                    ),
                    SANDBOX_CURRENT_USER_ACCESS_MASK,
                )
                is True
            )

        assert (
            verify_current_user_access_ace(
                Path(
                    sandbox[
                        "workspace"
                    ]
                )
                / "input.py",
                SANDBOX_CURRENT_USER_ACCESS_MASK,
            )
            is True
        )

    finally:
        cleanup_sandbox_workspace(
            primary,
            Path(
                sandbox[
                    "root"
                ]
            ),
        )


def test_v0295_phase3_dacl_contract_does_not_grant_security_descriptor_control():
    from agentos.windows_physical_isolation import (
        SANDBOX_CURRENT_USER_ACCESS_MASK,
    )

    WRITE_DAC = 0x00040000
    WRITE_OWNER = 0x00080000
    ACCESS_SYSTEM_SECURITY = 0x01000000

    assert (
        SANDBOX_CURRENT_USER_ACCESS_MASK
        & WRITE_DAC
    ) == 0

    assert (
        SANDBOX_CURRENT_USER_ACCESS_MASK
        & WRITE_OWNER
    ) == 0

    assert (
        SANDBOX_CURRENT_USER_ACCESS_MASK
        & ACCESS_SYSTEM_SECURITY
    ) == 0

@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows generic-vs-production ancestry contract",
)
def test_v0295_phase3_generic_boundary_is_root_local_without_controlled_ancestry(
    tmp_path,
):
    from agentos.windows_physical_isolation import (
        apply_low_integrity_sandbox_boundary,
    )

    root = tmp_path / "generic-boundary"
    root.mkdir()

    boundary = apply_low_integrity_sandbox_boundary(
        root
    )

    assert boundary.current_user_access_verified is True
    assert (
        boundary.ancestry_traverse_verified_count
        == 0
    )
    assert boundary.low_integrity is True
    assert boundary.no_write_up is True


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows strict production ancestry contract",
)
def test_v0295_phase3_strict_boundary_requires_agentos_controlled_ancestry(
    tmp_path,
):
    from agentos.windows_physical_isolation import (
        WindowsPhysicalIsolationError,
        apply_low_integrity_sandbox_boundary,
    )

    root = tmp_path / "not-agentos-owned"
    root.mkdir()

    with pytest.raises(
        WindowsPhysicalIsolationError,
        match="sandbox_controlled_ancestry_anchor_missing",
    ):
        apply_low_integrity_sandbox_boundary(
            root,
            require_controlled_ancestry=True,
        )
