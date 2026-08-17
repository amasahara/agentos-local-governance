"""Path: .agents/tests/test_architecture_compliance_v0254.py
Purpose: Regression tests for v0.25.4 Architecture Drift & Compliance Engine.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from agentos.architecture_compliance import architecture_compliance_check, architecture_target_check
from agentos.architecture_discovery import SCANNER_VERSION, architecture_observations_get
from agentos.db import SCHEMA_VERSION, connect


def _section(root: Path, section_id: str, payload: dict, applicability: str = "applicable") -> None:
    contract = {
        "contract_schema_version": 1,
        "section_id": section_id,
        "title": section_id,
        "applicability": applicability,
        "authority_mode": "current",
        "payload": payload,
    }
    text = json.dumps(contract, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode()).hexdigest()
    with connect(root, immediate=True) as c:
        base = c.execute("SELECT id FROM architecture_baselines WHERE status='active'").fetchone()
        if not base:
            c.execute("INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by,activated_by,activated_at) VALUES('test-baseline',1,'active',?,27,'human:test','human:test',CURRENT_TIMESTAMP)", ("b" * 64,))
            base = c.execute("SELECT id FROM architecture_baselines WHERE status='active'").fetchone()
        rev = c.execute("SELECT COALESCE(MAX(revision),0)+1 FROM architecture_section_revisions WHERE section_id=?", (section_id,)).fetchone()[0]
        c.execute("INSERT INTO architecture_section_revisions(section_id,revision,title,applicability,authority_mode,markdown_hash,contract_hash,section_hash,markdown_content,contract_json,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (section_id, rev, section_id, applicability, "current", "m"*64, digest, digest, "# test", text, "human:test"))
        sr = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute("INSERT OR REPLACE INTO architecture_baseline_sections(baseline_id,section_id,section_revision_id,section_hash) VALUES(?,?,?,?)", (base[0], section_id, sr, digest))


def test_schema_52_and_scanner_v2(tmp_path: Path) -> None:
    with connect(tmp_path) as c:
        version = c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 52
    assert SCANNER_VERSION == 2
    assert {"architecture_compliance_runs", "architecture_compliance_findings"} <= tables


def test_no_active_baseline_is_not_evaluable_and_non_blocking(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    report = architecture_compliance_check(tmp_path, mode="manual")
    assert report["ok"] is True
    assert report["enforced"] is False
    assert report["status"] == "not_evaluable"


def test_unapproved_dependency_blocks_active_baseline(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests==2.0\n", encoding="utf-8")
    _section(tmp_path, "ARCH-02", {"allowed_dependencies": ["httpx"]})
    report = architecture_compliance_check(tmp_path, mode="precommit")
    assert report["ok"] is False
    assert report["status"] == "block"
    assert any(x["finding_code"] == "unapproved_dependency" and x["subject"] == "requests" for x in report["findings"])


def test_target_write_root_is_enforced_only_with_active_baseline(tmp_path: Path) -> None:
    _section(tmp_path, "ARCH-03", {"allowed_write_roots": ["src"]})
    assert architecture_target_check(tmp_path, "src/app.py")["allowed"] is True
    denied = architecture_target_check(tmp_path, "scripts/escape.py")
    assert denied["allowed"] is False
    assert denied["reason"] == "architecture_write_root_violation"


def test_static_scanner_adds_module_domain_and_environment_name_without_value(tmp_path: Path) -> None:
    src = tmp_path / "src"; src.mkdir()
    secret = "VERY_SECRET_VALUE_MUST_NOT_PERSIST"
    (src / "app.py").write_text('import os\nTOKEN=os.getenv("SERVICE_TOKEN")\nURL="https://api.example.com/v1?token=' + secret + '"\n', encoding="utf-8")
    _section(tmp_path, "ARCH-13", {"allowed_domains": ["api.example.com"]})
    report = architecture_compliance_check(tmp_path, mode="manual")
    assert report["ok"] is True
    scan_id = report["scan_id"]
    observations = architecture_observations_get(tmp_path, scan_id=scan_id)
    kinds = {(x["section_id"], x["observation_kind"]) for x in observations}
    assert ("ARCH-05", "module_inventory") in kinds
    assert ("ARCH-13", "external_service_domains") in kinds
    assert ("ARCH-14", "environment_variables") in kinds
    database = tmp_path / ".agents/state/agentos.db"
    assert secret.encode() not in database.read_bytes()


def test_forbidden_import_edge_blocks(tmp_path: Path) -> None:
    src = tmp_path / "src"; src.mkdir()
    (src / "api.py").write_text("import sqlite3\n", encoding="utf-8")
    _section(tmp_path, "ARCH-12", {"forbidden_import_edges": [{"from": "src/api.py", "import": "sqlite3"}]})
    report = architecture_compliance_check(tmp_path, mode="manual")
    assert report["ok"] is False
    assert any(x["finding_code"] == "forbidden_import_edge" for x in report["findings"])


def test_pinned_evidence_hash_mismatch_blocks(tmp_path: Path) -> None:
    path = tmp_path / "requirements.txt"
    path.write_text("requests\n", encoding="utf-8")
    wrong = "0" * 64
    _section(tmp_path, "ARCH-02", {"evidence_bindings": [{"source_path": "requirements.txt", "sha256": wrong}]})
    report = architecture_compliance_check(tmp_path, mode="manual")
    assert report["ok"] is False
    assert any(x["finding_code"] == "architecture_evidence_hash_mismatch" for x in report["findings"])


def test_mcp_v0254_surface_is_read_only() -> None:
    from agentos.mcp_v0254 import TOOL_NAMES
    assert TOOL_NAMES == {
        "agentos.architecture_compliance_get",
        "agentos.architecture_compliance_findings_get",
        "agentos.architecture_compliance_status_get",
    }
    assert not any(any(word in name for word in ("approve", "waive", "ack", "execute", "activate")) for name in TOOL_NAMES)
