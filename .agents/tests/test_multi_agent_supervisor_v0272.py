"""Path: .agents/tests/test_multi_agent_supervisor_v0272.py
Purpose: Verify v0.27.2 supervisor authority, DAG, freshness, overlap, and read-only MCP invariants.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from agentos import multi_agent_supervisor as mas
from agentos import completion_verification as cv
from agentos import mcp_v0272
from agentos import multi_agent_supervisor_cli as supervisor_cli


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "agentos.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        """
        CREATE TABLE tasks(id TEXT PRIMARY KEY, approved INTEGER NOT NULL, owner_session_id TEXT, task_state TEXT NOT NULL DEFAULT 'ready');
        CREATE TABLE task_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, revision INTEGER NOT NULL,
            status TEXT NOT NULL, plan_json TEXT NOT NULL, plan_hash TEXT NOT NULL,
            submitted_by TEXT NOT NULL DEFAULT 'human', UNIQUE(task_id,revision));
        CREATE TABLE task_plan_architecture_contexts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL UNIQUE, task_id TEXT NOT NULL,
            baseline_hash TEXT, state TEXT NOT NULL, expected_files_json TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE session_tokens(
            token_hash TEXT PRIMARY KEY, token_id TEXT NOT NULL UNIQUE, session_id TEXT NOT NULL, task_id TEXT NOT NULL,
            capability_set_json TEXT NOT NULL, issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL, revoked_at TEXT);
        CREATE TABLE task_role_assignments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, session_id TEXT NOT NULL,
            role TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE promoted_skills(
            id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL, contract_version INTEGER NOT NULL,
            contract_hash TEXT, contract_status TEXT NOT NULL);
        CREATE TABLE skill_contracts(
            skill_id INTEGER PRIMARY KEY, validation_status TEXT NOT NULL, architecture_baseline_hash TEXT,
            contract_hash TEXT NOT NULL);
        CREATE TABLE skill_selection_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, plan_id INTEGER NOT NULL,
            plan_hash TEXT NOT NULL, architecture_baseline_hash TEXT, status TEXT NOT NULL,
            recommended_skill_id INTEGER);
        CREATE TABLE skill_selection_candidates(
            selection_run_id INTEGER NOT NULL, skill_id INTEGER NOT NULL, eligible INTEGER NOT NULL,
            recommendable INTEGER NOT NULL, contract_hash TEXT NOT NULL,
            PRIMARY KEY(selection_run_id,skill_id));
        """
    )
    mas.migration_60(con)
    cv.migration_62(con)
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
            c.rollback(); raise
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

    def policy(_root):
        return {
            "concurrency_policy": {"task_single_writer": True},
            "multi_agent_supervisor_policy": {
                "enabled": True,
                "max_workers": 8,
                "require_parent_active_plan": True,
                "require_current_worker_plans": True,
                "require_parent_plan_file_envelope": True,
                "overlapping_executor_write_targets": "block",
                "auto_process_launch": False,
                "mcp_mutation_allowed": False,
            },
        }

    def arch_status(_root, task_id):
        with ro(_root) as c:
            row = c.execute("SELECT * FROM task_plans WHERE task_id=? ORDER BY revision DESC LIMIT 1", (str(task_id),)).fetchone()
            if not row:
                return {"ready": False, "reason": "plan_missing", "plan_id": None, "plan_status": None}
            ctx = c.execute("SELECT * FROM task_plan_architecture_contexts WHERE plan_id=?", (row["id"],)).fetchone()
            ready = row["status"] == "active" and ctx is not None and ctx["state"] in {"bound", "not_evaluable"}
            return {
                "ready": ready,
                "reason": "architecture_plan_current" if ready else "architecture_plan_stale",
                "plan_id": int(row["id"]),
                "plan_status": row["status"],
                "architecture": dict(ctx) if ctx else None,
            }

    monkeypatch.setattr(mas, "connect", rw)
    monkeypatch.setattr(mas, "connect_read_only", ro)
    monkeypatch.setattr(cv, "connect", rw)
    monkeypatch.setattr(cv, "connect_read_only", ro)
    monkeypatch.setattr(mas, "load_policy", policy)
    monkeypatch.setattr(mas, "architecture_plan_status", arch_status)
    signed = lambda *a, **k: {"event_hash": hashlib.sha256(repr((a, k)).encode()).hexdigest()}
    monkeypatch.setattr(mas, "append_signed_event", signed)
    monkeypatch.setattr(cv, "append_signed_event", signed)

    def seed_task(task_id: str, files: list[str], session_id: str | None = None, role: str = "executor", sections: list[str] | None = None, owner: str | None = None):
        payload = {
            "files": files,
            "expected_files": files,
            "affected_architecture_sections": sections or ["ARCH-03", "ARCH-12"],
        }
        plan_hash = _sha(payload)
        with rw(tmp_path) as c:
            c.execute("INSERT INTO tasks(id,approved,owner_session_id,task_state) VALUES(?,1,?,'ready')", (task_id, owner))
            cur = c.execute("INSERT INTO task_plans(task_id,revision,status,plan_json,plan_hash) VALUES(?,1,'active',?,?)", (task_id, json.dumps(payload), plan_hash))
            plan_id = int(cur.lastrowid)
            c.execute("INSERT INTO task_plan_architecture_contexts(plan_id,task_id,baseline_hash,state,expected_files_json) VALUES(?,?,?,'bound',?)", (plan_id, task_id, "arch-1", json.dumps(files)))
            if session_id:
                c.execute(
                    "INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES(?,?,?,?,?,'2999-01-01 00:00:00')",
                    (_sha(session_id), "tok-" + session_id, session_id, task_id, json.dumps(["fs_read", "fs_write"])),
                )
                c.execute("INSERT INTO task_role_assignments(task_id,session_id,role,status) VALUES(?,?,?,'active')", (task_id, session_id, role))
        return plan_id, plan_hash

    return {"root": tmp_path, "rw": rw, "ro": ro, "seed_task": seed_task, "db": db_path}


def _base(runtime):
    seed = runtime["seed_task"]
    seed("parent", ["src/a.py", "src/b.py"], sections=["ARCH-03", "ARCH-12"])
    seed("worker-a", ["src/a.py"], "session-a", owner="session-a")
    seed("worker-b", ["src/b.py"], "session-b", owner="session-b")
    seed("reviewer", [], "review-session", role="reviewer", owner="review-session")
    sup = mas.create_supervisor(runtime["root"], "parent", "human:architect")
    return sup["supervisor_id"]


def test_migration_and_mcp_are_additive_and_read_only(runtime):
    with runtime["ro"](runtime["root"]) as c:
        names = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"multi_agent_supervisor_runs", "multi_agent_workers", "multi_agent_worker_dependencies", "multi_agent_supervisor_events"} <= names
    tool_names = {tool["name"] for tool in mcp_v0272.TOOLS}
    assert tool_names == {
        "agentos.multi_agent_supervisor_status_get",
        "agentos.multi_agent_supervisor_workers_get",
        "agentos.multi_agent_supervisor_readiness_get",
    }
    assert all(not any(word in name for word in ("create", "add", "activate", "start", "update", "cancel", "pause")) for name in tool_names)


def test_human_identity_required(runtime):
    runtime["seed_task"]("parent", ["src/a.py"])
    with pytest.raises(PermissionError, match="human_identity_required"):
        mas.create_supervisor(runtime["root"], "parent", "assistant")


def test_parent_envelope_and_task_owner_are_enforced(runtime):
    sid = _base(runtime)
    runtime["seed_task"]("outside", ["src/outside.py"], "session-o", owner="session-o")
    with pytest.raises(PermissionError, match="outside_parent_file_envelope"):
        mas.add_worker(runtime["root"], sid, "outside", "outside", "session-o", "executor")
    runtime["seed_task"]("owned", ["src/a.py"], "session-owned", owner="different-session")
    with pytest.raises(PermissionError, match="owned_by_other_session"):
        mas.add_worker(runtime["root"], sid, "owned", "owned", "session-owned", "executor")


def test_overlap_blocks_activation(runtime):
    seed = runtime["seed_task"]
    seed("parent", ["src/a.py"])
    seed("worker-a", ["src/a.py"], "session-a", owner="session-a")
    seed("worker-b", ["src/a.py"], "session-b", owner="session-b")
    sid = mas.create_supervisor(runtime["root"], "parent", "human:architect")["supervisor_id"]
    mas.add_worker(runtime["root"], sid, "a", "worker-a", "session-a", "executor")
    mas.add_worker(runtime["root"], sid, "b", "worker-b", "session-b", "executor")
    ready = mas.supervisor_readiness(runtime["root"], sid)
    assert not ready["ready"]
    assert ready["overlap_findings"][0]["files"] == ["src/a.py"]
    with pytest.raises(PermissionError, match="overlapping_executor_write_targets"):
        mas.activate_supervisor(runtime["root"], sid, "human:architect")


def test_dependency_cycle_is_blocked(runtime):
    sid = _base(runtime)
    mas.add_worker(runtime["root"], sid, "a", "worker-a", "session-a", "executor")
    mas.add_worker(runtime["root"], sid, "b", "worker-b", "session-b", "executor")
    mas.add_dependency(runtime["root"], sid, "b", "a")
    with pytest.raises(PermissionError, match="worker_dependency_cycle"):
        mas.add_dependency(runtime["root"], sid, "a", "b")


def test_dag_runnable_sequence_and_no_process_launch(runtime):
    sid = _base(runtime)
    mas.add_worker(runtime["root"], sid, "a", "worker-a", "session-a", "executor")
    mas.add_worker(runtime["root"], sid, "b", "worker-b", "session-b", "executor")
    mas.add_dependency(runtime["root"], sid, "b", "a")
    active = mas.activate_supervisor(runtime["root"], sid, "human:architect")
    assert active["effective_status"] == "active"
    assert active["runnable_workers"] == ["a"]
    started = mas.worker_start(runtime["root"], sid, "a", "worker-a", "session-a")
    assert started == {"supervisor_id": sid, "worker_key": "a", "status": "running", "process_launched": False}
    with pytest.raises(PermissionError, match="worker_not_runnable"):
        mas.worker_start(runtime["root"], sid, "b", "worker-b", "session-b")
    with pytest.raises(PermissionError, match="independent_completion_verification_required"):
        mas.worker_update(runtime["root"], sid, "a", "worker-a", "session-a", "completed")
    request_a = mas.worker_completion_request(runtime["root"], sid, "a", "worker-a", "session-a")
    verified_a = mas.worker_completion_verify(
        runtime["root"], request_a["request_id"], "reviewer", "review-session",
        verdict="pass", checks={"evidence": True, "tests": True},
        evidence={"review": "worker-a independently verified"},
    )
    assert verified_a["worker_status"] == "completed"
    assert verified_a["supervisor_completed"] is False
    assert mas.supervisor_readiness(runtime["root"], sid)["runnable_workers"] == ["b"]
    mas.worker_start(runtime["root"], sid, "b", "worker-b", "session-b")
    request_b = mas.worker_completion_request(runtime["root"], sid, "b", "worker-b", "session-b")
    verified_b = mas.worker_completion_verify(
        runtime["root"], request_b["request_id"], "reviewer", "review-session",
        verdict="pass", checks={"evidence": True, "tests": True},
        evidence={"review": "worker-b independently verified"},
    )
    assert verified_b["worker_status"] == "completed"
    assert verified_b["supervisor_completed"] is True
    final = mas.supervisor_readiness(runtime["root"], sid)
    assert final["effective_status"] == "completed"
    assert final["automatic_process_launch"] is False
    assert final["isolated_workspace"] is False
    assert final["controlled_integration"] is False


def test_session_revocation_makes_active_supervisor_stale(runtime):
    sid = _base(runtime)
    mas.add_worker(runtime["root"], sid, "a", "worker-a", "session-a", "executor")
    mas.add_worker(runtime["root"], sid, "b", "worker-b", "session-b", "executor")
    mas.activate_supervisor(runtime["root"], sid, "human:architect")
    with runtime["rw"](runtime["root"]) as c:
        c.execute("UPDATE session_tokens SET revoked_at=CURRENT_TIMESTAMP WHERE session_id='session-a'")
    status = mas.supervisor_readiness(runtime["root"], sid)
    assert status["effective_status"] == "stale"
    assert any("active_capability_session_required" in reason for reason in status["reasons"])


def test_worker_session_must_be_unique(runtime):
    sid = _base(runtime)
    mas.add_worker(runtime["root"], sid, "a", "worker-a", "session-a", "executor")
    # Give worker-b the same authenticated session and role to reach the database uniqueness gate.
    with runtime["rw"](runtime["root"]) as c:
        c.execute("DELETE FROM session_tokens WHERE task_id='worker-b'")
        c.execute("DELETE FROM task_role_assignments WHERE task_id='worker-b'")
        c.execute("INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES('x2','tok-x2','session-a','worker-b','[\"fs_read\"]','2999-01-01 00:00:00')")
        c.execute("INSERT INTO task_role_assignments(task_id,session_id,role,status) VALUES('worker-b','session-a','executor','active')")
        c.execute("UPDATE tasks SET owner_session_id='session-a' WHERE id='worker-b'")
    with pytest.raises(sqlite3.IntegrityError):
        mas.add_worker(runtime["root"], sid, "b", "worker-b", "session-a", "executor")


def test_optional_skill_binding_must_be_current_and_recommendable(runtime):
    sid = _base(runtime)
    with runtime["rw"](runtime["root"]) as c:
        plan = c.execute("SELECT id,plan_hash FROM task_plans WHERE task_id='worker-a'").fetchone()
        c.execute("INSERT INTO promoted_skills(status,contract_version,contract_hash,contract_status) VALUES('graduated',2,'contract-1','valid')")
        skill_id = int(c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        c.execute("INSERT INTO skill_contracts(skill_id,validation_status,architecture_baseline_hash,contract_hash) VALUES(?,'valid','arch-1','contract-1')", (skill_id,))
        cur = c.execute("INSERT INTO skill_selection_runs(task_id,plan_id,plan_hash,architecture_baseline_hash,status,recommended_skill_id) VALUES('worker-a',?,?,'arch-1','recommended',?)", (plan["id"], plan["plan_hash"], skill_id))
        run_id = int(cur.lastrowid)
        c.execute("INSERT INTO skill_selection_candidates(selection_run_id,skill_id,eligible,recommendable,contract_hash) VALUES(?,?,1,1,'contract-1')", (run_id, skill_id))
    result = mas.add_worker(runtime["root"], sid, "a", "worker-a", "session-a", "executor", selection_run_id=run_id, skill_id=skill_id)
    assert result["status"] == "registered"



def test_cli_registry_exposes_ten_commands_only_for_this_node():
    parser = supervisor_cli.build_parser()
    choices = {}
    for action in parser._actions:
        if isinstance(action, __import__("argparse")._SubParsersAction):
            choices = action.choices
            break
    assert set(choices) == {
        "multi-agent-supervisor-create",
        "multi-agent-supervisor-worker-add",
        "multi-agent-supervisor-dependency-add",
        "multi-agent-supervisor-activate",
        "multi-agent-supervisor-pause",
        "multi-agent-supervisor-cancel",
        "multi-agent-worker-start",
        "multi-agent-worker-update",
        "multi-agent-supervisor-status",
        "multi-agent-supervisor-workers",
    }

def test_module_never_launches_subprocess_or_selects_model():
    source = Path(mas.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "Popen(" not in source
    assert "model_name" not in source
    assert "provider_name" not in source
    assert '"auto_process_launch": False' in source
    assert '"auto_model_provider_select": False' in source
