"""
File: .agents/agentos/cli_runtime.py

Purpose:
    Provide one cross-platform AgentOS CLI registry and in-process dispatcher.

Responsibilities:
    - Route core and extension commands without version-chained shell execution.
    - Normalize project root, task, and session context on every platform.
    - Detect duplicate command registrations fail-closed.
    - Keep privileged v0.22.4 operations inside the task/session enforcement boundary.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

from . import __version__
from . import cli as core_cli
from .governance_enforcement import governed_operation_status
from .release_integrity import check_release_integrity, docs_check_current
from .release_manifest import verify_manifest
from .schema_version import CURRENT_SCHEMA_VERSION

VERSION = __version__

FEATURE_CLI_MODULES = (
    "project_identity_cli",
    "project_selection_cli",
    "project_consolidation_cli",
    "risk_tiered_batch_review_cli",
    "db_aware_context_projection_cli",
    "database_boundary_cli",
    "schema_mapping_cli",
    "read_only_extraction_cli",
    "controlled_target_insert_cli",
    "identity_resolution_cli",
    "reconciliation_recovery_cli",
    "secret_lineage_cli",
    "data_subject_rights_cli",
    "context_transport_cli",
    "context_authority_cli",
    "adaptive_budget_cli",
    "context_evaluation_cli",
    "consolidation_cockpit_cli",
    "architecture_contract_cli",
    "architecture_discovery_cli",
    "architecture_compliance_cli",
    "architecture_change_cli",
    "architecture_planning_cli",
    "architecture_structural_cli",
    "architecture_runtime_cli",
    "architecture_quality_cli",
    "skill_selection_cli",
    "multi_agent_supervisor_cli",
    "multi_agent_workspace_cli",
    "completion_cli",
    "command_center_cli",
    "web_control_plane_cli",
    "human_decision_cli",
)

SPECIAL_COMMANDS = {
    "release-integrity-check",
    "docs-check",
    "all-docs-check",
    "manifest-verify",
    "governed-operation-show",
    "runtime-health",
    "commands-list",
    "enforcement-attest",
}

PRIVILEGED_COMMANDS = {
    'multi-agent-supervisor-create', 'multi-agent-supervisor-worker-add', 'multi-agent-supervisor-dependency-add', 'multi-agent-supervisor-activate', 'multi-agent-supervisor-pause', 'multi-agent-supervisor-cancel', 'multi-agent-worker-start', 'multi-agent-worker-update',
    'multi-agent-workspace-provision', 'multi-agent-workspace-collect', 'multi-agent-workspace-seal', 'multi-agent-workspace-release', 'multi-agent-integration-proposal-create', 'multi-agent-integration-proposal-review', 'multi-agent-integration-proposal-approve', 'multi-agent-integration-proposal-reject', 'multi-agent-integration-apply',
    "db-connection-register", "db-source-verify-readonly", "db-consolidation-create", "db-consolidation-add-source",
    "db-schema-snapshot-register", "db-target-contract-create", "db-target-contract-review", "db-target-contract-approve",
    "db-field-mapping-add", "db-field-mapping-confirm", "db-field-mapping-reject",
    "db-extraction-batch-create", "db-extraction-run",
    "db-target-insert-plan-create", "db-target-insert-plan-review", "db-target-insert-plan-approve", "db-target-insert-execute",
    "db-identity-policy-create", "db-identity-policy-review", "db-identity-policy-approve",
    "db-identity-resolution-create", "db-identity-resolution-run", "db-identity-candidate-decide",
    "db-reconciliation-create", "db-reconciliation-run", "db-recovery-scan", "db-recovery-commit-decide", "db-recovery-lineage-finalize",
    "secret-provider-approve", "secret-provider-revoke", "lineage-keyring-initialize",
    "lineage-key-rotation-plan-create", "lineage-key-rotation-plan-review", "lineage-key-rotation-plan-approve",
    "lineage-key-rotation-execute", "lineage-key-revoke", "lineage-rekey-plan-create", "lineage-rekey-plan-review",
    "lineage-rekey-plan-approve", "lineage-rekey-source-reread-authorize",
    "data-subject-erasure-request-create", "data-subject-erasure-plan-create", "data-subject-erasure-plan-review",
    "data-subject-erasure-plan-approve", "data-subject-erasure-execute",
    "project-consolidation-batch-bundle-create", "project-consolidation-batch-review",
    "project-consolidation-mapping-review",
    "architecture-baseline-review", "architecture-baseline-approve", "architecture-baseline-activate", "architecture-baseline-reject",
    "architecture-proposal-review", "architecture-proposal-approve", "architecture-proposal-reject", "architecture-proposal-bind-baseline",
    "decision-resolve",
}


CORE_CONTROL_PLANE_COMMANDS = {
    "approve-task",
    "skill-graduate",
    "skill-revoke",
    "ack-baseline",
    "approve-local-override",
    "rotate-audit-key",
    "job-cancel",
    "plan-approve",
    "memory-forget",
    "observability-prune",
    "audit-segment-archive",
    "evolution-transition",
    "role-assign",

    # Project/bootstrap identity authority.
    "project-init",
    "project-identity-init",
    "project-purpose-set",
    "project-fork",

    # Human primary-project authority.
    "project-compatibility-confirm",
    "project-primary-select",

    # Human consolidation authority.
    "project-consolidation-review",
    "project-consolidation-approve",
    "project-consolidation-rollback",
}

CONTROL_PLANE_COMMANDS = frozenset(
    PRIVILEGED_COMMANDS | CORE_CONTROL_PLANE_COMMANDS
)


# These commands contain both a non-authority mode and an explicit
# privileged mode. The dispatcher applies argument-level separation.
DUAL_PLANE_COMMANDS = frozenset({
    "project-adopt",
    "architecture-init",
})


def _commands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Return subcommand parsers keyed by command name.

    Args:
        parser: Parser containing an argparse subparser action.

    Returns:
        Mapping from command name to its command parser.
    """
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _feature_registry() -> dict[str, str]:
    """Build the extension command registry and reject duplicates.

    Returns:
        Mapping from command name to feature CLI module name.

    Raises:
        RuntimeError: When two extension modules register the same command.
    """
    registry: dict[str, str] = {}
    duplicates: list[str] = []
    for module_name in FEATURE_CLI_MODULES:
        module = importlib.import_module(f"agentos.{module_name}")
        parser = module.build_parser()
        for command in _commands(parser):
            if command in registry:
                duplicates.append(command)
            else:
                registry[command] = module_name
    if duplicates:
        raise RuntimeError(f"duplicate extension CLI commands: {sorted(set(duplicates))}")
    return registry


