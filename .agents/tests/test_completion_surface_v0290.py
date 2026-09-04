"""Path: .agents/tests/test_completion_surface_v0290.py
Purpose: Verify v0.29.0 completion CLI/MCP surfaces and privacy boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".agents") not in sys.path:
    sys.path.insert(0, str(ROOT / ".agents"))

from agentos import completion_surface as surface
from agentos import completion_verification as cv
from agentos import workflow as wf
from agentos.core import start_task
from agentos.db import connect
from agentos.policy import load_policy


def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(
            ".git", "runtime", "agentos.db", "__pycache__", ".pytest_cache"
        ),
    )
    return root


def h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def schema62(root: Path) -> None:
    with connect(root) as c:
        cv.migration_62(c)


def add_session(root: Path, task_id: str, session_id: str, token_id: str, role: str) -> None:
    with connect(root) as c:
        c.execute(
            "INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES(?,?,?,?,?,?)",
            (h(token_id), token_id, session_id, task_id, "[]", "2999-01-01 00:00:00"),
        )
        c.execute(
            "INSERT INTO task_role_assignments(task_id,session_id,token_id,role,permissions_json,assigned_by,status) VALUES(?,?,?,?,?,'test','active')",
            (task_id, session_id, token_id, role, "[]"),
        )


def ready_pre_report(root: Path) -> None:
    start_task(root, "T1", "Phase 4 workflow completion")
    wf.seed_workflow(root, "T1")
    order = load_policy(root)["workflows"]["default"]
    with connect(root) as c:
        c.execute("UPDATE tasks SET approved=1,approved_scope='[\"src\",\"tests\"]',owner_session_id='producer-session' WHERE id='T1'")
        for step in order:
            if step in {"receive_request", "report"}:
                continue
            source = "auto" if step in wf.AUTOMATED_ONLY_STEPS else "manual"
            c.execute(
                """UPDATE workflow_steps
                   SET status='done',completion_source=?,result_hash=?,command_name='phase4-fixture',
                       exit_code=0,verification_status=?,note='phase4 fixture'
                   WHERE task_id='T1' AND workflow_name='default' AND step_name=?""",
                (source, h("step:" + step), "verified" if step in wf.AUTOMATED_ONLY_STEPS else "unverified", step),
            )
    start_task(root, "R1", "Independent reviewer")
    add_session(root, "T1", "producer-session", "producer-token", "executor")
    add_session(root, "R1", "reviewer-session", "reviewer-token", "reviewer")


def test_cli_registry_adds_agent_plane_commands_only():
    from agentos.cli_runtime import CONTROL_PLANE_COMMANDS, agent_command_registry, command_registry, privileged_command_registry
    registry = command_registry()
    agent = agent_command_registry()
    privileged = privileged_command_registry()
    expected = {"completion-request", "completion-verify", "completion-status"}
    assert expected <= set(registry)
    assert expected <= set(agent)
    assert not (expected & set(CONTROL_PLANE_COMMANDS))
    assert not (expected & set(privileged))
    assert len(registry) >= 344
    assert len(agent) >= 248
    # v0.29.0 invariant: the completion surface itself adds no privileged
    # commands. Successor releases may add separately governed control-plane
    # commands, which are pinned by their own release-node tests.
    assert len(privileged) >= 98


def test_cli_parser_registers_three_completion_commands():
    from agentos.completion_cli import build_parser
    parser = build_parser()
    commands = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            commands = set(action.choices)
            break
    assert commands == {"completion-request", "completion-verify", "completion-status"}


def test_schema62_status_is_read_only_and_available(tmp_path):
    root = project(tmp_path)
    start_task(root, "T1", "schema62")
    wf.seed_workflow(root, "T1")

    with connect(root) as c:
        before = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM workflow_steps WHERE task_id='T1'"
            ).fetchone()["n"]
        )

    status = surface.completion_public_status(
        root,
        subject_type="workflow",
        task_id="T1",
    )

    with connect(root) as c:
        after = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM workflow_steps WHERE task_id='T1'"
            ).fetchone()["n"]
        )

    assert before == after
    assert status["schema_available"] is True


def test_workflow_request_verify_and_public_status_are_redacted(tmp_path):
    root = project(tmp_path)
    schema62(root)
    ready_pre_report(root)
    request = surface.completion_request(
        root, subject_type="workflow", task_id="T1", session_id="producer-session"
    )
    result = surface.completion_verify(
        root,
        request_id=request["request_id"],
        verifier_task_id="R1",
        verifier_session_id="reviewer-session",
        verdict="pass",
        checks={"evidence": True, "requirements": True, "tests": True},
        evidence={"secret_review_note": "must_not_escape_public_status"},
    )
    assert result["verdict"] == "pass"
    status = surface.completion_public_status(root, request_id=request["request_id"])
    assert status["accepted"] is True
    assert status["current"] is True
    assert status["attempt"]["verdict"] == "pass"
    encoded = json.dumps(status, sort_keys=True)
    for forbidden in (
        "producer-session", "reviewer-session", "producer_assignment_id",
        "verifier_assignment_id", "secret_review_note",
        "must_not_escape_public_status", "evidence_json"
    ):
        assert forbidden not in encoded


def test_mcp_exposes_status_only():
    from agentos.mcp_runtime import ALL_TOOL_NAMES
    assert "agentos.completion_status_get" in ALL_TOOL_NAMES
    assert "agentos.completion_request" not in ALL_TOOL_NAMES
    assert "agentos.completion_verify" not in ALL_TOOL_NAMES


def test_mcp_status_dispatch_does_not_mutate_workflow(tmp_path):
    from agentos.mcp_v0290 import dispatch

    root = project(tmp_path)
    start_task(root, "T1", "mcp read only")
    wf.seed_workflow(root, "T1")

    with connect(root) as c:
        before = [
            tuple(row)
            for row in c.execute(
                "SELECT id,step_name,status,note,completion_source,result_hash "
                "FROM workflow_steps WHERE task_id='T1' ORDER BY id"
            ).fetchall()
        ]

    value = dispatch(
        root,
        "agentos.completion_status_get",
        {
            "subject_type": "workflow",
            "task_id": "T1",
        },
    )

    with connect(root) as c:
        after = [
            tuple(row)
            for row in c.execute(
                "SELECT id,step_name,status,note,completion_source,result_hash "
                "FROM workflow_steps WHERE task_id='T1' ORDER BY id"
            ).fetchall()
        ]

    assert value["schema_available"] is True
    assert before == after


def test_unseeded_workflow_mcp_status_does_not_seed(tmp_path):
    from agentos.mcp_v0290 import dispatch
    root = project(tmp_path)
    start_task(root, "T1", "not seeded")
    value = dispatch(root, "agentos.completion_status_get", {"subject_type": "workflow", "task_id": "T1"})
    assert value["reason"] == "workflow_not_seeded"
    with connect(root) as c:
        count = int(c.execute("SELECT COUNT(*) AS n FROM workflow_steps WHERE task_id='T1'").fetchone()["n"])
    assert count == 0


def test_request_id_status_returns_exact_request_not_latest(tmp_path):
    root = project(tmp_path)
    schema62(root)
    ready_pre_report(root)

    first = surface.completion_request(
        root,
        subject_type="workflow",
        task_id="T1",
        session_id="producer-session",
    )

    second = surface.completion_request(
        root,
        subject_type="workflow",
        task_id="T1",
        session_id="producer-session",
    )

    first_status = surface.completion_public_status(
        root,
        request_id=first["request_id"],
    )
    second_status = surface.completion_public_status(
        root,
        request_id=second["request_id"],
    )

    assert (
        first_status["request"]["request_id"]
        == first["request_id"]
    )
    assert (
        first_status["request"]["status"]
        == "superseded"
    )

    assert (
        second_status["request"]["request_id"]
        == second["request_id"]
    )
    assert (
        second_status["request"]["status"]
        == "pending"
    )


def test_phase4_surface_adds_no_process_primitive():
    modules = [
        surface,
        __import__("agentos.completion_cli", fromlist=["*"]),
        __import__("agentos.mcp_v0290", fromlist=["*"]),
    ]
    for module in modules:
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "subprocess.run(" not in source
        assert "subprocess.Popen(" not in source
