"""Path: .agents/tests/test_architecture_quality_v0263.py
Purpose: Regression tests for v0.26.3 Quality/Security/Operational Architecture Enforcement.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.architecture_quality import architecture_quality_check, architecture_quality_status, architecture_quality_target_check
from agentos.core import start_task
from agentos.db import SCHEMA_VERSION, connect
from agentos.human_decision import record_clarity_assessment
from agentos.mcp_v0263 import TOOLS as V0263_TOOLS
from agentos.planning import submit_plan


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / ".agents").mkdir(parents=True)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    start_task(root, "T1", "Change quality boundary safely")
    record_clarity_assessment(root, "T1", "pytest", objective_understood=True, scope_understood=True, constraints_understood=True, acceptance_understood=True)
    return root


def _active(root: Path, digest: str = "a" * 64, version: int = 1) -> int:
    with connect(root, immediate=True) as connection:
        cur = connection.execute(
            """INSERT INTO architecture_baselines(
               baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by,activated_by,activated_at
               ) VALUES(?,?, 'active', ?,27,'human:test','human:test',CURRENT_TIMESTAMP)""",
            (f"b-{version}", version, digest),
        )
        return int(cur.lastrowid)


def _section(root: Path, baseline_id: int, section_id: str, payload: dict) -> None:
    contract = json.dumps({"payload": payload}, sort_keys=True, separators=(",", ":"))
    with connect(root, immediate=True) as connection:
        cur = connection.execute(
            """INSERT INTO architecture_section_revisions(
               section_id,revision,title,applicability,authority_mode,markdown_hash,contract_hash,section_hash,
               markdown_content,contract_json,created_by
               ) VALUES(?,1,?,'applicable','current',?,?,?,?,?,?)""",
            (section_id, section_id, "m" * 64, "c" * 64, (section_id[-2:] * 32)[:64], "x", contract, "human:test"),
        )
        connection.execute(
            "INSERT INTO architecture_baseline_sections(baseline_id,section_id,section_revision_id,section_hash) VALUES(?,?,?,?)",
            (baseline_id, section_id, int(cur.lastrowid), (section_id[-2:] * 32)[:64]),
        )


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _plan(files: list[str], sections: list[str]) -> dict:
    return {
        "goal": "Change quality boundary",
        "requirements": ["REQ-1 preserve approved quality architecture"],
        "files": files,
        "affected_architecture_sections": sections,
        "expected_modules": [p for p in files if p.endswith(".py")],
        "expected_dependency_edges": [],
        "acceptance_criteria": ["quality architecture gates pass"],
        "tests": ["tests/test_quality.py"],
    }


def test_schema_57_quality_tables_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    with connect(root) as connection:
        version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION and version >= 57
    assert {"architecture_quality_runs", "architecture_quality_findings"} <= tables


def test_no_active_baseline_is_not_evaluable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    assert architecture_quality_target_check(root, "src/service.py")["enforced"] is False
    result = architecture_quality_check(root, task_id="T1", changed_files=["src/service.py"], mode="test")
    assert result["ok"] is True and result["status"] == "not_evaluable"


def test_sensitive_logging_contract_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-15", {"forbid_sensitive_log_arguments": True})
    _write(root, "src/service.py", 'import logging\nlogger=logging.getLogger(__name__)\napi_token="x"\nlogger.info(api_token)\n')
    result = architecture_quality_check(root, task_id="T1", changed_files=["src/service.py"], mode="test")
    assert any(item["finding_code"] == "architecture_sensitive_logging_forbidden" for item in result["findings"])


def test_bare_except_contract_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-16", {"forbid_bare_except": True})
    _write(root, "src/service.py", 'try:\n    run()\nexcept:\n    pass\n')
    result = architecture_quality_check(root, task_id="T1", changed_files=["src/service.py"], mode="test")
    assert any(item["finding_code"] == "architecture_bare_except_forbidden" for item in result["findings"])


def test_security_shell_true_and_verify_false_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-17", {"forbid_shell_true": True, "forbid_tls_verify_false": True})
    _write(root, "src/service.py", 'import subprocess, requests\nsubprocess.run("echo x", shell=True)\nrequests.get("https://example.com", verify=False)\n')
    result = architecture_quality_check(root, task_id="T1", changed_files=["src/service.py"], mode="test")
    codes = {item["finding_code"] for item in result["findings"]}
    assert {"architecture_shell_true_forbidden", "architecture_tls_verify_false_forbidden"} <= codes


def test_performance_async_blocking_call_contract_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-18", {"forbidden_blocking_calls_in_async": ["time.sleep"]})
    _write(root, "src/worker.py", 'import time\nasync def run():\n    time.sleep(1)\n')
    result = architecture_quality_check(root, task_id="T1", changed_files=["src/worker.py"], mode="test")
    assert any(item["finding_code"] == "architecture_async_blocking_call_forbidden" for item in result["findings"])


def test_deployment_container_contract_blocks_unapproved_root_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-20", {"allowed_container_base_images": ["python:3.12-slim"], "require_non_root_container_user": True})
    _write(root, "Dockerfile", "FROM python:3.13\nRUN echo hi\n")
    result = architecture_quality_check(root, task_id="T1", changed_files=["Dockerfile"], mode="test")
    codes = {item["finding_code"] for item in result["findings"]}
    assert {"architecture_container_base_image_unapproved", "architecture_container_non_root_user_required"} <= codes


def test_testing_contract_requires_test_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-21", {"required_test_changes_by_source": [{"source_paths": ["src/*.py"], "test_paths": ["tests/test_*.py"]}]})
    _write(root, "src/service.py", "def run():\n    return 1\n")
    result = architecture_quality_check(root, task_id="T1", changed_files=["src/service.py"], mode="test")
    assert any(item["finding_code"] == "architecture_required_test_change_missing" for item in result["findings"])


def test_quality_affected_plan_requires_explicit_declaration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); _active(root)
    plan = _plan(["src/service.py"], ["ARCH-17"])
    with pytest.raises(RuntimeError, match="architecture_plan_blocked"):
        submit_plan(root, "T1", "S1", plan)


def test_quality_plan_with_explicit_security_declaration_can_continue_to_other_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); _active(root)
    plan = _plan(["src/service.py"], ["ARCH-17"])
    plan["expected_security_changes"] = ["preserve-auth-boundary"]
    # This assertion only verifies the v0.26.3 declaration blocker is absent from impact analysis.
    from agentos.architecture_planning import architecture_plan_impact
    report = architecture_plan_impact(root, "T1", plan)
    assert not any(item.get("code") == "architecture_quality_plan_declaration_required" for item in report.get("blockers", []))


def test_quality_status_preserves_human_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    status = architecture_quality_status(root)
    assert status["approval_authority_exposed"] is False
    assert status["waiver_authority_exposed"] is False
    assert status["automatic_architecture_mutation"] is False
    assert status["project_code_execution"] is False
    assert status["network_access"] is False
    assert status["llm_quality_authority"] is False


def test_mcp_v0263_is_read_only_three_tool_surface() -> None:
    names = {item["name"] for item in V0263_TOOLS}
    assert names == {
        "agentos.architecture_quality_status_get",
        "agentos.architecture_quality_findings_get",
        "agentos.architecture_quality_target_get",
    }
    assert not any(any(word in name for word in ("approve", "submit", "activate", "mutate", "waive", "check_run")) for name in names)