def command_registry() -> dict[str, str]:
    """Return the complete unified CLI command registry.

    Returns:
        Mapping from command name to runtime handler class.

    Raises:
        RuntimeError: When core and extension commands collide unexpectedly.
    """
    registry = {command: "core" for command in _commands(core_cli.parser())}
    # Current docs-check is an aggregate release gate, not the historical core-only checker.
    registry.pop("docs-check", None)
    for command, module_name in _feature_registry().items():
        if command in registry or command in SPECIAL_COMMANDS:
            raise RuntimeError(f"duplicate CLI command registration: {command}")
        registry[command] = module_name
    for command in SPECIAL_COMMANDS:
        if command in registry:
            raise RuntimeError(f"duplicate special CLI command registration: {command}")
        registry[command] = "special"
    return registry


def agent_command_registry() -> dict[str, str]:
    """Return commands dispatchable from the normal agent plane."""
    return {
        command: handler
        for command, handler in command_registry().items()
        if command not in CONTROL_PLANE_COMMANDS
    }


def privileged_command_registry() -> dict[str, str]:
    """Return commands dispatchable only from the control plane."""
    registry = command_registry()
    return {
        command: registry[command]
        for command in sorted(
            CONTROL_PLANE_COMMANDS | DUAL_PLANE_COMMANDS
        )
        if command in registry
    }


def _resolve_root(value: str | None) -> Path:
    """Resolve the governed project root.

    Args:
        value: Explicit project root or None.

    Returns:
        Absolute project root.
    """
    if value:
        return Path(value).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _parse_prefix(argv: list[str]) -> tuple[Path, str | None, str | None, str | None, list[str]]:
    """Parse cross-platform global flags before the command.

    Args:
        argv: Raw command arguments excluding executable name.

    Returns:
        Tuple of root, task id, session id, command, and command arguments.

    Raises:
        RuntimeError: When a global option is missing its value.
    """
    root: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    items = list(argv)
    while items:
        token = items[0]
        if token in {"--root", "--task-id", "--session-id"}:
            if len(items) < 2:
                raise RuntimeError(f"{token} requires a value")
            value = items[1]
            del items[:2]
            if token == "--root":
                root = value
            elif token == "--task-id":
                task_id = value
            else:
                session_id = value
            continue
        if token in {"-h", "--help"}:
            return _resolve_root(root), task_id, session_id, "__help__", []
        if token == "--version":
            return _resolve_root(root), task_id, session_id, "__version__", []
        return _resolve_root(root), task_id, session_id, token, items[1:]
    return _resolve_root(root), task_id, session_id, None, []


