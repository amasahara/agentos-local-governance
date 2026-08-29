from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from agentos import jobs
from agentos.core import start_task
from agentos.db import connect


ROOT = Path(__file__).resolve().parents[2]


def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"

    shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(
            ".git",
            "runtime",
            "agentos.db",
            "__pycache__",
            ".pytest_cache",
        ),
    )

    return root


def queued_job(
    root: Path,
    *,
    job_id: str,
) -> tuple[dict, dict]:
    with connect(root) as c:
        task_exists = c.execute(
            "SELECT 1 FROM tasks WHERE id=?",
            ("T1",),
        ).fetchone()

    if task_exists is None:
        start_task(
            root,
            "T1",
            "Async containment test",
        )

    workspace = root / "src"
    workspace.mkdir(
        exist_ok=True,
    )

    job_dir = (
        root
        / ".agents/runtime/jobs"
        / job_id
    )
    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    env = jobs._filtered_env({})

    spec = {
        "job_id": job_id,
        "task_id": "T1",
        "session_id": "S1",
        "command": [
            "python",
            "-m",
            "pytest",
            "--version",
        ],
        "cwd": ".",
        "workspace": str(workspace),
        "timeout_seconds": 30,
        "profile": "test",
        "network_policy": "none",
        "environment_hash": hashlib.sha256(
            json.dumps(
                env,
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }

    spec_hash = hashlib.sha256(
        json.dumps(
            spec,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    with connect(root) as c:
        c.execute(
            "INSERT INTO async_jobs("
            "job_id,task_id,session_id,spec_json,spec_hash,"
            "state,timeout_seconds,stdout_path,stderr_path,created_at"
            ") VALUES(?,?,?,?,?,'queued',?,?,?,?)",
            (
                job_id,
                "T1",
                "S1",
                json.dumps(
                    spec,
                    sort_keys=True,
                ),
                spec_hash,
                30,
                str(job_dir / "stdout.log"),
                str(job_dir / "stderr.log"),
                jobs._now(),
            ),
        )

    guarded = {
        "command": list(
            spec["command"]
        ),
        "cwd": ".",
        "timeout": 30,
        "env": {},
        "auto_start": True,
    }

    return spec, guarded


def set_running(
    root: Path,
    job_id: str,
    pid: int,
) -> None:
    with connect(root) as c:
        c.execute(
            "UPDATE async_jobs "
            "SET state='running',pid=?,started_at=? "
            "WHERE job_id=?",
            (
                pid,
                jobs._now(),
                job_id,
            ),
        )



def test_v0291_queued_job_does_not_claim_process_containment(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)
    queued_job(
        root,
        job_id="queuedonly",
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )

    result = jobs.job_status(
        root,
        "queuedonly",
    )

    assert result["state"] == "queued"
    assert (
        result["process_tree_contained"]
        is False
    )
    assert (
        result[
            "process_tree_active_processes"
        ]
        is None
    )


def test_v0291_windows_async_start_routes_through_broker(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)
    spec, guarded = queued_job(
        root,
        job_id="brokerstart",
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "validate_execution_token",
        lambda *args, **kwargs: None,
    )

    calls = []

    def fake_launch(
        root_arg,
        job_id,
        spec_arg,
        launch_env,
        stdout_path,
        stderr_path,
    ):
        calls.append(job_id)

        return {
            "ok": True,
            "state": "ready",
            "worker_pid": 41001,
            "broker_pid": 41002,
            "job_name": (
                jobs.async_job_object_name(
                    job_id
                )
            ),
            "broker_profile": (
                "windows_job_broker_kill_on_close_v1"
            ),
            "containment_scope": (
                "agentos_mediated_process_execution"
            ),
            "assigned_before_resume": True,
            "kill_on_broker_exit": True,
        }

    monkeypatch.setattr(
        jobs,
        "_launch_windows_job_broker",
        fake_launch,
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda name: 1,
    )

    result = jobs.start_job(
        root,
        "brokerstart",
        execution_token="token",
        guarded_args=guarded,
    )

    assert calls == ["brokerstart"]
    assert result["state"] == "running"
    assert result["pid"] == 41001
    assert (
        result["process_tree_contained"]
        is True
    )
    assert (
        result[
            "process_tree_active_processes"
        ]
        == 1
    )


def test_v0291_windows_status_tracks_job_not_root_pid(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)
    queued_job(
        root,
        job_id="statusmembers",
    )
    set_running(
        root,
        "statusmembers",
        42001,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "_pid_alive",
        lambda pid: False,
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda name: 2,
    )

    result = jobs.job_status(
        root,
        "statusmembers",
    )

    assert result["state"] == "running"
    assert (
        result[
            "process_tree_active_processes"
        ]
        == 2
    )


def test_v0291_windows_broker_completion_materializes_success(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)
    queued_job(
        root,
        job_id="completedjob",
    )
    set_running(
        root,
        "completedjob",
        43001,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda name: None,
    )

    completion = (
        jobs._windows_broker_completion_path(
            root,
            "completedjob",
        )
    )
    completion.write_text(
        json.dumps(
            {
                "ok": True,
                "state": "drained",
                "job_id": "completedjob",
                "job_name": (
                    jobs.async_job_object_name(
                        "completedjob"
                    )
                ),
                "drained_at": jobs._now(),
            }
        ),
        encoding="utf-8",
    )

    result = jobs.job_status(
        root,
        "completedjob",
    )

    assert result["state"] == "succeeded"
    assert result["exit_code"] == 0


def test_v0291_windows_missing_broker_without_receipt_is_orphaned(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)
    queued_job(
        root,
        job_id="missingbroker",
    )
    set_running(
        root,
        "missingbroker",
        44001,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda name: None,
    )

    result = jobs.job_status(
        root,
        "missingbroker",
    )

    assert result["state"] == "orphaned"
    assert (
        result["process_tree_contained"]
        is False
    )


def test_v0291_windows_cancel_terminates_named_job(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)
    queued_job(
        root,
        job_id="canceljob",
    )
    set_running(
        root,
        "canceljob",
        45001,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )

    calls = []

    monkeypatch.setattr(
        jobs,
        "terminate_named_job",
        lambda name, code: (
            calls.append(
                (name, code)
            )
            or True
        ),
    )
    monkeypatch.setattr(
        jobs,
        "append_signed_event",
        lambda *args, **kwargs: {
            "event_hash": "signed"
        },
    )

    original_kill = jobs.os.kill

    def guarded_kill(*args, **kwargs):
        raise AssertionError(
            "Windows async cancel used root-only os.kill"
        )

    monkeypatch.setattr(
        jobs.os,
        "kill",
        guarded_kill,
    )

    result = jobs.cancel_job(
        root,
        "canceljob",
        "operator",
        "test",
    )

    monkeypatch.setattr(
        jobs.os,
        "kill",
        original_kill,
    )

    assert result["state"] == "cancelled"
    assert calls == [
        (
            jobs.async_job_object_name(
                "canceljob"
            ),
            130,
        )
    ]


def test_v0291_windows_recovery_uses_broker_membership(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)

    queued_job(
        root,
        job_id="alivejob",
    )
    queued_job(
        root,
        job_id="missingjob",
    )

    set_running(
        root,
        "alivejob",
        46001,
    )
    set_running(
        root,
        "missingjob",
        46002,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )

    def active(name):
        return (
            2
            if name.endswith(
                "alivejob"
            )
            else None
        )

    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        active,
    )

    result = jobs.recover_jobs(root)

    assert result["orphaned_jobs"] == [
        "missingjob"
    ]

    assert jobs.job_status(
        root,
        "alivejob",
    )["state"] == "running"


def test_v0291_jobs_source_has_no_windows_root_only_cancel():
    import ast

    source = Path(
        jobs.__file__
    ).read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)
    lines = source.splitlines()

    cancel_node = next(
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "cancel_job"
        )
    )

    cancel_source = "\n".join(
        lines[
            cancel_node.lineno - 1:
            cancel_node.end_lineno
        ]
    )

    assert "terminate_named_job" in cancel_source

    windows_branch = cancel_source.split(
        "if _is_windows_host():",
        1,
    )[1].split(
        'elif os.name == "posix":',
        1,
    )[0]

    assert "terminate_named_job" in windows_branch
    assert "os.kill(" not in windows_branch
