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
SENSITIVE_SECTIONS = {"claim_policy", "filesystem_policy", "tool_policy", "workflow_policy", "drift_policy", "instruction_policy", "task_context_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy", "context_transport_policy", "adaptive_token_budget_policy"}
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


def load_policy(root: Path) -> dict[str, Any]:
    """Load governance policy and merge only approved sensitive overrides."""
    base_path = root / ".agents" / "config" / "governance.json"
    policy = json.loads(base_path.read_text(encoding="utf-8"))
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


def validate_policy(policy: dict[str, Any]) -> None:
    """Fail closed when mandatory policy sections are absent or invalid."""
    required = {"version", "instruction_policy", "filesystem_policy", "claim_policy", "workflows", "workflow_policy", "drift_policy", "tool_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy", "context_transport_policy", "adaptive_token_budget_policy"}
    missing = sorted(required - policy.keys())
    if missing:
        raise RuntimeError(f"missing policy keys: {missing}")
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
