"""Focused v0.31.3 learning effectiveness and drift tests."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import agentos.learning_effectiveness as le
from agentos import cli_runtime, mcp_runtime
from agentos.schema_version import CURRENT_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]


CFG = {
    "minimum_treatment_tasks": 5,
    "minimum_control_tasks": 5,
    "minimum_distinct_tasks": 5,
    "window_days": 90,
    "small_sample_warning_below": 30,
    "significance_alpha": 0.05,
    "minimum_effect_size": 0.10,
}


def test_v0313_schema_stays_64_without_migration_65() -> None:
    assert CURRENT_SCHEMA_VERSION == 64
    source = (ROOT / ".agents/agentos/db.py").read_text(encoding="utf-8")
    assert "migration_65" not in source
    assert "from .learning_signals import migration_64" in source


def test_v0313_effectiveness_policy_preserves_human_authority() -> None:
    policy = json.loads(
        (ROOT / ".agents/config/policy/learning.json").read_text(encoding="utf-8")
    )["governed_learning_policy"]["effectiveness"]
    assert policy["comparative_effectiveness_enabled"] is True
    assert policy["drift_detection_enabled"] is True
    assert policy["actual_context_inclusion_required"] is True
    assert policy["automatic_review_request_creation"] is False
    assert policy["automatic_deactivation_allowed"] is False
    assert policy["automatic_supersede_allowed"] is False
    assert policy["automatic_stale_status_mutation"] is False
    assert policy["human_review_required_for_state_change"] is True
    assert policy["causal_effectiveness_claim_allowed"] is False
    assert policy["provider_model_matching_required"] is False
    assert policy["mcp_mutation_allowed"] is False


def test_insufficient_sample_warns_without_ineffective_verdict() -> None:
    result = le._classify_comparison(
        treatment_successes=0,
        treatment_n=2,
        control_successes=2,
        control_n=2,
        distinct_treatment_tasks=2,
        distinct_control_tasks=2,
        cfg=CFG,
    )
    assert result["verdict"] == "insufficient_evidence"
    assert result["sufficient_evidence"] is False
    assert "small_sample_warning" in result["warnings"]


def test_large_significantly_worse_cohort_is_only_possibly_ineffective() -> None:
    result = le._classify_comparison(
        treatment_successes=12,
        treatment_n=40,
        control_successes=32,
        control_n=40,
        distinct_treatment_tasks=40,
        distinct_control_tasks=40,
        cfg=CFG,
    )
    assert result["verdict"] == "possibly_ineffective"
    assert result["comparison"]["effect_size"] < 0
    assert result["comparison"]["p_value"] < 0.05


def test_unrelated_architecture_change_does_not_stale_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class C:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, params=()):
            if "FROM promoted_skills" in sql:
                return R({
                    "id": 1,
                    "status": "graduated",
                    "graduated_path": "",
                    "architecture_baseline_id": 1,
                    "architecture_baseline_hash": "a" * 64,
                })
            if "FROM skill_contracts" in sql:
                return R({
                    "architecture_baseline_id": 1,
                    "architecture_baseline_hash": "a" * 64,
                    "contract_json": json.dumps({
                        "required_architecture_sections": ["ARCH-03"],
                        "allowed_read_scope": [],
                        "allowed_write_scope": [],
                        "allowed_dependencies": [],
                        "allowed_external_services": [],
                        "architecture_constraints": {},
                    }),
                })
            raise AssertionError(sql)

    class R:
        def __init__(self, row):
            self.row = row
        def fetchone(self):
            return self.row

    monkeypatch.setattr(le, "connect_read_only", lambda _r: C())
    monkeypatch.setattr(
        le,
        "_baseline_sections",
        lambda _c, baseline_id: {
            "ARCH-03": {
                "section_id": "ARCH-03",
                "section_hash": "same",
                "applicability": "applicable",
            }
        },
    )
    result = le._skill_drift(
        Path("."),
        1,
        {"id": 2, "baseline_hash": "b" * 64},
    )
    assert result["state"] == "current"
    assert result["reason"] == "unrelated_architecture_sections_changed_only"


def test_memory_baseline_change_requires_review_not_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class C:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, params=()):
            if "FROM project_memory" in sql:
                return R({
                    "id": 4,
                    "status": "active",
                    "source_path": None,
                })
            if "SELECT DISTINCT pf.path" in sql:
                return Rows([])
            raise AssertionError(sql)

    class R:
        def __init__(self, row):
            self.row = row
        def fetchone(self):
            return self.row

    class Rows:
        def __init__(self, rows):
            self.rows = rows
        def fetchall(self):
            return self.rows

    monkeypatch.setattr(le, "connect_read_only", lambda _r: C())
    monkeypatch.setattr(
        le,
        "_linked_learning_architecture",
        lambda *_args, **_kwargs: "a" * 64,
    )
    result = le._memory_drift(
        Path("."),
        4,
        {"id": 2, "baseline_hash": "b" * 64},
    )
    assert result["state"] == "review_required_architecture_change"


def test_review_request_binds_exact_assessment_and_uses_existing_human_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        le,
        "_policy",
        lambda _r: {
            "review_options": [
                "retain",
                "revise",
                "supersede",
                "deactivate",
            ]
        },
    )
    assessment = {
        "ok": True,
        "assessment_hash": "f" * 64,
        "review_recommended": True,
        "effectiveness": {"verdict": "possibly_ineffective"},
        "drift": {"state": "current"},
    }
    monkeypatch.setattr(
        le,
        "learning_assessment",
        lambda *_args, **_kwargs: assessment,
    )
    called = {}
    monkeypatch.setattr(
        le,
        "request_human_decision",
        lambda *args, **kwargs: called.update({"args": args, "kwargs": kwargs}) or {
            "decision_uuid": "D-1"
        },
    )
    result = le.request_learning_review(
        Path("."),
        knowledge_kind="memory",
        knowledge_id=4,
        expected_assessment_hash="f" * 64,
        task_id="T1",
        raised_by_session="S1",
    )
    assert result["review_requested"] is True
    assert result["automatic_state_change"] is False
    assert called["kwargs"]["options"] == [
        "retain",
        "revise",
        "supersede",
        "deactivate",
    ]


def test_wrong_assessment_hash_blocks_review_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        le,
        "_policy",
        lambda _r: {
            "review_options": ["retain", "revise", "supersede", "deactivate"]
        },
    )
    monkeypatch.setattr(
        le,
        "learning_assessment",
        lambda *_args, **_kwargs: {
            "assessment_hash": "a" * 64,
            "review_recommended": True,
            "effectiveness": {"verdict": "possibly_ineffective"},
            "drift": {"state": "current"},
        },
    )
    with pytest.raises(
        le.LearningEffectivenessError,
        match="learning_assessment_hash_mismatch",
    ):
        le.request_learning_review(
            Path("."),
            knowledge_kind="memory",
            knowledge_id=1,
            expected_assessment_hash="b" * 64,
            task_id="T1",
        )


def test_four_new_commands_are_agent_plane_only_and_authority_surface_unchanged() -> None:
    registry = cli_runtime.command_registry()
    agent = cli_runtime.agent_command_registry()
    privileged = cli_runtime.privileged_command_registry()
    added = {
        "learning-effectiveness-status",
        "learning-effectiveness-evaluate",
        "learning-drift-evaluate",
        "learning-effectiveness-review-request",
    }
    assert added <= set(registry)
    assert added <= set(agent)
    assert not (added & set(cli_runtime.CONTROL_PLANE_COMMANDS))
    assert "decision-resolve" in cli_runtime.PRIVILEGED_COMMANDS
    assert len(registry) == 364
    assert len(agent) == 267
    assert len(privileged) == 99


def test_no_automatic_lifecycle_mutation_and_mcp_stays_132() -> None:
    source = inspect.getsource(le)
    for forbidden in (
        "UPDATE project_memory SET status",
        "UPDATE promoted_skills SET status",
        "transition_proposal(",
        "activate_baseline(",
        "graduate_skill(",
    ):
        assert forbidden not in source
    assert len(mcp_runtime.ALL_TOOLS) == 132
    assert not any(
        "learning_effectiveness" in str(tool.get("name", ""))
        for tool in mcp_runtime.ALL_TOOLS
    )


def test_release_notes_preserve_predecessor_attestations() -> None:
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    for marker in (
        "v0.29.5 — Native Physical Isolation Extensions",
        "v0.29.4 Restricted Token",
        "restricted_token_attested = true",
        "low_integrity_attested = true",
        "host_filesystem_isolation_attested = false",
    ):
        assert marker in notes
    assert "causal" in notes.lower()
    assert "prompt injection" in notes.lower()
