"""
File: .agents/tests/test_release_hardening_v0242.py

Purpose:
    Verify v0.24.2 publication hardening: clean CI, semantic docs, local links,
    and strict read-only SQLite access for DB-aware MCP telemetry.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agentos.core import docs_check
from agentos.db import SCHEMA_VERSION, connect_read_only
from agentos.db_aware_context_projection import projection_status

ROOT = Path(__file__).resolve().parents[2]


def test_github_workflow_uses_generic_current_release_validator() -> None:
    text = (ROOT / ".github/workflows/agentos-release-validation.yml").read_text(encoding="utf-8")
    assert "validate_v0232.py" not in text
    assert "python tools/validate_release.py ." in text
    assert "python tools/verify_manifest.py ." in text


def test_current_docs_identify_db_aware_context_projection_and_links_resolve() -> None:
    report = docs_check(ROOT)
    assert report["ok"] is True
    consistency = report["content_consistency"]
    assert consistency["release_identity_mismatches"] == []
    assert consistency["broken_local_links"] == []


def test_upgrade_guide_uses_external_release_asset_model() -> None:
    guides = sorted(ROOT.glob("UPGRADE_FROM_*.md"))
    assert len(guides) == 1
    text = guides[0].read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    updater = f"apply_v{version.replace('.', '')}.py"
    assert f"python tools/{updater}" not in text
    assert "GitHub Release" in text
    assert updater in text


def test_connect_read_only_missing_database_is_fail_closed_without_creation(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(RuntimeError, match="state_database_missing"):
        with connect_read_only(root):
            pass
    assert not (root / ".agents").exists()


def test_projection_status_does_not_migrate_stale_database(tmp_path: Path) -> None:
    root = tmp_path / "project"
    state = root / ".agents/state"
    state.mkdir(parents=True)
    db_path = state / "agentos.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (SCHEMA_VERSION - 1,))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(RuntimeError, match="state_schema_upgrade_required"):
        projection_status(root, "T-read-only")

    conn = sqlite3.connect(db_path)
    try:
        current = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        projection_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='context_db_projection_events'"
        ).fetchone()
    finally:
        conn.close()
    assert current == SCHEMA_VERSION - 1
    assert projection_table is None


def test_connect_read_only_current_database_is_query_only(tmp_path: Path) -> None:
    root = tmp_path / "project"
    from agentos.db import connect
    with connect(root):
        pass

    with connect_read_only(root) as conn:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE must_not_write(id INTEGER)")
