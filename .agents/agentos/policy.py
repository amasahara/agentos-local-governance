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
SENSITIVE_SECTIONS = {"claim_policy", "filesystem_policy", "tool_policy", "workflow_policy", "drift_policy", "instruction_policy", "task_context_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy"}
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
    required = {"version", "instruction_policy", "filesystem_policy", "claim_policy", "workflows", "workflow_policy", "drift_policy", "tool_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy", "governance_enforcement_policy", "unified_runtime_policy"}
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
