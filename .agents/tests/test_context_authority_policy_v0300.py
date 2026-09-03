"""
Focused v0.30.0 Phase 2 tests for schema and policy activation.
"""
from __future__ import annotations

from pathlib import Path

from agentos import db
from agentos.context_authority import migration_63
from agentos.policy import load_release_policy, validate_policy
from agentos.schema_version import CURRENT_SCHEMA_VERSION


def _project_root() -> Path:
    """Return the repository root without relying on a pytest fixture."""
    return Path(__file__).resolve().parents[2]


def test_schema_63_is_last_registered_migration() -> None:
    migrations = db._all_migrations()
    assert CURRENT_SCHEMA_VERSION == 63
    assert len(migrations) == 63
    assert migrations[-1] is migration_63


def test_release_policy_activates_context_authority() -> None:
    root = _project_root()
    current = (root / "VERSION").read_text(encoding="utf-8").strip()
    policy = load_release_policy(root)
    assert policy["version"] == current
    assert CURRENT_SCHEMA_VERSION >= 63
    section = policy["context_authority_policy"]
    assert section["database_schema"] == 63
    assert section["classification_basis"] == "source_origin_only"
    assert section["unknown_source_untrusted"] is True
    assert section["derived_content_may_raise_authority"] is False
    assert section["mcp_mutation_allowed"] is False
    validate_policy(policy)


def test_context_authority_nonclaims_remain_false() -> None:
    section = load_release_policy(_project_root())["context_authority_policy"]
    assert section["non_claims"] == {
        "prompt_injection_eliminated": False,
        "semantic_correctness_guaranteed": False,
        "model_manipulation_prevented": False,
        "all_agent_input_channels_secured": False,
        "human_review_replaced": False,
    }