def _emit(value: Any) -> None:
    """Emit deterministic UTF-8 JSON to stdout."""
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _runtime_health(root: Path) -> dict[str, Any]:
    """Return runtime, registry, wrapper, and control-plane health."""
    registry = command_registry()
    agent_registry = agent_command_registry()
    privileged_registry = privileged_command_registry()

    wrappers = {
        "posix_cli": root / ".agents/bin/agentos",
        "windows_cli": root / ".agents/bin/agentos.cmd",
        "posix_admin": root / ".agents/bin/agentos-admin",
        "windows_admin": root / ".agents/bin/agentos-admin.cmd",
        "posix_mcp": root / ".agents/bin/agentos-mcp",
        "windows_mcp": root / ".agents/bin/agentos-mcp.cmd",
    }

    wrapper_status = {
        name: path.is_file() and path.stat().st_size > 0
        for name, path in wrappers.items()
    }

    legacy_active: list[str] = []
    for name, path in wrappers.items():
        if not path.exists():
            continue
        body = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        if (
            "agentos.v0" in body
            or "agentos-mcp.v0" in body
            or "mcp_reconciliation_recovery_gateway" in body
        ):
            legacy_active.append(name)

    shared = sorted(
        set(agent_registry) & set(privileged_registry)
    )
    unexpected_overlap = sorted(
        set(shared) - set(DUAL_PLANE_COMMANDS)
    )

    from .enforcement_attestation import attest_enforcement

    enforcement_attestation = attest_enforcement(root)

    parity = (
        wrapper_status["posix_cli"]
        and wrapper_status["windows_cli"]
        and wrapper_status["posix_admin"]
        and wrapper_status["windows_admin"]
        and wrapper_status["posix_mcp"]
        and wrapper_status["windows_mcp"]
    )

    return {
        "ok": (
            all(wrapper_status.values())
            and not legacy_active
            and not unexpected_overlap
            and enforcement_attestation.get("ok") is True
            and enforcement_attestation.get(
                "attestation_ready"
            ) is True
        ),
        "version": VERSION,
        "schema": CURRENT_SCHEMA_VERSION,
        "runtime": "separated_control_plane_v1",
        "command_count": len(registry),
        "agent_command_count": len(agent_registry),
        "privileged_command_count": len(privileged_registry),
        "agent_privileged_overlap": unexpected_overlap,
        "dual_plane_commands": sorted(DUAL_PLANE_COMMANDS),
        "agent_plane_privileged_dispatch": False,
        "privileged_control_plane": True,
        "duplicate_commands": [],
        "enforcement_attestation": {
            "ok": enforcement_attestation.get("ok"),
            "attestation_ready": enforcement_attestation.get(
                "attestation_ready"
            ),
            "tool_exclusivity": enforcement_attestation.get(
                "tool_exclusivity"
            ),
            "scope": enforcement_attestation.get("scope"),
            "policy_declared_attested": enforcement_attestation.get(
                "policy_declared_attested"
            ),
            "findings": enforcement_attestation.get(
                "findings",
                [],
            ),
        },
        "wrappers": wrapper_status,
        "legacy_version_forwarding_active": legacy_active,
        "windows_posix_parity": parity,
    }


def _core_accepts_task_id(command: str) -> bool:
    """Return whether the historical core command parser accepts --task-id."""
    parser = _commands(core_cli.parser()).get(command)
    return bool(parser and "--task-id" in parser._option_string_actions)


