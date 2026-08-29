from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentos import windows_process_tree as process_tree


pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="Windows Job Object broker ownership contract",
)


def _start_broker(
    tmp_path: Path,
    *,
    job_id: str,
    worker_code: str,
):
    job_name = (
        process_tree.async_job_object_name(
            job_id
        )
    )

    stdout_path = (
        tmp_path / f"{job_id}.stdout.log"
    )
    stderr_path = (
        tmp_path / f"{job_id}.stderr.log"
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
    assert broker.stdout is not None
    assert broker.stderr is not None

    payload = {
        "job_id": job_id,
        "job_name": job_name,
        "command": [
            sys.executable,
            "-c",
            worker_code,
        ],
        "cwd": str(tmp_path),
        "env": dict(os.environ),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
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

    ready_line = broker.stdout.readline()

    if not ready_line:
        error_text = broker.stderr.read()
        raise AssertionError(
            "broker did not produce READY: "
            + error_text
        )

    ready = json.loads(
        ready_line
    )

    return (
        broker,
        ready,
        job_name,
        stdout_path,
        stderr_path,
    )


def _wait_dead(
    pid: int,
    timeout: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout

    while (
        time.monotonic() < deadline
        and process_tree.pid_is_alive(pid)
    ):
        time.sleep(0.05)

    assert not process_tree.pid_is_alive(pid)


def test_v0291_broker_keeps_named_job_reopenable(
    tmp_path,
):
    (
        broker,
        ready,
        job_name,
        _,
        _,
    ) = _start_broker(
        tmp_path,
        job_id="brokerlifetime",
        worker_code=(
            "import time; time.sleep(60)"
        ),
    )

    try:
        assert ready["ok"] is True
        assert ready["state"] == "ready"
        assert ready["job_name"] == job_name
        assert ready[
            "assigned_before_resume"
        ] is True
        assert ready[
            "kill_on_broker_exit"
        ] is True
        assert ready["broker_pid"] == broker.pid

        active = (
            process_tree.named_job_active_process_count(
                job_name
            )
        )

        assert active is not None
        assert active >= 1
        assert broker.poll() is None
    finally:
        process_tree.terminate_named_job(
            job_name,
            95,
        )
        broker.wait(timeout=5)


def test_v0291_broker_exit_kills_worker_tree(
    tmp_path,
):
    (
        broker,
        ready,
        job_name,
        _,
        _,
    ) = _start_broker(
        tmp_path,
        job_id="brokerfailclosed",
        worker_code=(
            "import time; time.sleep(60)"
        ),
    )

    worker_pid = int(
        ready["worker_pid"]
    )

    assert process_tree.pid_is_alive(
        worker_pid
    )

    active = (
        process_tree.named_job_active_process_count(
            job_name
        )
    )

    assert active is not None
    assert active >= 1

    broker.terminate()
    broker.wait(timeout=5)

    _wait_dead(
        worker_pid
    )

    assert (
        process_tree.named_job_active_process_count(
            job_name
        )
        is None
    )


def test_v0291_terminate_named_job_stops_worker_and_broker(
    tmp_path,
):
    (
        broker,
        ready,
        job_name,
        _,
        _,
    ) = _start_broker(
        tmp_path,
        job_id="brokercancel",
        worker_code=(
            "import time; time.sleep(60)"
        ),
    )

    worker_pid = int(
        ready["worker_pid"]
    )

    assert process_tree.terminate_named_job(
        job_name,
        96,
    ) is True

    _wait_dead(
        worker_pid
    )

    broker.wait(timeout=5)

    assert broker.returncode == 0
    assert (
        process_tree.named_job_active_process_count(
            job_name
        )
        is None
    )


def test_v0291_broker_duplicate_job_name_fails_closed(
    tmp_path,
):
    (
        broker1,
        ready1,
        job_name,
        _,
        _,
    ) = _start_broker(
        tmp_path,
        job_id="brokerduplicate",
        worker_code=(
            "import time; time.sleep(60)"
        ),
    )

    try:
        broker2 = subprocess.Popen(
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

        assert broker2.stdin is not None

        payload = {
            "job_id": "brokerduplicate",
            "job_name": job_name,
            "command": [
                sys.executable,
                "-c",
                "import time; time.sleep(1)",
            ],
            "cwd": str(tmp_path),
            "env": dict(os.environ),
            "stdout_path": str(
                tmp_path / "dup.out"
            ),
            "stderr_path": str(
                tmp_path / "dup.err"
            ),
        }

        broker2.stdin.write(
            json.dumps(
                payload,
                sort_keys=True,
            )
            + "\n"
        )
        broker2.stdin.flush()
        broker2.stdin.close()

        broker2.wait(timeout=5)

        assert broker2.returncode != 0
        assert (
            process_tree.named_job_active_process_count(
                job_name
            )
            is not None
        )
        assert process_tree.pid_is_alive(
            int(ready1["worker_pid"])
        )
    finally:
        process_tree.terminate_named_job(
            job_name,
            97,
        )
        broker1.wait(timeout=5)
