"""
File: .agents/tests/test_isolated_workspace_integration_v0273.py

Purpose:
    Verify v0.27.3 isolated-workspace routing, diff sealing, conflict detection, and human-gated controlled integration.

Responsibilities:
    - Exercise schema 61 workspace/integration state on a real temporary Git repository.
    - Prove worker writes remain outside the primary worktree until approved integration.
    - Verify plan containment, immutable diff gates, conflict analysis, and no automatic Git merge.
    - Verify CLI/MCP surfaces preserve mutation authority boundaries.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from agentos import completion_verification as cv
from agentos import mcp_v0273
from agentos import multi_agent_supervisor as mas
from agentos import multi_agent_workspace as maw
from agentos import multi_agent_workspace_cli as workspace_cli


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, shell=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "agentos-test@example.invalid")
    _git(root, "config", "user.name", "AgentOS Test")
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("OTHER = 1\n", encoding="utf-8")
    _git(root, "add", "src/a.py", "src/b.py")
    _git(root, "commit", "-m", "baseline")

    db_path = tmp_path / "agentos-state.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        """
        CREATE TABLE tasks(id TEXT PRIMARY KEY, approved INTEGER NOT NULL DEFAULT 1, owner_session_id TEXT, task_state TEXT NOT NULL DEFAULT 'ready');
        CREATE TABLE task_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, revision INTEGER NOT NULL,
            status TEXT NOT NULL, plan_json TEXT NOT NULL, plan_hash TEXT NOT NULL,
            submitted_by TEXT NOT NULL DEFAULT 'human', UNIQUE(task_id,revision));
        CREATE TABLE multi_agent_supervisor_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_task_id TEXT NOT NULL REFERENCES tasks(id),
            parent_plan_id INTEGER NOT NULL REFERENCES task_plans(id),
            parent_plan_hash TEXT NOT NULL,
            architecture_baseline_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            worker_limit INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            activated_by TEXT,
            supervisor_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            activated_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE multi_agent_workers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supervisor_id INTEGER NOT NULL REFERENCES multi_agent_supervisor_runs(id) ON DELETE CASCADE,
            worker_key TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            plan_id INTEGER NOT NULL REFERENCES task_plans(id),
            plan_hash TEXT NOT NULL,
            architecture_baseline_hash TEXT NOT NULL,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            skill_id INTEGER,
            selection_run_id INTEGER,
            capability_set_hash TEXT NOT NULL,
            assignment_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            last_heartbeat_at TEXT,
            completed_at TEXT,
            UNIQUE(supervisor_id,worker_key),
            UNIQUE(supervisor_id,session_id)
        );
        CREATE TABLE multi_agent_supervisor_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supervisor_id INTEGER NOT NULL
                REFERENCES multi_agent_supervisor_runs(id)
                ON DELETE CASCADE,
            worker_id INTEGER
                REFERENCES multi_agent_workers(id)
                ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            external_event_hash TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX idx_multi_agent_events_supervisor
            ON multi_agent_supervisor_events(
                supervisor_id,
                id
            );

        CREATE TABLE process_exec_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, session_id TEXT NOT NULL,
            command_json TEXT, cwd TEXT, command_profile TEXT NOT NULL, decision TEXT NOT NULL,
            success INTEGER NOT NULL, exit_code INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE session_tokens(
            token_hash TEXT PRIMARY KEY, token_id TEXT NOT NULL UNIQUE,
            session_id TEXT NOT NULL, task_id TEXT NOT NULL,
            capability_set_json TEXT NOT NULL DEFAULT '[]',
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL, revoked_at TEXT
        );
        CREATE TABLE task_role_assignments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            session_id TEXT NOT NULL, token_id TEXT, role TEXT NOT NULL,
            permissions_json TEXT NOT NULL DEFAULT '[]',
            assigned_by TEXT NOT NULL DEFAULT 'test', status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    maw.migration_61(con)
    cv.migration_62(con)

    parent_plan = {"expected_files": ["src/a.py", "src/b.py"], "affected_architecture_sections": ["ARCH-03", "ARCH-17", "ARCH-21"]}
    worker_plan = {"expected_files": ["src/a.py"], "affected_architecture_sections": ["ARCH-03", "ARCH-17", "ARCH-21"]}
    parent_hash = hashlib.sha256(json.dumps(parent_plan, sort_keys=True).encode()).hexdigest()
    worker_hash = hashlib.sha256(json.dumps(worker_plan, sort_keys=True).encode()).hexdigest()
    con.execute("INSERT INTO tasks(id,approved,owner_session_id) VALUES('parent',1,'parent-session')")
    con.execute("INSERT INTO tasks(id,approved,owner_session_id) VALUES('worker-a',1,'worker-session')")
    con.execute("INSERT INTO tasks(id,approved,owner_session_id) VALUES('reviewer-task',1,'reviewer-session')")
    cur = con.execute("INSERT INTO task_plans(task_id,revision,status,plan_json,plan_hash) VALUES('parent',1,'active',?,?)", (json.dumps(parent_plan), parent_hash))
    parent_plan_id = int(cur.lastrowid)
    cur = con.execute("INSERT INTO task_plans(task_id,revision,status,plan_json,plan_hash) VALUES('worker-a',1,'active',?,?)", (json.dumps(worker_plan), worker_hash))
    worker_plan_id = int(cur.lastrowid)
    cur = con.execute(
        "INSERT INTO multi_agent_supervisor_runs(parent_task_id,parent_plan_id,parent_plan_hash,architecture_baseline_hash,status,worker_limit,created_by,supervisor_hash,created_at) VALUES('parent',?,?,?,'active',8,'human:architect','sup-hash',CURRENT_TIMESTAMP)",
        (parent_plan_id, parent_hash, "arch-1"),
    )
    supervisor_id = int(cur.lastrowid)
    cur = con.execute(
        "INSERT INTO multi_agent_workers(supervisor_id,worker_key,task_id,plan_id,plan_hash,architecture_baseline_hash,session_id,role,capability_set_hash,assignment_hash,status) VALUES(?,'a','worker-a',?,?,'arch-1','worker-session','executor','cap-hash','assignment-hash','running')",
        (supervisor_id, worker_plan_id, worker_hash),
    )
    worker_id = int(cur.lastrowid)
    con.execute("INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES('worker-token-hash','worker-token','worker-session','worker-a','[]','2999-01-01 00:00:00')")
    con.execute("INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES('reviewer-token-hash','reviewer-token','reviewer-session','reviewer-task','[]','2999-01-01 00:00:00')")
    con.execute("INSERT INTO task_role_assignments(task_id,session_id,token_id,role,permissions_json,assigned_by,status) VALUES('worker-a','worker-session','worker-token','executor','[]','test','active')")
    con.execute("INSERT INTO task_role_assignments(task_id,session_id,token_id,role,permissions_json,assigned_by,status) VALUES('reviewer-task','reviewer-session','reviewer-token','reviewer','[]','test','active')")
    con.commit(); con.close()

    @contextlib.contextmanager
    def rw(_root, immediate=False):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        if immediate:
            c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    @contextlib.contextmanager
    def ro(_root):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
        finally:
            c.close()

    policy = {
        "isolated_workspace_integration_policy": {
            **maw._DEFAULT_POLICY,
            "enabled": True,
            "require_clean_primary_on_provision": True,
        }
    }
    lease_counter = {"value": 0}

    def acquire(*_args, **_kwargs):
        lease_counter["value"] += 1
        return {"acquired": True, "lease_id": lease_counter["value"]}

    signed = lambda *a, **k: {"event_hash": hashlib.sha256(repr((a, k)).encode()).hexdigest()}
    monkeypatch.setattr(maw, "connect", rw)
    monkeypatch.setattr(maw, "connect_read_only", ro)
    monkeypatch.setattr(maw, "load_policy", lambda _root: policy)
    monkeypatch.setattr(maw, "append_signed_event", signed)
    monkeypatch.setattr(mas, "connect", rw)
    monkeypatch.setattr(mas, "connect_read_only", ro)
    monkeypatch.setattr(mas, "load_policy", lambda _root: policy)
    monkeypatch.setattr(mas, "append_signed_event", signed)
    monkeypatch.setattr(cv, "connect", rw)
    monkeypatch.setattr(cv, "connect_read_only", ro)
    monkeypatch.setattr(cv, "append_signed_event", signed)
    monkeypatch.setattr(maw, "acquire_resource", acquire)
    monkeypatch.setattr(maw, "release_resource", lambda *a, **k: {"released": True})
    monkeypatch.setattr(maw, "_candidate_gates", lambda *a, **k: {"architecture_status": "pass", "security_status": "pass", "architecture_findings": [], "security_findings": []})
    monkeypatch.setattr(maw, "_test_receipt", lambda *a, **k: {"status": "pass", "receipt_id": 1, "exit_code": 0})

    import agentos.core as core
    monkeypatch.setattr(core, "check_write", lambda *_a, **_k: {"allowed": True, "reason": "approved_parent_scope"})

    return {
        "root": root,
        "rw": rw,
        "ro": ro,
        "supervisor_id": supervisor_id,
        "worker_id": worker_id,
        "task_id": "worker-a",
        "session_id": "worker-session",
        "parent_task_id": "parent",
        "parent_session_id": "parent-session",
    }


