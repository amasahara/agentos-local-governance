"""
File: .agents/tests/test_release_hardening_v0242.py

Purpose:
    Verify current publication hardening, bootstrap documentation, local links,
    and strict read-only SQLite access for DB-aware MCP telemetry.

Responsibilities:
    - Check current release validation and bootstrap documentation contracts.
    - Check documentation identity and local links.
    - Verify read-only database operations remain fail closed.
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
    """Require the workflow to use current generic release validators."""

    text = (ROOT / ".github/workflows/agentos-release-validation.yml").read_text(
        encoding="utf-8"
    )
    assert "validate_v0232.py" not in text
    assert "python tools/validate_release.py ." in text
    assert "python tools/build_manifest.py ." in text
    assert "python tools/verify_manifest.py ." in text


def test_current_docs_identify_db_aware_context_projection_and_links_resolve() -> None:
    """Require current documentation identity and local links to stay coherent."""

    report = docs_check(ROOT)
    assert report["ok"] is True
    consistency = report["content_consistency"]
    assert consistency["release_identity_mismatches"] == []
    assert consistency["broken_local_links"] == []


def test_current_quickstart_routes_project_bootstrap_journeys() -> None:
    """Require current onboarding to route journeys without legacy updaters."""

    from agentos.policy import load_policy

    policy = load_policy(ROOT)
    rel = policy.get("documentation_policy", {}).get("current_upgrade_guide")
    assert rel, "current_upgrade_guide must be declared by AgentOS documentation policy"
    guide = ROOT / str(rel)
    assert guide.is_file()
    text = guide.read_text(encoding="utf-8")
    for current_doc in (
        "NEW_PROJECT.md",
        "EXISTING_PROJECT.md",
        "WINDOWS.md",
        "REFERENCE.md",
    ):
        assert current_doc in text
    assert "apply_v" not in text
    assert "updater script" not in text.lower()


def test_connect_read_only_missing_database_is_fail_closed_without_creation(
    tmp_path: Path,
) -> None:
    """Require read-only connection to fail without creating missing state."""

    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(RuntimeError, match="state_database_missing"):
        with connect_read_only(root):
            pass
    assert not (root / ".agents").exists()


def test_projection_status_does_not_migrate_stale_database(tmp_path: Path) -> None:
    """Require read-only projection status not to migrate a stale database."""

    root = tmp_path / "project"
    state = root / ".agents/state"
    state.mkdir(parents=True)
    db_path = state / "agentos.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)")
        conn.execute(
            "INSERT INTO schema_migrations(version) VALUES(?)",
            (SCHEMA_VERSION - 1,),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(RuntimeError, match="state_schema_upgrade_required"):
        projection_status(root, "T-read-only")

    conn = sqlite3.connect(db_path)
    try:
        current = conn.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        projection_table = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='context_db_projection_events'"
        ).fetchone()
    finally:
        conn.close()
    assert current == SCHEMA_VERSION - 1
    assert projection_table is None


def test_connect_read_only_current_database_is_query_only(tmp_path: Path) -> None:
    """Require current read-only connections to reject all writes."""

    root = tmp_path / "project"
    from agentos.db import connect

    with connect(root):
        pass

    with connect_read_only(root) as conn:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        assert (
            conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            == SCHEMA_VERSION
        )
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE must_not_write(id INTEGER)")
