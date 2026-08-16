"""Path: .agents/tests/test_architecture_discovery_v0253.py
Purpose: Regression tests for v0.25.3 discovery/evidence and update-preservation invariants.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentos.architecture_discovery import (
    architecture_scan,
    architecture_scan_get,
    architecture_discrepancies_get,
    architecture_observations_get,
    discover_source,
    migration_51,
)
from agentos.architecture_discovery_cli import build_parser as build_discovery_parser
from agentos.mcp_v0253 import TOOL_NAMES
from agentos.update_preservation import (
    classify_path,
    distribution_hashes_from_lock,
    is_project_owned,
    sha256_file,
    verify_distribution_lock,
)


def test_migration_51_creates_discovery_tables():
    c = sqlite3.connect(":memory:")
    migration_51(c)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "architecture_scan_runs", "architecture_observations",
        "architecture_evidence", "architecture_discrepancies",
    } <= names


def test_static_discovery_detects_supported_architecture_signals(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / "src/app.py").write_text("import json\nfrom pathlib import Path\n", encoding="utf-8")
    (tmp_path / "tests/test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests==2.0\npytest>=8\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("TOKEN=example\n", encoding="utf-8")
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    observations, hashes = discover_source(tmp_path, tmp_path)
    kinds = {(o.section_id, o.kind) for o in observations}
    assert ("ARCH-02", "language_inventory") in kinds
    assert ("ARCH-02", "dependency_inventory") in kinds
    assert ("ARCH-12", "python_imports") in kinds
    assert ("ARCH-14", "configuration_inventory") in kinds
    assert ("ARCH-20", "ci_inventory") in kinds
    assert ("ARCH-20", "deployment_inventory") in kinds
    assert ("ARCH-21", "test_inventory") in kinds
    assert "src/app.py" in hashes


def test_discovery_does_not_execute_project_python(tmp_path: Path):
    marker = tmp_path / "EXECUTED"
    (tmp_path / "danger.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\nraise RuntimeError('must not run')\n",
        encoding="utf-8",
    )
    discover_source(tmp_path, tmp_path)
    assert not marker.exists()


def test_default_project_scan_excludes_agents_governance_tree(tmp_path: Path):
    (tmp_path / ".agents/architecture").mkdir(parents=True)
    (tmp_path / ".agents/architecture/secret.json").write_text('{"draft":"x"}', encoding="utf-8")
    (tmp_path / "app.py").write_text("import os\n", encoding="utf-8")
    _, hashes = discover_source(tmp_path, tmp_path)
    assert "app.py" in hashes
    assert ".agents/architecture/secret.json" not in hashes


def test_symlink_is_not_followed(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("import secrets\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    _, hashes = discover_source(tmp_path, tmp_path)
    assert "linked.py" not in hashes


def test_source_root_escape_is_rejected(tmp_path: Path):
    outside = tmp_path.parent
    with pytest.raises(ValueError, match="outside_project"):
        architecture_scan(tmp_path, source_root=outside, created_by="human")


def test_mcp_surface_is_read_only():
    assert TOOL_NAMES == {
        "agentos.architecture_scan_get",
        "agentos.architecture_observations_get",
        "agentos.architecture_evidence_get",
        "agentos.architecture_discrepancies_get",
    }
    assert not any("scan_run" in name or "approve" in name or "activate" in name for name in TOOL_NAMES)


def test_update_ownership_defaults_unknown_paths_to_project_owned():
    baseline = {".agents/agentos/db.py", ".agents/config/governance.json"}
    assert is_project_owned("AGENTS.md")
    assert is_project_owned(".agents/architecture/sections/02-tech-stack.md")
    assert classify_path("src/app.py", baseline) == "PROJECT_OWNED"
    assert classify_path(".agents/agentos/db.py", baseline) == "DISTRIBUTION_MANAGED"


def test_update_ownership_preserves_local_rules_and_workflow_paths():
    for rel in (
        ".agents/config/governance.local.json",
        ".agents/config/project.id",
        ".agents/config/project.purpose.json",
        ".agents/skills/custom/SKILL.md",
        ".agents/workflows/custom.json",
    ):
        assert is_project_owned(rel)


def test_scan_is_idempotent_on_same_source_and_baseline(tmp_path: Path):
    # Fresh AgentOS DB migration is expected to be available in the materialized release.
    (tmp_path / "app.py").write_text("import json\n", encoding="utf-8")
    first = architecture_scan(tmp_path, created_by="human")
    second = architecture_scan(tmp_path, created_by="human")
    assert first["id"] == second["id"]
    assert second["idempotent"] is True
    rows = architecture_observations_get(tmp_path, scan_id=int(first["id"]))
    assert rows
    assert architecture_scan_get(tmp_path, scan_id=int(first["id"]))["scan_hash"] == first["scan_hash"]


def test_distribution_lock_can_gate_future_updates_without_project_source(tmp_path: Path):
    managed = tmp_path / ".agents/agentos/db.py"
    managed.parent.mkdir(parents=True)
    managed.write_text("managed\n", encoding="utf-8")
    project = tmp_path / "src/app.py"
    project.parent.mkdir(parents=True)
    project.write_text("project\n", encoding="utf-8")
    lock = tmp_path / ".agents/config/agentos_distribution.lock.json"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        __import__("json").dumps({
            "managed_files": [{"path": ".agents/agentos/db.py", "sha256": sha256_file(managed)}]
        }),
        encoding="utf-8",
    )
    assert distribution_hashes_from_lock(tmp_path) == {".agents/agentos/db.py": sha256_file(managed)}
    assert verify_distribution_lock(tmp_path) == []
    project.write_text("user changed source\n", encoding="utf-8")
    assert verify_distribution_lock(tmp_path) == []
    managed.write_text("local edit\n", encoding="utf-8")
    assert verify_distribution_lock(tmp_path)[0]["path"] == ".agents/agentos/db.py"


def test_scan_remains_idempotent_after_evidence_change(tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text("import json\n", encoding="utf-8")
    first = architecture_scan(tmp_path, created_by="human")
    source.write_text("import json\nimport pathlib\n", encoding="utf-8")
    changed = architecture_scan(tmp_path, created_by="human")
    repeated = architecture_scan(tmp_path, created_by="human")
    assert changed["id"] != first["id"]
    assert repeated["id"] == changed["id"]
    assert repeated["idempotent"] is True
    findings = architecture_discrepancies_get(tmp_path, scan_id=int(changed["id"]))
    assert any(item["discrepancy_type"] == "evidence_hash_changed" for item in findings)


def test_explicit_agents_source_root_can_scan_agentos_code(tmp_path: Path):
    source_root = tmp_path / ".agents/agentos"
    source_root.mkdir(parents=True)
    target = source_root / "feature.py"
    target.write_text("import sqlite3\n", encoding="utf-8")
    observations, hashes = discover_source(tmp_path, source_root)
    assert ".agents/agentos/feature.py" in hashes
    assert any(o.section_id == "ARCH-12" and o.subject == ".agents/agentos/feature.py" for o in observations)


def test_scan_does_not_persist_raw_source_text(tmp_path: Path):
    secret = "SENSITIVE_SOURCE_LITERAL_9f2d7a"
    (tmp_path / "app.py").write_text(f"import json\nAPI_KEY={secret!r}\n", encoding="utf-8")
    scan = architecture_scan(tmp_path, created_by="human")
    db = sqlite3.connect(tmp_path / ".agents/state/agentos.db")
    try:
        persisted = "\n".join(
            str(value)
            for table, columns in (
                ("architecture_observations", ("value_json", "subject")),
                ("architecture_evidence", ("source_path", "locator_json")),
                ("architecture_discrepancies", ("details_json", "subject")),
            )
            for column in columns
            for (value,) in db.execute(f"SELECT {column} FROM {table} WHERE scan_id=?", (int(scan["id"]),))
        )
    finally:
        db.close()
    assert secret not in persisted


def test_cli_surface_contains_five_discovery_commands():
    parser = build_discovery_parser()
    action = next(a for a in parser._actions if getattr(a, "choices", None))
    assert set(action.choices) == {
        "architecture-scan",
        "architecture-scan-show",
        "architecture-observations",
        "architecture-evidence",
        "architecture-discrepancies",
    }
