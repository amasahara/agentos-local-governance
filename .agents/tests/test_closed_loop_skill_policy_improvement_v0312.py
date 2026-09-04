"""Focused v0.31.2 closed-loop skill and policy improvement tests."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import agentos.closed_loop_improvement as loop
from agentos import cli_runtime, mcp_runtime
from agentos.schema_version import CURRENT_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_schema_stays_64_and_reuses_reserved_relations() -> None:
    # Historical v0.31.2 floor. Successors may add later migrations.
    assert CURRENT_SCHEMA_VERSION >= 64
    learning = (
        ROOT
        / ".agents/agentos/learning_signals.py"
    ).read_text(encoding="utf-8")
    assert '"skill_candidate"' in learning
    assert '"evolution_proposal"' in learning
    db_source = (
        ROOT / ".agents/agentos/db.py"
    ).read_text(encoding="utf-8")
    assert "from .learning_signals import migration_64" in db_source


def test_policy_preserves_closed_loop_authority_boundary() -> None:
    policy = json.loads(
        (
            ROOT
            / ".agents/config/policy/learning.json"
        ).read_text(encoding="utf-8")
    )["governed_learning_policy"]["closed_loop"]

    assert policy["enabled"] is True
    assert (
        policy[
            "automatic_skill_candidate_creation"
        ]
        is True
    )
    assert (
        policy["automatic_skill_graduation"]
        is False
    )
    assert (
        policy["policy_patch_must_be_explicit"]
        is True
    )
    assert (
        policy[
            "automatic_policy_proposal_creation"
        ]
        is False
    )
    assert (
        policy[
            "automatic_policy_simulation_after_explicit_draft"
        ]
        is True
    )
    assert (
        policy["automatic_policy_transition"]
        is False
    )
    assert (
        policy["automatic_policy_activation"]
        is False
    )
    assert (
        policy[
            "automatic_architecture_mutation"
        ]
        is False
    )
    assert policy["mcp_mutation_allowed"] is False


def test_nonactive_skill_candidate_links_learning_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        loop,
        "_existing_skill_for_memory",
        lambda _r, _m: None,
    )
    monkeypatch.setattr(
        loop,
        "skill_candidate_readiness",
        lambda _r, _m: {
            "ready": True,
            "architecture_baseline_hash": "a" * 64,
            "reasons": [],
        },
    )
    monkeypatch.setattr(
        loop,
        "_memory_support_links",
        lambda _r, _m: [
            {"signal_id": "LS-1"},
            {"signal_id": "LS-2"},
        ],
    )
    monkeypatch.setattr(
        loop,
        "revalidate_learning_signal",
        lambda _r, signal_id, persist_eligibility=False: {
            "signal_id": signal_id,
            "source_current": True,
            "cross_task_eligible": True,
            "architecture_baseline_hash": "a" * 64,
        },
    )
    monkeypatch.setattr(
        loop,
        "promote_skill_candidate",
        lambda _r, _m, _p: {
            "skill_id": 7,
            "skill_key": "safe-skill",
            "status": "candidate",
            "content_hash": "b" * 64,
        },
    )

    links = []
    monkeypatch.setattr(
        loop,
        "link_learning_signal",
        lambda _r, **kwargs: (
            links.append(kwargs) or kwargs
        ),
    )

    result = (
        loop.create_skill_candidate_from_memory(
            Path("."),
            11,
        )
    )
    assert result["skill_status"] == "candidate"
    assert result["automatic_graduation"] is False
    assert (
        result["human_graduation_required"]
        is True
    )
    assert len(links) == 2
    assert {
        item["relation_type"]
        for item in links
    } == {"skill_candidate"}


def test_empty_policy_patch_is_rejected_before_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        loop,
        "_policy",
        lambda _r: {
            "automatic_policy_simulation_after_explicit_draft": True,
        },
    )
    with pytest.raises(
        loop.ClosedLoopImprovementError,
        match="explicit_nonempty_policy_patch_required",
    ):
        loop.create_policy_improvement_proposal(
            Path("."),
            skill_id=1,
            title="Improve policy",
            policy_patch={},
            expected_benefit="safer",
            risks=[],
            rollback_plan={"action": "revert"},
            created_by="operator",
        )


def test_explicit_proposal_simulates_without_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        loop,
        "_policy",
        lambda _r: {
            "automatic_policy_simulation_after_explicit_draft": True,
        },
    )
    monkeypatch.setattr(
        loop,
        "policy_improvement_readiness",
        lambda _r, _s: {
            "ready": True,
            "reasons": [],
            "trigger_findings": [3],
            "support_evaluations": [
                {"signal_id": "LS-A"},
                {"signal_id": "LS-B"},
            ],
        },
    )

    class EmptyConnection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, *_args, **_kwargs):
            class Result:
                def fetchone(self):
                    return None
            return Result()

    monkeypatch.setattr(
        loop,
        "connect_read_only",
        lambda _r: EmptyConnection(),
    )

    patch = {
        "tool_policy": {
            "mode": "narrower"
        }
    }
    proposal_hash = loop._proposal_hash(
        title="Improve policy",
        trigger_findings=[3],
        policy_patch=patch,
        expected_benefit="safer",
        risks=["false positive"],
        rollback_plan={"action": "revert"},
    )
    monkeypatch.setattr(
        loop,
        "create_proposal",
        lambda *_args, **_kwargs: {
            "proposal_id": 9,
            "status": "draft",
            "proposal_hash": proposal_hash,
        },
    )

    linked = []
    monkeypatch.setattr(
        loop,
        "link_learning_signal",
        lambda _r, **kwargs: (
            linked.append(kwargs) or kwargs
        ),
    )
    monkeypatch.setattr(
        loop,
        "simulate_proposal",
        lambda _r, pid: {
            "proposal_id": pid,
            "status": "simulated",
            "simulation": {},
        },
    )

    result = (
        loop.create_policy_improvement_proposal(
            Path("."),
            skill_id=4,
            title="Improve policy",
            policy_patch=patch,
            expected_benefit="safer",
            risks=["false positive"],
            rollback_plan={"action": "revert"},
            created_by="operator",
        )
    )
    assert result["status"] == "simulated"
    assert (
        result["automatic_policy_transition"]
        is False
    )
    assert (
        result["automatic_policy_activation"]
        is False
    )
    assert len(linked) == 2
    assert "transition_proposal" not in inspect.getsource(
        loop
    )


def test_graduation_revalidates_closed_loop_candidate() -> None:
    source = (
        ROOT / ".agents/agentos/skills.py"
    ).read_text(encoding="utf-8")
    assert (
        "validate_closed_loop_skill_candidate"
        in source
    )
    assert (
        "closed_loop_skill_candidate_not_current"
        in source
    )


def test_memory_activation_hook_is_degraded_safe() -> None:
    source = (
        ROOT
        / ".agents/agentos/memory_promotion.py"
    ).read_text(encoding="utf-8")
    assert (
        "create_skill_candidate_from_memory"
        in source
    )
    assert "closed_loop_skill_candidate_error" in source
    assert (
        "Candidate creation is non-active/degraded-safe"
        in source
    )


def test_four_new_commands_are_agent_plane_only() -> None:
    registry = cli_runtime.command_registry()
    agent = cli_runtime.agent_command_registry()
    privileged = (
        cli_runtime.privileged_command_registry()
    )

    added = {
        "closed-loop-status",
        "closed-loop-skill-candidate",
        "closed-loop-policy-readiness",
        "closed-loop-policy-proposal",
    }
    assert added <= set(registry)
    assert added <= set(agent)
    assert not (
        added
        & set(cli_runtime.CONTROL_PLANE_COMMANDS)
    )
    # Historical v0.31.2 surface floors. Successor releases may add commands,
    # while this test still proves the v0.31.2 closed-loop commands remain
    # agent-plane-only. The current release owns exact surface counts.
    assert len(registry) >= 360
    assert len(agent) >= 263
    assert len(privileged) >= 99


def test_existing_authority_surfaces_and_mcp_unchanged() -> None:
    agent = cli_runtime.agent_command_registry()

    assert (
        "skill-graduate"
        in cli_runtime.CONTROL_PLANE_COMMANDS
    )
    assert (
        "evolution-transition"
        in cli_runtime.CONTROL_PLANE_COMMANDS
    )
    assert "skill-graduate" not in agent
    assert "evolution-transition" not in agent

    assert len(mcp_runtime.ALL_TOOLS) == 132
    assert not any(
        "closed_loop"
        in str(tool.get("name", ""))
        for tool in mcp_runtime.ALL_TOOLS
    )


def test_release_notes_preserve_predecessor_contracts() -> None:
    notes = (
        ROOT / "RELEASE_NOTES.md"
    ).read_text(encoding="utf-8")

    markers = (
        "v0.29.5 — Native Physical Isolation Extensions",
        "v0.29.4 Restricted Token",
        "restricted_token_attested = true",
        "low_integrity_attested = true",
        "host_filesystem_isolation_attested = false",
    )
    for marker in markers:
        assert marker in notes
    assert "prompt injection" in notes.lower()
