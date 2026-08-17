"""Path: .agents/tests/test_architecture_change_v0255.py
Purpose: Regression tests for v0.25.5 Architecture Change Proposal & ADR lifecycle.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentos.architecture_contract import activate_baseline
from agentos.architecture_change import (
    approve_change_proposal,
    architecture_adr_get,
    architecture_change_proposal_get,
    architecture_change_status,
    bind_change_proposal_baseline,
    create_change_proposal,
    reject_change_proposal,
    review_change_proposal,
    submit_change_proposal,
)
from agentos.db import SCHEMA_VERSION, connect


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / ".agents").mkdir(parents=True)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    return root


def _active_baseline(root: Path, *, baseline_hash: str = "a" * 64, version: int = 1) -> int:
    with connect(root, immediate=True) as c:
        cur = c.execute(
            """INSERT INTO architecture_baselines(
                baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by,activated_by,activated_at
            ) VALUES(?,?, 'active', ?,27,'human:test','human:test',CURRENT_TIMESTAMP)""",
            (f"baseline-{version}", version, baseline_hash),
        )
        return int(cur.lastrowid)


def _compliance_block(root: Path, baseline_id: int, baseline_hash: str = "a" * 64) -> tuple[int, int]:
    with connect(root, immediate=True) as c:
        cur = c.execute(
            """INSERT INTO architecture_compliance_runs(
                run_uuid,engine_version,mode,baseline_id,baseline_hash,status,finding_count,warning_count,blocking_count,
                changed_files_json,run_hash,created_by
            ) VALUES('run-1',1,'manual',?,?,'block',1,0,1,'[]',?,'system:test')""",
            (baseline_id, baseline_hash, "r" * 64),
        )
        run_id = int(cur.lastrowid)
        f = c.execute(
            """INSERT INTO architecture_compliance_findings(
                run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash
            ) VALUES(?,'ARCH-02','unapproved_dependency','block','aiohttp','[\"requests\"]','\"aiohttp\"','[]',?)""",
            (run_id, "f" * 64),
        )
        return run_id, int(f.lastrowid)


def _proposal(root: Path, run_id: int | None = None, finding_ids: list[int] | None = None) -> dict:
    return create_change_proposal(
        root,
        title="Adopt async HTTP client",
        summary="Permit an async HTTP dependency for the service boundary.",
        rationale="The approved synchronous client cannot satisfy the new concurrency requirement.",
        affected_sections=["ARCH-02", "ARCH-12"],
        proposed_changes={"ARCH-02": {"allowed_dependencies_add": ["aiohttp"]}},
        impact_analysis={"risk": "medium", "affected_modules": ["src/service.py"]},
        validation_plan={"tests": ["unit", "integration"]},
        rollback_plan={"action": "restore synchronous client"},
        created_by="ai:proposal-drafter",
        compliance_run_id=run_id,
        finding_ids=finding_ids,
        adr_alternatives=[{"option": "keep requests", "rejected_reason": "insufficient concurrency"}],
    )


def test_schema_53_tables_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    with connect(root) as c:
        version = c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 53
    assert {
        "architecture_change_proposals",
        "architecture_change_proposal_findings",
        "architecture_adrs",
        "architecture_change_events",
    } <= tables


def test_proposal_requires_active_architecture_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    with connect(root):
        pass
    with pytest.raises(RuntimeError, match="architecture_change_requires_active_baseline"):
        _proposal(root)


def test_ai_can_draft_and_submit_but_does_not_gain_architecture_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline_id = _active_baseline(root)
    run_id, finding_id = _compliance_block(root, baseline_id)
    created = _proposal(root, run_id, [finding_id])
    proposal = created["proposal"]
    assert proposal["status"] == "draft"
    assert proposal["source_baseline_id"] == baseline_id
    assert created["findings"][0]["id"] == finding_id
    assert created["adr"]["status"] == "proposed"
    assert created["architecture_authority_changed"] is False
    submitted = submit_change_proposal(root, proposal["id"], proposal["proposal_hash"], "ai:proposal-drafter")
    assert submitted["proposal"]["status"] == "submitted"
    assert submitted["working_copy_modified"] is False


def test_human_review_and_approval_require_exact_hash_and_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline_id = _active_baseline(root)
    run_id, _ = _compliance_block(root, baseline_id)
    created = _proposal(root, run_id)
    p = created["proposal"]
    submit_change_proposal(root, p["id"], p["proposal_hash"], "ai:proposal-drafter")
    with pytest.raises(RuntimeError, match="explicit_human_confirmation_required"):
        review_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", False)
    with pytest.raises(RuntimeError, match="architecture_change_proposal_hash_mismatch"):
        review_change_proposal(root, p["id"], "wrong", "human:architect", True)
    reviewed = review_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", True)
    assert reviewed["proposal"]["status"] == "reviewed"
    with pytest.raises(RuntimeError, match="explicit_human_confirmation_required"):
        approve_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", False)
    approved = approve_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", True)
    assert approved["proposal"]["status"] == "approved"
    assert approved["adr"]["status"] == "accepted"


def test_stale_source_baseline_cannot_be_human_approved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline_id = _active_baseline(root)
    run_id, _ = _compliance_block(root, baseline_id)
    created = _proposal(root, run_id)
    p = created["proposal"]
    submit_change_proposal(root, p["id"], p["proposal_hash"], "ai:proposal-drafter")
    with connect(root, immediate=True) as c:
        c.execute("UPDATE architecture_baselines SET status='superseded' WHERE id=?", (baseline_id,))
        c.execute("INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by,activated_by,activated_at) VALUES('baseline-2',2,'active',?,27,'human:test','human:test',CURRENT_TIMESTAMP)", ("b" * 64,))
    with pytest.raises(RuntimeError, match="architecture_change_proposal_stale_baseline"):
        review_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", True)


def test_rejection_rejects_linked_adr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    _active_baseline(root)
    created = _proposal(root)
    p = created["proposal"]
    rejected = reject_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", "Not aligned with platform strategy", True)
    assert rejected["proposal"]["status"] == "rejected"
    assert rejected["adr"]["status"] == "rejected"


def test_approved_proposal_binds_target_baseline_without_activating_it_or_writing_architecture_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    arch = root / ".agents/architecture"
    arch.mkdir(parents=True)
    marker = arch / "human-owned.txt"
    marker.write_text("human architecture workspace\n", encoding="utf-8")
    before = hashlib.sha256(marker.read_bytes()).hexdigest()
    source_id = _active_baseline(root)
    created = _proposal(root)
    p = created["proposal"]
    submit_change_proposal(root, p["id"], p["proposal_hash"], "ai:proposal-drafter")
    review_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", True)
    approve_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", True)
    with connect(root, immediate=True) as c:
        cur = c.execute("INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by) VALUES('candidate-2',2,'draft',?,27,'human:architect')", ("c" * 64,))
        target_id = int(cur.lastrowid)
    bound = bind_change_proposal_baseline(root, p["id"], p["proposal_hash"], target_id, "c" * 64, "human:architect", True)
    assert bound["proposal"]["target_baseline_id"] == target_id
    with connect(root) as c:
        target_status = c.execute("SELECT status FROM architecture_baselines WHERE id=?", (target_id,)).fetchone()[0]
        source_status = c.execute("SELECT status FROM architecture_baselines WHERE id=?", (source_id,)).fetchone()[0]
    assert target_status == "draft"
    assert source_status == "active"
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == before


def test_adr_read_model_and_status_make_separate_baseline_lifecycle_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    _active_baseline(root)
    created = _proposal(root)
    adr = architecture_adr_get(root, proposal_id=created["proposal"]["id"])
    assert adr["adr"]["status"] == "proposed"
    assert "## Context" in adr["markdown"]
    status = architecture_change_status(root)
    assert status["proposal_creation_authority"] == "ai_or_human_proposal_only"
    assert status["human_approval_required"] is True
    assert status["automatic_working_copy_mutation"] is False
    assert status["approved_proposal_requires_separate_baseline_lifecycle"] is True


def test_mcp_v0255_is_strictly_read_only() -> None:
    from agentos.mcp_v0255 import TOOL_NAMES
    assert TOOL_NAMES == {
        "agentos.architecture_change_proposal_get",
        "agentos.architecture_change_proposals_list",
        "agentos.architecture_adr_get",
        "agentos.architecture_change_status_get",
    }
    forbidden = ("create", "submit", "review", "approve", "reject", "bind", "activate", "waive", "execute")
    assert not any(any(word in name for word in forbidden) for name in TOOL_NAMES)

def test_successor_baseline_activation_requires_approved_bound_proposal_and_accepted_adr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    _active_baseline(root)
    created = _proposal(root)
    p = created["proposal"]
    submit_change_proposal(root, p["id"], p["proposal_hash"], "ai:proposal-drafter")
    review_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", True)
    approve_change_proposal(root, p["id"], p["proposal_hash"], "human:architect", True)
    with connect(root, immediate=True) as c:
        cur = c.execute("INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by,approved_by,approved_at) VALUES('candidate-3',3,'approved',?,27,'human:architect','human:architect',CURRENT_TIMESTAMP)", ("d" * 64,))
        target_id = int(cur.lastrowid)
    with pytest.raises(RuntimeError, match="architecture_successor_baseline_requires_approved_change_proposal"):
        activate_baseline(root, target_id, "d" * 64, "human:architect", True)
    bind_change_proposal_baseline(root, p["id"], p["proposal_hash"], target_id, "d" * 64, "human:architect", True)
    activated = activate_baseline(root, target_id, "d" * 64, "human:architect", True)
    assert activated["status"] == "active"

def test_release_integrity_accounts_for_v0255_mcp_surface() -> None:
    from agentos.release_integrity import check_release_integrity

    report = check_release_integrity(Path.cwd())
    mcp_findings = [
        item for item in report.get("findings", [])
        if item.get("code") == "mcp_tool_surface_changed"
    ]
    assert mcp_findings == []