def _provision(runtime):
    return maw.provision_workspace(runtime["root"], runtime["supervisor_id"], "a", "human:operator")


def _collect_and_seal(runtime):
    maw.collect_workspace_diff(runtime["root"], runtime["supervisor_id"], "a", runtime["task_id"], runtime["session_id"])
    return maw.seal_workspace(runtime["root"], runtime["supervisor_id"], "a", runtime["task_id"], runtime["session_id"])


def _verify_worker_completion(runtime):
    request = mas.worker_completion_request(
        runtime["root"], runtime["supervisor_id"], "a",
        runtime["task_id"], runtime["session_id"],
    )
    result = mas.worker_completion_verify(
        runtime["root"], request["request_id"],
        "reviewer-task", "reviewer-session",
        verdict="pass",
        checks={"evidence": True, "tests": True},
        evidence={"review": "independent verification", "test_receipt": 1},
    )
    assert result["worker_status"] == "completed"
    return result


def test_schema_cli_and_mcp_surfaces_are_additive_and_mcp_is_read_only(runtime):
    with runtime["ro"](runtime["root"]) as c:
        names = {row["name"] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "multi_agent_workspaces",
        "multi_agent_workspace_files",
        "multi_agent_workspace_file_versions",
        "multi_agent_integration_proposals",
        "multi_agent_integration_events",
        "completion_verification_requests",
        "completion_verification_attempts",
    } <= names
    with runtime["ro"](runtime["root"]) as c:
        proposal_columns = {
            row["name"] for row in c.execute(
                "PRAGMA table_info(multi_agent_integration_proposals)"
            )
        }
    assert {
        "completion_verification_request_id",
        "completion_verification_result_hash",
    } <= proposal_columns

    parser = workspace_cli.build_parser()
    commands = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            commands = action.choices
            break
    assert len(commands) == 11
    assert set(mcp_v0273.TOOL_NAMES) == {
        "agentos.multi_agent_workspace_status_get",
        "agentos.multi_agent_workspace_diff_summary_get",
        "agentos.multi_agent_integration_proposal_get",
        "agentos.multi_agent_integration_readiness_get",
    }
    assert all(not any(token in name for token in ("create", "review", "approve", "reject", "apply", "release", "seal", "collect")) for name in mcp_v0273.TOOL_NAMES)


