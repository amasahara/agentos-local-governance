"""
File: .agents/tests/test_architecture_contract_v0252.py

Purpose:
    Verify v0.25.2 Architecture Contract and Human Clarification fail-closed behavior.

Responsibilities:
    - Verify migration-50 architecture contracts against the current schema and fixed 27-section registry.
    - Verify architecture working-copy/baseline authority separation.
    - Verify explicit human confirmation and exact-hash lifecycle gates.
    - Verify Grill Me task approval and runtime decision blockers.
    - Verify human answers never need to be copied into external audit payloads.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.architecture_contract import (
    ARCHITECTURE_SECTIONS,
    activate_baseline,
    approve_baseline,
    architecture_init,
    architecture_status,
    create_baseline,
    review_baseline,
    validate_working_copy,
)
from agentos.core import approve_task, check_write, start_task
from agentos.db import SCHEMA_VERSION, connect
from agentos.human_decision import (
    grill_me,
    record_clarity_assessment,
    request_human_decision,
    resolve_human_decision,
)


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated library-style AgentOS root with private audit home."""
    root = tmp_path / "project"
    (root / ".agents").mkdir(parents=True)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    return root


def _resolve_architecture_working_copy(root: Path) -> None:
    """Turn generated templates into minimally non-empty human-authored contracts."""
    for md_path in (root / ".agents/architecture/sections").glob("ARCH-*.md"):
        text = md_path.read_text(encoding="utf-8")
        text = text.replace("UNRESOLVED — human architect input required.", "Human-reviewed section intent.")
        text = text.replace("## Contract\n\nUNRESOLVED.", "## Contract\n\nHuman-reviewed architecture statement.")
        md_path.write_text(text, encoding="utf-8")
    for json_path in (root / ".agents/architecture/contracts").glob("ARCH-*.json"):
        value = json.loads(json_path.read_text(encoding="utf-8"))
        value["applicability"] = "applicable"
        value["payload"] = {"summary": f'Human-reviewed {value["section_id"]} contract.'}
        json_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_schema_50_and_fixed_architecture_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Architecture migration 50 must remain covered and the registry must be exactly ARCH-01..ARCH-27."""
    root = _root(tmp_path, monkeypatch)
    with connect(root) as conn:
        version = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
    assert version == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 50
    assert [s["section_id"] for s in ARCHITECTURE_SECTIONS] == [f"ARCH-{i:02d}" for i in range(1, 28)]
    assert ARCHITECTURE_SECTIONS[25]["authority_mode"] == "proposal_only"


def test_architecture_init_is_unresolved_and_non_inferential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Initialization must create templates only and must not claim architecture understanding."""
    root = _root(tmp_path, monkeypatch)
    with connect(root):
        pass
    result = architecture_init(root, created_by="human")
    report = validate_working_copy(root)
    assert result["section_count"] == 27
    assert result["source_inference_performed"] is False
    assert report["ok"] is True
    assert report["approval_ready"] is False
    assert len(report["unresolved_sections"]) == 27


def test_baseline_requires_human_confirmation_hash_and_stays_immutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only explicit human/hash lifecycle can activate; later working-copy edits cannot rewrite authority."""
    root = _root(tmp_path, monkeypatch)
    with connect(root):
        pass
    architecture_init(root)
    _resolve_architecture_working_copy(root)
    report = validate_working_copy(root)
    assert report["approval_ready"] is True
    baseline = create_baseline(root, "architect")
    with pytest.raises(RuntimeError, match="explicit_human_confirmation_required"):
        review_baseline(root, baseline["id"], baseline["baseline_hash"], "architect", False)
    assert review_baseline(root, baseline["id"], baseline["baseline_hash"], "architect", True)["status"] == "reviewed"
    with pytest.raises(RuntimeError, match="architecture_baseline_hash_mismatch"):
        approve_baseline(root, baseline["id"], "wrong", "architect", True)
    assert approve_baseline(root, baseline["id"], baseline["baseline_hash"], "architect", True)["status"] == "approved"
    assert activate_baseline(root, baseline["id"], baseline["baseline_hash"], "architect", True)["status"] == "active"
    before = architecture_status(root)
    assert before["workspace_matches_active"] is True
    path = next((root / ".agents/architecture/sections").glob("ARCH-02-*.md"))
    path.write_text(path.read_text(encoding="utf-8") + "\nWorking-copy change.\n", encoding="utf-8")
    after = architecture_status(root)
    assert after["workspace_matches_active"] is False
    assert after["active_baseline"]["baseline_hash"] == baseline["baseline_hash"]


def test_task_approval_requires_clear_structured_clarity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A task cannot be approved until all material ambiguity is explicitly cleared."""
    root = _root(tmp_path, monkeypatch)
    start_task(root, "T1", "Implement defined behavior")
    with pytest.raises(RuntimeError, match="clarity_gate_blocked"):
        approve_task(root, "T1", ["src"])
    record_clarity_assessment(
        root, "T1", "agent",
        objective_understood=True, scope_understood=True,
        constraints_understood=True, acceptance_understood=True,
    )
    assert approve_task(root, "T1", ["src"])["approved"] is True


