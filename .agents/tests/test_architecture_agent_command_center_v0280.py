"""
Path: .agents/tests/test_architecture_agent_command_center_v0280.py
Purpose: Verify the v0.28.0 Command Center remains a privacy-safe read-only projection.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from agentos import command_center as cc


SCHEMA_SQL = """
CREATE TABLE architecture_baselines(
 id INTEGER PRIMARY KEY, baseline_version INTEGER, status TEXT, baseline_hash TEXT,
 section_count INTEGER, activated_at TEXT, created_at TEXT
);
CREATE TABLE architecture_baseline_sections(baseline_id INTEGER, section_id TEXT);
CREATE TABLE architecture_change_proposals(
 id INTEGER PRIMARY KEY,status TEXT,title TEXT,created_at TEXT
);
CREATE TABLE architecture_adrs(
 id INTEGER PRIMARY KEY,proposal_id INTEGER,status TEXT,created_at TEXT
);
CREATE TABLE tasks(
 id TEXT PRIMARY KEY,approved INTEGER,task_state TEXT
);
CREATE TABLE resource_leases(
 id INTEGER PRIMARY KEY,status TEXT
);
CREATE TABLE multi_agent_supervisor_runs(
 id INTEGER PRIMARY KEY,parent_task_id TEXT,status TEXT,created_at TEXT
);
CREATE TABLE multi_agent_workers(
 id INTEGER PRIMARY KEY,status TEXT
);
CREATE TABLE multi_agent_workspaces(
 id INTEGER PRIMARY KEY,status TEXT,workspace_path TEXT
);
CREATE TABLE multi_agent_integration_proposals(
 id INTEGER PRIMARY KEY,parent_task_id TEXT,status TEXT,conflict_status TEXT,
 architecture_status TEXT,security_status TEXT,test_status TEXT,created_at TEXT
);
CREATE TABLE human_decision_requests(
 id INTEGER PRIMARY KEY,decision_uuid TEXT,task_id TEXT,phase TEXT,decision_type TEXT,
 severity TEXT,blocking INTEGER,status TEXT,created_at TEXT,question TEXT
);
CREATE TABLE architecture_compliance_runs(
 id INTEGER PRIMARY KEY,status TEXT,warning_count INTEGER DEFAULT 0,blocking_count INTEGER DEFAULT 0,
 finding_count INTEGER DEFAULT 0,created_at TEXT
);
CREATE TABLE architecture_structural_runs(
 id INTEGER PRIMARY KEY,status TEXT,warning_count INTEGER DEFAULT 0,blocking_count INTEGER DEFAULT 0,
 finding_count INTEGER DEFAULT 0,created_at TEXT
);
CREATE TABLE architecture_runtime_runs(
 id INTEGER PRIMARY KEY,status TEXT,warning_count INTEGER DEFAULT 0,blocking_count INTEGER DEFAULT 0,
 finding_count INTEGER DEFAULT 0,created_at TEXT
);
CREATE TABLE architecture_quality_runs(
 id INTEGER PRIMARY KEY,status TEXT,warning_count INTEGER DEFAULT 0,blocking_count INTEGER DEFAULT 0,
 finding_count INTEGER DEFAULT 0,created_at TEXT
);
"""


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "repo"
    root.mkdir()
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA_SQL)

    @contextmanager
    def ro(_root: Path):
        yield db

    monkeypatch.setattr(cc, "connect_read_only", ro)
    monkeypatch.setattr(
        cc,
        "load_policy",
        lambda _root: {
            "command_center_policy": {
                "enabled": True,
                "database_read_only": True,
                "mutation_authority": False,
                "mcp_mutation_allowed": False,
                "raw_source_content_exposed": False,
                "physical_workspace_paths_exposed": False,
                "web_control_plane_reserved_for_v0281": True,
            }
        },
    )
    return root, db


def test_empty_snapshot_is_read_only_and_privacy_safe(runtime):
    root, _ = runtime
    report = cc.command_center_snapshot(root)
    assert report["ok"] is True
    assert report["schema"] == cc.CURRENT_SCHEMA_VERSION
    assert report["authority"]["projection_only"] is True
    assert report["authority"]["mutation_authority"] is False
    assert report["authority"]["mcp_mutation_allowed"] is False
    assert report["authority"]["raw_source_content_exposed"] is False
    assert report["authority"]["physical_workspace_paths_exposed"] is False


def test_architecture_and_execution_counts_are_aggregated(runtime):
    root, db = runtime
    db.execute("INSERT INTO architecture_baselines VALUES(1,12,'active','hash',27,'now','now')")
    for index in range(27):
        db.execute("INSERT INTO architecture_baseline_sections VALUES(1,?)", (f"ARCH-{index+1:02d}",))
    db.execute("INSERT INTO tasks VALUES('T1',1,'running')")
    db.execute("INSERT INTO tasks VALUES('T2',1,'blocked')")
    db.execute("INSERT INTO resource_leases VALUES(1,'active')")
    db.execute("INSERT INTO multi_agent_supervisor_runs VALUES(1,'T1','active','now')")
    db.execute("INSERT INTO multi_agent_workers VALUES(1,'running')")
    db.execute("INSERT INTO multi_agent_workers VALUES(2,'blocked')")
    db.execute("INSERT INTO multi_agent_workspaces VALUES(1,'sealed','C:/secret/worktree')")
    db.commit()

    report = cc.command_center_snapshot(root)
    assert report["architecture"]["active_sections"] == 27
    assert report["execution"]["tasks_total"] == 2
    assert report["execution"]["workers_running"] == 1
    assert report["execution"]["workers_blocked"] == 1
    assert report["execution"]["active_leases"] == 1
    assert report["overall_status"] == "block"


def test_compliance_layer_precedence_is_block_warn_pass(runtime):
    root, db = runtime
    db.execute("INSERT INTO architecture_compliance_runs VALUES(1,'pass',0,0,0,'now')")
    db.execute("INSERT INTO architecture_structural_runs VALUES(1,'warn',1,0,1,'now')")
    db.execute("INSERT INTO architecture_runtime_runs VALUES(1,'block',0,1,1,'now')")
    db.execute("INSERT INTO architecture_quality_runs VALUES(1,'pass',0,0,0,'now')")
    db.commit()
    report = cc.command_center_snapshot(root)
    assert report["compliance"]["overall"] == "block"
    assert report["overall_status"] == "block"


def test_pending_human_actions_do_not_expose_question_text(runtime):
    root, db = runtime
    secret = "patient full name and confidential question"
    db.execute(
        "INSERT INTO human_decision_requests VALUES(1,'D-1','T1','planning','scope','high',1,'open','now',?)",
        (secret,),
    )
    db.commit()
    report = cc.command_center_human_actions(root)
    encoded = repr(report)
    assert report["count"] == 1
    assert report["blocking_count"] == 1
    assert secret not in encoded
    assert "question" not in report["items"][0]


def test_integration_conflict_is_blocking_attention(runtime):
    root, db = runtime
    db.execute(
        "INSERT INTO multi_agent_integration_proposals VALUES(1,'PARENT','draft','conflict','pass','pass','pass','now')"
    )
    db.commit()
    report = cc.command_center_snapshot(root)
    assert report["execution"]["integration_conflicts"] == 1
    assert report["human_actions"]["items"][0]["blocking"] is True
    assert report["overall_status"] == "block"


def test_physical_workspace_path_never_appears_in_snapshot(runtime):
    root, db = runtime
    secret_path = r"C:\Users\operator\secret-worktree"
    db.execute("INSERT INTO multi_agent_workspaces VALUES(1,'sealed',?)", (secret_path,))
    db.commit()
    assert secret_path not in repr(cc.command_center_snapshot(root))


def test_command_center_section_rejects_unknown_section(runtime):
    root, _ = runtime
    with pytest.raises(ValueError, match="invalid_command_center_section"):
        cc.command_center_section(root, "secrets")


def test_rendered_tui_contains_core_sections(runtime):
    root, _ = runtime
    text = cc.render_command_center(cc.command_center_snapshot(root))
    assert "Architecture" in text
    assert "Execution" in text
    assert "Compliance" in text
    assert "Human Actions" in text
    assert "READ-ONLY PROJECTION" in text


def test_policy_rejects_any_mutation_authority(runtime, monkeypatch: pytest.MonkeyPatch):
    root, _ = runtime
    monkeypatch.setattr(
        cc,
        "load_policy",
        lambda _root: {"command_center_policy": {"mutation_authority": True}},
    )
    with pytest.raises(RuntimeError, match="mutation_authority_must_be_false"):
        cc.command_center_snapshot(root)


def test_web_control_plane_remains_reserved_for_v0281(runtime):
    root, _ = runtime
    report = cc.command_center_snapshot(root)
    assert report["authority"]["web_control_plane_reserved_for_v0281"] is True
