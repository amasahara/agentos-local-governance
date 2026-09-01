"""
AgentOS v0.29.4 restricted-execution structural attestation.

This module is deliberately source/contract based so it can run on both
Windows and non-Windows CI. Live Windows token behavior remains covered by
the focused v0.29.4 runtime tests.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .policy import load_release_policy


ATTESTATION_VERSION = 1
ATTESTATION_SCOPE = "agentos_mediated_process_execution"


def _source(
    root: Path,
    rel: str,
) -> str:
    return (
        root / rel
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
            and node.name == name
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


def _windows_ci_contract(
    root: Path,
) -> dict[str, Any]:
    workflow = (
        root
        / ".github/workflows/agentos-release-validation.yml"
    )

    focused_tests = (
        "test_windows_restricted_execution_v0294.py",
        "test_windows_restricted_sync_v0294.py",
        "test_windows_restricted_async_v0294.py",
        "test_windows_restricted_fail_closed_v0294.py",
        "test_windows_restricted_attestation_v0294.py",
        "test_windows_restricted_ci_gate_v0294.py",
        "test_windows_restricted_activation_v0294.py",
        "test_successor_policy_activation_v0294.py",
        "test_windows_restricted_release_integrity_v0294.py",
    )

    if not workflow.is_file():
        return {
            "ok": False,
            "workflow": str(
                workflow.relative_to(root)
            ),
            "runner": "windows-latest",
            "focused_suite": False,
            "full_regression_suite": False,
            "missing_markers": [
                "workflow_missing"
            ],
        }

    text = workflow.read_text(
        encoding="utf-8"
    )

    required = (
        "validate-windows:",
        "runs-on: windows-latest",
        "Windows restricted execution v0.29.4",
        *focused_tests,
        "python -m pytest -q .agents/tests -rs",
    )

    missing = [
        marker
        for marker in required
        if marker not in text
    ]

    return {
        "ok": not missing,
        "workflow": (
            ".github/workflows/agentos-release-validation.yml"
        ),
        "runner": "windows-latest",
        "focused_suite": not any(
            test in missing
            for test in focused_tests
        ),
        "full_regression_suite": (
            "python -m pytest -q .agents/tests -rs"
            not in missing
        ),
        "missing_markers": missing,
    }


def attest_windows_restricted_execution(
    root: Path,
) -> dict[str, Any]:
    root = root.resolve()

    policy = (
        load_release_policy(root).get(
            "windows_restricted_execution_policy"
        )
        or {}
    )

    restricted_source = _source(
        root,
        ".agents/agentos/windows_restricted_execution.py",
    )
    create_source = _function_source(
        root,
        ".agents/agentos/windows_restricted_execution.py",
        "create_restricted_primary_token",
    )
    spawn_source = _function_source(
        root,
        ".agents/agentos/windows_restricted_execution.py",
        "spawn_restricted_suspended_in_job",
    )
    sync_capture_source = _function_source(
        root,
        ".agents/agentos/windows_restricted_execution.py",
        "run_restricted_contained_capture",
    )
    proxy_source = _function_source(
        root,
        ".agents/agentos/proxy.py",
        "_run_process_command",
    )
    jobs_source = _function_source(
        root,
        ".agents/agentos/jobs.py",
        "_launch_windows_job_broker",
    )
    broker_source = _source(
        root,
        ".agents/agentos/windows_job_broker.py",
    )

    ci = _windows_ci_contract(
        root
    )

    create_restricted = (
        create_source.find(
            "advapi32.CreateRestrictedToken("
        )
    )
    verify_source = (
        create_source.find(
            "verify_restricted_primary_token("
        )
    )
    return_token = (
        create_source.find(
            "return RestrictedPrimaryToken("
        )
    )

    create_child = (
        spawn_source.find(
            "advapi32.CreateProcessAsUserW("
        )
    )
    verify_child = (
        spawn_source.find(
            "_verify_child_process_token("
        )
    )
    assign_child = (
        spawn_source.find(
            "job.assign_process_handle("
        )
    )
    resume_child = (
        spawn_source.find(
            "kernel32.ResumeThread("
        )
    )

    checks = {
        "policy_enabled": (
            policy.get("enabled")
            is True
        ),
        "bounded_scope": (
            policy.get("scope")
            == ATTESTATION_SCOPE
        ),
        "windows_only": (
            policy.get("windows_only")
            is True
        ),
        "sync_enforced": (
            policy.get(
                "sync_execution_enforced"
            )
            is True
            and (
                "run_restricted_contained_capture("
                in proxy_source
            )
        ),
        "async_enforced": (
            policy.get(
                "async_execution_enforced"
            )
            is True
            and (
                '"restricted_execution": True'
                in jobs_source
            )
            and (
                "spawn_restricted_suspended_in_job("
                in broker_source
            )
        ),
        "restricted_token_profile_exact": (
            "RESTRICTED_TOKEN_FLAGS = "
            "DISABLE_MAX_PRIVILEGE | LUA_TOKEN"
            in restricted_source
            and (
                "RESTRICTED_TOKEN_FLAGS = "
                "DISABLE_MAX_PRIVILEGE | "
                "LUA_TOKEN | SANDBOX_INERT"
                not in restricted_source
            )
        ),
        "sandbox_inert_forbidden": (
            policy.get(
                "sandbox_inert_allowed"
            )
            is False
            and policy.get(
                "sandbox_inert_forbidden"
            )
            is True
            and (
                "restricted_token_sandbox_inert_forbidden"
                in restricted_source
            )
        ),
        "enabled_privilege_allowlist_enforced": (
            policy.get(
                "enabled_privilege_allowlist"
            )
            == [
                "SeChangeNotifyPrivilege"
            ]
            and policy.get(
                "unexpected_enabled_privileges_forbidden"
            )
            is True
            and (
                "unexpected_enabled_privileges"
                in restricted_source
            )
        ),
        "source_token_verified_before_return": (
            create_restricted >= 0
            and verify_source >= 0
            and return_token >= 0
            and (
                create_restricted
                < verify_source
                < return_token
            )
        ),
        "child_verified_before_job_assignment": (
            create_child >= 0
            and verify_child >= 0
            and assign_child >= 0
            and resume_child >= 0
            and (
                create_child
                < verify_child
                < assign_child
                < resume_child
            )
        ),
        "create_suspended_required": (
            "CREATE_SUSPENDED"
            in spawn_source
        ),
        "unrestricted_sync_fallback_absent": (
            policy.get(
                "unrestricted_sync_fallback_forbidden"
            )
            is True
            and (
                "spawn_suspended_in_job("
                not in sync_capture_source
            )
            and (
                "CreateProcessW("
                not in spawn_source
            )
        ),
        "async_production_downgrade_forbidden": (
            policy.get(
                "unrestricted_async_production_downgrade_forbidden"
            )
            is True
            and (
                '"restricted_execution": True'
                in jobs_source
            )
            and (
                '"restricted_token_verified"'
                in jobs_source
            )
            and (
                '"assigned_before_resume"'
                in jobs_source
            )
        ),
        "post_create_cleanup_present": (
            "job.terminate(1)"
            in spawn_source
            and (
                "kernel32.TerminateProcess("
                in spawn_source
            )
            and (
                "kernel32.WaitForSingleObject("
                in spawn_source
            )
            and (
                "raise original_exc"
                in spawn_source
            )
        ),
        "fail_closed_policy_contract": all(
            policy.get(key)
            is True
            for key in (
                "source_token_validation_fail_closed",
                "child_token_validation_fail_closed",
                "job_assignment_failure_fail_closed",
                "resume_failure_fail_closed",
                "unrestricted_sync_fallback_forbidden",
                "unrestricted_async_production_downgrade_forbidden",
                "sandbox_inert_forbidden",
                "unexpected_enabled_privileges_forbidden",
                "negative_test_suite_required",
            )
        ),
        "windows_ci_covered": (
            ci.get("ok")
            is True
        ),
        "broad_nonclaims_preserved": all(
            policy.get(key)
            is False
            for key in (
                "low_integrity_attested",
                "desktop_isolation_attested",
                "host_filesystem_isolation_attested",
                "os_write_confinement_attested",
                "same_user_host_bypass_resistance_claimed",
            )
        ),
        "release_attestation_activated": (
            policy.get(
                "restricted_token_attested"
            )
            is True
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
            == "0.29.4"
        ),
    }

    structurally_attested = all(
        checks.values()
    )

    return {
        "attestation_version": (
            ATTESTATION_VERSION
        ),
        "scope": ATTESTATION_SCOPE,
        "structurally_attested": (
            structurally_attested
        ),
        "sync_enforced": bool(
            checks["sync_enforced"]
        ),
        "async_enforced": bool(
            checks["async_enforced"]
        ),
        "source_token_verified": bool(
            checks[
                "source_token_verified_before_return"
            ]
        ),
        "child_token_verified": bool(
            checks[
                "child_verified_before_job_assignment"
            ]
        ),
        "assignment_before_resume": bool(
            checks[
                "child_verified_before_job_assignment"
            ]
        ),
        "fail_closed": bool(
            checks[
                "fail_closed_policy_contract"
            ]
            and checks[
                "post_create_cleanup_present"
            ]
        ),
        "unrestricted_fallback_forbidden": bool(
            checks[
                "unrestricted_sync_fallback_absent"
            ]
            and checks[
                "async_production_downgrade_forbidden"
            ]
        ),
        "sandbox_inert_forbidden": bool(
            checks[
                "sandbox_inert_forbidden"
            ]
        ),
        "privilege_allowlist_enforced": bool(
            checks[
                "enabled_privilege_allowlist_enforced"
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
        "policy_declared_attested": (
            policy.get(
                "restricted_token_attested"
            )
            is True
        ),
        "restricted_token_attested": (
            policy.get(
                "restricted_token_attested"
            )
            is True
        ),
        "low_integrity_attested": False,
        "checks": checks,
        "windows_ci": ci,
    }
