"""
File: .agents/tests/test_agentos.py

Purpose:
    Verify AgentOS v0.7.1 runtime and synchronization guarantees.

Responsibilities:
    - Test guarded task and write behavior.
    - Test composite change preparation.
    - Test evidence-grounded claims and atomicity.
    - Test symlink containment and documentation synchronization.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agentos.core import (
    approve_task,
    check_write,
    db_status,
    docs_check,
    instruction_check,
    list_claims,
    prepare_change,
    record_claim,
    record_tool_execution,
    show_claim,
    start_task,
)
from agentos.db import connect
from agentos.indexing import duplicate_report, index_build
from agentos.policy import load_policy, validate_policy


def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".agents" / "config").mkdir(parents=True)
    (root / ".agents" / "state").mkdir(parents=True)
    (root / ".agents" / "docs").mkdir(parents=True)
    (root / "src").mkdir()
    source_root = Path(__file__).resolve().parents[2]
    (root / ".agents" / "config" / "governance.json").write_text(
        (source_root / ".agents" / "config" / "governance.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for rel in ["README.md", "AGENTS.md", "huong_dan.md", "VERSION"]:
        (root / rel).write_text((source_root / rel).read_text(encoding="utf-8"), encoding="utf-8")
    for rel in ["USAGE.md", "PROJECT_STRUCTURE.md", "RULES_WORKFLOW_CHANGELOG.md"]:
        (root / ".agents" / "docs" / rel).write_text((source_root / ".agents" / "docs" / rel).read_text(encoding="utf-8"), encoding="utf-8")
    return root


def ready(root: Path, task_id: str = "T1", scope: list[str] | None = None) -> None:
    start_task(root, task_id, "test request")
    approve_task(root, task_id, scope or ["src", "tests", ".agents", "README.md"])


def test_write_requires_approval(tmp_path: Path) -> None:
    root = project(tmp_path)
    start_task(root, "T1", "x")
    result = check_write(root, "T1", "src/a.py")
    assert result == {"allowed": False, "reason": "task_not_approved", "target": "src/a.py"}


def test_write_rejects_outside_scope(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root, scope=["src/orders"])
    assert check_write(root, "T1", "src/payments/a.py")["reason"] == "outside_approved_scope"


def test_path_traversal_denied(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    result = check_write(root, "T1", "../outside.py")
    assert not result["allowed"]
    assert result["reason"] == "outside_project_root"


def _symlink(link: Path, target: Path, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is not permitted: {exc}")


def test_symlink_file_escape_denied(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "target.py"
    target.write_text("x = 1\n", encoding="utf-8")
    link = root / "src" / "linked.py"
    _symlink(link, target)
    result = check_write(root, "T1", "src/linked.py")
    assert result["allowed"] is False
    assert result["reason"] == "outside_project_root"


def test_symlink_directory_escape_denied(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "src" / "outside_dir"
    _symlink(link, outside, target_is_directory=True)
    result = check_write(root, "T1", "src/outside_dir/a.py")
    assert result["allowed"] is False
    assert result["reason"] == "outside_project_root"


def test_internal_symlink_allowed_when_scope_allows(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    actual = root / "src" / "actual"
    actual.mkdir()
    link = root / "src" / "alias"
    _symlink(link, actual, target_is_directory=True)
    result = check_write(root, "T1", "src/alias/a.py")
    assert result["allowed"] is True
    assert result["target"] == "src/actual/a.py"


def test_prepare_change_modify_combines_context_and_write(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    (root / "src" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    index_build(root)
    result = prepare_change(root, "T1", "modify", "src/a.py", "Change return value", ["a"])
    assert result["effective_target"] == "src/a.py"
    assert result["write"]["allowed"]
    assert result["ready"]
    assert result["recommended_context"][0]["qualname"] == "a"


def test_prepare_change_create_uses_resolved_target_everywhere(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    result = prepare_change(root, "T1", "create", "date_converter.py", "Convert dates", ["convert_excel_date"], feature="reporting", layer="application", file_kind="source")
    assert result["effective_target"] == "src/reporting/application/date_converter.py"
    assert result["placement"]["resolved_path"] == result["effective_target"]
    assert result["write"]["target"] == result["effective_target"]


def test_prepare_change_rejects_invalid_operation(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    with pytest.raises(RuntimeError, match="operation must be create or modify"):
        prepare_change(root, "T1", "delete", "src/a.py", "x")


def test_prepare_change_rejects_unknown_task(tmp_path: Path) -> None:
    root = project(tmp_path)
    with pytest.raises(RuntimeError, match="task not found"):
        prepare_change(root, "missing", "modify", "src/a.py", "x")


def test_duplicate_report_detects_identical_functions(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "src" / "a.py").write_text("def a(x):\n    return x + 1\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("def a(x):\n    return x + 1\n", encoding="utf-8")
    index_build(root)
    assert len(duplicate_report(root)) == 1


def test_record_claim_links_successful_local_evidence(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    call_id = record_tool_execution(root, "T1", "bounded_file_read", {"path": "src/a.py"}, True, "read ok")["tool_call_id"]
    result = record_claim(root, "T1", "Function a returns a constant", "business_logic", "high", [call_id])
    assert result["evidence_count"] == 1
    assert list_claims(root, "T1")[0]["evidence_count"] == 1
    assert show_claim(root, result["claim_id"])["evidence"][0]["tool_call_id"] == call_id


def test_high_risk_claim_requires_evidence(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    with pytest.raises(RuntimeError, match="evidence is required"):
        record_claim(root, "T1", "Unverified", "security", "high", [])


def test_sensitive_medium_claim_requires_evidence(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    with pytest.raises(RuntimeError, match="evidence is required"):
        record_claim(root, "T1", "Unverified", "data_behavior", "medium", [])


def test_low_risk_claim_can_be_recorded_without_evidence(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    result = record_claim(root, "T1", "Naming could be clearer", "other", "low", [])
    assert result["evidence_count"] == 0


def test_claim_rejects_unknown_or_failed_evidence(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    with pytest.raises(RuntimeError, match="not found"):
        record_claim(root, "T1", "x", "security", "high", [999])
    failed = record_tool_execution(root, "T1", "read", {}, False, "failed")["tool_call_id"]
    with pytest.raises(RuntimeError, match="not successful"):
        record_claim(root, "T1", "x", "security", "high", [failed])


def test_claim_rejects_other_task_evidence(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root, "T1")
    ready(root, "T2")
    call_id = record_tool_execution(root, "T2", "read", {}, True, "ok")["tool_call_id"]
    with pytest.raises(RuntimeError, match="another task"):
        record_claim(root, "T1", "x", "security", "high", [call_id])


def test_claim_rejects_nonlocal_evidence_by_default(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    call_id = record_tool_execution(root, "T1", "web", {}, True, "ok", "network")["tool_call_id"]
    with pytest.raises(RuntimeError, match="not local evidence"):
        record_claim(root, "T1", "x", "security", "high", [call_id])


def test_claim_validation_and_evidence_deduplication(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    call_id = record_tool_execution(root, "T1", "read", {}, True, "ok")["tool_call_id"]
    result = record_claim(root, "T1", "x", "security", "high", [call_id, call_id])
    assert result["linked_evidence"] == [call_id]
    with pytest.raises(RuntimeError, match="invalid claim_type"):
        record_claim(root, "T1", "x", "invalid", "low", [])
    with pytest.raises(RuntimeError, match="invalid risk"):
        record_claim(root, "T1", "x", "other", "critical", [])


def test_claim_insert_is_atomic(tmp_path: Path) -> None:
    root = project(tmp_path)
    ready(root)
    good = record_tool_execution(root, "T1", "read", {}, True, "ok")["tool_call_id"]
    with pytest.raises(RuntimeError):
        record_claim(root, "T1", "must not persist", "security", "high", [good, 999])
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"] == 0


def test_policy_and_database_are_current(tmp_path: Path) -> None:
    root = project(tmp_path)
    policy = load_policy(root)
    assert policy["version"] == "0.7.1"
    assert db_status(root) == {"current": 4, "required": 4, "is_current": True}


def test_policy_validation_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="missing policy key"):
        validate_policy({"version": "0.7.1"})


def test_docs_and_instruction_checks_pass_for_release() -> None:
    root = Path(__file__).resolve().parents[2]
    assert docs_check(root)["ok"] is True
    assert instruction_check(root)["ok"] is True
