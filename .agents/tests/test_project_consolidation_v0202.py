"""
File: .agents/tests/test_project_consolidation_v0202.py

Purpose:
    Verify v0.20.2 Primary-Project Consolidation safety invariants.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from agentos.project_identity import ensure_instance_id, ensure_project_id, set_purpose
from agentos.project_selection import create_candidate_set, scan_candidate_readonly, select_primary
from agentos.project_consolidation import (
    ProjectConsolidationError,
    add_component_mapping,
    approve_consolidation,
    complete_consolidation,
    create_consolidation,
    execute_mapping,
    get_consolidation,
    remove_component_mapping,
    review_consolidation,
    rollback_mapping,
    sync_consolidation_schema,
)


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Create a symlink or skip when Windows has no symlink privilege."""
    try:
        link.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable for this test")
        raise


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _tree_state(root: Path) -> dict[str, tuple[str, int]]:
    state: dict[str, tuple[str, int]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            state[p.relative_to(root).as_posix()] = (_digest(p), p.stat().st_mtime_ns)
    return state


def _make_project(root: Path, *, name: str, role: str = "core_application") -> Path:
    (root / ".agents/config").mkdir(parents=True)
    (root / ".agents/state").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / "VERSION").write_text("0.20.1\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
    (root / ".agents/config/governance.json").write_text(json.dumps({"version": "0.20.1"}), encoding="utf-8")
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
    state = create_candidate_set(primary, [source], created_by="human")
    set_id = int(state["candidate_set"]["id"])
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


def _approved_move(tmp_path: Path, *, target_exists: bool = False):
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/adapter.py").write_text("VALUE = 'source'\n", encoding="utf-8")
    if target_exists:
        (primary / "src/adapter.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    c = add_component_mapping(
        primary,
        cid,
        source_project_uuid=source_uuid,
        source_path="src/adapter.py",
        target_path="src/adapter.py",
        action="MOVE",
        rationale="Import exact adapter implementation into primary",
        created_by="operator",
    )
    mid = int(c["mappings"][0]["id"])
    review_consolidation(primary, cid, reviewed_by="reviewer", reason="Reviewed source hash and target path", human_confirmed=True)
    approve_consolidation(primary, cid, approved_by="owner", reason="Approved exact plan hash for execution", human_confirmed=True)
    return primary, source, cid, mid


def test_create_requires_human_selected_primary(tmp_path: Path) -> None:
    primary = _make_project(tmp_path / "primary", name="Core")
    source = _make_project(tmp_path / "source", name="Adapter", role="integration_adapter")
    state = create_candidate_set(primary, [source], created_by="human")
    with pytest.raises(ProjectConsolidationError, match="human-selected"):
        create_consolidation(primary, int(state["candidate_set"]["id"]), created_by="operator")


def test_create_and_mapping_do_not_modify_secondary_project(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    before = _tree_state(source)
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path="src/a.py", action="MOVE", rationale="Import source module into primary", created_by="operator")
    after = _tree_state(source)
    assert before == after


def test_schema_34_tables_are_created(tmp_path: Path) -> None:
    primary, _source, _set_id, _uuid = _selected_pair(tmp_path)
    result = sync_consolidation_schema(primary)
    assert result["ok"] is True
    assert result["schema"] == 34


def test_source_governance_files_cannot_be_consolidated(tmp_path: Path) -> None:
    primary, _source, set_id, source_uuid = _selected_pair(tmp_path)
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    with pytest.raises(ProjectConsolidationError, match="governance/instruction"):
        add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="AGENTS.md", target_path="docs/source-agents.md", action="MOVE", rationale="Must be rejected by authority rule", created_by="operator")


