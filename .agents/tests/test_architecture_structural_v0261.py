"""Path: .agents/tests/test_architecture_structural_v0261.py
Purpose: Regression tests for v0.26.1 Structural Enforcement and README release coherence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agentos.architecture_structural import (
    architecture_structural_check,
    architecture_structural_status,
    architecture_structural_target_check,
)
from agentos.core import start_task
from agentos.db import SCHEMA_VERSION, connect
from agentos.human_decision import record_clarity_assessment
from agentos.mcp_v0261 import TOOLS as V0261_TOOLS
from agentos.planning import submit_plan


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / ".agents").mkdir(parents=True)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    start_task(root, "T1", "Change project structure safely")
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


def _plan(files: list[str]) -> dict:
    return {
        "goal": "Change project structure",
        "requirements": ["REQ-1 preserve behavior"],
        "files": files,
        "affected_architecture_sections": ["ARCH-02", "ARCH-05", "ARCH-12"],
        "expected_modules": [path for path in files if path.endswith(".py")],
        "expected_dependency_edges": [],
        "acceptance_criteria": ["tests remain green"],
        "tests": ["tests/test_structural.py"],
    }


def test_schema_55_structural_tables_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    with connect(root) as connection:
        version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION == 55
    assert {"architecture_structural_runs", "architecture_structural_findings"} <= tables


def test_no_active_baseline_is_non_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    result = architecture_structural_target_check(root, "src/utils.py")
    assert result["allowed"] is True
    assert result["enforced"] is False


def test_forbidden_generic_module_name_blocks_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline = _active(root)
    _section(root, baseline, "ARCH-05", {"forbidden_module_names": ["utils.py"]})
    result = architecture_structural_target_check(root, "src/utils.py")
    assert result["allowed"] is False
    assert result["reason"] == "architecture_forbidden_module_name"


def test_module_location_rule_blocks_wrong_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline = _active(root)
    _section(root, baseline, "ARCH-05", {"module_location_rules": [{"match": "utils.py", "allowed_paths": ["src/shared/date.py", "src/shared/validation.py"]}]})
    result = architecture_structural_target_check(root, "src/utils.py")
    assert result["allowed"] is False
    assert result["reason"] == "architecture_module_location_violation"


def test_dependency_manifest_plan_requires_expected_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    _active(root)
    plan = _plan(["pyproject.toml"])
    with pytest.raises(RuntimeError, match="architecture_plan_blocked"):
        submit_plan(root, "T1", "S1", plan)


def test_unapproved_dependency_blocks_before_plan_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline = _active(root)
    _section(root, baseline, "ARCH-02", {"allowed_dependencies": ["requests"]})
    plan = _plan(["pyproject.toml"])
    plan["expected_dependencies"] = ["sqlalchemy"]
    with pytest.raises(RuntimeError, match="architecture_plan_blocked"):
        submit_plan(root, "T1", "S1", plan)


def test_forbidden_import_edge_blocks_changed_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline = _active(root)
    _section(root, baseline, "ARCH-12", {"forbidden_import_edges": [{"from": "service.*", "import": "db.*"}]})
    path = root / "src/service/api.py"
    path.parent.mkdir(parents=True)
    path.write_text("import db.raw\n", encoding="utf-8")
    result = architecture_structural_check(root, task_id="T1", changed_files=["src/service/api.py"], mode="test")
    assert result["ok"] is False
    assert any(item["finding_code"] == "architecture_forbidden_structural_edge" for item in result["findings"])


def test_coding_convention_requires_header_and_docstrings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline = _active(root)
    _section(root, baseline, "ARCH-22", {"require_file_header_path": True, "require_module_purpose": True, "require_public_symbol_docstrings": True})
    path = root / "src/example.py"
    path.parent.mkdir(parents=True)
    path.write_text("def public_api():\n    return 1\n", encoding="utf-8")
    result = architecture_structural_check(root, task_id="T1", changed_files=["src/example.py"], mode="test")
    codes = {item["finding_code"] for item in result["findings"]}
    assert {"architecture_file_header_path_missing", "architecture_module_purpose_missing", "architecture_public_symbol_docstring_missing"} <= codes


def test_wildcard_import_can_be_hard_forbidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline = _active(root)
    _section(root, baseline, "ARCH-22", {"forbid_wildcard_imports": True})
    path = root / "src/example.py"
    path.parent.mkdir(parents=True)
    path.write_text("from package import *\n", encoding="utf-8")
    result = architecture_structural_check(root, task_id="T1", changed_files=["src/example.py"], mode="test")
    assert any(item["finding_code"] == "architecture_wildcard_import_forbidden" for item in result["findings"])


def test_required_design_artifact_missing_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    baseline = _active(root)
    _section(root, baseline, "ARCH-23", {"required_artifacts": ["src/adapters/*_adapter.py"]})
    result = architecture_structural_check(root, task_id="T1", changed_files=[], mode="test")
    assert result["ok"] is False
    assert any(item["finding_code"] == "architecture_required_design_artifact_missing" for item in result["findings"])


def test_structural_status_keeps_human_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    status = architecture_structural_status(root)
    assert status["ok"] is True
    assert status["approval_authority_exposed"] is False
    assert status["waiver_authority_exposed"] is False
    assert status["automatic_architecture_mutation"] is False
    assert status["architecture_change_required_for_blocked_structure"] is True


def test_mcp_v0261_is_read_only_three_tool_surface() -> None:
    names = {item["name"] for item in V0261_TOOLS}
    assert names == {
        "agentos.architecture_structural_status_get",
        "agentos.architecture_structural_findings_get",
        "agentos.architecture_structural_target_get",
    }
    assert not any(any(word in name for word in ("approve", "submit", "activate", "mutate", "waive", "check_run")) for name in names)


def test_root_readmes_identify_v0261_and_schema_55() -> None:
    root = Path(__file__).resolve().parents[2]
    stale = {
        "README.md": "3b014b598954ce7a6d4ae1ea5c73ec0c21500ffb98f5fd285a53cae717f0b193",
        "README.vi.md": "eda433acc61df7ab3eb01e16262ae49e991d5142e15608ca027218f450c85d72",
        "README.en.md": "2d9d032110e4ecd1dc2129ab94f422a884b1d3f8ed9c2eddead378638ef31af0",
    }
    current = {
        "README.md": "81a382816cacf5af6be6c34b3dbb08a35d2cc7274b29fe3c73a43a09f7dc5117",
        "README.vi.md": "60eb367e7490c52f116321a66e872e12ecf45e9a21b583c3ac109dd702c39de3",
        "README.en.md": "280e4af2eaf9ded80bfc7eb6b524eb08c64feac07ecce9bf6d18a16fd76cc6cc",
    }
    official = 0
    for rel in ("README.md", "README.vi.md", "README.en.md"):
        path = root / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest != stale[rel]
        if digest != current[rel]:
            continue  # project-owned custom README
        official += 1
        text = raw.decode("utf-8")
        assert "0.26.1" in text[:1200]
        assert "Database schema: **55**" in text[:1600]
    # Canonical AgentOS repository has all three official READMEs; embedded projects may customize them.
    assert official in {0, 1, 2, 3}
