"""
AgentOS v0.29.5 physical-isolation structural attestation.

This module attests only the bounded AgentOS-mediated Windows execution path:
Restricted Token + Low Integrity + Low-labeled sandbox + explicit current-user
sandbox DACL + Job Object assign-before-resume.

It does not claim general host-filesystem isolation, arbitrary process
containment, desktop isolation, credential isolation, or same-user bypass
resistance.

Live Windows behavior is covered by the focused v0.29.5 tests. This attester is
source/policy/CI-contract based so it can also run on non-Windows CI.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .policy import load_release_policy


ATTESTATION_VERSION = 1
ATTESTATION_SCOPE = (
    "agentos_mediated_process_execution"
)


def _source(
    root: Path,
    rel: str,
) -> str:
    return (
        root
        / rel
    ).read_text(
        encoding="utf-8",
        errors="strict",
    )


def _function_source(
    root: Path,
    rel: str,
    name: str,
) -> str:
    text = _source(
        root,
        rel,
    )

    tree = ast.parse(
        text,
        filename=rel,
    )

    lines = text.splitlines()

    for node in tree.body:
        if (
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and node.name
            == name
        ):
            end = (
                node.end_lineno
                or node.lineno
            )

            return "\n".join(
                lines[
                    node.lineno - 1:
                    end
                ]
            )

    raise RuntimeError(
        "function not found: "
        + rel
        + ":"
        + name
    )


def _module_constant(
    source: str,
    name: str,
):
    """
    Return a simple top-level constant value from Python source.

    This avoids treating equivalent source spellings such as 0x1000 and
    0x00001000 as different security contracts.
    """
    tree = ast.parse(
        source
    )

    matches = []

    for node in tree.body:
        if isinstance(
            node,
            ast.Assign,
        ):
            for target in node.targets:
                if (
                    isinstance(
                        target,
                        ast.Name,
                    )
                    and target.id
                    == name
                ):
                    matches.append(
                        node.value
                    )

        elif isinstance(
            node,
            ast.AnnAssign,
        ):
            target = node.target

            if (
                isinstance(
                    target,
                    ast.Name,
                )
                and target.id
                == name
            ):
                matches.append(
                    node.value
                )

    if len(
        matches
    ) != 1:
        raise RuntimeError(
            "expected one top-level constant "
            + name
            + ", found "
            + str(
                len(
                    matches
                )
            )
        )

    value_node = matches[
        0
    ]

    if value_node is None:
        raise RuntimeError(
            "constant has no value: "
            + name
        )

    try:
        return ast.literal_eval(
            value_node
        )
    except Exception as exc:
        raise RuntimeError(
            "constant is not a literal: "
            + name
        ) from exc


def _ordered(
    source: str,
    *markers: str,
) -> bool:
    positions = [
        source.find(
            marker
        )
        for marker in markers
    ]

    return (
        all(
            position
            >= 0
            for position in positions
        )
        and positions
        == sorted(
            positions
        )
    )


def _windows_ci_contract(
    root: Path,
) -> dict[str, Any]:
    workflow = (
        root
        / ".github/workflows/agentos-release-validation.yml"
    )

    focused_tests = (
        "test_windows_low_integrity_primitives_v0295.py",
        "test_windows_sandbox_mandatory_label_v0295.py",
        "test_windows_sandbox_dacl_access_v0295.py",
        "test_windows_low_integrity_sync_v0295.py",
        "test_windows_low_integrity_async_v0295.py",
        "test_windows_physical_isolation_attestation_v0295.py",
        "test_windows_physical_isolation_ci_gate_v0295.py",
        "test_windows_physical_isolation_activation_v0295.py",
        'test_windows_physical_isolation_release_integrity_v0295.py',
    )

    if not workflow.is_file():
        return {
            "ok": False,
            "workflow": str(
                workflow.relative_to(
                    root
                )
            ),
            "runner": (
                "windows-latest"
            ),
            "focused_suite": False,
            "full_regression_suite": False,
            "missing_markers": [
                "workflow_missing"
            ],
        }

    text = workflow.read_text(
        encoding="utf-8",
    )

    required = (
        "validate-windows:",
        "runs-on: windows-latest",
        "Windows physical isolation v0.29.5",
        *focused_tests,
        "python -m pytest -q .agents/tests -rs",
    )

    missing = [
        marker
        for marker in required
        if marker not in text
    ]

    return {
        "ok": (
            not missing
        ),
        "workflow": (
            ".github/workflows/agentos-release-validation.yml"
        ),
        "runner": (
            "windows-latest"
        ),
        "focused_suite": (
            not any(
                test
                in missing
                for test in focused_tests
            )
        ),
        "full_regression_suite": (
            "python -m pytest -q .agents/tests -rs"
            not in missing
        ),
        "missing_markers": (
            missing
        ),
    }


def attest_windows_physical_isolation(
    root: Path,
) -> dict[str, Any]:
    root = root.resolve()

    policy = (
        load_release_policy(
            root
        ).get(
            "windows_physical_isolation_policy"
        )
        or {}
    )

    physical_source = _source(
        root,
        ".agents/agentos/windows_physical_isolation.py",
    )

    low_token_source = _function_source(
        root,
        ".agents/agentos/windows_physical_isolation.py",
        "create_low_integrity_restricted_primary_token",
    )

    sandbox_boundary_source = _function_source(
        root,
        ".agents/agentos/windows_physical_isolation.py",
        "apply_low_integrity_sandbox_boundary",
    )

    sandbox_dacl_source = _function_source(
        root,
        ".agents/agentos/windows_physical_isolation.py",
        "ensure_restricted_user_sandbox_dacl",
    )

    sync_spawn_source = _function_source(
        root,
        ".agents/agentos/windows_physical_isolation.py",
        "spawn_low_integrity_restricted_suspended_in_job",
    )

    sync_capture_source = _function_source(
        root,
        ".agents/agentos/windows_physical_isolation.py",
        "run_low_integrity_restricted_contained_capture",
    )

    proxy_source = _function_source(
        root,
        ".agents/agentos/proxy.py",
        "_run_process_command",
    )

    sandbox_create_source = _function_source(
        root,
        ".agents/agentos/tool_runtime_profiles.py",
        "create_sandbox_workspace",
    )

    jobs_source = _function_source(
        root,
        ".agents/agentos/jobs.py",
        "_launch_windows_job_broker",
    )

    broker_source = _function_source(
        root,
        ".agents/agentos/windows_job_broker.py",
        "run_broker",
    )

    broker_payload_source = _function_source(
        root,
        ".agents/agentos/windows_job_broker.py",
        "_load_payload",
    )

    broker_ready_source = _function_source(
        root,
        ".agents/agentos/windows_job_broker.py",
        "_ready_record",
    )

    ci = _windows_ci_contract(
        root
    )

    checks = {
        "policy_enabled": (
            policy.get(
                "enabled"
            )
            is True
        ),
        "bounded_scope": (
            policy.get(
                "scope"
            )
            == ATTESTATION_SCOPE
        ),
        "windows_only": (
            policy.get(
                "windows_only"
            )
            is True
        ),
        "restricted_token_preserved": (
            policy.get(
                "restricted_token_required"
            )
            is True
            and policy.get(
                "restricted_token_profile_preserved"
            )
            is True
        ),
        "low_integrity_identity_exact": (
            policy.get(
                "low_integrity_sid"
            )
            == "S-1-16-4096"
            and policy.get(
                "low_integrity_rid"
            )
            == 4096
            and (
                _module_constant(
                    physical_source,
                    "LOW_INTEGRITY_SID",
                )
                == "S-1-16-4096"
            )
            and (
                _module_constant(
                    physical_source,
                    "SECURITY_MANDATORY_LOW_RID",
                )
                == 4096
            )
        ),
        "token_integrity_level_set_and_verified": (
            policy.get(
                "token_integrity_level_set_required"
            )
            is True
            and policy.get(
                "token_integrity_level_verification_required"
            )
            is True
            and (
                "SetTokenInformation("
                in physical_source
            )
            and (
                "TokenIntegrityLevel"
                in physical_source
            )
            and (
                low_token_source.find(
                    "CreateRestrictedToken("
                )
                >= 0
            )
            and (
                low_token_source.find(
                    "verify_restricted_primary_token("
                )
                > low_token_source.find(
                    "CreateRestrictedToken("
                )
            )
            and (
                low_token_source.find(
                    "set_low_integrity_token("
                )
                > low_token_source.find(
                    "verify_restricted_primary_token("
                )
            )
            and (
                low_token_source.rfind(
                    "verify_restricted_primary_token("
                )
                > low_token_source.find(
                    "set_low_integrity_token("
                )
            )
        ),
        "sandbox_low_label_enforced": (
            policy.get(
                "sandbox_mandatory_label_enforced"
            )
            is True
            and policy.get(
                "sandbox_low_integrity_label_runtime_verified"
            )
            is True
            and policy.get(
                "sandbox_label_no_write_up_required"
            )
            is True
            and (
                'LOW_DIRECTORY_LABEL_SDDL = "S:(ML;OICI;NW;;;LW)"'
                in physical_source
            )
            and (
                "SetNamedSecurityInfoW"
                in physical_source
            )
            and (
                "GetNamedSecurityInfoW"
                in physical_source
            )
            and (
                "verify_low_mandatory_label("
                in sandbox_boundary_source
            )
        ),
        "sandbox_current_user_dacl_enforced": (
            policy.get(
                "sandbox_current_user_dacl_access_required"
            )
            is True
            and policy.get(
                "sandbox_current_user_dacl_runtime_verified"
            )
            is True
            and (
                "SetEntriesInAclW"
                in physical_source
            )
            and (
                "verify_current_user_access_ace("
                in sandbox_dacl_source
            )
            and (
                "WRITE_DAC"
                not in sandbox_dacl_source
            )
        ),
        "production_sandbox_controlled_ancestry": (
            policy.get(
                "production_sandbox_controlled_ancestry_required"
            )
            is True
            and policy.get(
                "production_sandbox_ancestry_outside_anchor_modification_forbidden"
            )
            is True
            and (
                "require_controlled_ancestry=True"
                in sandbox_create_source
            )
            and (
                "sandbox_controlled_ancestry_anchor_missing"
                in physical_source
            )
        ),
        "sync_low_integrity_enforced": (
            policy.get(
                "sync_execution_enforced"
            )
            is True
            and policy.get(
                "sync_low_integrity_token_required"
            )
            is True
            and (
                "run_low_integrity_restricted_contained_capture"
                in proxy_source
            )
            and (
                "low_integrity_token_verified"
                in proxy_source
            )
            and _ordered(
                sync_spawn_source,
                "CreateProcessAsUserW(",
                "_verify_child_process_token(",
                "_verify_child_process_low_integrity(",
                "job.assign_process_handle(",
                "ResumeThread(",
            )
        ),
        "sync_fail_closed": (
            policy.get(
                "sync_fail_closed_without_medium_integrity_fallback"
            )
            is True
            and (
                "CreateProcessW("
                not in sync_spawn_source
            )
            and (
                "TerminateProcess("
                in sync_spawn_source
            )
            and (
                "terminate_tree("
                in sync_capture_source
            )
        ),
        "async_low_integrity_enforced": (
            policy.get(
                "async_execution_enforced"
            )
            is True
            and policy.get(
                "async_low_integrity_token_required"
            )
            is True
            and policy.get(
                "async_restricted_token_required"
            )
            is True
            and (
                '"low_integrity_execution": True'
                in jobs_source
            )
            and (
                '"restricted_execution": True'
                in jobs_source
            )
            and (
                "spawn_low_integrity_restricted_suspended_in_job("
                in broker_source
            )
        ),
        "async_ready_low_integrity_verified": (
            policy.get(
                "async_ready_requires_low_integrity_verification"
            )
            is True
            and (
                '"low_integrity_token_verified"'
                in jobs_source
            )
            and (
                '"low_integrity_execution"'
                in broker_ready_source
            )
            and (
                '"low_integrity_token_verified"'
                in broker_ready_source
            )
            and (
                '"assigned_before_resume"'
                in broker_ready_source
            )
        ),
        "async_completion_low_integrity_evidence": (
            policy.get(
                "async_completion_requires_low_integrity_verification"
            )
            is True
            and (
                '"low_integrity_token_verified"'
                in broker_source
            )
            and (
                '"low_integrity_execution"'
                in broker_source
            )
        ),
        "async_production_downgrade_forbidden": (
            policy.get(
                "async_fail_closed_without_medium_integrity_fallback"
            )
            is True
            and policy.get(
                "async_historical_restricted_only_branch_not_production_selectable"
            )
            is True
            and policy.get(
                "async_historical_generic_branch_not_production_selectable"
            )
            is True
            and (
                '"low_integrity_execution": True'
                in jobs_source
            )
            and (
                "low_integrity_execution"
                in broker_payload_source
            )
            and (
                "low_integrity_requires_restricted_execution"
                in broker_payload_source
            )
        ),
        "broker_remains_trusted_lifecycle_process": (
            policy.get(
                "async_broker_remains_trusted_lifecycle_process"
            )
            is True
            and (
                "create_low_integrity_restricted_primary_token("
                not in jobs_source
            )
        ),
        "sandbox_inert_forbidden": (
            "SANDBOX_INERT"
            not in low_token_source
        ),
        "security_descriptor_control_not_granted": (
            policy.get(
                "sandbox_dacl_write_dac_grant_forbidden"
            )
            is True
            and policy.get(
                "sandbox_dacl_write_owner_grant_forbidden"
            )
            is True
            and policy.get(
                "sandbox_dacl_access_system_security_grant_forbidden"
            )
            is True
            and (
                "SANDBOX_CURRENT_USER_ACCESS_MASK"
                in physical_source
            )
        ),
        "windows_ci_covered": (
            ci.get(
                "ok"
            )
            is True
        ),
        "release_attestation_activated": (
            policy.get(
                "production_activation_deferred"
            )
            is False
            and policy.get(
                "release_activation_deferred_until_phase6"
            )
            is False
            and policy.get(
                "activation_complete"
            )
            is True
            and policy.get(
                "activation_version"
            )
            == "0.29.5"
            and policy.get(
                "low_integrity_attested"
            )
            is True
            and policy.get(
                "sandbox_low_integrity_label_attested"
            )
            is True
            and policy.get(
                "primary_root_write_up_prevention_attested"
            )
            is False
        ),
        "broad_nonclaims_preserved": all(
            policy.get(
                key
            )
            is False
            for key in (
                "host_filesystem_isolation_attested",
                "os_write_confinement_attested",
                "same_user_host_bypass_resistance_claimed",
                "desktop_isolation_attested",
            )
        ),
    }

    structurally_attested = all(
        checks.values()
    )

    return {
        "attestation_version": (
            ATTESTATION_VERSION
        ),
        "scope": (
            ATTESTATION_SCOPE
        ),
        "structurally_attested": (
            structurally_attested
        ),
        "sync_enforced": bool(
            checks[
                "sync_low_integrity_enforced"
            ]
        ),
        "async_enforced": bool(
            checks[
                "async_low_integrity_enforced"
            ]
        ),
        "restricted_token_preserved": bool(
            checks[
                "restricted_token_preserved"
            ]
        ),
        "low_integrity_token_verified": bool(
            checks[
                "token_integrity_level_set_and_verified"
            ]
        ),
        "sandbox_low_integrity_boundary_verified": bool(
            checks[
                "sandbox_low_label_enforced"
            ]
            and checks[
                "sandbox_current_user_dacl_enforced"
            ]
        ),
        "production_controlled_ancestry_verified": bool(
            checks[
                "production_sandbox_controlled_ancestry"
            ]
        ),
        "assignment_before_resume": bool(
            checks[
                "sync_low_integrity_enforced"
            ]
            and checks[
                "async_low_integrity_enforced"
            ]
        ),
        "windows_ci_covered": bool(
            checks[
                "windows_ci_covered"
            ]
        ),
        "broad_nonclaims_preserved": bool(
            checks[
                "broad_nonclaims_preserved"
            ]
        ),
        "release_activation_deferred": False,
        "policy_declared_attested": bool(
            checks[
                "release_attestation_activated"
            ]
        ),
        "low_integrity_attested": bool(
            checks[
                "release_attestation_activated"
            ]
        ),
        "sandbox_low_integrity_label_attested": bool(
            checks[
                "release_attestation_activated"
            ]
        ),
        "host_filesystem_isolation_attested": False,
        "os_write_confinement_attested": False,
        "same_user_host_bypass_resistance_claimed": False,
        "desktop_isolation_attested": False,
        "checks": checks,
        "windows_ci": ci,
    }