def test_grill_me_material_ambiguity_opens_blocker_and_requires_reassessment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Incomplete clarity must become a human question rather than an AI-selected default."""
    root = _root(tmp_path, monkeypatch)
    start_task(root, "T2", "Implement timeout behavior")
    assessment = record_clarity_assessment(
        root, "T2", "agent",
        objective_understood=True, scope_understood=True,
        constraints_understood=True, acceptance_understood=False,
        decisions_required=["Should timeout return behavior A or B?"],
    )
    assert assessment["status"] == "needs_clarification"
    assert assessment["blocking_question_count"] == 1
    grill = grill_me(root, "T2")
    assert grill["open_blocking_count"] == 1
    decision = grill["questions"][0]
    resolution = resolve_human_decision(
        root, decision["decision_uuid"], "Use behavior B.", "human", "none", human_confirmed=True
    )
    assert resolution["status"] == "resolved"
    assert grill_me(root, "T2")["ready"] is False
    record_clarity_assessment(
        root, "T2", "agent",
        objective_understood=True, scope_understood=True,
        constraints_understood=True, acceptance_understood=True,
    )
    assert grill_me(root, "T2")["ready"] is True


def test_runtime_decision_blocks_write_and_scope_change_revokes_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A new runtime decision pauses dependent mutation and material impact forces reapproval."""
    root = _root(tmp_path, monkeypatch)
    start_task(root, "T3", "Implement approved feature")
    record_clarity_assessment(
        root, "T3", "agent",
        objective_understood=True, scope_understood=True,
        constraints_understood=True, acceptance_understood=True,
    )
    approve_task(root, "T3", ["src"])
    assert check_write(root, "T3", "src/a.py")["allowed"] is True
    decision = request_human_decision(
        root, "T3", "execution", "architecture_choice", "high", "Use existing module or introduce a new boundary?",
        options=["existing", "new"], recommendation="existing", raised_by_session="agent-session",
    )
    blocked = check_write(root, "T3", "src/a.py")
    assert blocked == {"allowed": False, "reason": "human_decision_pending", "target": "src/a.py"}
    result = resolve_human_decision(
        root, decision["decision_uuid"], "Use a new approved scope.", "human", "scope_change",
        selected_option="new", human_confirmed=True,
    )
    assert result["task_approval_revoked"] is True
    assert result["resume_action"] == "task_reapproval_required"
    assert check_write(root, "T3", "src/a.py")["reason"] == "task_not_approved"


def test_duplicate_decision_request_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated identical blocker signals must not flood human review state."""
    root = _root(tmp_path, monkeypatch)
    start_task(root, "T4", "Need a decision")
    first = request_human_decision(root, "T4", "execution", "other", "normal", "Choose A or B?")
    second = request_human_decision(root, "T4", "execution", "other", "normal", "Choose A or B?")
    assert first["decision_uuid"] == second["decision_uuid"]
    assert second["existing"] is True


def test_external_signed_audit_does_not_persist_raw_human_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Human answer text must stay local while signed audit stores only its hash."""
    root = _root(tmp_path, monkeypatch)
    start_task(root, "T5", "Need sensitive human decision")
    decision = request_human_decision(root, "T5", "pre_execution", "security_privacy", "critical", "Choose the privacy behavior?")
    secret_answer = "Human chooses private behavior Z with internal rationale 987654."
    result = resolve_human_decision(root, decision["decision_uuid"], secret_answer, "human", "none", human_confirmed=True)
    assert result["answer_hash"]
    from agentos.external_audit import log_path
    audit_text = log_path(root).read_text(encoding="utf-8")
    assert secret_answer not in audit_text
    assert result["answer_hash"] in audit_text


def test_v0252_mcp_has_only_monotonic_human_decision_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP may inspect architecture/decisions and open a blocker but cannot resolve human authority."""
    root = _root(tmp_path, monkeypatch)
    with connect(root):
        pass
    from agentos.mcp_v0252 import TOOLS, TOOL_NAMES, dispatch
    assert "agentos.human_decision_request" in TOOL_NAMES
    assert not any("resolve" in name or "approve" in name or "activate" in name or "waive" in name for name in TOOL_NAMES)
    state_path = root / ".agents/state/agentos.db"
    before = state_path.stat().st_mtime_ns
    architecture_init(root)
    dispatch("agentos.architecture_status_get", {}, root, None, None)
    assert state_path.stat().st_mtime_ns == before