def test_workspace_is_outside_primary_and_bound_to_exact_owner(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"]).resolve()
    assert workspace.is_dir()
    with pytest.raises(ValueError):
        workspace.relative_to(runtime["root"].resolve())
    binding = maw.workspace_binding(runtime["root"], runtime["task_id"], runtime["session_id"])
    assert binding and binding["path"] == workspace
    assert maw.workspace_execution_root(runtime["root"], runtime["task_id"], runtime["session_id"]) == workspace
    assert maw.executor_workspace_required(runtime["root"], runtime["task_id"], runtime["session_id"]) is True


def test_workspace_write_never_changes_primary_before_integration(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    primary = runtime["root"] / "src" / "a.py"
    target = workspace / "src" / "a.py"
    before = primary.read_bytes()
    expected = _sha_bytes(target.read_bytes())
    result = maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 2\n", expected)
    assert result["allowed"] is True
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert primary.read_bytes() == before
    collected = maw.collect_workspace_diff(runtime["root"], runtime["supervisor_id"], "a", runtime["task_id"], runtime["session_id"])
    assert collected["changed_files"] == ["src/a.py"]


def test_diff_collection_rejects_files_outside_worker_plan(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    (workspace / "src" / "outside.py").write_text("OUTSIDE = True\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="workspace_changes_outside_worker_plan"):
        maw.collect_workspace_diff(runtime["root"], runtime["supervisor_id"], "a", runtime["task_id"], runtime["session_id"])


def test_seal_requires_current_diff_and_all_candidate_gates(runtime, monkeypatch):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 3\n", expected)
    maw.collect_workspace_diff(runtime["root"], runtime["supervisor_id"], "a", runtime["task_id"], runtime["session_id"])
    monkeypatch.setattr(maw, "_test_receipt", lambda *a, **k: {"status": "missing", "receipt_id": None})
    with pytest.raises(PermissionError, match="workspace_test_gate_not_satisfied"):
        maw.seal_workspace(runtime["root"], runtime["supervisor_id"], "a", runtime["task_id"], runtime["session_id"])
    monkeypatch.setattr(maw, "_test_receipt", lambda *a, **k: {"status": "pass", "receipt_id": 7, "exit_code": 0})
    sealed = maw.seal_workspace(runtime["root"], runtime["supervisor_id"], "a", runtime["task_id"], runtime["session_id"])
    assert sealed["status"] == "sealed"
    with pytest.raises(PermissionError, match="sealed_workspace_is_read_only"):
        maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 4\n", _sha_bytes((workspace / "src" / "a.py").read_bytes()))


def test_primary_change_after_workspace_base_is_reported_as_conflict(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 5\n", expected)
    _collect_and_seal(runtime)
    (runtime["root"] / "src" / "a.py").write_text("VALUE = 99\n", encoding="utf-8")
    with runtime["ro"](runtime["root"]) as c:
        workspace_id = int(c.execute("SELECT id FROM multi_agent_workspaces").fetchone()["id"])
    conflicts = maw._conflicts(runtime["root"], workspace_id)
    assert conflicts and conflicts[0]["reason"] == "primary_changed_since_workspace_base"


def test_eol_normalization_does_not_create_false_primary_conflict(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 51\n", expected)
    _collect_and_seal(runtime)

    # Simulate a Windows-style CRLF worktree while Git clean filtering still
    # considers the primary path unchanged relative to the pinned base commit.
    _git(runtime["root"], "config", "core.autocrlf", "true")
    (runtime["root"] / "src" / "a.py").write_bytes(b"VALUE = 1\r\n")
    _git(runtime["root"], "diff", "--quiet", "HEAD", "--", "src/a.py")

    with runtime["ro"](runtime["root"]) as c:
        workspace_id = int(c.execute("SELECT id FROM multi_agent_workspaces").fetchone()["id"])
    assert maw._conflicts(runtime["root"], workspace_id) == []


def test_integration_proposal_rejects_completed_worker_without_independent_receipt(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(
        runtime["root"], runtime["task_id"], runtime["session_id"],
        "src/a.py", "VALUE = 61\n", expected,
    )
    _collect_and_seal(runtime)
    with runtime["rw"](runtime["root"]) as c:
        c.execute(
            "UPDATE multi_agent_workers SET status='completed' WHERE id=?",
            (runtime["worker_id"],),
        )
    with pytest.raises(
        PermissionError,
        match="independent_completion_verification_required_for_integration_proposal",
    ):
        maw.create_integration_proposal(
            runtime["root"], runtime["supervisor_id"], "a", "human:operator"
        )


def test_integration_readiness_rejects_stale_completion_receipt(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(
        runtime["root"], runtime["task_id"], runtime["session_id"],
        "src/a.py", "VALUE = 62\n", expected,
    )
    _collect_and_seal(runtime)
    verified = _verify_worker_completion(runtime)
    proposal = maw.create_integration_proposal(
        runtime["root"], runtime["supervisor_id"], "a", "human:operator"
    )
    assert proposal["completion_verification_request_id"] == verified["request_id"]
    assert proposal["completion_verification_result_hash"] == verified["result_hash"]
    with runtime["rw"](runtime["root"]) as c:
        c.execute(
            "UPDATE multi_agent_workers SET plan_hash='tampered-after-verification' WHERE id=?",
            (runtime["worker_id"],),
        )
    readiness = maw.integration_readiness(runtime["root"], proposal["proposal_id"])
    assert readiness["ready"] is False
    assert "independent_completion_verification_stale" in readiness["reasons"]


def test_integration_proposal_requires_human_review_then_human_approval(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 6\n", expected)
    _collect_and_seal(runtime)
    _verify_worker_completion(runtime)
    proposal = maw.create_integration_proposal(runtime["root"], runtime["supervisor_id"], "a", "human:operator")
    assert proposal["status"] == "draft"
    with pytest.raises(PermissionError, match="human_identity_required"):
        maw.review_integration(runtime["root"], proposal["proposal_id"], "assistant")
    assert maw.review_integration(runtime["root"], proposal["proposal_id"], "human:reviewer")["status"] == "reviewed"
    assert maw.approve_integration(runtime["root"], proposal["proposal_id"], "human:approver")["status"] == "approved"


def test_controlled_apply_uses_parent_authority_and_never_git_merge(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 7\n", expected)
    _collect_and_seal(runtime)
    _verify_worker_completion(runtime)
    proposal = maw.create_integration_proposal(runtime["root"], runtime["supervisor_id"], "a", "human:operator")
    maw.review_integration(runtime["root"], proposal["proposal_id"], "human:reviewer")
    maw.approve_integration(runtime["root"], proposal["proposal_id"], "human:approver")
    head_before = _git(runtime["root"], "rev-parse", "HEAD")
    result = maw.apply_integration(runtime["root"], proposal["proposal_id"], "human:integrator", runtime["parent_task_id"], runtime["parent_session_id"])
    assert result["status"] == "applied"
    assert result["automatic_merge"] is False
    assert result["git_merge_invoked"] is False
    assert (runtime["root"] / "src" / "a.py").read_text(encoding="utf-8") == "VALUE = 7\n"
    backup_root = runtime["root"] / ".agents" / "runtime" / "integration-v0273" / f"proposal-{proposal['proposal_id']}"
    assert (backup_root / "manifest.json").is_file()
    assert (backup_root / "files" / "src" / "a.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert _git(runtime["root"], "rev-parse", "HEAD") == head_before


def test_wrong_parent_session_cannot_apply(runtime):
    provisioned = _provision(runtime)
    workspace = Path(provisioned["workspace_path"])
    expected = _sha_bytes((workspace / "src" / "a.py").read_bytes())
    maw.workspace_atomic_write(runtime["root"], runtime["task_id"], runtime["session_id"], "src/a.py", "VALUE = 8\n", expected)
    _collect_and_seal(runtime)
    _verify_worker_completion(runtime)
    proposal = maw.create_integration_proposal(runtime["root"], runtime["supervisor_id"], "a", "human:operator")
    maw.review_integration(runtime["root"], proposal["proposal_id"], "human:reviewer")
    maw.approve_integration(runtime["root"], proposal["proposal_id"], "human:approver")
    with pytest.raises(PermissionError, match="integration_parent_session_owner_mismatch"):
        maw.apply_integration(runtime["root"], proposal["proposal_id"], "human:integrator", runtime["parent_task_id"], "wrong-session")


def test_workspace_status_never_exposes_physical_path(runtime):
    _provision(runtime)
    status = maw.workspace_status(runtime["root"], runtime["supervisor_id"], "a")
    assert status["physical_path_exposed"] is False
    assert "workspace_path" not in status
    assert len(status["workspace_path_hash"]) == 64


def test_source_contract_contains_no_automatic_merge_invocation():
    source = Path(maw.__file__).read_text(encoding="utf-8")
    proxy_source = Path(maw.__file__).with_name("proxy.py").read_text(encoding="utf-8")
    assert '"automatic_merge": False' in source
    assert '"automatic_branch_merge": False' in source
    assert '_git(root, "merge"' not in source
    assert 'subprocess.run(["git", "merge"' not in source
    assert "workspace_execution_root" in proxy_source
    assert "workspace_atomic_write" in proxy_source
