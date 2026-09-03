"""
File: .agents/agentos/policy.py

Purpose:
    Load, validate, and stage project governance policy.

Responsibilities:
    - Validate required governance sections.
    - Apply safe local settings immediately.
    - Stage sensitive local overrides until approved.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .db import connect

CLAIM_TYPES = {"business_logic", "security", "data_behavior", "destructive_effect", "governance", "other"}
RISK_LEVELS = {"low", "medium", "high"}
SENSITIVE_SECTIONS = {"claim_policy", "filesystem_policy", "tool_policy", "workflow_policy", "drift_policy", "instruction_policy", "task_context_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy", "context_transport_policy", "adaptive_token_budget_policy", "architecture_contract_policy", "human_clarification_policy", "governed_skill_contract_policy", "architecture_aware_skill_selection_policy", "privileged_control_plane_policy", "sandbox_workspace_runtime_profile_policy", "context_authority_policy", "governed_learning_policy"}
SAFE_OVERRIDE_KEYS = {"source_root", "test_path", "encoding", "runtime_paths"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approve_local_override(root: Path, reviewed_by: str, note: str, method: str = "interactive_human") -> dict[str, Any]:
    """Approve the exact current local override content."""
    path = root / ".agents" / "config" / "governance.local.json"
    if not path.exists():
        raise RuntimeError("governance.local.json does not exist")
    digest = _digest(path)
    with connect(root) as c:
        c.execute("INSERT INTO policy_override_approvals(content_hash,status,reviewed_by,review_method,reviewed_at,note) VALUES(?, 'approved',?,?,CURRENT_TIMESTAMP,?) ON CONFLICT(content_hash) DO UPDATE SET status='approved',reviewed_by=excluded.reviewed_by,review_method=excluded.review_method,reviewed_at=CURRENT_TIMESTAMP,note=excluded.note", (digest, reviewed_by, method, note))
    return {"ok": True, "content_hash": digest, "status": "approved", "reviewed_by": reviewed_by}


def local_override_status(root: Path) -> dict[str, Any]:
    """Return safe and sensitive local override status."""
    path = root / ".agents" / "config" / "governance.local.json"
    if not path.exists():
        return {"exists": False, "sensitive": False, "status": "none", "content_hash": None}
    override = json.loads(path.read_text(encoding="utf-8"))
    sensitive = any(key in SENSITIVE_SECTIONS for key in override)
    digest = _digest(path)
    with connect(root) as c:
        row = c.execute("SELECT status,reviewed_by,review_method,reviewed_at,note FROM policy_override_approvals WHERE content_hash=?", (digest,)).fetchone()
        if sensitive and not row:
            c.execute("INSERT OR IGNORE INTO policy_override_approvals(content_hash,status) VALUES(?, 'pending')", (digest,))
    return {"exists": True, "sensitive": sensitive, "status": row["status"] if row else ("pending" if sensitive else "safe"), "content_hash": digest, "review": dict(row) if row else None}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge release-owned policy data without mutating inputs."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_release_policy(root: Path) -> dict[str, Any]:
    """Load base governance plus the optional release-owned managed policy overlay."""
    base_path = root / ".agents" / "config" / "governance.json"
    policy = json.loads(base_path.read_text(encoding="utf-8"))
    release_path = root / ".agents" / "config" / "release_policy.json"
    if release_path.is_file():
        release = json.loads(release_path.read_text(encoding="utf-8"))
        if not isinstance(release, dict):
            raise RuntimeError("release policy overlay must be an object")
        policy = _deep_merge(policy, release)
    return policy


def load_policy(root: Path) -> dict[str, Any]:
    """Load effective release policy and merge only approved project-local overrides."""
    policy = load_release_policy(root)
    local_path = root / ".agents" / "config" / "governance.local.json"
    if local_path.exists():
        override = json.loads(local_path.read_text(encoding="utf-8"))
        status = local_override_status(root)
        for key, value in override.items():
            if key in SAFE_OVERRIDE_KEYS or (key in SENSITIVE_SECTIONS and status["status"] == "approved"):
                if isinstance(value, dict) and isinstance(policy.get(key), dict):
                    policy[key] = {**policy[key], **value}
                else:
                    policy[key] = value
    validate_policy(policy)
    return policy


def _policy_version_tuple(policy: dict[str, Any]) -> tuple[int, int, int]:
    """Return the semantic policy version used for version-gated invariants."""
    raw = str(policy.get("version", "")).strip()
    parts = raw.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise RuntimeError("policy version is invalid")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def _validate_windows_process_tree_policy_v0291(
    policy: dict[str, Any],
    version: tuple[int, ...],
) -> None:
    """Fail closed on the bounded v0.29.1 Windows containment contract."""
    if version < (0, 29, 1):
        return

    containment = policy.get(
        "windows_process_tree_containment_policy"
    )
    if not isinstance(containment, dict):
        raise RuntimeError(
            "windows process-tree containment policy is required"
        )

    required_true = (
        "enabled",
        "windows_only",
        "job_objects_required_on_windows",
        "root_created_suspended",
        "assignment_before_resume_required",
        "synchronous_exec_enforced",
        "async_job_enforced",
        "sync_kill_on_job_close_required",
        "async_broker_required",
        "async_broker_kill_on_close_required",
        "timeout_terminates_tree",
        "cancellation_terminates_tree",
        "broker_failure_terminates_tree",
        "completion_receipt_required",
        "windows_ci_required",
        "windows_ci_containment_suite_required",
        "windows_ci_full_regression_required",
        "process_tree_containment_attested",
    )
    disabled = [
        key
        for key in required_true
        if containment.get(key) is not True
    ]
    if disabled:
        raise RuntimeError(
            "windows process-tree containment invariant disabled: "
            f"{disabled}"
        )

    required_false = (
        "same_user_host_bypass_resistance_claimed",
        "general_os_process_isolation_attested",
        "arbitrary_host_process_containment_attested",
    )
    overclaims = [
        key
        for key in required_false
        if containment.get(key) is not False
    ]
    if overclaims:
        raise RuntimeError(
            "windows process-tree containment overclaim: "
            f"{overclaims}"
        )

    if int(containment.get("containment_version", 0)) != 1:
        raise RuntimeError(
            "windows process-tree containment version is invalid"
        )
    if int(containment.get("database_schema", 0)) != 62:
        raise RuntimeError(
            "windows process-tree containment schema is invalid"
        )
    if (
        containment.get("scope")
        != "agentos_mediated_process_execution"
    ):
        raise RuntimeError(
            "windows process-tree containment scope is invalid"
        )
    if (
        containment.get("windows_ci_runner")
        != "windows-latest"
    ):
        raise RuntimeError(
            "windows process-tree containment CI runner is invalid"
        )


def _validate_sandbox_workspace_runtime_profile_policy_v0292(
    policy: dict[str, Any],
    version: tuple[int, ...],
) -> None:
    """
    Fail closed on the v0.29.2 sandbox workspace/runtime-profile contract.

    Before activation the section may exist with
    runtime_profile_sandbox_attested=false. Once policy VERSION is v0.29.2+,
    the full declaration becomes mandatory.
    """
    if version < (0, 29, 2):
        return

    sandbox = policy.get(
        "sandbox_workspace_runtime_profile_policy"
    )

    if not isinstance(
        sandbox,
        dict,
    ):
        raise RuntimeError(
            "sandbox workspace runtime-profile policy is required"
        )

    required_true = (
        "enabled",
        "command_profile_binding_required",
        "snapshot_copy_required",
        "sandbox_outside_primary_required",
        "sandbox_home_required",
        "sandbox_temp_required",
        "sandbox_cache_required",
        "package_cache_sandbox_local",
        "python_bytecode_cache_sandbox_local",
        "sync_exec_enforced",
        "async_job_enforced",
        "async_snapshot_hash_required",
        "async_prelaunch_revalidation_required",
        "terminal_cleanup_evidence_required",
        "windows_process_tree_containment_preserved",
        "runtime_profile_sandbox_attested",
    )

    disabled = [
        key
        for key in required_true
        if sandbox.get(key) is not True
    ]

    if disabled:
        raise RuntimeError(
            "sandbox workspace runtime-profile invariant disabled: "
            + repr(disabled)
        )

    required_false = (
        "caller_runtime_profile_override_allowed",
        "source_reparse_points_allowed",
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    )

    overclaims = [
        key
        for key in required_false
        if sandbox.get(key) is not False
    ]

    if overclaims:
        raise RuntimeError(
            "sandbox workspace runtime-profile overclaim: "
            + repr(overclaims)
        )

    if int(
        sandbox.get(
            "sandbox_version",
            0,
        )
    ) != 1:
        raise RuntimeError(
            "sandbox workspace version is invalid"
        )

    if int(
        sandbox.get(
            "runtime_profile_version",
            0,
        )
    ) != 1:
        raise RuntimeError(
            "runtime profile version is invalid"
        )

    if int(
        sandbox.get(
            "database_schema",
            0,
        )
    ) != 62:
        raise RuntimeError(
            "sandbox workspace runtime-profile schema is invalid"
        )

    if (
        sandbox.get("scope")
        != "agentos_mediated_process_execution"
    ):
        raise RuntimeError(
            "sandbox workspace runtime-profile scope is invalid"
        )

    if set(
        sandbox.get(
            "known_profiles",
            [],
        )
    ) != {
        "inspect",
        "test",
        "build",
    }:
        raise RuntimeError(
            "sandbox runtime-profile allowlist is invalid"
        )

    if (
        sandbox.get(
            "network_policy_default"
        )
        != "none"
    ):
        raise RuntimeError(
            "sandbox runtime-profile network policy must default to none"
        )

    ci_required_true = (
        "windows_ci_required",
        "windows_ci_runtime_profile_suite_required",
        "windows_ci_v0291_containment_regression_required",
        "windows_ci_full_regression_required",
        "windows_ci_activation_suite_required",
    )

    ci_disabled = [
        key
        for key in ci_required_true
        if sandbox.get(key) is not True
    ]

    if ci_disabled:
        raise RuntimeError(
            "sandbox workspace runtime-profile CI invariant disabled: "
            + repr(ci_disabled)
        )

    if sandbox.get("windows_ci_runner") != "windows-latest":
        raise RuntimeError(
            "sandbox workspace runtime-profile CI runner is invalid"
        )

def _validate_sandbox_configuration_contract_v0293_preactivation(
    policy: dict[str, Any],
) -> None:
    """Validate the v0.29.3 Phase 1 contract when present."""
    section = policy.get(
        "sandbox_workspace_runtime_profile_policy"
    )
    if not isinstance(section, dict):
        return

    if "sandbox_configuration_contract_enabled" not in section:
        return

    required_true = [
        'sandbox_configuration_contract_enabled',
        'sandbox_configuration_hash_required',
        'configured_profiles_must_match_known_profiles',
        'security_invariants_runtime_enforced',
    ]
    required_false = [
        'unknown_profile_fields_allowed',
        'caller_configuration_override_allowed',
    ]

    version = _policy_version_tuple(policy)
    if version < (0, 29, 3):
        return

    activated = True

    if activated:
        required_true.extend(
            (
                'sandbox_configuration_attested',
                'credential_boundary_enabled',
            )
        )
    else:
        required_false.extend(
            (
                'sandbox_configuration_attested',
                'credential_boundary_enabled',
            )
        )


    disabled = [
        key
        for key in required_true
        if section.get(key) is not True
    ]
    invalid_false = [
        key
        for key in required_false
        if section.get(key) is not False
    ]

    if disabled or invalid_false:
        raise RuntimeError(
            "sandbox configuration contract invalid: "
            + repr(
                {
                    "disabled": disabled,
                    "invalid_false": invalid_false,
                }
            )
        )

    if int(
        section.get(
            "sandbox_configuration_version",
            0,
        )
    ) != 1:
        raise RuntimeError(
            "sandbox configuration version is invalid"
        )

    if (
        section.get("sandbox_configuration_source")
        != "effective_policy"
    ):
        raise RuntimeError(
            "sandbox configuration source is invalid"
        )

    configured = section.get("configured_profiles")
    known = set(section.get("known_profiles", []))

    if not isinstance(configured, dict):
        raise RuntimeError(
            "sandbox configured profiles must be an object"
        )

    if set(configured) != known:
        raise RuntimeError(
            "sandbox configured profile set mismatch"
        )

    expected_keys = {
        "profile_version",
        "command_profile",
        "source_mode",
        "writable_scope",
        "persistent_workspace_writes",
        "network_policy",
        "sandbox_temp",
        "sandbox_cache",
        "sandbox_home",
        "package_cache_mode",
        "python_bytecode_cache",
    }

    for name in sorted(known):
        profile = configured.get(name)
        if not isinstance(profile, dict):
            raise RuntimeError(
                "sandbox configured profile must be an object"
            )
        if set(profile) != expected_keys:
            raise RuntimeError(
                "sandbox configured profile schema is invalid"
            )

        expected = {
            "profile_version": 1,
            "command_profile": name,
            "source_mode": "snapshot_copy",
            "writable_scope": "sandbox_only",
            "persistent_workspace_writes": False,
            "network_policy": "none",
            "sandbox_temp": True,
            "sandbox_cache": True,
            "sandbox_home": True,
            "package_cache_mode": "sandbox_local",
            "python_bytecode_cache": "sandbox_local",
        }

        if profile != expected:
            raise RuntimeError(
                "sandbox configured profile weakens runtime invariants"
            )

def _validate_credential_reference_contract_v0293_preactivation(
    policy: dict[str, Any],
) -> None:
    """
    Validate Phase 2 reference-only credential configuration.

    Secret values are not resolved or projected in this phase.
    """
    section = policy.get(
        "sandbox_workspace_runtime_profile_policy"
    )
    if not isinstance(section, dict):
        return

    if (
        "credential_reference_contract_enabled"
        not in section
    ):
        return

    required_true = [
        'credential_reference_contract_enabled',
        'credential_reference_secret_alias_only',
        'credential_reference_hash_required',
        'credential_raw_values_forbidden',
        'credential_values_persisted_forbidden',
    ]
    required_false = [
        'caller_credential_reference_override_allowed',
        'caller_raw_credential_override_allowed',
        'windows_file_secret_process_projection_attested',
    ]

    version = _policy_version_tuple(policy)
    if version < (0, 29, 3):
        return

    activated = True

    if activated:
        required_true.extend(
            (
                'credential_environment_projection_enabled',
                'credential_boundary_attested',
                'credential_boundary_enabled',
            )
        )
    else:
        required_false.extend(
            (
                'credential_environment_projection_enabled',
                'credential_boundary_attested',
                'credential_boundary_enabled',
            )
        )


    bad_true = [
        key
        for key in required_true
        if section.get(key) is not True
    ]
    bad_false = [
        key
        for key in required_false
        if section.get(key) is not False
    ]

    if bad_true or bad_false:
        raise RuntimeError(
            "credential reference policy contract invalid: "
            + repr(
                {
                    "required_true": bad_true,
                    "required_false": bad_false,
                }
            )
        )

    if int(
        section.get(
            "credential_reference_version",
            0,
        )
    ) != 1:
        raise RuntimeError(
            "credential reference version is invalid"
        )

    if (
        section.get(
            "credential_reference_scheme"
        )
        != "secret"
    ):
        raise RuntimeError(
            "credential reference scheme is invalid"
        )

    if (
        section.get(
            "credential_resolver_contract"
        )
        != "secret-resolver-v1"
    ):
        raise RuntimeError(
            "credential resolver contract is invalid"
        )

    if (
        section.get(
            "process_credential_capability"
        )
        != "process.exec.credential"
    ):
        raise RuntimeError(
            "process credential capability is invalid"
        )

    known = set(
        section.get(
            "known_profiles",
            [],
        )
    )
    bindings = section.get(
        "credential_bindings"
    )

    if not isinstance(bindings, dict):
        raise RuntimeError(
            "credential bindings must be an object"
        )

    if set(bindings) != known:
        raise RuntimeError(
            "credential binding profile set mismatch"
        )

    allowed_fields = {
        "binding_id",
        "credential_ref",
        "target_env",
        "secret_field",
    }

    reserved = {
        "PATH",
        "PYTHONPATH",
        "HOME",
        "USERPROFILE",
        "TMP",
        "TEMP",
        "TMPDIR",
        "SYSTEMROOT",
        "WINDIR",
        "XDG_CACHE_HOME",
        "PIP_CACHE_DIR",
        "PYTHONPYCACHEPREFIX",
        "NPM_CONFIG_CACHE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSH_AUTH_SOCK",
    }

    secret_markers = (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "API_KEY",
        "AUTH",
        "COOKIE",
        "CREDENTIAL",
    )

    for profile in sorted(known):
        items = bindings.get(profile)

        if not isinstance(items, list):
            raise RuntimeError(
                "credential profile bindings must be a list"
            )

        seen_ids: set[str] = set()
        seen_targets: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                raise RuntimeError(
                    "credential binding must be an object"
                )

            if set(item) != allowed_fields:
                raise RuntimeError(
                    "credential binding schema is invalid"
                )

            binding_id = str(
                item.get("binding_id")
                or ""
            ).strip()
            if not binding_id:
                raise RuntimeError(
                    "credential binding id is invalid"
                )

            ref = str(
                item.get("credential_ref")
                or ""
            ).strip()
            if (
                not ref.startswith("secret://")
                or ref == "secret://"
                or any(
                    token in ref
                    for token in (
                        "/",
                        "?",
                        "#",
                    )
                    if token != "/"
                )
            ):
                raise RuntimeError(
                    "credential reference must be secret alias only"
                )

            target = str(
                item.get("target_env")
                or ""
            ).strip().upper()

            if (
                not target
                or target in reserved
                or not any(
                    marker in target
                    for marker in secret_markers
                )
            ):
                raise RuntimeError(
                    "credential target environment is invalid"
                )

            secret_field = str(
                item.get("secret_field")
                or ""
            ).strip()
            if not secret_field:
                raise RuntimeError(
                    "credential secret field is invalid"
                )

            if binding_id in seen_ids:
                raise RuntimeError(
                    "credential binding id duplicate"
                )
            if target in seen_targets:
                raise RuntimeError(
                    "credential target environment duplicate"
                )

            seen_ids.add(binding_id)
            seen_targets.add(target)

def _validate_sync_credential_boundary_v0293_preactivation(
    policy: dict[str, Any],
) -> None:
    """Validate Phase 3+4 sync/async credential controls."""
    section = policy.get(
        "sandbox_workspace_runtime_profile_policy"
    )
    if not isinstance(section, dict):
        return

    if "sync_credential_boundary_enabled" not in section:
        return

    required_true = [
        'sync_credential_boundary_enabled',
        'sync_credential_environment_projection_enabled',
        'credential_resolution_at_launch_only',
        'credential_field_projection_only',
        'credential_projection_metadata_only_persisted',
        'credential_environment_hash_secret_independent',
        'credential_output_exact_value_redaction_required',
        'async_credential_boundary_enabled',
        'async_credential_environment_projection_enabled',
        'async_credential_resolution_at_launch_only',
        'async_credential_spec_reference_hash_only',
        'async_credential_provider_approval_revalidated',
        'async_credential_output_persistence_disabled',
        'async_credential_environment_hash_secret_independent',
        'credential_structural_attestation_required',
        'credential_ci_validation_required',
    ]
    required_false = [
        'windows_file_secret_process_projection_attested',
    ]

    version = _policy_version_tuple(policy)
    if version < (0, 29, 3):
        return

    activated = True

    if activated:
        required_true.extend(
            (
                'credential_environment_projection_enabled',
                'credential_boundary_enabled',
                'credential_boundary_attested',
                'sync_credential_boundary_attested',
                'async_credential_boundary_attested',
            )
        )
    else:
        required_false.extend(
            (
                'credential_environment_projection_enabled',
                'credential_boundary_enabled',
                'credential_boundary_attested',
                'sync_credential_boundary_attested',
                'async_credential_boundary_attested',
            )
        )


    bad_true = [
        key for key in required_true
        if section.get(key) is not True
    ]
    bad_false = [
        key for key in required_false
        if section.get(key) is not False
    ]

    if bad_true or bad_false:
        raise RuntimeError(
            "sync/async credential boundary policy invalid: "
            + repr(
                {
                    "required_true": bad_true,
                    "required_false": bad_false,
                }
            )
        )

    if (
        section.get("process_credential_capability")
        != "process.exec.credential"
    ):
        raise RuntimeError(
            "process credential capability is invalid"
        )


def _validate_context_authority_policy_v0300(
    policy: dict[str, Any],
    version: tuple[int, ...],
) -> None:
    """Fail closed on v0.30.0 context-authority/provenance invariants."""
    if version < (0, 30, 0):
        return
    section = policy.get("context_authority_policy")
    if not isinstance(section, dict):
        raise RuntimeError("context authority policy is required")

    required_true = (
        "enabled",
        "unknown_source_untrusted",
        "exact_authority_copy_may_preserve_same_authority",
        "source_locator_hash_only_persistence",
        "provenance_manifest_hash_required",
        "context_authority_hash_required",
        "transport_pack_pin_required",
        "mcp_status_read_only",
    )
    disabled = [
        key for key in required_true
        if section.get(key) is not True
    ]
    if disabled:
        raise RuntimeError(
            "context authority invariant disabled: " + repr(disabled)
        )

    required_false = (
        "evidence_instruction_authority",
        "semantic_instruction_detection_grants_authority",
        "derived_content_may_raise_authority",
        "generated_summary_instruction_authority",
        "external_content_instruction_authority",
        "tool_output_instruction_authority",
        "project_evidence_instruction_authority",
        "raw_context_persistence_allowed",
        "mcp_mutation_allowed",
    )
    poisoned = [
        key for key in required_false
        if section.get(key) is not False
    ]
    if poisoned:
        raise RuntimeError(
            "context authority fail-closed invariant violated: "
            + repr(poisoned)
        )

    if int(section.get("authority_version", 0)) != 1:
        raise RuntimeError("context authority version is invalid")
    if int(section.get("provenance_version", 0)) != 1:
        raise RuntimeError("context provenance version is invalid")
    if int(section.get("database_schema", 0)) != 63:
        raise RuntimeError("context authority schema is invalid")
    if section.get("scope") != "agentos_context_assembly":
        raise RuntimeError("context authority scope is invalid")
    if section.get("classification_basis") != "source_origin_only":
        raise RuntimeError(
            "context authority must classify by source origin"
        )

    expected_mcp_tools = {
        "agentos.context_authority_status_get",
        "agentos.context_provenance_get",
        "agentos.context_authority_explain",
        "agentos.context_authority_findings_get",
    }
    if set(section.get("mcp_read_tools", [])) != expected_mcp_tools:
        raise RuntimeError("context authority MCP read surface is invalid")
    expected_cli_commands = {
        "context-authority-status",
        "context-provenance-show",
        "context-authority-explain",
        "context-authority-findings",
    }
    if set(section.get("cli_read_commands", [])) != expected_cli_commands:
        raise RuntimeError("context authority CLI read surface is invalid")

    expected_authority = {
        "none",
        "governance",
        "human_request",
        "approved_task",
        "human_decision",
    }
    if set(section.get("authority_classes", [])) != expected_authority:
        raise RuntimeError("context authority class registry is invalid")

    expected_trust = {
        "governance_authority",
        "human_authority",
        "approved_task_authority",
        "project_evidence",
        "tool_evidence",
        "external_untrusted",
        "generated_evidence",
        "unknown_untrusted",
    }
    if set(section.get("trust_classes", [])) != expected_trust:
        raise RuntimeError("context trust class registry is invalid")

    non_claims = section.get("non_claims")
    if not isinstance(non_claims, dict):
        raise RuntimeError("context authority non-claims are required")
    required_non_claims = (
        "prompt_injection_eliminated",
        "semantic_correctness_guaranteed",
        "model_manipulation_prevented",
        "all_agent_input_channels_secured",
        "human_review_replaced",
    )
    overclaims = [
        key for key in required_non_claims
        if non_claims.get(key) is not False
    ]
    if overclaims:
        raise RuntimeError(
            "context authority overclaim: " + repr(overclaims)
        )

def _validate_governed_learning_policy_v0310(policy: dict[str, Any], version: tuple[int, ...]) -> None:
    """Fail closed on v0.31.0 governed-learning authority invariants."""
    if version < (0, 31, 0):
        return
    section = policy.get("governed_learning_policy")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        raise RuntimeError("governed learning policy is required and enabled")
    if int(section.get("version", 0)) != 1:
        raise RuntimeError("governed learning policy version is invalid")
    if int(section.get("database_schema", 0)) != 64:
        raise RuntimeError("governed learning policy schema is invalid")
    creation = section.get("signal_creation") or {}
    for key in (
        "completed_task_required_for_cross_task_learning",
        "verification_required_for_verification_signals",
        "source_hash_pin_required",
        "per_task_monotonic_sequence_required",
        "transactional_sequence_assignment_required",
    ):
        if creation.get(key) is not True:
            raise RuntimeError("governed learning signal invariant disabled:" + key)
    for key in ("same_active_session_context_reuse_allowed", "raw_content_duplication_allowed"):
        if creation.get(key) is not False:
            raise RuntimeError("governed learning safety invariant violated:" + key)
    retention = section.get("retention") or {}
    if retention.get("canonical_signal_deletion_allowed") is not False:
        raise RuntimeError("canonical learning signal deletion is forbidden in v0.31.0")
    if retention.get("automatic_archive_enabled") is not False:
        raise RuntimeError("automatic learning archive is forbidden in v0.31.0")
    promotion = section.get("promotion") or {}
    for key in (
        "automatic_memory_authority_promotion",
        "automatic_skill_graduation",
        "automatic_policy_activation",
        "automatic_architecture_mutation",
    ):
        if promotion.get(key) is not False:
            raise RuntimeError("governed learning automatic authority mutation forbidden:" + key)
    context = section.get("context") or {}
    if context.get("learning_signals_directly_injected") is not False:
        raise RuntimeError("raw learning signals must not be injected into context")
    if context.get("learning_signal_context_source_registered") is not False:
        raise RuntimeError("raw learning signal must not become a registered context source")
    if context.get("learning_derived_knowledge_uses_existing_provenance") is not True:
        raise RuntimeError("learning-derived knowledge must use existing knowledge provenance")
    if context.get("learning_derived_knowledge_trust_class") != "project_evidence":
        raise RuntimeError("learning-derived knowledge trust class is invalid")
    if context.get("learning_derived_authority_class") != "none":
        raise RuntimeError("learning-derived authority class is invalid")
    if context.get("learning_derived_instruction_authority") is not False:
        raise RuntimeError("learning-derived evidence cannot gain instruction authority")
    if context.get("context_authority_hash_may_include_learning_evidence") is not False:
        raise RuntimeError("learning-derived evidence cannot alter context authority hash")
    effectiveness = section.get("effectiveness") or {}
    if effectiveness.get("automatic_deactivation_allowed") is not False:
        raise RuntimeError("automatic learning-driven deactivation is forbidden")
    if effectiveness.get("human_review_required_for_state_change") is not True:
        raise RuntimeError("human review is required for learning-driven state change")
    if effectiveness.get("causal_effectiveness_claim_allowed") is not False:
        raise RuntimeError("causal effectiveness claims are forbidden in v0.31.0")
    mcp = section.get("mcp") or {}
    if mcp.get("mutation_allowed") is not False or mcp.get("read_only") is not True:
        raise RuntimeError("governed learning MCP must remain read-only")
    expected_tools = {
        "agentos.learning_signals_get",
        "agentos.learning_signal_links_get",
        "agentos.knowledge_usage_get",
        "agentos.learning_status_get",
    }
    if set(mcp.get("tools", [])) != expected_tools:
        raise RuntimeError("governed learning MCP read surface is invalid")

def validate_policy(policy: dict[str, Any]) -> None:
    """Fail closed while preserving historical policy contracts by release version."""
    required = {"version", "instruction_policy", "filesystem_policy", "claim_policy", "workflows", "workflow_policy", "drift_policy", "tool_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy", "context_transport_policy", "adaptive_token_budget_policy", "architecture_contract_policy", "human_clarification_policy"}
    version = _policy_version_tuple(policy)
    _validate_windows_process_tree_policy_v0291(
        policy,
        version,
    )
    _validate_sandbox_workspace_runtime_profile_policy_v0292(
        policy,
        version,
    )
    _validate_sandbox_configuration_contract_v0293_preactivation(
        policy,
    )
    _validate_credential_reference_contract_v0293_preactivation(
        policy,
    )
    _validate_sync_credential_boundary_v0293_preactivation(
        policy,
    )
    _validate_context_authority_policy_v0300(
        policy,
        version,
    )
    _validate_governed_learning_policy_v0310(
        policy,
        version,
    )
    if version >= (0, 27, 0):
        required.add("governed_skill_contract_policy")
    if version >= (0, 27, 1):
        required.add("architecture_aware_skill_selection_policy")
    if version >= (0, 28, 1):
        required.add("command_center_policy")
        required.add("web_control_plane_policy")
    if version >= (0, 28, 3):
        required.add("privileged_control_plane_policy")
    if version >= (0, 29, 0):
        required.add("completion_verification_policy")
    if version >= (0, 29, 2):
        required.add("sandbox_workspace_runtime_profile_policy")
    if version >= (0, 30, 0):
        required.add("context_authority_policy")
    if version >= (0, 31, 0):
        required.add("governed_learning_policy")
    missing = sorted(required - policy.keys())
    if missing:
        raise RuntimeError(f"missing policy keys: {missing}")
    architecture = policy["architecture_contract_policy"]
    if architecture.get("enabled") is not True or int(architecture.get("section_count", 0)) != 27:
        raise RuntimeError("architecture contract policy is invalid")
    architecture_required_false = (
        "ai_may_activate_architecture", "ai_may_approve_architecture", "working_copy_is_authority",
        "mcp_architecture_mutation_allowed", "architecture_discovery_enabled_v0252", "architecture_drift_enforcement_enabled_v0252",
    )
    poisoned_architecture = [key for key in architecture_required_false if architecture.get(key) is not False]
    if poisoned_architecture:
        raise RuntimeError(f"architecture authority invariant violated: {poisoned_architecture}")
    if version >= (0, 27, 0):
        skill_contract = policy["governed_skill_contract_policy"]
        skill_required_true = (
            "enabled", "new_candidates_require_v2", "legacy_v1_preserved",
            "human_graduation_required", "human_revocation_required",
            "contract_validation_deterministic", "architecture_sensitive_contract_requires_active_baseline",
            "architecture_baseline_hash_pin_required",
        )
        disabled_skill = [key for key in skill_required_true if skill_contract.get(key) is not True]
        if disabled_skill:
            raise RuntimeError(f"governed skill contract invariant disabled: {disabled_skill}")
        skill_required_false = (
            "legacy_v1_in_place_rewrite", "skill_may_exceed_task_authority",
            "skill_may_exceed_architecture_authority", "mcp_mutation_allowed",
            "automatic_skill_selection_enabled",
        )
        poisoned_skill = [key for key in skill_required_false if skill_contract.get(key) is not False]
        if poisoned_skill:
            raise RuntimeError(f"governed skill contract authority invariant violated: {poisoned_skill}")
        if int(skill_contract.get("contract_version", 0)) != 2:
            raise RuntimeError("governed skill contract version must be 2")
        if set(skill_contract.get("allowed_risk_tiers", [])) != {"low", "medium", "high"}:
            raise RuntimeError("governed skill risk-tier allowlist is invalid")
        if version == (0, 27, 0) and skill_contract.get("selection_evaluation_reserved_for_v0271") is not True:
            raise RuntimeError("v0.27.0 must reserve skill selection/evaluation for v0.27.1")
        if version >= (0, 27, 1):
            if skill_contract.get("selection_evaluation_reserved_for_v0271") is not False:
                raise RuntimeError("v0.27.1+ skill selection/evaluation reservation must be released")
            if skill_contract.get("architecture_aware_selection_available") is not True:
                raise RuntimeError("v0.27.1+ architecture-aware skill selection must be explicitly available")

    if version >= (0, 27, 1):
        selection = policy["architecture_aware_skill_selection_policy"]
        selection_required_true = (
            "enabled", "deterministic_local_ranking_required", "selection_is_advisory",
            "active_plan_context_required", "graduated_v2_only", "stale_contract_selection_blocked",
            "architecture_mismatch_selection_blocked", "task_scope_subset_required",
            "required_capabilities_must_be_available", "required_tools_must_be_available",
            "human_authority_unchanged",
        )
        disabled_selection = [key for key in selection_required_true if selection.get(key) is not True]
        if disabled_selection:
            raise RuntimeError(f"architecture-aware skill selection invariant disabled: {disabled_selection}")
        selection_required_false = (
            "legacy_v1_selection_allowed", "automatic_execution_allowed", "automatic_skill_graduation_allowed",
            "automatic_skill_revocation_allowed", "selection_changes_plan_authority",
            "evaluation_changes_skill_lifecycle", "evaluation_changes_future_selection_weights",
            "mcp_mutation_allowed", "model_provider_selection_authority",
        )
        poisoned_selection = [key for key in selection_required_false if selection.get(key) is not False]
        if poisoned_selection:
            raise RuntimeError(f"architecture-aware skill selection authority invariant violated: {poisoned_selection}")
        if int(selection.get("database_schema", 0)) != 59 or int(selection.get("selection_version", 0)) != 1 or int(selection.get("evaluation_version", 0)) != 1:
            raise RuntimeError("architecture-aware skill selection version/schema is invalid")
        positive = float(selection.get("positive_test_pass_rate_min", -1))
        negative = float(selection.get("negative_test_pass_rate_below", -1))
        if not (0.0 <= negative < positive <= 1.0):
            raise RuntimeError("architecture-aware skill evaluation thresholds are invalid")
        if int(selection.get("high_rework_threshold", 0)) < 2:
            raise RuntimeError("architecture-aware skill evaluation rework threshold is invalid")
        if int(selection.get("max_candidates", 0)) < 1:
            raise RuntimeError("architecture-aware skill selection candidate limit is invalid")

    if version >= (0, 28, 1):
        web = policy["web_control_plane_policy"]
        web_required_true = (
            "enabled", "optional", "loopback_only", "command_center_read_model_only",
            "host_header_validation_required", "same_origin_bootstrap_required",
            "one_time_bootstrap_required",
        )
        web_disabled = [key for key in web_required_true if web.get(key) is not True]
        if web_disabled:
            raise RuntimeError(f"web control plane invariant disabled: {web_disabled}")
        web_required_false = (
            "direct_database_access", "mutation_authority", "privileged_cli_execution_allowed",
            "architecture_approval_authority", "integration_approval_authority",
            "worker_launch_authority", "model_provider_selection_authority",
            "external_assets_allowed", "cors_allowed", "websocket_allowed",
        )
        web_poisoned = [key for key in web_required_false if web.get(key) is not False]
        if web_poisoned:
            raise RuntimeError(f"web control plane authority invariant violated: {web_poisoned}")
        expected_web_schema = (
            63
            if version >= (0, 30, 0)
            else 62
            if version >= (0, 29, 0)
            else 61
        )

        if (
            int(web.get("database_schema", 0))
            != expected_web_schema
            or int(web.get("web_version", 0)) != 1
        ):
            raise RuntimeError(
                "web control plane version/schema is invalid"
            )
        if str(web.get("default_host")) != "127.0.0.1":
            raise RuntimeError("web control plane default host must be loopback")
        port = int(web.get("default_port", 0) or 0)
        if port < 1 or port > 65535:
            raise RuntimeError("web control plane default port is invalid")
        ttl = int(web.get("session_ttl_seconds", 0) or 0)
        if ttl < 60 or ttl > 86400:
            raise RuntimeError("web control plane session ttl is invalid")
        command_center = policy["command_center_policy"]
        if command_center.get("web_control_plane_reserved_for_v0281") is not False:
            raise RuntimeError("v0.28.1 web control plane reservation must be released")
        if command_center.get("web_control_plane_available") is not True:
            raise RuntimeError("v0.28.1 web control plane must be explicitly available")
    if version >= (0, 28, 3):
        control = policy["privileged_control_plane_policy"]

        control_required_true = (
            "enabled",
            "privileged_control_plane_required",
            "control_plane_allowlist_explicit",
            "dual_plane_argument_enforcement",
            "existing_governed_mutation_enforcement_preserved",
            "human_authority_preserved",
        )

        disabled_control = [
            key
            for key in control_required_true
            if control.get(key) is not True
        ]

        if disabled_control:
            raise RuntimeError(
                "privileged control-plane invariant disabled: "
                f"{disabled_control}"
            )

        control_required_false = (
            "agent_plane_privileged_execution_allowed",
            "mcp_privileged_mutation_exposed",
            "web_mutation_authority",
        )

        poisoned_control = [
            key
            for key in control_required_false
            if control.get(key) is not False
        ]

        if poisoned_control:
            raise RuntimeError(
                "privileged control-plane authority invariant "
                f"violated: {poisoned_control}"
            )

        if version == (0, 28, 3):
            if (
                control.get(
                    "hard_anti_bypass_reserved_for_v0284"
                )
                is not True
            ):
                raise RuntimeError(
                    "v0.28.3 must reserve hard anti-bypass "
                    "attestation for v0.28.4"
                )

            if (
                control.get("tool_exclusivity_attested")
                is not False
            ):
                raise RuntimeError(
                    "v0.28.3 must not declare tool exclusivity"
                )

        if version >= (0, 28, 4):
            if (
                control.get(
                    "hard_anti_bypass_reserved_for_v0284"
                )
                is not False
            ):
                raise RuntimeError(
                    "v0.28.4+ must release the v0.28.4 "
                    "anti-bypass reservation"
                )

            if (
                control.get("tool_exclusivity_attested")
                is not True
            ):
                raise RuntimeError(
                    "v0.28.4+ requires tool exclusivity "
                    "attestation"
                )

            if (
                control.get("tool_exclusivity_scope")
                != "agentos_mediated_agent_execution"
            ):
                raise RuntimeError(
                    "v0.28.4+ tool exclusivity scope is invalid"
                )

            if int(
                control.get(
                    "enforcement_attestation_version",
                    0,
                )
            ) != 1:
                raise RuntimeError(
                    "v0.28.4+ enforcement attestation "
                    "version must be 1"
                )

            non_claim_keys = (
                "same_user_host_bypass_resistance_claimed",
                "os_level_process_isolation_attested",
                "arbitrary_host_process_containment_attested",
            )

            invalid_non_claims = [
                key
                for key in non_claim_keys
                if control.get(key) is not False
            ]

            if invalid_non_claims:
                raise RuntimeError(
                    "v0.28.4+ enforcement scope overclaim: "
                    f"{invalid_non_claims}"
                )

        expected_control_schema = (
            62
            if version >= (0, 29, 0)
            else 61
        )

        if (
            int(control.get("database_schema", 0))
            != expected_control_schema
        ):
            raise RuntimeError(
                "privileged control-plane schema is invalid"
            )

        if int(control.get("control_plane_version", 0)) != 1:
            raise RuntimeError(
                "privileged control-plane version is invalid"
            )

        if control.get("agent_entrypoint") != "agentos.cli_runtime":
            raise RuntimeError(
                "agent execution-plane entrypoint is invalid"
            )

        if (
            control.get("admin_entrypoint")
            != "agentos.privileged_control_plane"
        ):
            raise RuntimeError(
                "privileged control-plane entrypoint is invalid"
            )

        if control.get("agent_launcher") != "agentos":
            raise RuntimeError(
                "agent execution-plane launcher is invalid"
            )

        if control.get("admin_launcher") != "agentos-admin":
            raise RuntimeError(
                "privileged control-plane launcher is invalid"
            )

        if set(control.get("dual_plane_commands", [])) != {
            "architecture-init",
            "project-adopt",
        }:
            raise RuntimeError(
                "dual-plane command allowlist is invalid"
            )

    if version >= (0, 29, 0):
        completion = policy[
            "completion_verification_policy"
        ]

        completion_required_true = (
            "enabled",
            "independent_completion_attested",
            "producer_task_independence_required",
            "producer_session_independence_required",
            "reviewer_role_required",
            "subject_hash_binding_required",
            "fresh_receipt_required",
            "evidence_required_for_pass",
            "workflow_report_receipt_binding_required",
            "worker_completion_receipt_required",
            "integration_receipt_revalidation_required",
            "mcp_status_read_only",
        )

        disabled_completion = [
            key
            for key in completion_required_true
            if completion.get(key) is not True
        ]

        if disabled_completion:
            raise RuntimeError(
                "independent completion invariant disabled: "
                f"{disabled_completion}"
            )

        completion_required_false = (
            "mcp_mutation_allowed",
            "semantic_correctness_guaranteed",
            "model_provider_independence_attested",
            "human_review_replaced",
            "human_approval_replaced",
        )

        poisoned_completion = [
            key
            for key in completion_required_false
            if completion.get(key) is not False
        ]

        if poisoned_completion:
            raise RuntimeError(
                "independent completion scope/authority overclaim: "
                f"{poisoned_completion}"
            )

        if int(
            completion.get(
                "verification_version",
                0,
            )
        ) != 1:
            raise RuntimeError(
                "independent completion verification version is invalid"
            )

        if int(
            completion.get(
                "database_schema",
                0,
            )
        ) != 62:
            raise RuntimeError(
                "independent completion schema is invalid"
            )

        if (
            completion.get("scope")
            != "agentos_mediated_agent_execution"
        ):
            raise RuntimeError(
                "independent completion attestation scope is invalid"
            )

    clarification = policy["human_clarification_policy"]
    clarification_required_true = (
        "enabled", "structured_clarity_assessment_required", "no_silent_material_assumptions",
        "task_approval_requires_clear_assessment", "blocking_decisions_block_dependent_mutation",
        "llm_may_open_blocking_decision", "human_resolution_lossless_local_persistence",
        "resolution_revalidation_required",
    )
    disabled_clarification = [key for key in clarification_required_true if clarification.get(key) is not True]
    if disabled_clarification:
        raise RuntimeError(f"human clarification invariant disabled: {disabled_clarification}")
    clarification_required_false = (
        "llm_may_resolve_decision", "llm_may_waive_decision", "llm_may_silently_select_material_option",
        "raw_human_answer_external_audit_allowed",
    )
    poisoned_clarification = [key for key in clarification_required_false if clarification.get(key) is not False]
    if poisoned_clarification:
        raise RuntimeError(f"human clarification authority invariant violated: {poisoned_clarification}")
    if clarification.get("mcp_monotonic_blocker_signal_allowed") is not True:
        raise RuntimeError("human clarification MCP blocker signal must be explicitly monotonic")
    if clarification.get("mcp_monotonic_blocker_tool") != "agentos.human_decision_request":
        raise RuntimeError("human clarification MCP blocker tool is invalid")
    if clarification.get("mcp_human_decision_resolution_allowed") is not False:
        raise RuntimeError("human decision resolution over MCP is forbidden")
    if int(clarification.get("max_open_blocking_decisions_per_task", 0) or 0) != 32:
        raise RuntimeError("human decision open-blocker limit is invalid")

    claim = policy["claim_policy"]
    if set(claim.get("claim_types", [])) != CLAIM_TYPES or set(claim.get("risk_levels", [])) != RISK_LEVELS:
        raise RuntimeError("claim policy allowlists are invalid")
    enforcement = policy["governance_enforcement_policy"]
    required_true = (
        "enabled", "valid_project_root_requires_governed_mutations", "require_task_id", "require_session_id",
        "require_task_approval", "require_task_owner_session", "require_workflow_approval_step",
        "require_initialized_baseline", "block_on_drift", "sensitive_override_requires_approval",
        "one_time_execution_token_required", "signed_request_event_required", "signed_domain_event_required",
        "signed_completion_event_required", "denied_operations_signed", "signed_audit_failure_blocks_mutation",
    )
    disabled = [key for key in required_true if enforcement.get(key) is not True]
    if disabled:
        raise RuntimeError(f"unified governance enforcement invariant disabled: {disabled}")
    required_false = [
        ("database_boundary_policy", "source_insert_allowed"),
        ("database_boundary_policy", "source_update_allowed"),
        ("database_boundary_policy", "source_delete_allowed"),
        ("controlled_target_insert_policy", "raw_target_insert_allowed"),
        ("controlled_target_insert_policy", "source_write_allowed"),
        ("controlled_target_insert_policy", "update_allowed"),
        ("controlled_target_insert_policy", "upsert_allowed"),
        ("controlled_target_insert_policy", "delete_allowed"),
        ("identity_resolution_policy", "llm_may_decide_identity"),
        ("reconciliation_recovery_policy", "in_doubt_auto_retry_allowed"),
        ("reconciliation_recovery_policy", "in_doubt_auto_resolution_allowed"),
        ("reconciliation_recovery_policy", "partial_target_auto_repair_allowed"),
    ]
    poisoned = [f"{section}.{key}" for section, key in required_false if policy[section].get(key) is not False]
    if poisoned:
        raise RuntimeError(f"non-overridable safety invariant violated: {poisoned}")
    runtime = policy["unified_runtime_policy"]
    runtime_required_true = (
        "enabled", "single_python_cli_runtime_required", "single_python_mcp_runtime_required",
        "windows_posix_cli_parity_required", "windows_posix_mcp_parity_required",
        "unknown_cli_command_must_fail", "unknown_mcp_method_must_return_jsonrpc_error",
        "mcp_health_tool_required", "legacy_launchers_may_exist_but_must_not_be_active",
    )
    runtime_disabled = [key for key in runtime_required_true if runtime.get(key) is not True]
    if runtime_disabled:
        raise RuntimeError(f"unified runtime invariant disabled: {runtime_disabled}")
    runtime_required_false = (
        "version_forwarding_runtime_allowed", "mcp_subprocess_forwarding_allowed",
        "duplicate_cli_commands_allowed", "duplicate_mcp_tools_allowed",
        "extension_mutation_tools_exposed_over_mcp",
    )
    runtime_poisoned = [key for key in runtime_required_false if runtime.get(key) is not False]
    if runtime_poisoned:
        raise RuntimeError(f"unified runtime fail-closed invariant violated: {runtime_poisoned}")
    if runtime.get("monotonic_blocker_signal_allowed") is not True:
        raise RuntimeError("unified runtime monotonic blocker signal must be enabled")
    if runtime.get("monotonic_blocker_signal_tools") != ["agentos.human_decision_request"]:
        raise RuntimeError("unified runtime monotonic blocker tool allowlist is invalid")

    transport = policy["context_transport_policy"]
    transport_required_true = (
        "original_user_request_verbatim_required",
        "original_user_request_hash_required",
        "requirement_ledger_required",
        "stable_requirement_ids",
        "agents_authority_verbatim_required",
        "approved_scope_lossless_required",
        "active_plan_hash_required",
        "policy_authority_hash_required",
        "source_freshness_required",
        "transport_integrity_hash_required",
        "fail_closed_if_control_plane_exceeds_budget",
        "tokenizer_abstraction_required",
        "expansion_read_only",
        "evaluation_shadow_framework",
        "adaptive_token_budget_enabled",
        "model_profile_hash_pin_required",
        "budget_decision_persistence_required",
    )
    disabled_transport = [key for key in transport_required_true if transport.get(key) is not True]
    if disabled_transport:
        raise RuntimeError(f"context transport invariant disabled: {disabled_transport}")
    transport_required_false = (
        "protected_content_translation_allowed",
        "protected_content_paraphrase_allowed",
        "protected_content_summarization_allowed",
        "protected_content_token_pruning_allowed",
        "protected_content_word_level_deletion_allowed",
        "generative_llm_summarization_allowed",
        "gzip_base64_minify_as_semantic_compression_allowed",
        "mcp_mutation_allowed",
        "token_observation_content_persistence_allowed",
        "network_model_profile_discovery_allowed",
        "provider_api_model_profile_discovery_allowed",
        "dynamic_model_profile_code_allowed",
        "tokenizer_auto_download_allowed",
    )
    poisoned_transport = [key for key in transport_required_false if transport.get(key) is not False]
    if poisoned_transport:
        raise RuntimeError(f"context transport fail-closed invariant violated: {poisoned_transport}")
    if float(transport.get("requirement_preservation_rate_required", 0.0)) != 1.0:
        raise RuntimeError("context transport requires 100% protected requirement preservation")

    adaptive = policy["adaptive_token_budget_policy"]
    adaptive_required_true = (
        "profile_hash_pin_required",
        "calibration_enabled",
        "calibration_numeric_only",
        "fail_closed_if_control_plane_exceeds_budget",
        "agentos_budget_profile_must_not_switch_provider_or_model",
    )
    disabled_adaptive = [key for key in adaptive_required_true if adaptive.get(key) is not True]
    if disabled_adaptive:
        raise RuntimeError(f"adaptive token budget invariant disabled: {disabled_adaptive}")
    adaptive_required_false = (
        "network_model_discovery_allowed",
        "provider_api_profile_discovery_allowed",
        "dynamic_profile_code_allowed",
        "tokenizer_auto_download_allowed",
        "calibration_prompt_content_persist_allowed",
        "calibration_response_content_persist_allowed",
        "calibration_can_reduce_safety_margin",
        "calibration_can_reduce_output_floor",
        "mcp_observation_mutation_allowed",
        "mcp_profile_mutation_allowed",
        "mcp_budget_mutation_allowed",
    )
    poisoned_adaptive = [key for key in adaptive_required_false if adaptive.get(key) is not False]
    if poisoned_adaptive:
        raise RuntimeError(f"adaptive token budget fail-closed invariant violated: {poisoned_adaptive}")
    if adaptive.get("default_mode") not in {"adaptive", "fixed"}:
        raise RuntimeError("adaptive token budget default_mode is invalid")
    if set(adaptive.get("allowed_modes", [])) != {"adaptive", "fixed"}:
        raise RuntimeError("adaptive token budget allowed_modes are invalid")
    if adaptive.get("algorithm") != "adaptive_budget_v1":
        raise RuntimeError("adaptive token budget algorithm is invalid")
    observation_sources = set(adaptive.get("observation_sources", []))
    expected_observation_sources = {
        "runtime_report", "provider_usage", "tokenizer_probe",
        "operator_verified", "benchmark", "local_runtime",
    }
    if observation_sources != expected_observation_sources:
        raise RuntimeError("adaptive token observation-source allowlist is invalid")
    calibration_window = int(adaptive.get("calibration_window", 0) or 0)
    if calibration_window < 1 or calibration_window > 512:
        raise RuntimeError("adaptive token calibration window is invalid")
    if adaptive.get("model_switching_authority") != "external_runtime_only":
        raise RuntimeError("AgentOS must not gain provider/model switching authority")

    profiles = transport.get("model_profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        raise RuntimeError("context transport model_profiles registry is missing")
    forbidden_profile_keys = {"importlib", "module", "function", "callable", "command", "executable", "provider_api"}
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            raise RuntimeError(f"model profile must be data-only object: {profile_name}")
        if forbidden_profile_keys & set(profile):
            raise RuntimeError(f"dynamic model profile code/discovery is forbidden: {profile_name}")
        try:
            capacity = int(profile.get("context_capacity", 0) or 0)
            output_min = int(profile.get("reserved_output_min", 0) or 0)
            output_default = int(profile.get("reserved_output_default", 0) or 0)
            output_max = int(profile.get("reserved_output_max", 0) or 0)
            safety_min = int(profile.get("safety_margin_min", 0) or 0)
            overhead = int(profile.get("system_tool_overhead", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"model profile numeric fields are invalid: {profile_name}") from exc
        if capacity < 128 or min(output_min, output_default, output_max, safety_min, overhead) < 0:
            raise RuntimeError(f"model profile budget values are invalid: {profile_name}")
        if not (output_min <= output_default <= output_max < capacity):
            raise RuntimeError(f"model profile output bounds are invalid: {profile_name}")
        if str(profile.get("tokenizer", "auto")) not in {"auto", "heuristic", "tiktoken"}:
            raise RuntimeError(f"model profile tokenizer policy is invalid: {profile_name}")
