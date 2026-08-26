"""
File: .agents/agentos/enforcement_attestation.py

Purpose:
    Produce deterministic evidence that supported AgentOS-mediated
    agent execution surfaces use the canonical enforcement boundary.

Security scope:
    This module attests AgentOS-mediated execution paths. It does not
    claim OS-level isolation or resistance to an arbitrary same-user
    process that directly modifies or bypasses AgentOS itself.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from . import __version__
from .mcp_core_runtime import CORE_TOOL_NAMES
from .mcp_feature_runtime import (
    LEGACY_GATEWAY_MODULES,
    feature_runtime_health,
)
from .mcp_runtime import _health as mcp_runtime_health
from .policy import load_policy
from .proxy import CAPABILITIES
from .schema_version import CURRENT_SCHEMA_VERSION


ATTESTATION_VERSION = 1
ATTESTATION_SCOPE = "agentos_mediated_agent_execution"

_CANONICAL_PROCESS_PRIMITIVES = {
    ".agents/agentos/proxy.py": {
        "subprocess.run",
    },
    ".agents/agentos/jobs.py": {
        "subprocess.Popen",
    },
}

_INTERNAL_GOVERNANCE_PROCESS_PRIMITIVES = {
    ".agents/agentos/drift.py": {
        "subprocess.run",
    },
    ".agents/agentos/planning.py": {
        "subprocess.run",
    },
    ".agents/agentos/multi_agent_workspace.py": {
        "subprocess.run",
    },
}

_ACTIVE_RUNTIME_MODULES = (
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/mcp_core_runtime.py",
    ".agents/agentos/mcp_feature_runtime.py",
)


def _source(root: Path, rel: str) -> str:
    path = root / rel
    return path.read_text(
        encoding="utf-8",
        errors="strict",
    )


def _function_source(
    root: Path,
    rel: str,
    function_name: str,
) -> str:
    text = _source(root, rel)
    tree = ast.parse(text, filename=rel)
    lines = text.splitlines()

    for node in tree.body:
        if (
            isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and node.name == function_name
        ):
            end = node.end_lineno or node.lineno
            return "\n".join(
                lines[node.lineno - 1 : end]
            )

    raise RuntimeError(
        f"function not found: {rel}:{function_name}"
    )


def _process_primitives(
    root: Path,
) -> list[dict[str, Any]]:
    """Return process-creation primitive sites using AST imports."""
    findings: list[dict[str, Any]] = []
    base = root / ".agents/agentos"

    for path in sorted(base.glob("*.py")):
        text = path.read_text(
            encoding="utf-8",
            errors="strict",
        )

        tree = ast.parse(
            text,
            filename=str(path),
        )

        module_aliases: dict[str, str] = {}
        direct_aliases: dict[str, str] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {
                        "subprocess",
                        "os",
                    }:
                        module_aliases[
                            alias.asname or alias.name
                        ] = alias.name

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""

                if module in {
                    "subprocess",
                    "os",
                }:
                    for alias in node.names:
                        direct_aliases[
                            alias.asname or alias.name
                        ] = (
                            f"{module}.{alias.name}"
                        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            call_name: str | None = None
            func = node.func

            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
            ):
                module = module_aliases.get(
                    func.value.id
                )

                if module:
                    call_name = (
                        f"{module}.{func.attr}"
                    )

            elif isinstance(func, ast.Name):
                call_name = direct_aliases.get(
                    func.id
                )

            if not call_name:
                continue

            process_primitive = False

            if call_name in {
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
            }:
                process_primitive = True

            if call_name in {
                "os.system",
                "os.popen",
            }:
                process_primitive = True

            if (
                call_name.startswith("os.exec")
                or call_name.startswith("os.spawn")
            ):
                process_primitive = True

            if not process_primitive:
                continue

            findings.append(
                {
                    "path": path.relative_to(
                        root
                    ).as_posix(),
                    "line": int(node.lineno),
                    "primitive": call_name,
                }
            )

    return findings


def _legacy_module_paths() -> set[str]:
    paths = set()

    for module in LEGACY_GATEWAY_MODULES:
        name = module.rsplit(".", 1)[-1]
        paths.add(
            f".agents/agentos/{name}.py"
        )

    return paths


def _real_legacy_runtime_imports(
    root: Path,
) -> list[dict[str, Any]]:
    legacy = set(LEGACY_GATEWAY_MODULES)
    legacy_names = {
        item.rsplit(".", 1)[-1]
        for item in legacy
    }

    findings: list[dict[str, Any]] = []

    for rel in _ACTIVE_RUNTIME_MODULES:
        text = _source(root, rel)
        tree = ast.parse(text, filename=rel)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    tail = alias.name.rsplit(
                        ".",
                        1,
                    )[-1]

                    if (
                        alias.name in legacy
                        or tail in legacy_names
                    ):
                        findings.append(
                            {
                                "path": rel,
                                "line": node.lineno,
                                "module": alias.name,
                            }
                        )

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                tail = module.rsplit(".", 1)[-1]

                if (
                    module in legacy
                    or tail in legacy_names
                ):
                    findings.append(
                        {
                            "path": rel,
                            "line": node.lineno,
                            "module": module,
                        }
                    )

    return findings


def attest_enforcement(
    root: Path,
) -> dict[str, Any]:
    """Return deterministic tool-exclusivity evidence."""
    root = root.resolve()

    policy = load_policy(root)
    tool_policy = policy.get(
        "tool_policy",
        {},
    )
    proxy_policy = policy.get(
        "proxy_policy",
        {},
    )
    privileged_policy = policy.get(
        "privileged_control_plane_policy",
        {},
    )

    checks: dict[str, bool] = {}
    findings: list[dict[str, str]] = []

    def require(
        name: str,
        condition: bool,
        message: str,
    ) -> None:
        checks[name] = bool(condition)

        if not condition:
            findings.append(
                {
                    "code": name,
                    "message": message,
                }
            )

    # --------------------------------------------------------
    # Policy boundary
    # --------------------------------------------------------

    require(
        "proxy_enabled",
        proxy_policy.get("enabled") is True,
        "proxy policy must be enabled",
    )

    require(
        "proxy_only_mode",
        tool_policy.get(
            "proxy_only_mode"
        ) is True,
        "tool policy must require proxy-only execution",
    )

    require(
        "canonical_guarded_lifecycle",
        tool_policy.get(
            "canonical_guarded_lifecycle"
        ) is True,
        "canonical guarded lifecycle must be enabled",
    )

    require(
        "direct_backend_access_forbidden",
        proxy_policy.get(
            "direct_backend_access_forbidden"
        ) is True,
        "direct backend access must be forbidden",
    )

    require(
        "direct_record_tool_forbidden",
        tool_policy.get(
            "direct_record_tool_forbidden"
        ) is True,
        "direct tool evidence recording must be forbidden",
    )

    require(
        "legacy_guarded_execution_disabled",
        tool_policy.get(
            "legacy_guarded_execution_enabled"
        ) is False,
        "legacy guard/complete public execution must be disabled",
    )

    require(
        "unknown_tools_fail_closed",
        tool_policy.get(
            "unknown_tools_fail_closed"
        ) is True,
        "unknown tools must fail closed",
    )

    require(
        "argv_only_process_mode",
        proxy_policy.get(
            "shell_mode"
        ) == "argv_only_no_shell",
        "process execution must use argv-only no-shell mode",
    )

    # --------------------------------------------------------
    # Runtime registry separation
    # --------------------------------------------------------

    from .cli_runtime import (
        CONTROL_PLANE_COMMANDS,
        DUAL_PLANE_COMMANDS,
        agent_command_registry,
        privileged_command_registry,
    )

    agent_registry = agent_command_registry()
    privileged_registry = (
        privileged_command_registry()
    )

    overlap = (
        set(agent_registry)
        & set(privileged_registry)
    )

    unexpected_overlap = sorted(
        overlap - set(DUAL_PLANE_COMMANDS)
    )

    require(
        "agent_privileged_registry_separated",
        not unexpected_overlap,
        "agent and privileged registries have unexpected overlap",
    )

    require(
        "agent_plane_privileged_execution_denied",
        privileged_policy.get(
            "agent_plane_privileged_execution_allowed"
        )
        is False,
        "agent plane must not permit privileged execution",
    )

    require(
        "control_plane_allowlist_explicit",
        privileged_policy.get(
            "control_plane_allowlist_explicit"
        )
        is True,
        "privileged control plane must use explicit allowlisting",
    )

    # --------------------------------------------------------
    # MCP active execution boundary
    # --------------------------------------------------------

    feature_health = feature_runtime_health()
    mcp_health = mcp_runtime_health(
        root,
        None,
        None,
    )

    legacy_runtime_imports = (
        _real_legacy_runtime_imports(root)
    )

    require(
        "legacy_mcp_handler_inactive",
        (
            feature_health.get(
                "legacy_gateway_handler_count"
            )
            == 0
        ),
        "active MCP handler provenance includes a legacy gateway",
    )

    require(
        "legacy_mcp_runtime_imports_absent",
        not legacy_runtime_imports,
        "active runtime imports a legacy MCP gateway module",
    )

    require(
        "mcp_subprocess_forwarding_disabled",
        mcp_health.get(
            "subprocess_forwarding"
        )
        is False,
        "active MCP runtime reports subprocess forwarding",
    )

    require(
        "mcp_trusted_enforcement_gateway",
        mcp_health.get(
            "trusted_enforcement_gateway"
        )
        is True,
        "MCP core runtime is not bound to trusted enforcement gateway",
    )

    require(
        "mcp_core_catalog_proxy_bound",
        set(CORE_TOOL_NAMES)
        == set(CAPABILITIES),
        "MCP core tool catalog and proxy capability catalog differ",
    )

    # --------------------------------------------------------
    # Supported CLI / gateway execution routes
    # --------------------------------------------------------

    cli_source = _source(
        root,
        ".agents/agentos/cli.py",
    )
    gateway_source = _source(
        root,
        ".agents/agentos/gatewayd.py",
    )

    run_tests_source = _function_source(
        root,
        ".agents/agentos/cli.py",
        "_run_tests",
    )

    start_job_source = _function_source(
        root,
        ".agents/agentos/jobs.py",
        "start_job",
    )

    proxy_execute_source = _function_source(
        root,
        ".agents/agentos/proxy.py",
        "proxy_execute",
    )

    proxy_submit_source = _function_source(
        root,
        ".agents/agentos/proxy.py",
        "proxy_submit_job",
    )

    record_source = _function_source(
        root,
        ".agents/agentos/core.py",
        "record_tool_execution",
    )

    require(
        "run_tests_proxy_bound",
        (
            "proxy_execute(" in run_tests_source
            and '"agentos.run_command"'
            in run_tests_source
            and "subprocess." not in run_tests_source
        ),
        "run-tests is not exclusively bound to canonical process proxy",
    )

    require(
        "cli_async_proxy_bound",
        (
            "proxy_submit_job(" in cli_source
            and "result=submit_job("
            not in cli_source
        ),
        "CLI async execution bypasses proxy_submit_job",
    )

    require(
        "gateway_async_proxy_bound",
        (
            "proxy_submit_job("
            in gateway_source
            and "return submit_job("
            not in gateway_source
        ),
        "gateway async execution bypasses proxy_submit_job",
    )

    validate_position = (
        start_job_source.find(
            "validate_execution_token("
        )
    )
    popen_position = (
        start_job_source.find(
            "subprocess.Popen("
        )
    )

    require(
        "async_actual_side_effect_guarded",
        (
            "execution_token:" in start_job_source
            and "guarded_args:" in start_job_source
            and validate_position >= 0
            and popen_position >= 0
            and validate_position < popen_position
            and "shell=False" in start_job_source
            and (
                'guarded_args.get("auto_start") '
                "is not True"
                in start_job_source
            )
        ),
        "async Popen boundary is not guarded immediately before execution",
    )

    require(
        "direct_record_tool_hard_disabled",
        (
            "raise RuntimeError("
            in record_source
            and "direct record-tool"
            in record_source
        ),
        "direct record-tool implementation is not hard disabled",
    )

    require(
        "legacy_guard_complete_cli_blocked",
        (
            'args.cmd in {"guard-tool", "complete-tool"}'
            in cli_source
            and "proxy_only_mode"
            in cli_source
        ),
        "legacy guard/complete CLI path is not fail-closed",
    )

    # --------------------------------------------------------
    # Signed execution evidence
    # --------------------------------------------------------

    def signed_lifecycle(
        source: str,
    ) -> bool:
        return all(
            marker in source
            for marker in (
                "guard_tool(",
                "complete_tool(",
                "append_signed_event(",
                '"proxy.request"',
                '"proxy.completed"',
            )
        )

    require(
        "sync_signed_execution_lifecycle",
        signed_lifecycle(
            proxy_execute_source
        ),
        "synchronous proxy lacks canonical signed execution lifecycle",
    )

    require(
        "async_signed_execution_lifecycle",
        signed_lifecycle(
            proxy_submit_source
        ),
        "asynchronous proxy lacks canonical signed execution lifecycle",
    )

    # --------------------------------------------------------
    # Process primitive classification
    # --------------------------------------------------------

    process_inventory = _process_primitives(
        root
    )

    legacy_paths = _legacy_module_paths()

    canonical: list[dict[str, Any]] = []
    internal: list[dict[str, Any]] = []
    inactive_legacy: list[
        dict[str, Any]
    ] = []
    unexpected: list[
        dict[str, Any]
    ] = []

    for item in process_inventory:
        rel = str(item["path"])
        primitive = str(
            item["primitive"]
        )

        if rel in legacy_paths:
            inactive_legacy.append(item)
            continue

        allowed = (
            _CANONICAL_PROCESS_PRIMITIVES
            .get(rel, set())
        )

        if primitive in allowed:
            canonical.append(item)
            continue

        internal_allowed = (
            _INTERNAL_GOVERNANCE_PROCESS_PRIMITIVES
            .get(rel, set())
        )

        if primitive in internal_allowed:
            internal.append(item)
            continue

        unexpected.append(item)

    observed_canonical = {
        (
            str(item["path"]),
            str(item["primitive"]),
        )
        for item in canonical
    }

    expected_canonical = {
        (rel, primitive)
        for rel, primitives in (
            _CANONICAL_PROCESS_PRIMITIVES.items()
        )
        for primitive in primitives
    }

    require(
        "canonical_process_adapters_present",
        expected_canonical.issubset(
            observed_canonical
        ),
        "expected canonical process adapters are missing",
    )

    require(
        "process_primitives_classified",
        not unexpected,
        "unclassified process-creation primitive exists",
    )

    # --------------------------------------------------------
    # Final derived assertion
    # --------------------------------------------------------

    ok = not findings

    return {
        "ok": ok,
        "attestation_version": (
            ATTESTATION_VERSION
        ),
        "version": __version__,
        "schema": CURRENT_SCHEMA_VERSION,
        "scope": ATTESTATION_SCOPE,
        "tool_exclusivity": ok,
        "attestation_ready": ok,
        "policy_declared_attested": bool(
            privileged_policy.get(
                "tool_exclusivity_attested",
                False,
            )
        ),
        "checks": checks,
        "findings": findings,
        "agent_privileged_overlap": (
            unexpected_overlap
        ),
        "mcp": {
            "ok": bool(
                mcp_health.get("ok")
            ),
            "trusted_enforcement_gateway": (
                mcp_health.get(
                    "trusted_enforcement_gateway"
                )
            ),
            "subprocess_forwarding": (
                mcp_health.get(
                    "subprocess_forwarding"
                )
            ),
            "legacy_gateway_active": (
                mcp_health.get(
                    "legacy_gateway_active"
                )
            ),
            "legacy_gateway_handler_count": (
                feature_health.get(
                    "legacy_gateway_handler_count"
                )
            ),
            "legacy_runtime_imports": (
                legacy_runtime_imports
            ),
        },
        "process_execution": {
            "canonical": canonical,
            "internal_governance": internal,
            "inactive_legacy": inactive_legacy,
            "unexpected": unexpected,
            "canonical_primitive_site_count": (
                len(canonical)
            ),
        },
        "non_claims": {
            "same_user_host_bypass_resistance": False,
            "os_level_process_isolation_attested": False,
            "arbitrary_host_process_containment": False,
        },
    }
