"""
File: .agents/tests/test_risk_tiered_batch_review_v0241.py

Purpose:
    Verify v0.24.1 deterministic risk tiers, signed LOW-risk bundles, stale-plan
    rejection, and preservation of whole-plan approval authority.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agentos.external_audit import verify_external_log
from agentos.project_consolidation import (
    add_component_mapping,
    approve_consolidation,
    create_consolidation,
    get_consolidation,
)
from agentos.project_identity import ensure_instance_id, ensure_project_id, set_purpose
from agentos.project_selection import create_candidate_set, scan_candidate_readonly, select_primary
from agentos.risk_tiered_batch_review import (
    RISK_BLOCKED,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    RiskTieredBatchReviewError,
    assess_consolidation_risk,
    classify_mapping,
    create_low_risk_bundle,
    get_risk_review_status,
    review_low_risk_bundle,
    review_mapping_individual,
)


def _make_project(root: Path, *, name: str, role: str) -> Path:
    (root / ".agents/config").mkdir(parents=True)
    (root / ".agents/state").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / "VERSION").write_text("0.23.4\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
    (root / ".agents/config/governance.json").write_text(json.dumps({"version": "0.23.4"}), encoding="utf-8")
    ensure_project_id(root, created_by="test")
    ensure_instance_id(root)
    set_purpose(
        root,
        name=name,
        domain_id="healthcare",
        domain_name="Healthcare",
        purpose_id="hospital_management",
        purpose_description=f"Hospital purpose for {name}",
        capabilities=("patient_management", "reporting"),
        role=role,
        confirmed_by="human",
        human_confirmed=True,
    )
    sqlite3.connect(root / ".agents/state/agentos.db").close()
    return root


def _selected_pair(tmp_path: Path) -> tuple[Path, Path, int, str]:
    primary = _make_project(tmp_path / "primary", name="Core", role="core_application")
    source = _make_project(tmp_path / "source", name="Adapter", role="integration_adapter")
    source_uuid = scan_candidate_readonly(source).project_uuid
    candidates = create_candidate_set(primary, [source], created_by="human")
    set_id = int(candidates["candidate_set"]["id"])
    primary_uuid = scan_candidate_readonly(primary).project_uuid
    select_primary(
        primary,
        set_id,
        primary_uuid,
        selected_by="human",
        reason="Core is the production primary project",
        human_confirmed=True,
    )
    return primary, source, set_id, source_uuid


def _mixed_plan(tmp_path: Path) -> tuple[Path, int, list[int]]:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/ignore.py").write_text("IGNORE = True\n", encoding="utf-8")
    (source / "src/new.py").write_text("NEW = True\n", encoding="utf-8")
    (source / "src/replace.py").write_text("SOURCE = True\n", encoding="utf-8")
    (primary / "src/replace.py").write_text("PRIMARY = True\n", encoding="utf-8")
    state = create_consolidation(primary, set_id, created_by="operator")
    cid = int(state["consolidation"]["id"])
    ids: list[int] = []
    state = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/ignore.py", target_path=None, action="IGNORE", rationale="Primary does not need this legacy component", created_by="operator")
    ids.append(int(state["mappings"][-1]["id"]))
    state = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/new.py", target_path="src/new.py", action="MOVE", rationale="Exact copy into a new primary target", created_by="operator")
    ids.append(int(state["mappings"][-1]["id"]))
    state = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/replace.py", target_path="src/replace.py", action="MOVE", rationale="Exact replacement needs individual review", created_by="operator")
    ids.append(int(state["mappings"][-1]["id"]))
    return primary, cid, ids


def _mapping(action: str, *, absent: int = 0, target_hash: str | None = None) -> dict[str, object]:
    return {
        "id": 1, "consolidation_id": 1, "source_project_uuid": "source",
        "source_path": "src/a.py", "source_hash": "a" * 64, "source_size": 12,
        "target_path": "src/a.py", "target_expected_hash": target_hash,
        "target_expected_absent": absent, "action": action, "status": "planned",
        "rationale": "deterministic fixture",
    }


def test_classifier_contract_is_conservative_and_deterministic() -> None:
    assert classify_mapping(_mapping("IGNORE"))["risk_tier"] == RISK_LOW
    assert classify_mapping(_mapping("REUSE", target_hash="b" * 64))["risk_tier"] == RISK_LOW
    assert classify_mapping(_mapping("MOVE", absent=1))["risk_tier"] == RISK_LOW
    assert classify_mapping(_mapping("MOVE", target_hash="b" * 64))["risk_tier"] == RISK_MEDIUM
    assert classify_mapping(_mapping("ADAPT"))["risk_tier"] == RISK_HIGH
    assert classify_mapping(_mapping("REIMPLEMENT"))["risk_tier"] == RISK_HIGH
    assert classify_mapping(_mapping("CONFLICT"))["risk_tier"] == RISK_BLOCKED
    assert classify_mapping(_mapping("MOVE", absent=1)) == classify_mapping(_mapping("MOVE", absent=1))


def test_low_bundle_is_signed_and_only_covers_low_mappings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    monkeypatch.setenv("AGENTOS_TASK_ID", "T-V0241")
    monkeypatch.setenv("AGENTOS_SESSION_ID", "S-V0241")
    primary, cid, ids = _mixed_plan(tmp_path)
    risk = assess_consolidation_risk(primary, cid)
    assert risk["counts"] == {"LOW": 2, "MEDIUM": 1, "HIGH": 0, "BLOCKED": 0}
    bundle = create_low_risk_bundle(primary, cid, created_by="operator")
    b = bundle["bundle"]
    assert b["mapping_ids"] == ids[:2]
    assert b["mapping_count"] == 2
    assert len(b["bundle_hash"]) == 64
    assert b["signed_key_id"]
    assert b["signed_signature"]
    again = create_low_risk_bundle(primary, cid, created_by="operator")
    assert again["idempotent"] is True
    assert again["bundle"]["bundle_id"] == b["bundle_id"]
    assert verify_external_log(primary)["ok"] is True


def test_bundle_rejects_medium_mapping_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    primary, cid, ids = _mixed_plan(tmp_path)
    with pytest.raises(RiskTieredBatchReviewError, match="only LOW may be batched"):
        create_low_risk_bundle(primary, cid, created_by="operator", mapping_ids=[ids[2]])


def test_batch_plus_individual_review_finalizes_review_but_not_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    primary, cid, ids = _mixed_plan(tmp_path)
    bundle = create_low_risk_bundle(primary, cid, created_by="operator")
    reviewed = review_low_risk_bundle(primary, bundle["bundle"]["bundle_id"], reviewed_by="reviewer", reason="Reviewed deterministic low-risk bundle", human_confirmed=True)
    assert reviewed["plan_review"]["finalized"] is False
    assert reviewed["review_status"]["missing_mapping_ids"] == [ids[2]]
    individual = review_mapping_individual(primary, cid, ids[2], reviewed_by="reviewer", reason="Reviewed replacement of existing target", human_confirmed=True)
    assert individual["plan_review"]["finalized"] is True
    status = get_risk_review_status(primary, cid)
    assert status["ready_for_plan_approval"] is True
    state = get_consolidation(primary, cid)
    assert state["consolidation"]["status"] == "reviewed"
    assert state.get("approval") is None
    approved = approve_consolidation(primary, cid, approved_by="owner", reason="Approved exact reviewed plan after risk-tiered review", human_confirmed=True)
    assert approved["consolidation"]["status"] == "approved"


def test_bundle_review_requires_explicit_human_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    primary, cid, _ = _mixed_plan(tmp_path)
    bundle = create_low_risk_bundle(primary, cid, created_by="operator")
    with pytest.raises(RiskTieredBatchReviewError, match="explicit human confirmation"):
        review_low_risk_bundle(primary, bundle["bundle"]["bundle_id"], reviewed_by="reviewer", reason="Review should be human confirmed", human_confirmed=False)


def test_bundle_is_stale_after_plan_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("A = 1\n", encoding="utf-8")
    (source / "src/b.py").write_text("B = 1\n", encoding="utf-8")
    state = create_consolidation(primary, set_id, created_by="operator")
    cid = int(state["consolidation"]["id"])
    add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path=None, action="IGNORE", rationale="Ignore first legacy component", created_by="operator")
    bundle = create_low_risk_bundle(primary, cid, created_by="operator")
    add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/b.py", target_path=None, action="IGNORE", rationale="Second mapping changes exact plan hash", created_by="operator")
    with pytest.raises(RiskTieredBatchReviewError, match="stale"):
        review_low_risk_bundle(primary, bundle["bundle"]["bundle_id"], reviewed_by="reviewer", reason="Old bundle must be rejected after plan drift", human_confirmed=True)


def test_low_mapping_cannot_bypass_signed_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    primary, cid, ids = _mixed_plan(tmp_path)
    with pytest.raises(RiskTieredBatchReviewError, match="must use a signed batch bundle"):
        review_mapping_individual(primary, cid, ids[0], reviewed_by="reviewer", reason="Cannot bypass the signed low-risk bundle", human_confirmed=True)



def test_signed_bundle_core_is_database_immutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    primary, cid, _ = _mixed_plan(tmp_path)
    bundle = create_low_risk_bundle(primary, cid, created_by="operator")["bundle"]
    from agentos.db import connect
    with connect(primary) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE consolidation_review_bundles SET bundle_hash=? WHERE bundle_id=?", ("0" * 64, bundle["bundle_id"]))
    with connect(primary) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM consolidation_review_bundles WHERE bundle_id=?", (bundle["bundle_id"],))


def test_individual_review_is_idempotent_without_duplicate_attestation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    primary, cid, ids = _mixed_plan(tmp_path)
    first = review_mapping_individual(primary, cid, ids[2], reviewed_by="reviewer", reason="Reviewed replacement of existing target", human_confirmed=True)
    second = review_mapping_individual(primary, cid, ids[2], reviewed_by="reviewer", reason="Reviewed replacement of existing target", human_confirmed=True)
    assert first["ok"] is True
    assert second["idempotent"] is True

def test_mcp_surface_is_read_only() -> None:
    from agentos.mcp_risk_tiered_batch_review import TOOLS
    names = {item["name"] for item in TOOLS}
    assert names == {
        "agentos.project_consolidation_risk_review_get",
        "agentos.project_consolidation_batch_bundle_get",
    }
    assert all(name.endswith("_get") for name in names)
