from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from agentos import jobs
from agentos.core import start_task
from agentos.db import connect
from agentos.tool_runtime_profiles import (
    create_sandbox_workspace,
    resolve_runtime_profile,
)


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
    start_task(
        root,
        "T1",
        "Async sandbox lifecycle test",
    )
    return root


def _insert_job(
    root: Path,
    *,
    job_id: str,
    state: str,
    pid: int | None,
) -> dict:
    source = root / "src"
    source.mkdir(exist_ok=True)

    sandbox = create_sandbox_workspace(
        root,
        source,
        "T1",
        "S1",
        job_id,
        "test",
    )

    runtime_profile = resolve_runtime_profile("test")

    spec = {
        "job_id": job_id,
        "task_id": "T1",
        "session_id": "S1",
        "command": [
            "python",
            "-m",
            "pytest",
        ],
        "cwd": ".",
        "workspace": sandbox["workspace"],
        "timeout_seconds": 30,
        "profile": "test",
        "runtime_profile": runtime_profile["name"],
        "runtime_profile_hash": runtime_profile["profile_hash"],
        "runtime_profile_version": runtime_profile["profile_version"],
        "runtime_profile_scope": runtime_profile["scope"],
        "sandbox": sandbox,
        "snapshot_hash": sandbox["snapshot_hash"],
        "network_policy": "none",
        "environment_hash": hashlib.sha256(
            b"{}"
        ).hexdigest(),
    }

    spec_json = json.dumps(
        spec,
        sort_keys=True,
    )
    spec_hash = hashlib.sha256(
        json.dumps(
            spec,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    job_dir = (
        root
        / ".agents/runtime/jobs"
        / job_id
    )
    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with connect(root) as c:
        c.execute(
            "INSERT INTO async_jobs("
            "job_id,task_id,session_id,spec_json,spec_hash,"
            "state,pid,timeout_seconds,stdout_path,stderr_path,created_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                "T1",
                "S1",
                spec_json,
                spec_hash,
                state,
                pid,
                30,
                str(job_dir / "stdout.log"),
                str(job_dir / "stderr.log"),
                jobs._now(),
            ),
        )

    return {
        "sandbox": sandbox,
        "spec": spec,
    }


def test_v0292_queued_cancelled_sandbox_is_cleanup_safe(
    tmp_path,
):
    root = project(tmp_path)
    item = _insert_job(
        root,
        job_id="queued-cancel",
        state="cancelled",
        pid=None,
    )

    result = jobs._maybe_cleanup_terminal_sandbox(
        root,
        "queued-cancel",
    )

    assert result["status"] == "cleaned"
    assert not Path(
        item["sandbox"]["root"]
    ).exists()


def test_v0292_windows_completion_requires_drained_receipt_before_cleanup(
    tmp_path,
    monkeypatch,
):
    root = project(tmp_path)
    item = _insert_job(
        root,
        job_id="done",
        state="succeeded",
        pid=1001,
    )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "_windows_completion_record",
        lambda *args, **kwargs: None,
    )

    deferred = jobs._maybe_cleanup_terminal_sandbox(
        root,
        "done",
    )

    assert deferred["status"] == "deferred"
    assert Path(
        item["sandbox"]["root"]
    ).exists()

    monkeypatch.setattr(
        jobs,
        "_windows_completion_record",
        lambda *args, **kwargs: {
            "process_tree_drained": True,
        },
    )

    cleaned = jobs._maybe_cleanup_terminal_sandbox(
        root,
        "done",
    )

    assert cleaned["status"] == "cleaned"
    assert not Path(
        item["sandbox"]["root"]
    ).exists()


def test_v0292_windows_timeout_defers_while_job_tree_is_active(
    tmp_path,
    monkeypatch,
):
    root = project(tmp_path)
    item = _insert_job(
        root,
        job_id="timeout-active",
        state="timed_out",
        pid=2001,
    )

    with connect(root) as c:
        c.execute(
            "INSERT INTO job_events("
            "job_id,event_type,details_json"
            ") VALUES(?,?,?)",
            (
                "timeout-active",
                "timed_out",
                json.dumps(
                    {
                        "process_tree_terminated": True,
                    }
                ),
            ),
        )

    monkeypatch.setattr(
        jobs,
        "_is_windows_host",
        lambda: True,
    )
    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda *args, **kwargs: 1,
    )

    deferred = jobs._maybe_cleanup_terminal_sandbox(
        root,
        "timeout-active",
    )

    assert deferred["status"] == "deferred"
    assert Path(
        item["sandbox"]["root"]
    ).exists()

    monkeypatch.setattr(
        jobs,
        "named_job_active_process_count",
        lambda *args, **kwargs: 0,
    )

    cleaned = jobs._maybe_cleanup_terminal_sandbox(
        root,
        "timeout-active",
    )

    assert cleaned["status"] == "cleaned"
    assert not Path(
        item["sandbox"]["root"]
    ).exists()


def test_v0292_orphaned_job_never_cleans_uncertain_sandbox(
    tmp_path,
):
    root = project(tmp_path)
    item = _insert_job(
        root,
        job_id="orphaned",
        state="orphaned",
        pid=3001,
    )

    result = jobs._maybe_cleanup_terminal_sandbox(
        root,
        "orphaned",
    )

    assert result["status"] == "deferred"
    assert result["reason"] == "job_not_terminal"
    assert Path(
        item["sandbox"]["root"]
    ).exists()


def test_v0292_job_status_calls_terminal_sandbox_cleanup():
    source = Path(
        jobs.__file__
    ).read_text(
        encoding="utf-8"
    )

    start = source.index("def job_status(")
    end = source.index(
        "\ndef cancel_job(",
        start,
    )
    function_source = source[start:end]

    assert (
        "_maybe_cleanup_terminal_sandbox("
        in function_source
    )


def test_v0292_recover_jobs_rechecks_cleanup_after_materialization():
    source = Path(
        jobs.__file__
    ).read_text(
        encoding="utf-8"
    )

    start = source.index("def recover_jobs(")
    end = source.index(
        "\ndef discover_tools(",
        start,
    )
    function_source = source[start:end]

    assert (
        "_maybe_cleanup_terminal_sandbox("
        in function_source
    )
    assert "sandbox_cleanup" in function_source
