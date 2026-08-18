"""Path: .agents/tests/test_architecture_runtime_v0262.py
Purpose: Regression tests for v0.26.2 Runtime/Data/API & Business Boundary Enforcement.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.architecture_runtime import (
    architecture_runtime_check,
    architecture_runtime_status,
    architecture_runtime_target_check,
)
from agentos.core import start_task
from agentos.db import SCHEMA_VERSION, connect
from agentos.human_decision import record_clarity_assessment
from agentos.mcp_v0262 import TOOLS as V0262_TOOLS
from agentos.planning import submit_plan


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / ".agents").mkdir(parents=True)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    start_task(root, "T1", "Change runtime boundary safely")
    record_clarity_assessment(
        root,
        "T1",
        "pytest",
        objective_understood=True,
        scope_understood=True,
        constraints_understood=True,
        acceptance_understood=True,
    )
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
        "goal": "Change runtime boundary",
        "requirements": ["REQ-1 preserve approved runtime architecture"],
        "files": files,
        "affected_architecture_sections": sections,
        "expected_modules": [p for p in files if p.endswith(".py")],
        "expected_dependency_edges": [],
        "acceptance_criteria": ["runtime architecture gates pass"],
        "tests": ["tests/test_runtime.py"],
    }


def test_schema_56_runtime_tables_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    with connect(root) as connection:
        version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION
    assert version >= 56
    assert {"architecture_runtime_runs", "architecture_runtime_findings"} <= tables


def test_no_active_baseline_preserves_non_enforcement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    assert architecture_runtime_target_check(root, "src/api.py")["enforced"] is False
    result = architecture_runtime_check(root, task_id="T1", changed_files=["src/api.py"], mode="test")
    assert result["ok"] is True and result["status"] == "not_evaluable"


def test_database_write_outside_approved_data_layer_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-09", {"allowed_sql_operations": ["SELECT", "UPDATE"], "allowed_data_objects": ["users"], "data_write_allowed_paths": ["src/repository/*.py"]})
    _write(root, "src/api/users.py", 'SQL = "UPDATE users SET name = ?"\n')
    result = architecture_runtime_check(root, task_id="T1", changed_files=["src/api/users.py"], mode="test")
    assert result["ok"] is False
    assert any(item["finding_code"] == "architecture_data_write_boundary_violation" for item in result["findings"])


def test_api_route_outside_contract_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-10", {"allowed_http_methods": ["GET", "POST"], "allowed_route_prefixes": ["/api/v1"]})
    _write(root, "src/api/routes.py", '@router.get("/admin/raw")\ndef raw():\n    return {}\n')
    result = architecture_runtime_check(root, task_id="T1", changed_files=["src/api/routes.py"], mode="test")
    assert any(item["finding_code"] == "architecture_api_route_outside_contract" for item in result["findings"])


def test_unapproved_external_service_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-13", {"allowed_hosts": ["api.example.com"], "allowed_url_schemes": ["https"]})
    _write(root, "src/integrations/client.py", 'URL = "https://evil.example.net/v1"\n')
    result = architecture_runtime_check(root, task_id="T1", changed_files=["src/integrations/client.py"], mode="test")
    assert any(item["finding_code"] == "architecture_external_service_unapproved" for item in result["findings"])


def test_config_secret_access_boundary_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-14", {"allowed_env_vars": ["API_TOKEN"], "secret_env_vars": ["API_TOKEN"], "secret_access_allowed_paths": ["src/config/*.py"]})
    _write(root, "src/api/routes.py", 'import os\nTOKEN = os.getenv("API_TOKEN")\n')
    result = architecture_runtime_check(root, task_id="T1", changed_files=["src/api/routes.py"], mode="test")
    assert any(item["finding_code"] == "architecture_secret_access_boundary_violation" for item in result["findings"])


def test_required_authentication_guard_by_path_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-07", {"required_auth_calls_by_path": [{"paths": ["src/api/*.py"], "calls": ["auth.require_user"]}]})
    _write(root, "src/api/profile.py", 'def profile():\n    return {}\n')
    result = architecture_runtime_check(root, task_id="T1", changed_files=["src/api/profile.py"], mode="test")
    assert any(item["finding_code"] == "architecture_authentication_guard_missing" for item in result["findings"])


def test_runtime_affected_plan_requires_explicit_declaration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); _active(root)
    plan = _plan(["src/repository/users.py"], ["ARCH-09"])
    with pytest.raises(RuntimeError, match="architecture_plan_blocked"):
        submit_plan(root, "T1", "S1", plan)


def test_plan_unapproved_external_service_blocks_before_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch); baseline = _active(root)
    _section(root, baseline, "ARCH-13", {"allowed_hosts": ["api.example.com"]})
    plan = _plan(["src/integrations/client.py"], ["ARCH-13"])
    plan["expected_external_services"] = ["https://evil.example.net/v1"]
    with pytest.raises(RuntimeError, match="architecture_plan_blocked"):
        submit_plan(root, "T1", "S1", plan)


def test_runtime_status_keeps_human_architecture_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    status = architecture_runtime_status(root)
    assert status["approval_authority_exposed"] is False
    assert status["waiver_authority_exposed"] is False
    assert status["automatic_architecture_mutation"] is False
    assert status["project_code_execution"] is False
    assert status["llm_runtime_authority"] is False


def test_mcp_v0262_is_read_only_three_tool_surface() -> None:
    names = {item["name"] for item in V0262_TOOLS}
    assert names == {
        "agentos.architecture_runtime_status_get",
        "agentos.architecture_runtime_findings_get",
        "agentos.architecture_runtime_target_get",
    }
    assert not any(any(word in name for word in ("approve", "submit", "activate", "mutate", "waive", "check_run")) for name in names)
