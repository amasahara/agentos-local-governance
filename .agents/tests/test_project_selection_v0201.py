"""
File: .agents/tests/test_project_selection_v0201.py

Purpose:
    Verify v0.20.1 Primary Project Selection and Domain Compatibility guarantees.

Responsibilities:
    - Prove source candidate scans are read-only.
    - Prove domain mismatch is fail-closed and non-overridable.
    - Prove different purposes in one domain require human confirmation.
    - Prove recommendations remain advisory and selection remains human-owned.
    - Prove the selected primary must be the active project root.
    - Prove schema 33 is additive and selection provenance is persisted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = PROJECT_ROOT / ".agents"
if str(AGENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENTS_ROOT))

from agentos.project_identity import ensure_instance_id, ensure_project_id, set_purpose  # noqa: E402
from agentos.project_selection import (  # noqa: E402
    COMPATIBLE,
    CONDITIONAL,
    INCOMPATIBLE,
    ProjectSelectionError,
    assess_compatibility,
    confirm_conditional_compatibility,
    create_candidate_set,
    get_candidate_set,
    migration_33,
    recommend_primary,
    scan_candidate_readonly,
    select_primary,
)


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _make_project(
    root: Path,
    *,
    name: str,
    domain_id: str,
    purpose_id: str,
    role: str = "core_application",
    capabilities: tuple[str, ...] = ("patient_management",),
) -> Path:
    (root / ".agents/config").mkdir(parents=True)
    (root / ".agents/state").mkdir(parents=True)
    (root / ".agents/agentos").mkdir(parents=True)
    (root / "VERSION").write_text("0.20.0\n", encoding="utf-8")
    (root / ".agents/config/governance.json").write_text(
        json.dumps({"version": "0.20.0", "project_identity_policy": {}}, indent=2),
        encoding="utf-8",
    )
    ensure_project_id(root, created_by="test")
    ensure_instance_id(root)
    set_purpose(
        root,
        name=name,
        domain_id=domain_id,
        domain_name=domain_id.replace("_", " ").title(),
        purpose_id=purpose_id,
        purpose_description=f"Business purpose for {name} project.",
        capabilities=capabilities,
        role=role,
        confirmed_by="test-human",
        human_confirmed=True,
    )
    sqlite3.connect(root / ".agents/state/agentos.db").close()
    return root


def test_exact_domain_and_purpose_are_compatible(tmp_path: Path) -> None:
    a = _make_project(tmp_path / "a", name="A", domain_id="healthcare", purpose_id="hospital_management")
    b = _make_project(tmp_path / "b", name="B", domain_id="healthcare", purpose_id="hospital_management")
    result = assess_compatibility(scan_candidate_readonly(a), scan_candidate_readonly(b))
    assert result["status"] == COMPATIBLE
    assert result["reason"] == "exact_domain_and_purpose_match"


def test_domain_mismatch_is_incompatible_even_with_capability_overlap(tmp_path: Path) -> None:
    a = _make_project(tmp_path / "a", name="A", domain_id="healthcare", purpose_id="hospital_management", capabilities=("reporting",))
    b = _make_project(tmp_path / "b", name="B", domain_id="retail", purpose_id="sales_management", capabilities=("reporting",))
    result = assess_compatibility(scan_candidate_readonly(a), scan_candidate_readonly(b))
    assert result["status"] == INCOMPATIBLE
    assert result["capability_overlap"] == ["reporting"]
    assert result["technical_similarity_can_override_domain"] is False


def test_same_domain_different_purpose_is_conditional(tmp_path: Path) -> None:
    a = _make_project(tmp_path / "a", name="A", domain_id="healthcare", purpose_id="hospital_management")
    b = _make_project(tmp_path / "b", name="B", domain_id="healthcare", purpose_id="hospital_integration", role="integration_adapter")
    result = assess_compatibility(scan_candidate_readonly(a), scan_candidate_readonly(b))
    assert result["status"] == CONDITIONAL


def test_candidate_scan_does_not_modify_source_metadata(tmp_path: Path) -> None:
    source = _make_project(tmp_path / "source", name="Source", domain_id="healthcare", purpose_id="hospital_management")
    tracked = [
        source / ".agents/config/project.id",
        source / ".agents/config/project.purpose.json",
        source / ".agents/state/project.instance.json",
        source / ".agents/config/governance.json",
        source / "VERSION",
    ]
    before = {str(path): (_digest(path), path.stat().st_mtime_ns) for path in tracked}
    scan_candidate_readonly(source)
    after = {str(path): (_digest(path), path.stat().st_mtime_ns) for path in tracked}
    assert before == after


def test_duplicate_project_uuid_is_blocked(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="A", domain_id="healthcare", purpose_id="hospital_management")
    clone = tmp_path / "clone"
    shutil.copytree(active, clone)
    with pytest.raises(ProjectSelectionError, match="duplicate project_uuid"):
        create_candidate_set(active, [clone], created_by="human")


def test_conditional_pair_requires_explicit_human_confirmation(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management")
    source = _make_project(tmp_path / "source", name="Adapter", domain_id="healthcare", purpose_id="hospital_integration", role="integration_adapter")
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]
    active_uuid = scan_candidate_readonly(active).project_uuid
    recommendation = recommend_primary(active, set_id)
    assert recommendation["recommended_project_uuid"] is None
    with pytest.raises(ProjectSelectionError, match="explicit human confirmation"):
        confirm_conditional_compatibility(
            active, set_id, active_uuid, scan_candidate_readonly(source).project_uuid,
            confirmed_by="human", reason="Same hospital platform integration purpose", human_confirmed=False,
        )


def test_domain_mismatch_cannot_be_human_overridden(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management")
    source = _make_project(tmp_path / "source", name="Sales", domain_id="retail", purpose_id="sales_management")
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]
    with pytest.raises(ProjectSelectionError, match="cannot be human-overridden"):
        confirm_conditional_compatibility(
            active,
            set_id,
            scan_candidate_readonly(active).project_uuid,
            scan_candidate_readonly(source).project_uuid,
            confirmed_by="human",
            reason="Attempted domain override must be rejected",
            human_confirmed=True,
        )


def test_human_confirmed_conditional_pair_becomes_feasible(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management", role="core_application", capabilities=("patient_management", "billing"))
    source = _make_project(tmp_path / "source", name="Adapter", domain_id="healthcare", purpose_id="hospital_integration", role="integration_adapter", capabilities=("patient_management",))
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]
    active_uuid = scan_candidate_readonly(active).project_uuid
    source_uuid = scan_candidate_readonly(source).project_uuid
    confirm_conditional_compatibility(
        active,
        set_id,
        active_uuid,
        source_uuid,
        confirmed_by="human",
        reason="Both projects serve the same hospital platform objective",
        human_confirmed=True,
    )
    recommendation = recommend_primary(active, set_id)
    assert recommendation["recommended_project_uuid"] == active_uuid
    assert recommendation["recommendation_is_advisory_only"] is True
    assert recommendation["human_selection_required"] is True


def test_recommendation_prefers_core_application_but_never_selects(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management", role="core_application", capabilities=("patient_management", "billing", "reporting"))
    source = _make_project(tmp_path / "source", name="Adapter", domain_id="healthcare", purpose_id="hospital_management", role="integration_adapter", capabilities=("patient_management",))
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]
    recommendation = recommend_primary(active, set_id)
    assert recommendation["recommended_project_uuid"] == scan_candidate_readonly(active).project_uuid
    assert get_candidate_set(active, set_id)["selection"] is None


def test_primary_selection_requires_human_confirmation(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management")
    source = _make_project(tmp_path / "source", name="Other", domain_id="healthcare", purpose_id="hospital_management")
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]
    with pytest.raises(ProjectSelectionError, match="explicit human confirmation"):
        select_primary(
            active,
            set_id,
            scan_candidate_readonly(active).project_uuid,
            selected_by="human",
            reason="Primary system selected by business owner",
            human_confirmed=False,
        )


def test_selected_primary_must_be_active_root(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="A", domain_id="healthcare", purpose_id="hospital_management")
    other = _make_project(tmp_path / "other", name="B", domain_id="healthcare", purpose_id="hospital_management")
    state = create_candidate_set(active, [other], created_by="human")
    set_id = state["candidate_set"]["id"]
    with pytest.raises(ProjectSelectionError, match="active AgentOS root"):
        select_primary(
            active,
            set_id,
            scan_candidate_readonly(other).project_uuid,
            selected_by="human",
            reason="Attempting to select an external candidate",
            human_confirmed=True,
        )


def test_incompatible_source_blocks_primary_selection(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Hospital", domain_id="healthcare", purpose_id="hospital_management")
    other = _make_project(tmp_path / "other", name="Retail", domain_id="retail", purpose_id="sales_management")
    state = create_candidate_set(active, [other], created_by="human")
    set_id = state["candidate_set"]["id"]
    with pytest.raises(ProjectSelectionError, match="domain_incompatible"):
        select_primary(
            active,
            set_id,
            scan_candidate_readonly(active).project_uuid,
            selected_by="human",
            reason="Should fail because business domains are different",
            human_confirmed=True,
        )


def test_successful_selection_is_persisted_once_with_hash(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management")
    source = _make_project(tmp_path / "source", name="Legacy", domain_id="healthcare", purpose_id="hospital_management")
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]
    active_uuid = scan_candidate_readonly(active).project_uuid
    selected = select_primary(
        active,
        set_id,
        active_uuid,
        selected_by="human-owner",
        reason="Core is the production hospital application and consolidation target",
        human_confirmed=True,
    )
    assert selected["selection"]["primary_project_uuid"] == active_uuid
    assert len(selected["selection"]["selection_hash"]) == 64
    with pytest.raises(ProjectSelectionError, match="already been selected"):
        select_primary(
            active,
            set_id,
            active_uuid,
            selected_by="human-owner",
            reason="Duplicate selection must not replace the original decision",
            human_confirmed=True,
        )


def test_migration_33_creates_only_local_selection_tables(tmp_path: Path) -> None:
    db = tmp_path / "agentos.db"
    conn = sqlite3.connect(db)
    migration_33(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {
        "project_candidate_sets",
        "project_candidates",
        "project_compatibility",
        "primary_project_selections",
        "project_selection_events",
    } <= tables


def test_mcp_gateway_exposes_no_selection_mutation_tool() -> None:
    from agentos.mcp_selection_gateway import TOOLS

    names = {tool["name"] for tool in TOOLS}
    assert "agentos.project_primary_recommend" in names
    assert "agentos.project_primary_selection_get" in names
    assert not any("select" in name and name != "agentos.project_primary_selection_get" for name in names)
    assert not any("confirm" in name for name in names)


def test_compatibility_state_freezes_after_primary_selection(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management")
    source = _make_project(tmp_path / "source", name="Legacy", domain_id="healthcare", purpose_id="hospital_management")
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]
    select_primary(
        active,
        set_id,
        scan_candidate_readonly(active).project_uuid,
        selected_by="human",
        reason="Primary is confirmed before compatibility state is frozen",
        human_confirmed=True,
    )
    # Exact-compatible pairs never need confirmation, but attempting to mutate the
    # pair after selection must still fail before status-specific handling.
    with pytest.raises(ProjectSelectionError, match="frozen"):
        confirm_conditional_compatibility(
            active,
            set_id,
            scan_candidate_readonly(active).project_uuid,
            scan_candidate_readonly(source).project_uuid,
            confirmed_by="human",
            reason="Post-selection compatibility mutation must be rejected",
            human_confirmed=True,
        )


def test_candidate_set_cannot_be_selected_from_copied_database_under_other_identity(tmp_path: Path) -> None:
    active = _make_project(tmp_path / "active", name="Core", domain_id="healthcare", purpose_id="hospital_management")
    source = _make_project(tmp_path / "source", name="Legacy", domain_id="healthcare", purpose_id="hospital_management")
    state = create_candidate_set(active, [source], created_by="human")
    set_id = state["candidate_set"]["id"]

    other = _make_project(tmp_path / "other", name="Other Core", domain_id="healthcare", purpose_id="hospital_management")
    shutil.copy2(active / ".agents/state/agentos.db", other / ".agents/state/agentos.db")
    other_uuid = scan_candidate_readonly(other).project_uuid
    with pytest.raises(ProjectSelectionError, match="different active project root"):
        select_primary(
            other,
            set_id,
            other_uuid,
            selected_by="human",
            reason="Copied coordination database must not transfer selection authority",
            human_confirmed=True,
        )