def test_primary_governance_target_is_blocked(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("x=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    with pytest.raises(ProjectConsolidationError, match="governance/instruction"):
        add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path=".agents/config/governance.json", action="MOVE", rationale="Must not overwrite primary governance", created_by="operator")


def test_two_writing_mappings_cannot_target_same_primary_path(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("a=1\n", encoding="utf-8")
    (source / "src/b.py").write_text("b=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path="src/shared.py", action="MOVE", rationale="First source mapping target", created_by="operator")
    with pytest.raises(ProjectConsolidationError, match="same primary path"):
        add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/b.py", target_path="src/shared.py", action="ADAPT", rationale="Second mapping must be rejected", created_by="operator")


def test_conflict_blocks_review_and_can_be_replanned(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("a=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    c = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path=None, action="CONFLICT", rationale="Primary already has incompatible responsibility", created_by="operator")
    mid = int(c["mappings"][0]["id"])
    with pytest.raises(ProjectConsolidationError, match="CONFLICT"):
        review_consolidation(primary, cid, reviewed_by="reviewer", reason="Conflict is unresolved and must block", human_confirmed=True)
    remove_component_mapping(primary, cid, mid, removed_by="reviewer", reason="Resolve conflict by ignoring legacy component")
    add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path=None, action="IGNORE", rationale="Existing primary implementation remains authoritative", created_by="operator")
    state = review_consolidation(primary, cid, reviewed_by="reviewer", reason="Conflict resolved explicitly as IGNORE", human_confirmed=True)
    assert state["consolidation"]["status"] == "reviewed"


def test_review_and_approval_require_explicit_human_confirmation(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("a=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path=None, action="IGNORE", rationale="Primary already provides this capability", created_by="operator")
    with pytest.raises(ProjectConsolidationError, match="explicit human confirmation"):
        review_consolidation(primary, cid, reviewed_by="reviewer", reason="Review must be confirmed by human", human_confirmed=False)
    review_consolidation(primary, cid, reviewed_by="reviewer", reason="Human reviewed the exact plan hash", human_confirmed=True)
    with pytest.raises(ProjectConsolidationError, match="explicit human confirmation"):
        approve_consolidation(primary, cid, approved_by="owner", reason="Approval must be human confirmed", human_confirmed=False)


def test_approval_is_bound_to_plan_hash_and_freezes_plan(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("a=1\n", encoding="utf-8")
    (source / "src/b.py").write_text("b=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path=None, action="IGNORE", rationale="Ignore one legacy component safely", created_by="operator")
    review_consolidation(primary, cid, reviewed_by="reviewer", reason="Reviewed immutable plan before approval", human_confirmed=True)
    state = approve_consolidation(primary, cid, approved_by="owner", reason="Approved exact reviewed plan hash", human_confirmed=True)
    assert state["approval"]["plan_hash"] == state["current_plan_hash"]
    with pytest.raises(ProjectConsolidationError, match="before approval"):
        add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/b.py", target_path=None, action="IGNORE", rationale="Cannot mutate approved plan", created_by="operator")


def test_move_copies_exact_bytes_to_primary_and_keeps_source_unchanged(tmp_path: Path) -> None:
    primary, source, cid, mid = _approved_move(tmp_path)
    before_source = _tree_state(source)
    source_bytes = (source / "src/adapter.py").read_bytes()
    state = execute_mapping(primary, cid, mid, executed_by="operator")
    assert (primary / "src/adapter.py").read_bytes() == source_bytes
    assert _tree_state(source) == before_source
    assert state["provenance"][0]["source_project_uuid"] == scan_candidate_readonly(source).project_uuid
    assert state["mappings"][0]["status"] == "applied"


def test_source_component_change_after_approval_blocks_execution(tmp_path: Path) -> None:
    primary, source, cid, mid = _approved_move(tmp_path)
    (source / "src/adapter.py").write_text("VALUE = 'changed'\n", encoding="utf-8")
    with pytest.raises(ProjectConsolidationError, match="source component hash changed"):
        execute_mapping(primary, cid, mid, executed_by="operator")


def test_target_change_after_planning_blocks_execution(tmp_path: Path) -> None:
    primary, _source, cid, mid = _approved_move(tmp_path, target_exists=True)
    (primary / "src/adapter.py").write_text("VALUE = 'concurrent-change'\n", encoding="utf-8")
    with pytest.raises(ProjectConsolidationError, match="target hash changed"):
        execute_mapping(primary, cid, mid, executed_by="operator")


def test_adapt_requires_prepared_content_inside_primary(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("a=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    c = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path="src/a.py", action="ADAPT", rationale="Adapt source contract to primary architecture", created_by="operator")
    mid = int(c["mappings"][0]["id"])
    review_consolidation(primary, cid, reviewed_by="reviewer", reason="Reviewed adapted component mapping", human_confirmed=True)
    approve_consolidation(primary, cid, approved_by="owner", reason="Approved adapted component target", human_confirmed=True)
    outside = tmp_path / "outside.py"
    outside.write_text("a=2\n", encoding="utf-8")
    with pytest.raises(ProjectConsolidationError, match="inside the primary project"):
        execute_mapping(primary, cid, mid, executed_by="operator", prepared_content_file=outside)
    staging = primary / ".agents/runtime/task-workspaces/T/adapted.py"
    staging.parent.mkdir(parents=True)
    staging.write_text("a=2\n", encoding="utf-8")
    execute_mapping(primary, cid, mid, executed_by="operator", prepared_content_file=staging)
    assert (primary / "src/a.py").read_text(encoding="utf-8") == "a=2\n"


def test_reuse_records_provenance_without_writing_target(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("legacy=1\n", encoding="utf-8")
    (primary / "src/a.py").write_text("primary=1\n", encoding="utf-8")
    before = _digest(primary / "src/a.py")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    c = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path="src/a.py", action="REUSE", rationale="Reuse established primary implementation", created_by="operator")
    mid = int(c["mappings"][0]["id"])
    review_consolidation(primary, cid, reviewed_by="reviewer", reason="Reuse preserves primary implementation", human_confirmed=True)
    approve_consolidation(primary, cid, approved_by="owner", reason="Approved reuse without file mutation", human_confirmed=True)
    state = execute_mapping(primary, cid, mid, executed_by="operator")
    assert _digest(primary / "src/a.py") == before
    assert state["provenance"][0]["target_before_hash"] == state["provenance"][0]["target_after_hash"]


def test_rollback_restores_replaced_target(tmp_path: Path) -> None:
    primary, _source, cid, mid = _approved_move(tmp_path, target_exists=True)
    old = (primary / "src/adapter.py").read_bytes()
    execute_mapping(primary, cid, mid, executed_by="operator")
    assert (primary / "src/adapter.py").read_bytes() != old
    state = rollback_mapping(primary, cid, mid, confirmed_by="owner", reason="Rollback verified consolidation component", human_confirmed=True)
    assert (primary / "src/adapter.py").read_bytes() == old
    assert state["provenance"][0]["rollback_status"] == "rolled_back"


def test_rollback_removes_new_target_created_by_move(tmp_path: Path) -> None:
    primary, _source, cid, mid = _approved_move(tmp_path, target_exists=False)
    execute_mapping(primary, cid, mid, executed_by="operator")
    assert (primary / "src/adapter.py").exists()
    rollback_mapping(primary, cid, mid, confirmed_by="owner", reason="Remove target created by consolidation", human_confirmed=True)
    assert not (primary / "src/adapter.py").exists()


def test_completion_requires_all_mappings_terminal(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("a=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    c = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path=None, action="IGNORE", rationale="Legacy component is not needed", created_by="operator")
    mid = int(c["mappings"][0]["id"])
    review_consolidation(primary, cid, reviewed_by="reviewer", reason="Reviewed ignore decision for legacy component", human_confirmed=True)
    approve_consolidation(primary, cid, approved_by="owner", reason="Approved ignore decision and exact plan hash", human_confirmed=True)
    with pytest.raises(ProjectConsolidationError, match="non-terminal"):
        complete_consolidation(primary, cid, completed_by="operator")
    execute_mapping(primary, cid, mid, executed_by="operator")
    state = complete_consolidation(primary, cid, completed_by="operator")
    assert state["consolidation"]["status"] == "completed"


def test_path_traversal_and_source_symlink_are_blocked(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("x=1\n", encoding="utf-8")
    _symlink_or_skip(source / "src/link.py", outside)
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    with pytest.raises(ProjectConsolidationError, match="symlink"):
        add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/link.py", target_path="src/link.py", action="MOVE", rationale="Symlink source must fail closed", created_by="operator")
    (source / "src/a.py").write_text("x=1\n", encoding="utf-8")
    with pytest.raises(ProjectConsolidationError, match="clean project-relative"):
        add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path="../escape.py", action="MOVE", rationale="Traversal target must fail closed", created_by="operator")


def test_copied_consolidation_database_cannot_transfer_primary_path_authority(tmp_path: Path) -> None:
    primary, source, set_id, _source_uuid = _selected_pair(tmp_path)
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    clone = tmp_path / "clone"
    import shutil
    shutil.copytree(primary, clone)
    with pytest.raises(ProjectConsolidationError, match="different primary root path"):
        get_consolidation(clone, cid)


def test_mcp_consolidation_tools_are_read_only() -> None:
    from agentos.mcp_consolidation_gateway import TOOLS
    names = {item["name"] for item in TOOLS}
    assert names == {
        "agentos.project_consolidation_get",
        "agentos.project_consolidation_plan_get",
        "agentos.project_consolidation_provenance_get",
    }
    assert not any(any(word in name for word in ("approve", "execute", "rollback", "write", "select")) for name in names)


def test_adapt_rejects_symlink_prepared_content(tmp_path: Path) -> None:
    primary, source, set_id, source_uuid = _selected_pair(tmp_path)
    (source / "src/a.py").write_text("a=1\n", encoding="utf-8")
    c = create_consolidation(primary, set_id, created_by="operator")
    cid = int(c["consolidation"]["id"])
    c = add_component_mapping(primary, cid, source_project_uuid=source_uuid, source_path="src/a.py", target_path="src/a.py", action="ADAPT", rationale="Adapt source under primary architecture", created_by="operator")
    mid = int(c["mappings"][0]["id"])
    review_consolidation(primary, cid, reviewed_by="reviewer", reason="Reviewed adapted mapping and path", human_confirmed=True)
    approve_consolidation(primary, cid, approved_by="owner", reason="Approved adapted mapping hash", human_confirmed=True)
    real = primary / ".agents/runtime/task-workspaces/T/real.py"
    real.parent.mkdir(parents=True)
    real.write_text("a=2\n", encoding="utf-8")
    link = primary / ".agents/runtime/task-workspaces/T/link.py"
    _symlink_or_skip(link, real)
    with pytest.raises(ProjectConsolidationError, match="symlink"):
        execute_mapping(primary, cid, mid, executed_by="operator", prepared_content_file=link)
