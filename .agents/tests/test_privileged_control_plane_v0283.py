"""
File: .agents/tests/test_privileged_control_plane_v0283.py

Purpose:
    Protect v0.28.3 Privileged Control Plane Separation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from agentos.cli_runtime import (
    CONTROL_PLANE_COMMANDS,
    DUAL_PLANE_COMMANDS,
    agent_command_registry,
    privileged_command_registry,
)
from agentos.project_identity_cli import CURRENT_LAUNCHERS


ROOT = Path(__file__).resolve().parents[2]


def _agent(*args: str) -> list[str]:
    if os.name == "nt":
        return [
            os.environ.get("ComSpec", "cmd.exe"),
            "/d",
            "/c",
            str(ROOT / ".agents/bin/agentos.cmd"),
            *args,
        ]
    return [
        str(ROOT / ".agents/bin/agentos"),
        *args,
    ]


def _admin(*args: str) -> list[str]:
    if os.name == "nt":
        return [
            os.environ.get("ComSpec", "cmd.exe"),
            "/d",
            "/c",
            str(ROOT / ".agents/bin/agentos-admin.cmd"),
            *args,
        ]
    return [
        str(ROOT / ".agents/bin/agentos-admin"),
        *args,
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )


def test_registry_separation_is_explicit() -> None:
    agent = set(agent_command_registry())
    privileged = set(privileged_command_registry())

    assert CONTROL_PLANE_COMMANDS
    assert DUAL_PLANE_COMMANDS == {
        "project-adopt",
        "architecture-init",
    }

    assert (
        (agent & privileged) - set(DUAL_PLANE_COMMANDS)
    ) == set()

    assert "db-connection-register" not in agent
    assert "db-connection-register" in privileged

    assert "approve-task" not in agent
    assert "approve-task" in privileged

    assert "project-primary-select" not in agent
    assert "project-primary-select" in privileged

    assert "project-purpose-set" not in agent
    assert "project-purpose-set" in privileged

    assert "project-consolidation-review" not in agent
    assert "project-consolidation-review" in privileged

    assert "project-consolidation-approve" not in agent
    assert "project-consolidation-approve" in privileged

    assert "project-consolidation-rollback" not in agent
    assert "project-consolidation-rollback" in privileged


def test_bounded_execution_remains_agent_plane() -> None:
    agent = set(agent_command_registry())

    assert "db-boundary-authorize" in agent
    assert "policy-compile" in agent
    assert "project-consolidation-execute" in agent
    assert "project-consolidation-complete" in agent
    assert "skill-promote" in agent
    assert "skill-contract-set" in agent
    assert "proxy-execute" in agent


def test_agent_commands_list_does_not_leak_privileged_surface() -> None:
    cp = _run(_agent("commands-list"))

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)

    assert payload["plane"] == "agent"
    assert payload["count"] == len(agent_command_registry())

    commands = set(payload["commands"])

    assert "status" in commands
    assert "project-adopt" in commands

    assert "approve-task" not in commands
    assert "db-connection-register" not in commands
    assert "project-primary-select" not in commands


def test_project_adopt_scan_is_agent_accessible() -> None:
    cp = _run(
        _agent(
            "project-adopt",
            "--help",
        )
    )

    assert cp.returncode == 0


def test_project_adopt_apply_requires_admin_plane() -> None:
    cp = _run(
        _agent(
            "project-adopt",
            "--target",
            str(ROOT / ".agents/runtime/v0283-denied-adopt"),
            "--apply",
            "--human-confirmed",
        )
    )

    assert cp.returncode == 2
    assert (
        "project-adopt --apply requires privileged control plane"
        in cp.stderr
    )


def test_admin_accepts_project_adopt_entrypoint() -> None:
    cp = _run(
        _admin(
            "project-adopt",
            "--help",
        )
    )

    assert cp.returncode == 0


def test_architecture_init_overwrite_requires_admin_plane() -> None:
    cp = _run(
        _agent(
            "architecture-init",
            "--overwrite",
        )
    )

    assert cp.returncode == 2
    assert (
        "architecture-init --overwrite requires privileged control plane"
        in cp.stderr
    )


def test_project_init_is_admin_only() -> None:
    denied = _run(
        _agent(
            "project-init",
            "--help",
        )
    )
    allowed = _run(
        _admin(
            "project-init",
            "--help",
        )
    )

    assert denied.returncode == 2
    assert "requires privileged control plane" in denied.stderr
    assert allowed.returncode == 0


def test_installed_payload_contains_admin_launchers() -> None:
    assert "agentos-admin" in CURRENT_LAUNCHERS
    assert "agentos-admin.cmd" in CURRENT_LAUNCHERS


def test_v0283_policy_declares_control_plane_boundary() -> None:
    """Protect the v0.28.3 boundary across later releases."""
    from agentos.policy import load_release_policy

    policy = load_release_policy(ROOT)
    control = policy[
        "privileged_control_plane_policy"
    ]

    version = tuple(
        int(part)
        for part in policy["version"].split(".")
    )

    assert version >= (0, 28, 3)

    assert control["enabled"] is True
    assert (
        control[
            "privileged_control_plane_required"
        ]
        is True
    )
    assert (
        control[
            "control_plane_allowlist_explicit"
        ]
        is True
    )
    assert (
        control[
            "dual_plane_argument_enforcement"
        ]
        is True
    )
    assert (
        control[
            "agent_plane_privileged_execution_allowed"
        ]
        is False
    )
    assert (
        control[
            "mcp_privileged_mutation_exposed"
        ]
        is False
    )
    assert (
        control[
            "web_mutation_authority"
        ]
        is False
    )

    assert set(
        control["dual_plane_commands"]
    ) == {
        "architecture-init",
        "project-adopt",
    }

    if version == (0, 28, 3):
        assert (
            control[
                "tool_exclusivity_attested"
            ]
            is False
        )
        assert (
            control[
                "hard_anti_bypass_reserved_for_v0284"
            ]
            is True
        )

    if version >= (0, 28, 4):
        assert (
            control[
                "tool_exclusivity_attested"
            ]
            is True
        )
        assert (
            control[
                "hard_anti_bypass_reserved_for_v0284"
            ]
            is False
        )
        assert (
            control[
                "tool_exclusivity_scope"
            ]
            == "agentos_mediated_agent_execution"
        )
        assert (
            control[
                "enforcement_attestation_version"
            ]
            == 1
        )

def test_v0283_policy_poisoning_fails_closed() -> None:
    """Protect both historical v0.28.3 and current v0.28.4 contracts."""
    from copy import deepcopy

    from agentos.policy import (
        load_release_policy,
        validate_policy,
    )

    policy = load_release_policy(ROOT)

    # --------------------------------------------------------
    # Boundary invariant shared by v0.28.3+
    # --------------------------------------------------------

    poisoned = deepcopy(policy)

    poisoned[
        "privileged_control_plane_policy"
    ][
        "agent_plane_privileged_execution_allowed"
    ] = True

    try:
        validate_policy(poisoned)
    except RuntimeError as exc:
        assert (
            "control-plane" in str(exc)
            or "authority invariant" in str(exc)
        )
    else:
        raise AssertionError(
            "poisoned agent-plane authority was accepted"
        )

    # --------------------------------------------------------
    # Historical v0.28.3 reservation contract
    # --------------------------------------------------------

    historical = deepcopy(policy)
    historical["version"] = "0.28.3"
    historical["web_control_plane_policy"]["database_schema"] = 61
    historical[
        "privileged_control_plane_policy"
    ][
        "database_schema"
    ] = 61
    historical.pop(
        "completion_verification_policy",
        None,
    )

    historical_control = historical[
        "privileged_control_plane_policy"
    ]

    historical_control[
        "tool_exclusivity_attested"
    ] = False

    historical_control[
        "hard_anti_bypass_reserved_for_v0284"
    ] = True

    # A reconstructed valid v0.28.3 contract must still validate.
    validate_policy(historical)

    poisoned_v0283 = deepcopy(historical)

    poisoned_v0283[
        "privileged_control_plane_policy"
    ][
        "tool_exclusivity_attested"
    ] = True

    try:
        validate_policy(poisoned_v0283)
    except RuntimeError as exc:
        message = str(exc)

        assert (
            "v0.28.3" in message
            or "tool exclusivity" in message
        )
    else:
        raise AssertionError(
            "v0.28.3 falsely accepted tool-exclusivity attestation"
        )

    # --------------------------------------------------------
    # Current v0.28.4 activation contract
    # --------------------------------------------------------

    current_version = tuple(
        int(part)
        for part in policy["version"].split(".")
    )

    if current_version >= (0, 28, 4):
        poisoned_v0284 = deepcopy(policy)

        poisoned_v0284[
            "privileged_control_plane_policy"
        ][
            "tool_exclusivity_attested"
        ] = False

        try:
            validate_policy(poisoned_v0284)
        except RuntimeError as exc:
            assert (
                "tool exclusivity"
                in str(exc)
            )
        else:
            raise AssertionError(
                "v0.28.4 accepted disabled tool exclusivity"
            )

        poisoned_reservation = deepcopy(policy)

        poisoned_reservation[
            "privileged_control_plane_policy"
        ][
            "hard_anti_bypass_reserved_for_v0284"
        ] = True

        try:
            validate_policy(
                poisoned_reservation
            )
        except RuntimeError as exc:
            assert (
                "reservation" in str(exc)
                or "v0.28.4" in str(exc)
            )
        else:
            raise AssertionError(
                "v0.28.4 accepted stale anti-bypass reservation"
            )

def test_admin_help_uses_control_plane_program_identity() -> None:
    for command in (
        "project-init",
        "project-adopt",
        "approve-task",
    ):
        cp = _run(
            _admin(
                command,
                "--help",
            )
        )

        assert cp.returncode == 0, cp.stderr
        assert (
            f"usage: agentos-admin {command}"
            in cp.stdout
        )


def test_agent_help_retains_agent_program_identity() -> None:
    cp = _run(
        _agent(
            "project-adopt",
            "--help",
        )
    )

    assert cp.returncode == 0, cp.stderr
    assert "usage: agentos project-adopt" in cp.stdout
    assert "usage: agentos-admin" not in cp.stdout


MIXED_PLANE_HELP_CASES = (
    (
        "architecture-proposal-show",
        "architecture-proposal-approve",
    ),
    (
        "architecture-show",
        "architecture-baseline-approve",
    ),
    (
        "db-connection-show",
        "db-connection-register",
    ),
    (
        "decision-show",
        "decision-resolve",
    ),
    (
        "multi-agent-supervisor-status",
        "multi-agent-supervisor-create",
    ),
    (
        "multi-agent-workspace-status",
        "multi-agent-workspace-provision",
    ),
    (
        "project-consolidation-show",
        "project-consolidation-approve",
    ),
    (
        "project-primary-status",
        "project-primary-select",
    ),
    (
        "db-extraction-batch-show",
        "db-extraction-batch-create",
    ),
    (
        "project-consolidation-risk-assess",
        "project-consolidation-batch-review",
    ),
    (
        "db-field-mapping-show",
        "db-target-contract-approve",
    ),
)


def test_mixed_modules_preserve_agent_help_identity() -> None:
    for agent_command, _ in MIXED_PLANE_HELP_CASES:
        cp = _run(
            _agent(
                agent_command,
                "--help",
            )
        )

        assert cp.returncode == 0, (
            agent_command,
            cp.stdout,
            cp.stderr,
        )

        assert (
            f"usage: agentos {agent_command}"
            in cp.stdout
        )

        assert "usage: agentos-admin" not in cp.stdout


def test_mixed_modules_use_admin_help_identity() -> None:
    for _, privileged_command in MIXED_PLANE_HELP_CASES:
        cp = _run(
            _admin(
                "--task-id",
                "T-V0283-HELP",
                "--session-id",
                "S-V0283-HELP",
                privileged_command,
                "--help",
            )
        )

        assert cp.returncode == 0, (
            privileged_command,
            cp.stdout,
            cp.stderr,
        )

        assert (
            f"usage: agentos-admin {privileged_command}"
            in cp.stdout
        )

def test_posix_launchers_are_executable() -> None:
    if os.name == "nt":
        pytest.skip("POSIX executable-bit contract")

    launchers = (
        ".agents/bin/agentos",
        ".agents/bin/agentos-admin",
        ".agents/bin/agentos-audit-daemon",
        ".agents/bin/agentos-gatewayd",
        ".agents/bin/agentos-mcp",
        ".agents/bin/agentosctl",
        ".agents/bin/hooks/pre-commit",
        ".agents/bin/install-git-hooks.sh",
        ".agents/bin/install.sh",
    )

    for rel in launchers:
        path = ROOT / rel
        assert path.is_file(), rel
        assert os.access(path, os.X_OK), (
            f"POSIX launcher is not executable: {rel}"
        )
