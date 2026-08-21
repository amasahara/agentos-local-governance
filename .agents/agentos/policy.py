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
SENSITIVE_SECTIONS = {"claim_policy", "filesystem_policy", "tool_policy", "workflow_policy", "drift_policy", "instruction_policy", "task_context_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy", "context_transport_policy", "adaptive_token_budget_policy", "architecture_contract_policy", "human_clarification_policy", "governed_skill_contract_policy", "architecture_aware_skill_selection_policy"}
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


def validate_policy(policy: dict[str, Any]) -> None:
    """Fail closed while preserving historical policy contracts by release version."""
    required = {"version", "instruction_policy", "filesystem_policy", "claim_policy", "workflows", "workflow_policy", "drift_policy", "tool_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy", "context_transport_policy", "adaptive_token_budget_policy", "architecture_contract_policy", "human_clarification_policy"}
    version = _policy_version_tuple(policy)
    if version >= (0, 27, 0):
        required.add("governed_skill_contract_policy")
    if version >= (0, 27, 1):
        required.add("architecture_aware_skill_selection_policy")
    if version >= (0, 28, 1):
        required.add("command_center_policy")
        required.add("web_control_plane_policy")
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
        if int(web.get("database_schema", 0)) != 61 or int(web.get("web_version", 0)) != 1:
            raise RuntimeError("web control plane version/schema is invalid")
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
