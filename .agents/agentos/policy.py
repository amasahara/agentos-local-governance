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
SENSITIVE_SECTIONS = {"claim_policy", "filesystem_policy", "tool_policy", "workflow_policy", "drift_policy", "instruction_policy", "task_context_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy"}
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
    required = {"version", "instruction_policy", "filesystem_policy", "claim_policy", "workflows", "workflow_policy", "drift_policy", "tool_policy", "project_identity_policy", "primary_project_selection_policy", "primary_project_consolidation_policy", "database_boundary_policy", "schema_mapping_policy", "read_only_extraction_policy", "controlled_target_insert_policy", "identity_resolution_policy", "reconciliation_recovery_policy"}
    missing = sorted(required - policy.keys())
    if missing:
        raise RuntimeError(f"missing policy keys: {missing}")
    claim = policy["claim_policy"]
    if set(claim.get("claim_types", [])) != CLAIM_TYPES or set(claim.get("risk_levels", [])) != RISK_LEVELS:
        raise RuntimeError("claim policy allowlists are invalid")
