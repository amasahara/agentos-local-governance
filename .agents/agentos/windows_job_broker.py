"""
Windows Job Object broker for AgentOS asynchronous execution.

The broker owns the durable handle to a named Job Object configured with
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. The governed worker root is created
suspended, assigned before resume, and cannot outlive the broker without
kernel-enforced process-tree termination.

Protocol:
    stdin  : one UTF-8 JSON object line with launch payload
    stdout : one UTF-8 JSON READY record line
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if os.name == "nt":
    import msvcrt

from .windows_process_tree import (
    CONTAINMENT_SCOPE,
    WindowsProcessTreeError,
    async_job_object_name,
    create_named_kill_on_close_job,
    named_job_active_process_count,
    spawn_suspended_in_job,
)
from .windows_restricted_execution import (
    RESTRICTED_TOKEN_PROFILE,
    spawn_restricted_suspended_in_job,
)
from .windows_physical_isolation import (
    LOW_INTEGRITY_PROFILE,
    spawn_low_integrity_restricted_suspended_in_job,
)


BROKER_PROTOCOL_VERSION = 1
BROKER_PROFILE = "windows_job_broker_kill_on_close_v1"


def _fail(message: str) -> int:
    try:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    return 2



def _load_payload() -> dict[str, Any]:
    line = sys.stdin.readline()

    if not line:
        raise RuntimeError(
            "windows_job_broker_missing_payload"
        )

    value = json.loads(line)
    if not isinstance(value, dict):
        raise RuntimeError(
            "windows_job_broker_payload_must_be_object"
        )

    command = value.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(
            isinstance(item, str)
            and item
            for item in command
        )
    ):
        raise RuntimeError(
            "windows_job_broker_invalid_command"
        )

    job_id = str(
        value.get("job_id") or ""
    ).strip()

    expected_name = async_job_object_name(
        job_id
    )
    job_name = str(
        value.get("job_name") or ""
    )
    if job_name != expected_name:
        raise RuntimeError(
            "windows_job_broker_job_name_mismatch"
        )

    cwd = str(
        value.get("cwd") or ""
    ).strip()
    if not cwd:
        raise RuntimeError(
            "windows_job_broker_missing_cwd"
        )

    env = value.get("env")
    if not isinstance(env, dict):
        raise RuntimeError(
            "windows_job_broker_env_must_be_object"
        )

    restricted_execution = value.get(
        "restricted_execution",
        False,
    )
    if not isinstance(
        restricted_execution,
        bool,
    ):
        raise RuntimeError(
            "windows_job_broker_restricted_execution_must_be_bool"
        )
    low_integrity_execution = value.get(
        "low_integrity_execution",
        False,
    )
    if not isinstance(
        low_integrity_execution,
        bool,
    ):
        raise RuntimeError(
            "windows_job_broker_low_integrity_execution_must_be_bool"
        )
    if low_integrity_execution and not restricted_execution:
        raise RuntimeError(
            "windows_job_broker_low_integrity_requires_restricted_execution"
        )

    stdout_path = str(
        value.get("stdout_path") or ""
    ).strip()
    stderr_path = str(
        value.get("stderr_path") or ""
    ).strip()

    if not stdout_path or not stderr_path:
        raise RuntimeError(
            "windows_job_broker_missing_output_path"
        )

    return {
        "job_id": job_id,
        "job_name": job_name,
        "command": command,
        "cwd": cwd,
        "env": {
            str(key): str(item)
            for key, item in env.items()
        },
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "restricted_execution": restricted_execution,
        "low_integrity_execution": low_integrity_execution,
        "ready_path": str(
            value.get("ready_path") or ""
        ).strip(),
        "completion_path": str(
            value.get("completion_path") or ""
        ).strip(),
    }

def _ready_record(
    *,
    job_id: str,
    job_name: str,
    worker_pid: int,
    restricted_execution: bool,
    low_integrity_execution: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "state": "ready",
        "broker_protocol_version": (
            BROKER_PROTOCOL_VERSION
        ),
        "broker_profile": BROKER_PROFILE,
        "containment_scope": CONTAINMENT_SCOPE,
        "job_id": job_id,
        "job_name": job_name,
        "broker_pid": os.getpid(),
        "worker_pid": int(worker_pid),
        "assigned_before_resume": True,
        "kill_on_broker_exit": True,
        "restricted_execution": bool(
            restricted_execution
        ),
        "restricted_execution_profile": (
            RESTRICTED_TOKEN_PROFILE
            if restricted_execution
            else None
        ),
        "restricted_token_verified": bool(
            restricted_execution
        ),
        "restricted_token_attested": False,
        "low_integrity_execution": bool(
            low_integrity_execution
        ),
        "low_integrity_profile": (
            LOW_INTEGRITY_PROFILE
            if low_integrity_execution
            else None
        ),
        "low_integrity_token_verified": bool(
            low_integrity_execution
        ),
        "sandbox_low_integrity_boundary_required": bool(
            low_integrity_execution
        ),
        "low_integrity_attested": False,
    }

def _os_handle(file_object) -> int:
    handle = int(
        msvcrt.get_osfhandle(
            file_object.fileno()
        )
    )

    os.set_handle_inheritable(
        handle,
        True,
    )

    return handle



def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        path.name + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    os.replace(
        temporary,
        path,
    )


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()



def run_broker() -> int:
    if os.name != "nt":
        return _fail(
            "windows_job_broker_requires_windows"
        )

    job = None
    proc = None
    try:
        payload = _load_payload()

        stdout_path = Path(
            payload["stdout_path"]
        )
        stderr_path = Path(
            payload["stderr_path"]
        )

        stdout_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        stderr_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        job = create_named_kill_on_close_job(
            name=payload["job_name"],
        )

        with open(
            os.devnull,
            "rb",
            buffering=0,
        ) as worker_stdin, stdout_path.open(
            "ab",
            buffering=0,
        ) as worker_stdout, stderr_path.open(
            "ab",
            buffering=0,
        ) as worker_stderr:
            stdin_handle = _os_handle(
                worker_stdin
            )
            stdout_handle = _os_handle(
                worker_stdout
            )
            stderr_handle = _os_handle(
                worker_stderr
            )

            if payload["low_integrity_execution"]:
                if not payload["restricted_execution"]:
                    raise RuntimeError(
                        "windows_job_broker_low_integrity_requires_restricted_execution"
                    )
                proc = (
                    spawn_low_integrity_restricted_suspended_in_job(
                        payload["command"],
                        cwd=payload["cwd"],
                        env=payload["env"],
                        job=job,
                        stdin_handle=stdin_handle,
                        stdout_handle=stdout_handle,
                        stderr_handle=stderr_handle,
                    )
                )
            elif payload["restricted_execution"]:
                proc = (
                    spawn_restricted_suspended_in_job(
                        payload["command"],
                        cwd=payload["cwd"],
                        env=payload["env"],
                        job=job,
                        stdin_handle=stdin_handle,
                        stdout_handle=stdout_handle,
                        stderr_handle=stderr_handle,
                    )
                )
            else:
                proc = spawn_suspended_in_job(
                    payload["command"],
                    cwd=payload["cwd"],
                    env=payload["env"],
                    job=job,
                    stdin_handle=stdin_handle,
                    stdout_handle=stdout_handle,
                    stderr_handle=stderr_handle,
                )

        record = _ready_record(
            job_id=payload["job_id"],
            job_name=payload["job_name"],
            worker_pid=proc.pid,
            restricted_execution=payload[
                "restricted_execution"
            ],
            low_integrity_execution=payload[
                "low_integrity_execution"
            ],
        )

        ready_path = payload.get(
            "ready_path"
        )
        if ready_path:
            _write_json_atomic(
                Path(ready_path),
                record,
            )

        sys.stdout.write(
            json.dumps(
                record,
                sort_keys=True,
            )
            + "\n"
        )
        sys.stdout.flush()

        while True:
            active = (
                named_job_active_process_count(
                    payload["job_name"]
                )
            )

            if active is None:
                raise WindowsProcessTreeError(
                    "windows_job_broker_job_disappeared"
                )

            if active == 0:
                worker_exit_code = proc.poll()
                if worker_exit_code is None:
                    worker_exit_code = proc.wait(
                        timeout=1.0
                    )

                completion_path = payload.get(
                    "completion_path"
                )
                if completion_path:
                    _write_json_atomic(
                        Path(completion_path),
                        {
                            "ok": True,
                            "state": "drained",
                            "job_id": payload[
                                "job_id"
                            ],
                            "job_name": payload[
                                "job_name"
                            ],
                            "broker_pid": os.getpid(),
                            "worker_pid": proc.pid,
                            "worker_exit_code": int(
                                worker_exit_code
                            ),
                            "process_tree_drained": True,
                            "containment_scope": (
                                CONTAINMENT_SCOPE
                            ),
                            "broker_profile": (
                                BROKER_PROFILE
                            ),
                            "restricted_execution": payload[
                                "restricted_execution"
                            ],
                            "restricted_execution_profile": (
                                RESTRICTED_TOKEN_PROFILE
                                if payload[
                                    "restricted_execution"
                                ]
                                else None
                            ),
                            "restricted_token_verified": payload[
                                "restricted_execution"
                            ],
                            "restricted_token_attested": False,
                            "low_integrity_execution": payload[
                                "low_integrity_execution"
                            ],
                            "low_integrity_profile": (
                                LOW_INTEGRITY_PROFILE
                                if payload[
                                    "low_integrity_execution"
                                ]
                                else None
                            ),
                            "low_integrity_token_verified": payload[
                                "low_integrity_execution"
                            ],
                            "sandbox_low_integrity_boundary_required": payload[
                                "low_integrity_execution"
                            ],
                            "low_integrity_attested": False,
                            "drained_at": _utc_now(),
                        },
                    )
                break

            time.sleep(0.1)

        proc.close()
        proc = None
        job = None
        return 0

    except Exception as exc:
        return _fail(
            f"{type(exc).__name__}: {exc}"
        )

    finally:
        if proc is not None:
            try:
                proc.close()
            except Exception:
                pass
        elif job is not None:
            try:
                job.close()
            except Exception:
                pass

def main() -> None:
    raise SystemExit(
        run_broker()
    )


if __name__ == "__main__":
    main()
