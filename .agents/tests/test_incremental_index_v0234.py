"""Regression tests for v0.23.4 Incremental Symbol Index."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from agentos.db import connect
from agentos.indexing import index_build, index_query, index_status


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    src = root / "src"
    src.mkdir(parents=True)
    (src / "a.py").write_bytes(b"def alpha():\n    return 1\n")
    (src / "b.py").write_bytes(b"class Beta:\n    pass\n")
    return root


def test_schema_47_adds_incremental_index_state(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with connect(root) as conn:
        version = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == 47
    assert {"symbol_index_state", "symbol_index_files"} <= tables


def test_bootstrap_then_no_change_parses_zero_files(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = index_build(root)
    second = index_build(root)
    assert first["mode"] == "bootstrap_full_rebuild"
    assert first["files_parsed"] == 2
    assert second["mode"] == "incremental"
    assert second["files_parsed"] == 0
    assert second["files_unchanged"] == 2
    assert second["symbols"] == first["symbols"]


def test_single_change_replaces_only_changed_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index_build(root)
    (root / "src/a.py").write_bytes(b"def gamma():\n    return 2\n")
    result = index_build(root)
    assert result["files_parsed"] == 1
    assert result["files_changed"] == 1
    assert not index_query(root, "alpha")
    assert index_query(root, "gamma")
    assert index_query(root, "Beta")


def test_deleted_file_removes_stale_symbols_without_reparse(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index_build(root)
    (root / "src/b.py").unlink()
    result = index_build(root)
    assert result["files_deleted"] == 1
    assert result["files_parsed"] == 0
    assert not index_query(root, "Beta")
    assert index_query(root, "alpha")


def test_parse_failure_is_atomic(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index_build(root)
    before = index_status(root)
    (root / "src/a.py").write_bytes(b"def broken(:\n")
    with pytest.raises(RuntimeError, match="cannot index src/a.py"):
        index_build(root)
    after = index_status(root)
    assert after["generation"] == before["generation"]
    assert index_query(root, "alpha")


def test_source_change_and_force_full_rebuild(tmp_path: Path) -> None:
    root = _project(tmp_path)
    other = root / "other"
    other.mkdir()
    (other / "c.py").write_bytes(b"def charlie():\n    return 3\n")
    index_build(root)
    switched = index_build(root, "other")
    assert switched["mode"] == "full_rebuild"
    assert not index_query(root, "alpha")
    assert index_query(root, "charlie")
    forced = index_build(root, "other", force_full=True)
    assert forced["mode"] == "full_rebuild"
    assert forced["files_parsed"] == 1
