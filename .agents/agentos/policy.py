"""
File: .agents/agentos/policy.py

Purpose:
    Load and validate machine-readable AgentOS governance policy.

Responsibilities:
    - Parse governance.json.
    - Fail closed when required policy fields are missing or invalid.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CLAIM_TYPES = {"business_logic", "security", "data_behavior", "destructive_effect", "governance", "other"}
RISK_LEVELS = {"low", "medium", "high"}


def load_policy(root: Path) -> dict[str, Any]:
    """Load and validate project governance policy.

    Args:
        root: Project root.

    Returns:
        Validated policy dictionary.

    Raises:
        RuntimeError: Policy is missing or invalid.
    """
    path = root.resolve() / ".agents" / "config" / "governance.json"
    if not path.exists():
        raise RuntimeError("governance policy not found")
    policy = json.loads(path.read_text(encoding="utf-8"))
    local_path = root.resolve() / ".agents" / "config" / "governance.local.json"
    if local_path.exists():
        override = json.loads(local_path.read_text(encoding="utf-8"))
        if not isinstance(override, dict):
            raise RuntimeError("governance.local.json must contain an object")
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(policy.get(key), dict):
                policy[key] = {**policy[key], **value}
            else:
                policy[key] = value
    validate_policy(policy)
    return policy


def validate_policy(policy: dict[str, Any]) -> None:
    """Validate required AgentOS policy contracts.

    Args:
        policy: Parsed governance policy.

    Returns:
        None.

    Raises:
        RuntimeError: A required field is missing or invalid.
    """
    required = ["version", "filesystem_policy", "claim_policy", "workflows"]
    for key in required:
        if key not in policy:
            raise RuntimeError(f"missing policy key: {key}")
    claim = policy["claim_policy"]
    if set(claim.get("claim_types", [])) != CLAIM_TYPES:
        raise RuntimeError("claim_policy.claim_types is invalid")
    if set(claim.get("risk_levels", [])) != RISK_LEVELS:
        raise RuntimeError("claim_policy.risk_levels is invalid")
    for key in ("require_evidence_for_high_risk", "require_successful_evidence", "require_same_task_evidence"):
        if claim.get(key) is not True:
            raise RuntimeError(f"claim_policy.{key} must be true")