def _dispatch_special(command: str, root: Path, args: list[str]) -> int:
    """Dispatch current-release utility commands in-process."""
    if command == "release-integrity-check":
        result = check_release_integrity(root)
    elif command in {"docs-check", "all-docs-check"}:
        result = docs_check_current(root)
    elif command == "manifest-verify":
        result = verify_manifest(root)
    elif command == "governed-operation-show":
        parser = argparse.ArgumentParser(prog="agentos governed-operation-show")
        parser.add_argument("--operation-id", required=True)
        parsed = parser.parse_args(args)
        result = governed_operation_status(root, parsed.operation_id)
    elif command == "runtime-health":
        result = _runtime_health(root)
    elif command == "enforcement-attest":
        from .enforcement_attestation import attest_enforcement
        result = attest_enforcement(root)
    elif command == "commands-list":
        registry = agent_command_registry()
        result = {
            "ok": True,
            "version": VERSION,
            "plane": "agent",
            "commands": sorted(registry),
            "count": len(registry),
        }
    else:
        raise RuntimeError(f"unknown special command: {command}")
    _emit(result)
    return 0 if not isinstance(result, dict) or result.get("ok", True) else 2


def _help(plane: str = "agent") -> None:
    """Show only the commands dispatchable from the selected plane."""
    if plane == "control":
        registry = privileged_command_registry()
        executable = "agentos-admin"
        label = "privileged control plane"
    else:
        registry = agent_command_registry()
        executable = "agentos"
        label = "agent execution plane"

    print(f"AgentOS Local Governance v{VERSION} — {label}")
    print(
        f"Usage: {executable} [--root PATH] "
        "[--task-id ID] [--session-id ID] COMMAND [ARGS]"
    )
    print("Commands:")

    for command in sorted(registry):
        print(f"  {command}")


def main(
    argv: list[str] | None = None,
    *,
    plane: str = "agent",
) -> int:
    """Execute a command through an explicitly selected execution plane."""
    if plane not in {"agent", "control"}:
        raise ValueError(f"unknown execution plane: {plane}")

    executable = (
        "agentos-admin"
        if plane == "control"
        else "agentos"
    )

    try:
        root, task_id, session_id, command, command_args = _parse_prefix(
            list(sys.argv[1:] if argv is None else argv)
        )

        if command in {None, "__help__"}:
            _help(plane)
            return 0

        if command == "__version__":
            print(VERSION)
            return 0

        registry = command_registry()
        handler = registry.get(command)

        if handler is None:
            print(
                f"{executable}: unknown command: {command}",
                file=sys.stderr,
            )
            return 2

        if plane == "agent" and command in CONTROL_PLANE_COMMANDS:
            print(
                "agentos: command requires privileged control plane "
                f"(agentos-admin): {command}",
                file=sys.stderr,
            )
            return 2

        if (
            plane == "control"
            and command not in CONTROL_PLANE_COMMANDS
            and command not in DUAL_PLANE_COMMANDS
        ):
            print(
                "agentos-admin: command is not available in privileged "
                f"control plane: {command}",
                file=sys.stderr,
            )
            return 2

        if (
            plane == "agent"
            and command == "project-adopt"
            and "--apply" in command_args
        ):
            print(
                "agentos: project-adopt --apply requires privileged "
                "control plane (agentos-admin)",
                file=sys.stderr,
            )
            return 2

        if (
            plane == "agent"
            and command == "architecture-init"
            and "--overwrite" in command_args
        ):
            print(
                "agentos: architecture-init --overwrite requires "
                "privileged control plane (agentos-admin)",
                file=sys.stderr,
            )
            return 2

        if task_id:
            os.environ["AGENTOS_TASK_ID"] = task_id

        if session_id:
            os.environ["AGENTOS_SESSION_ID"] = session_id

        os.environ["AGENTOS_PROJECT_ROOT"] = str(root)
        os.environ["AGENTOS_EXECUTION_PLANE"] = plane

        # Preserve the existing v0.22.4 requirement for historical
        # governed privileged mutations.
        if (
            command in PRIVILEGED_COMMANDS
            and (not task_id or not session_id)
        ):
            print(
                "privileged command requires --task-id and --session-id",
                file=sys.stderr,
            )
            return 2

        if handler == "special":
            return _dispatch_special(
                command,
                root,
                command_args,
            )

        if handler == "core":
            forwarded = ["--root", str(root)]

            if session_id:
                forwarded += ["--session-id", session_id]

            forwarded.append(command)

            if task_id and _core_accepts_task_id(command):
                forwarded += ["--task-id", task_id]

            forwarded += command_args

            return int(core_cli.main(forwarded))

        module = importlib.import_module(
            f"agentos.{handler}"
        )

        return int(
            module.main(
                [
                    "--root",
                    str(root),
                    command,
                    *command_args,
                ]
            )
        )

    except SystemExit as exc:
        return int(exc.code or 0)

    except Exception as exc:
        _emit(
            {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
