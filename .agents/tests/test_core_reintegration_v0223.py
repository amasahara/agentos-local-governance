"""AgentOS v0.22.3 core reintegration and release-integrity regression tests."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT/".agents") not in sys.path: sys.path.insert(0,str(ROOT/".agents"))
from agentos.db import SCHEMA_VERSION, connect
from agentos.release_integrity import check_release_integrity
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.policy import load_policy


def test_schema_source_of_truth_is_current():
    assert CURRENT_SCHEMA_VERSION == SCHEMA_VERSION and CURRENT_SCHEMA_VERSION >= 41


def test_fresh_database_runs_contiguous_migrations_1_to_current(tmp_path: Path):
    root=tmp_path/"project"; (root/".agents/state").mkdir(parents=True); (root/".agents/config").mkdir(parents=True)
    with connect(root) as c:
        versions=[r["version"] for r in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables={r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert versions == list(range(1, CURRENT_SCHEMA_VERSION + 1))
    assert {"tasks","guarded_executions","audit_events","project_identity","db_connections","db_reconciliation_runs"} <= tables


def test_release_contains_core_and_extension():
    report=check_release_integrity(ROOT)
    assert report["ok"], report


def test_governance_keeps_core_and_extension_sections():
    p=load_policy(ROOT)
    for key in ("tool_policy","proxy_policy","external_audit_policy","project_identity_policy","database_boundary_policy","reconciliation_recovery_policy"):
        assert key in p


def test_core_compat_launchers_are_not_dead_stubs():
    assert "exit 0" not in (ROOT/".agents/bin/agentos.v0195").read_text()
    assert (ROOT/".agents/bin/agentos-mcp.v0195").read_text().strip() != "#!/bin/sh\ncat"


def test_unknown_core_cli_command_fails_nonzero():
    cp=subprocess.run([str(ROOT/".agents/bin/agentos"),"definitely-not-an-agentos-command"],cwd=ROOT,capture_output=True,text=True)
    assert cp.returncode != 0


def test_historical_test_is_release_critical():
    text=(ROOT/".agents/tests/test_agentos.py").read_text()
    assert "test_proxy_read_creates_signed_external_evidence" in text
    assert 'load_policy(ROOT)["version"] == (ROOT / "VERSION").read_text().strip()' in text


def test_runtime_cache_files_are_not_release_authority(tmp_path: Path):
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from verify_manifest import _candidate_files
    root = tmp_path / "release"
    (root / ".agents/agentos/__pycache__").mkdir(parents=True)
    (root / ".agents/cache").mkdir(parents=True)
    (root / ".pytest_cache").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / ".agents/agentos/__pycache__/x.pyc").write_bytes(b"cache")
    (root / ".agents/cache/derived.json").write_text("cache")
    (root / ".pytest_cache/CACHEDIR.TAG").write_text("cache")
    (root / "src/real.py").write_text("print('ok')\n")
    assert _candidate_files(root) == {"src/real.py"}


def test_v0223_docs_check_replaces_stale_version_chain():
    cp=subprocess.run([str(ROOT/".agents/bin/agentos"),"docs-check"],cwd=ROOT,capture_output=True,text=True)
    assert cp.returncode == 0, cp.stderr + cp.stdout
    report=json.loads(cp.stdout)
    assert report["ok"] is True
    assert report["version"] == (ROOT / "VERSION").read_text().strip()

