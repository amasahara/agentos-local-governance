from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agentos import jobs
from agentos import windows_process_tree as process_tree
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


def make_running_job(
    root: Path,
    *,
    job_id: str,
    timeout_seconds: int,
    started_at: str,
) -> None:
    with connect(root) as c:
        task = c.execute(
            "SELECT 1 FROM tasks WHERE id='T1'"
        ).fetchone()

    if task is None:
        start_task(
            root,
            "T1",
            "Timeout containment test",
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
        "timeout_seconds": timeout_seconds,
        "profile": "test",
        "network_policy": "none",
        "environment_hash": hashlib.sha256(
            json.dumps(
                jobs._filtered_env({}),
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
            "state,pid,timeout_seconds,stdout_path,stderr_path,"
            "created_at,started_at"
            ") VALUES(?,?,?,?,?,'running',?,?,?,?,?,?)",
            (
                job_id,
                "T1",
                "S1",
                json.dumps(
                    spec,
                    sort_keys=True,
                ),
                spec_hash,
                50001,
                timeout_seconds,
                str(job_dir / "stdout.log"),
                str(job_dir / "stderr.log"),
                started_at,
                started_at,
            ),
        )


def test_v0291_timeout_evidence_parses_sqlite_and_iso_timestamps():
    now = datetime(
        2026,
        8,
        29,
        2,
        0,
        0,
        tzinfo=timezone.utc,
    )

    row = {
        "started_at": "2026-08-29 01:59:00",
        "timeout_seconds": 30,
    }

    evidence = jobs._job_timeout_evidence(
        row,
        now=now,
    )

    assert evidence is not None
    assert evidence["timeout_seconds"] == 30
    assert evidence["deadline"].endswith(
        "+00:00"
    )


def test_v0291_windows_status_timeout_terminates_tree(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)

    started = (
        datetime.now(timezone.utc)
        - timedelta(seconds=60)
    ).isoformat()

    make_running_job(
        root,
        job_id="statustimeout",
        timeout_seconds=1,
        started_at=started,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "_windows_completion_record",
        lambda root_arg, job_id: None,
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda name: 2,
    )

    terminated = []

    monkeypatch.setattr(
        jobs,
        "terminate_named_job",
        lambda name, code: (
            terminated.append(
                (name, code)
            )
            or True
        ),
    )

    result = jobs.job_status(
        root,
        "statustimeout",
    )

    assert result["state"] == "timed_out"
    assert result["exit_code"] == 124
    assert terminated == [
        (
            jobs.async_job_object_name(
                "statustimeout"
            ),
            124,
        )
    ]
    assert (
        result[
            "process_tree_timeout_evidence"
        ]["process_tree_terminated"]
        is True
    )


def test_v0291_timeout_precedes_missing_broker_orphaning(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)

    started = (
        datetime.now(timezone.utc)
        - timedelta(seconds=60)
    ).isoformat()

    make_running_job(
        root,
        job_id="timeoutmissing",
        timeout_seconds=1,
        started_at=started,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "_windows_completion_record",
        lambda root_arg, job_id: None,
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda name: None,
    )
    monkeypatch.setattr(
        jobs,
        "terminate_named_job",
        lambda name, code: False,
    )

    result = jobs.job_status(
        root,
        "timeoutmissing",
    )

    assert result["state"] == "timed_out"
    assert (
        result[
            "process_tree_timeout_evidence"
        ]["process_tree_terminated"]
        is False
    )


def test_v0291_nonzero_broker_receipt_materializes_failed(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)

    started = datetime.now(
        timezone.utc
    ).isoformat()

    make_running_job(
        root,
        job_id="failedreceipt",
        timeout_seconds=300,
        started_at=started,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "_windows_completion_record",
        lambda root_arg, job_id: {
            "ok": True,
            "state": "drained",
            "job_id": job_id,
            "job_name": (
                jobs.async_job_object_name(
                    job_id
                )
            ),
            "worker_exit_code": 7,
            "process_tree_drained": True,
            "drained_at": jobs._now(),
        },
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda name: None,
    )

    result = jobs.job_status(
        root,
        "failedreceipt",
    )

    assert result["state"] == "failed"
    assert result["exit_code"] == 7


def test_v0291_recovery_enforces_windows_timeout(
    monkeypatch,
    tmp_path,
):
    root = project(tmp_path)

    started = (
        datetime.now(timezone.utc)
        - timedelta(seconds=60)
    ).isoformat()

    make_running_job(
        root,
        job_id="recovertimeout",
        timeout_seconds=1,
        started_at=started,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "_windows_completion_record",
        lambda root_arg, job_id: None,
    )
    monkeypatch.setattr(
        jobs,
        "terminate_named_job",
        lambda name, code: True,
    )

    result = jobs.recover_jobs(
        root
    )

    assert result["timed_out_jobs"] == [
        "recovertimeout"
    ]

    with connect(root) as c:
        row = c.execute(
            "SELECT state,exit_code "
            "FROM async_jobs WHERE job_id=?",
            ("recovertimeout",),
        ).fetchone()

    assert row["state"] == "timed_out"
    assert row["exit_code"] == 124


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows broker completion receipt exit-code contract",
)
def test_v0291_real_broker_receipt_records_exit_code(
    tmp_path,
):
    job_id = "receiptcode"
    job_name = (
        process_tree.async_job_object_name(
            job_id
        )
    )

    ready_path = tmp_path / "ready.json"
    completion_path = (
        tmp_path / "completion.json"
    )

    broker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agentos.windows_job_broker",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )

    assert broker.stdin is not None

    payload = {
        "job_id": job_id,
        "job_name": job_name,
        "command": [
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        "cwd": str(tmp_path),
        "env": dict(os.environ),
        "stdout_path": str(
            tmp_path / "worker.out"
        ),
        "stderr_path": str(
            tmp_path / "worker.err"
        ),
        "ready_path": str(
            ready_path
        ),
        "completion_path": str(
            completion_path
        ),
    }

    broker.stdin.write(
        json.dumps(
            payload,
            sort_keys=True,
        )
        + "\n"
    )
    broker.stdin.flush()
    broker.stdin.close()

    broker.wait(timeout=10)

    assert broker.returncode == 0
    assert completion_path.is_file()

    completion = json.loads(
        completion_path.read_text(
            encoding="utf-8"
        )
    )

    assert completion[
        "worker_exit_code"
    ] == 7
    assert completion[
        "process_tree_drained"
    ] is True
    assert completion[
        "broker_profile"
    ] == (
        "windows_job_broker_kill_on_close_v1"
    )
