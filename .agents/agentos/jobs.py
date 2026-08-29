"""
File: .agents/agentos/jobs.py

Purpose:
    Provide the governed asynchronous execution runtime for AgentOS v0.16.0.

Responsibilities:
    - Persist immutable job specifications and lifecycle transitions.
    - Launch allowlisted commands without blocking the caller.
    - Poll, cancel, recover, and audit asynchronous jobs.
    - Discover tools according to the current workflow state.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timedelta, timezone
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect
from .external_audit import append_signed_event
from .proxy import _command_profile, _filtered_env, _inside, _isolated_workspace, _scan_agentos_imports
from .policy import load_policy
from .tooling import validate_execution_token
from .workflow import workflow_status
from .windows_process_tree import (
    async_job_object_name,
    named_job_active_process_count,
    terminate_named_job,
)

_FINAL = {"succeeded", "failed", "cancelled", "timed_out"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()



def _is_windows_host() -> bool:
    return os.name == "nt"


def _windows_broker_ready_path(
    root: Path,
    job_id: str,
) -> Path:
    return (
        _job_dir(root, job_id)
        / "windows-broker-ready.json"
    )


def _windows_broker_completion_path(
    root: Path,
    job_id: str,
) -> Path:
    return (
        _job_dir(root, job_id)
        / "windows-broker-completion.json"
    )


def _windows_broker_error_path(
    root: Path,
    job_id: str,
) -> Path:
    return (
        _job_dir(root, job_id)
        / "windows-broker.stderr.log"
    )


def _read_json_object(
    path: Path,
) -> dict[str, Any] | None:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
    ):
        return None

    return (
        value
        if isinstance(value, dict)
        else None
    )


def _windows_completion_record(
    root: Path,
    job_id: str,
) -> dict[str, Any] | None:
    record = _read_json_object(
        _windows_broker_completion_path(
            root,
            job_id,
        )
    )

    if not record:
        return None

    if (
        record.get("state") != "drained"
        or record.get("job_id") != job_id
        or record.get("job_name")
        != async_job_object_name(job_id)
    ):
        return None

    return record


def _windows_broker_environment(
    root: Path,
) -> dict[str, str]:
    env = dict(os.environ)

    agent_root = str(
        (root / ".agents").resolve()
    )

    existing = env.get(
        "PYTHONPATH",
        "",
    )

    env["PYTHONPATH"] = (
        agent_root
        if not existing
        else agent_root
        + os.pathsep
        + existing
    )

    return env


def _launch_windows_job_broker(
    root: Path,
    job_id: str,
    spec: dict[str, Any],
    launch_env: dict[str, str],
    stdout_path: str,
    stderr_path: str,
    *,
    ready_timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    job_name = async_job_object_name(
        job_id
    )

    ready_path = (
        _windows_broker_ready_path(
            root,
            job_id,
        )
    )
    completion_path = (
        _windows_broker_completion_path(
            root,
            job_id,
        )
    )
    error_path = (
        _windows_broker_error_path(
            root,
            job_id,
        )
    )

    for path in (
        ready_path,
        completion_path,
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    payload = {
        "job_id": job_id,
        "job_name": job_name,
        "command": list(
            spec["command"]
        ),
        "cwd": str(
            spec["workspace"]
        ),
        "env": dict(
            launch_env
        ),
        "stdout_path": str(
            stdout_path
        ),
        "stderr_path": str(
            stderr_path
        ),
        "ready_path": str(
            ready_path
        ),
        "completion_path": str(
            completion_path
        ),
    }

    broker_stderr = error_path.open(
        "ab",
        buffering=0,
    )

    broker = None

    try:
        broker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agentos.windows_job_broker",
            ],
            cwd=root,
            env=_windows_broker_environment(
                root
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=broker_stderr,
            text=True,
            encoding="utf-8",
            shell=False,
        )

        if broker.stdin is None:
            raise RuntimeError(
                "windows_job_broker_stdin_unavailable"
            )

        broker.stdin.write(
            json.dumps(
                payload,
                sort_keys=True,
            )
            + "\n"
        )
        broker.stdin.flush()
        broker.stdin.close()

        deadline = (
            time.monotonic()
            + float(
                ready_timeout_seconds
            )
        )

        while time.monotonic() < deadline:
            ready = _read_json_object(
                ready_path
            )

            if ready is not None:
                if (
                    ready.get("ok") is not True
                    or ready.get("state")
                    != "ready"
                    or ready.get("job_id")
                    != job_id
                    or ready.get("job_name")
                    != job_name
                    or int(
                        ready.get(
                            "broker_pid",
                            0,
                        )
                    )
                    != int(broker.pid)
                ):
                    raise RuntimeError(
                        "windows_job_broker_invalid_ready_record"
                    )

                return ready

            code = broker.poll()

            if code is not None:
                try:
                    error = error_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )[-4000:]
                except OSError:
                    error = ""

                raise RuntimeError(
                    "windows_job_broker_start_failed"
                    + (
                        ": " + error.strip()
                        if error.strip()
                        else ""
                    )
                )

            time.sleep(0.05)

        broker.terminate()

        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
            broker.wait(timeout=5)

        raise RuntimeError(
            "windows_job_broker_ready_timeout"
        )

    except Exception:
        if (
            broker is not None
            and broker.poll() is None
        ):
            try:
                broker.terminate()
                broker.wait(timeout=5)
            except Exception:
                try:
                    broker.kill()
                except Exception:
                    pass
        raise

    finally:
        broker_stderr.close()


def _job_dir(root: Path, job_id: str) -> Path:
    path = root / ".agents" / "runtime" / "jobs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def submit_job(
    root: Path,
    task_id: str,
    session_id: str,
    command: list[str],
    cwd: str = ".",
    timeout_seconds: int = 900,
    env: dict[str, Any] | None = None,
    auto_start: bool = True,
    *,
    execution_token: str,
) -> dict[str, Any]:
    """Create an immutable governed job and optionally start it.

    Args:
        root: Governed project root.
        task_id: Owning task identifier.
        session_id: Owning session identifier.
        command: Allowlisted executable and arguments.
        cwd: Project-relative working directory.
        timeout_seconds: Maximum job runtime.
        env: Optional non-sensitive environment additions.
        auto_start: Whether to launch immediately.

    Returns:
        Serialized job status.
    """
    guarded_args = {
        "command": list(command),
        "cwd": cwd,
        "timeout": int(timeout_seconds),
        "env": env or {},
        "auto_start": bool(auto_start),
    }

    validate_execution_token(
        root,
        execution_token,
        task_id,
        session_id,
        "shell_local",
        guarded_args,
    )

    policy = load_policy(root)
    profile = _command_profile(command, policy)
    source_cwd = _inside(root, cwd)
    _scan_agentos_imports(root, command, source_cwd)
    workspace = _isolated_workspace(root, task_id, source_cwd)
    job_id = uuid.uuid4().hex
    job_path = _job_dir(root, job_id)
    stdout_path = job_path / "stdout.log"
    stderr_path = job_path / "stderr.log"
    clean_env = _filtered_env(env)
    spec = {
        "job_id": job_id,
        "task_id": task_id,
        "session_id": session_id,
        "command": command,
        "cwd": cwd,
        "workspace": str(workspace),
        "timeout_seconds": int(timeout_seconds),
        "profile": profile,
        "network_policy": "none",
        "environment_hash": hashlib.sha256(json.dumps(clean_env, sort_keys=True).encode()).hexdigest(),
    }
    spec_hash = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with connect(root) as c:
        c.execute("INSERT INTO async_jobs(job_id,task_id,session_id,spec_json,spec_hash,state,timeout_seconds,stdout_path,stderr_path,created_at) VALUES(?,?,?,?,?,'queued',?,?,?,?)", (job_id, task_id, session_id, json.dumps(spec, sort_keys=True), spec_hash, int(timeout_seconds), str(stdout_path), str(stderr_path), _now()))
        c.execute("INSERT INTO job_events(job_id,event_type,details_json) VALUES(?,?,?)", (job_id, "queued", json.dumps({"spec_hash": spec_hash})))
    event = append_signed_event(root, "job.queued", {"job_id": job_id, "spec_hash": spec_hash}, task_id, session_id)
    with connect(root) as c:
        c.execute("UPDATE async_jobs SET external_event_hash=? WHERE job_id=?", (event["event_hash"], job_id))
    return (
        start_job(
            root,
            job_id,
            execution_token=execution_token,
            guarded_args=guarded_args,
        )
        if auto_start
        else job_status(root, job_id)
    )


def start_job(
    root: Path,
    job_id: str,
    *,
    execution_token: str,
    guarded_args: dict[str, Any],
) -> dict[str, Any]:
    """Launch a queued asynchronous job under guarded authority.

    The actual subprocess side effect is allowed only while the
    original execution token is still valid and bound to the
    immutable queued job specification.

    Deferred queued jobs require a future newly-guarded start
    operation; a token created for ``auto_start=False`` cannot
    launch a process.
    """
    with connect(root, immediate=True) as c:
        row = c.execute(
            "SELECT * FROM async_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()

        if not row:
            raise RuntimeError("job not found")

        if row["state"] != "queued":
            return dict(row)

        spec = json.loads(row["spec_json"])

        # Re-validate immediately before the actual process
        # side effect. complete_tool() consumes this token only
        # after submit_job/start_job returns to the proxy.
        validate_execution_token(
            root,
            execution_token,
            row["task_id"],
            row["session_id"],
            "shell_local",
            guarded_args,
        )

        if guarded_args.get("auto_start") is not True:
            raise RuntimeError(
                "queued job requires a new guarded start operation"
            )

        expected_command = list(
            guarded_args.get("command") or []
        )

        if spec.get("command") != expected_command:
            raise RuntimeError(
                "queued job command does not match guarded arguments"
            )

        if spec.get("cwd") != guarded_args.get("cwd"):
            raise RuntimeError(
                "queued job cwd does not match guarded arguments"
            )

        if int(spec.get("timeout_seconds", 0)) != int(
            guarded_args.get("timeout", 0)
        ):
            raise RuntimeError(
                "queued job timeout does not match guarded arguments"
            )

        # Rebuild the launch environment from guarded input.
        # start_job no longer accepts caller-supplied clean_env.
        launch_env = _filtered_env(
            guarded_args.get("env") or {}
        )

        environment_hash = hashlib.sha256(
            json.dumps(
                launch_env,
                sort_keys=True,
            ).encode()
        ).hexdigest()

        if spec.get("environment_hash") != environment_hash:
            raise RuntimeError(
                "queued job environment does not match guarded arguments"
            )

        # Detect modification of the immutable queued job spec.
        actual_spec_hash = hashlib.sha256(
            json.dumps(
                spec,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        if actual_spec_hash != row["spec_hash"]:
            raise RuntimeError(
                "queued job specification hash mismatch"
            )

        containment_details: dict[str, Any] = {}

        if _is_windows_host():
            ready = _launch_windows_job_broker(
                root,
                job_id,
                spec,
                launch_env,
                row["stdout_path"],
                row["stderr_path"],
            )

            pid = int(
                ready["worker_pid"]
            )

            containment_details = {
                "process_tree_contained": True,
                "process_tree_containment_profile": (
                    ready["broker_profile"]
                ),
                "process_tree_containment_scope": (
                    ready["containment_scope"]
                ),
                "process_tree_job_name": (
                    ready["job_name"]
                ),
                "broker_pid": int(
                    ready["broker_pid"]
                ),
                "assigned_before_resume": bool(
                    ready[
                        "assigned_before_resume"
                    ]
                ),
                "kill_on_broker_exit": bool(
                    ready[
                        "kill_on_broker_exit"
                    ]
                ),
            }
        else:
            stdout = open(
                row["stdout_path"],
                "ab",
                buffering=0,
            )
            stderr = open(
                row["stderr_path"],
                "ab",
                buffering=0,
            )

            kwargs: dict[str, Any] = {}

            if os.name == "posix":
                kwargs[
                    "start_new_session"
                ] = True

            try:
                proc = subprocess.Popen(
                    spec["command"],
                    cwd=spec["workspace"],
                    env=launch_env,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    **kwargs,
                )
                pid = int(proc.pid)
            finally:
                stdout.close()
                stderr.close()

        c.execute(
            "UPDATE async_jobs "
            "SET state='running',pid=?,started_at=? "
            "WHERE job_id=?",
            (
                pid,
                _now(),
                job_id,
            ),
        )

        c.execute(
            "INSERT INTO job_events("
            "job_id,event_type,details_json"
            ") VALUES(?,?,?)",
            (
                job_id,
                "running",
                json.dumps(
                    {
                        "pid": pid,
                        "spec_hash": row["spec_hash"],
                        **containment_details,
                    },
                    sort_keys=True,
                ),
            ),
        )

    return job_status(root, job_id)

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False



def _parse_job_timestamp(
    value: Any,
) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.endswith("Z"):
        text = (
            text[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            text
        )
    except ValueError:
        try:
            parsed = datetime.strptime(
                text,
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _job_timeout_evidence(
    row: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    started_at = _parse_job_timestamp(
        row["started_at"]
    )

    timeout_seconds = int(
        row["timeout_seconds"]
    )

    if (
        started_at is None
        or timeout_seconds <= 0
    ):
        return None

    current = (
        now
        if now is not None
        else datetime.now(
            timezone.utc
        )
    )

    if current.tzinfo is None:
        current = current.replace(
            tzinfo=timezone.utc
        )

    current = current.astimezone(
        timezone.utc
    )

    deadline = (
        started_at
        + timedelta(
            seconds=timeout_seconds
        )
    )

    if current < deadline:
        return None

    return {
        "started_at": (
            started_at.isoformat()
        ),
        "deadline": (
            deadline.isoformat()
        ),
        "observed_at": (
            current.isoformat()
        ),
        "timeout_seconds": (
            timeout_seconds
        ),
    }


def _materialize_windows_completion(
    c,
    row: Any,
    completion: dict[str, Any],
) -> str:
    exit_code = int(
        completion.get(
            "worker_exit_code",
            0,
        )
    )

    state = (
        "succeeded"
        if exit_code == 0
        else "failed"
    )

    c.execute(
        "UPDATE async_jobs "
        "SET state=?,exit_code=?,finished_at=? "
        "WHERE job_id=?",
        (
            state,
            exit_code,
            completion.get(
                "drained_at"
            )
            or _now(),
            row["job_id"],
        ),
    )

    c.execute(
        "INSERT INTO job_events("
        "job_id,event_type,details_json"
        ") VALUES(?,?,?)",
        (
            row["job_id"],
            state,
            json.dumps(
                {
                    "completion_source": (
                        "windows_job_broker"
                    ),
                    "worker_exit_code": (
                        exit_code
                    ),
                    "process_tree_drained": bool(
                        completion.get(
                            "process_tree_drained",
                            True,
                        )
                    ),
                    "job_name": (
                        async_job_object_name(
                            row["job_id"]
                        )
                    ),
                },
                sort_keys=True,
            ),
        ),
    )

    return state


def _materialize_windows_timeout(
    c,
    row: Any,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    job_name = async_job_object_name(
        row["job_id"]
    )

    terminated = terminate_named_job(
        job_name,
        124,
    )

    details = {
        **evidence,
        "job_name": job_name,
        "process_tree_terminated": (
            bool(terminated)
        ),
        "process_tree_containment_profile": (
            "windows_job_broker_kill_on_close_v1"
        ),
        "process_tree_containment_scope": (
            "agentos_mediated_process_execution"
        ),
    }

    c.execute(
        "UPDATE async_jobs "
        "SET state='timed_out',"
        "exit_code=124,finished_at=? "
        "WHERE job_id=?",
        (
            evidence["observed_at"],
            row["job_id"],
        ),
    )

    c.execute(
        "INSERT INTO job_events("
        "job_id,event_type,details_json"
        ") VALUES(?,?,?)",
        (
            row["job_id"],
            "timed_out",
            json.dumps(
                details,
                sort_keys=True,
            ),
        ),
    )

    return details


def job_status(root: Path, job_id: str) -> dict[str, Any]:
    """Poll one job and materialize terminal state when possible.

    On Windows, liveness is defined by the named Job Object owned by the
    AgentOS broker, not by the original worker PID. A broker completion
    receipt proves normal tree drain. Timeout wins over a missing broker
    when the persisted deadline has already expired.
    """
    active_processes = None
    timeout_details = None

    with connect(
        root,
        immediate=True,
    ) as c:
        row = c.execute(
            "SELECT * FROM async_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()

        if not row:
            raise RuntimeError(
                "job not found"
            )

        state = row["state"]

        if state == "running":
            if _is_windows_host():
                completion = (
                    _windows_completion_record(
                        root,
                        job_id,
                    )
                )

                active_processes = (
                    named_job_active_process_count(
                        async_job_object_name(
                            job_id
                        )
                    )
                )

                if completion is not None:
                    state = (
                        _materialize_windows_completion(
                            c,
                            row,
                            completion,
                        )
                    )
                else:
                    timeout_evidence = (
                        _job_timeout_evidence(
                            row
                        )
                    )

                    if timeout_evidence is not None:
                        timeout_details = (
                            _materialize_windows_timeout(
                                c,
                                row,
                                timeout_evidence,
                            )
                        )
                        state = "timed_out"
                        active_processes = 0
                    elif active_processes is None:
                        state = "orphaned"

                        c.execute(
                            "UPDATE async_jobs "
                            "SET state=?,finished_at=? "
                            "WHERE job_id=?",
                            (
                                state,
                                _now(),
                                job_id,
                            ),
                        )

                        c.execute(
                            "INSERT INTO job_events("
                            "job_id,event_type,details_json"
                            ") VALUES(?,?,?)",
                            (
                                job_id,
                                state,
                                json.dumps(
                                    {
                                        "reason": (
                                            "windows_job_broker_missing"
                                        ),
                                        "process_tree_contained": False,
                                    },
                                    sort_keys=True,
                                ),
                            ),
                        )
            elif (
                row["pid"]
                and not _pid_alive(
                    int(row["pid"])
                )
            ):
                state = "succeeded"

                c.execute(
                    "UPDATE async_jobs "
                    "SET state=?,exit_code=0,finished_at=? "
                    "WHERE job_id=?",
                    (
                        state,
                        _now(),
                        job_id,
                    ),
                )

                c.execute(
                    "INSERT INTO job_events("
                    "job_id,event_type,details_json"
                    ") VALUES(?,?,?)",
                    (
                        job_id,
                        state,
                        "{}",
                    ),
                )

        row = c.execute(
            "SELECT * FROM async_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()

    result = dict(row)

    if _is_windows_host():
        result[
            "process_tree_containment_profile"
        ] = "windows_job_broker_kill_on_close_v1"
        result[
            "process_tree_containment_scope"
        ] = "agentos_mediated_process_execution"
        result["process_tree_job_name"] = (
            async_job_object_name(job_id)
        )
        result["process_tree_contained"] = (
            bool(
                result.get("pid")
            )
            and result["state"]
            != "orphaned"
        )
        result[
            "process_tree_active_processes"
        ] = (
            active_processes
            if result["state"] == "running"
            else (
                0
                if result.get("pid")
                else None
            )
        )
        result[
            "process_tree_timeout_evidence"
        ] = timeout_details
    else:
        result[
            "process_tree_containment_profile"
        ] = None
        result[
            "process_tree_containment_scope"
        ] = None
        result["process_tree_job_name"] = None
        result["process_tree_contained"] = False
        result[
            "process_tree_active_processes"
        ] = None
        result[
            "process_tree_timeout_evidence"
        ] = None

    for field in (
        "stdout_path",
        "stderr_path",
    ):
        path = Path(
            result[field]
        )

        result[
            field.replace(
                "_path",
                "_tail",
            )
        ] = (
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )[-4000:]
            if path.exists()
            else ""
        )

    result["spec"] = json.loads(
        result.pop("spec_json")
    )

    return result


def cancel_job(root: Path, job_id: str, requested_by: str, reason: str) -> dict[str, Any]:
    """Cancel a queued or running job and record signed evidence."""
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM async_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise RuntimeError("job not found")
        if row["state"] in _FINAL:
            return dict(row)
        process_tree_terminated = None

        if row["pid"]:
            try:
                if _is_windows_host():
                    process_tree_terminated = (
                        terminate_named_job(
                            async_job_object_name(
                                job_id
                            ),
                            130,
                        )
                    )
                elif os.name == "posix":
                    os.killpg(
                        int(row["pid"]),
                        signal.SIGTERM,
                    )
                else:
                    os.kill(
                        int(row["pid"]),
                        signal.SIGTERM,
                    )
            except OSError:
                pass

        c.execute(
            "UPDATE async_jobs "
            "SET state='cancelled',finished_at=?,cancel_reason=? "
            "WHERE job_id=?",
            (
                _now(),
                reason,
                job_id,
            ),
        )
        c.execute(
            "INSERT INTO job_events("
            "job_id,event_type,details_json"
            ") VALUES(?,?,?)",
            (
                job_id,
                "cancelled",
                json.dumps(
                    {
                        "requested_by": requested_by,
                        "reason": reason,
                        "process_tree_terminated": (
                            process_tree_terminated
                        ),
                    },
                    sort_keys=True,
                ),
            ),
        )
    event = append_signed_event(root, "job.cancelled", {"job_id": job_id, "requested_by": requested_by, "reason": reason}, row["task_id"], row["session_id"])
    return {**job_status(root, job_id), "cancellation_event_hash": event["event_hash"]}


def recover_jobs(root: Path) -> dict[str, Any]:
    """Reconcile running jobs without weakening Windows containment."""
    recovered: list[str] = []
    timed_out: list[str] = []
    completed: list[str] = []

    with connect(
        root,
        immediate=True,
    ) as c:
        rows = c.execute(
            "SELECT * FROM async_jobs "
            "WHERE state='running'"
        ).fetchall()

        for row in rows:
            job_id = row["job_id"]

            if _is_windows_host():
                completion = (
                    _windows_completion_record(
                        root,
                        job_id,
                    )
                )

                if completion is not None:
                    _materialize_windows_completion(
                        c,
                        row,
                        completion,
                    )
                    completed.append(
                        job_id
                    )
                    continue

                timeout_evidence = (
                    _job_timeout_evidence(
                        row
                    )
                )

                if timeout_evidence is not None:
                    _materialize_windows_timeout(
                        c,
                        row,
                        timeout_evidence,
                    )
                    timed_out.append(
                        job_id
                    )
                    continue

                active = (
                    named_job_active_process_count(
                        async_job_object_name(
                            job_id
                        )
                    )
                )

                missing = (
                    active is None
                )
            else:
                missing = (
                    not row["pid"]
                    or not _pid_alive(
                        int(row["pid"])
                    )
                )

            if missing:
                c.execute(
                    "UPDATE async_jobs "
                    "SET state='orphaned',finished_at=? "
                    "WHERE job_id=?",
                    (
                        _now(),
                        job_id,
                    ),
                )

                c.execute(
                    "INSERT INTO job_events("
                    "job_id,event_type,details_json"
                    ") VALUES(?,?,?)",
                    (
                        job_id,
                        "orphaned",
                        json.dumps(
                            {
                                "reason": (
                                    "windows_job_broker_missing"
                                    if _is_windows_host()
                                    else "process_missing"
                                )
                            },
                            sort_keys=True,
                        ),
                    ),
                )

                recovered.append(
                    job_id
                )

    return {
        "ok": True,
        "orphaned_jobs": recovered,
        "timed_out_jobs": timed_out,
        "completed_jobs": completed,
        "count": len(recovered),
    }


def discover_tools(root: Path, task_id: str) -> dict[str, Any]:
    """Return workflow-aware tool availability groups."""
    status = workflow_status(root, task_id)
    pending = status["required_pending"]
    approved = not any(step == "approve_task" for step in pending)
    prepared = not any(step == "prepare_change" for step in pending)
    available = ["agentos.read_file", "agentos.task_status", "agentos.list_resources"]
    if approved:
        available += ["agentos.acquire_resource", "agentos.task_heartbeat"]
    if approved and prepared:
        available += ["agentos.write_file", "agentos.run_command", "agentos.run_command_async"]
    return {
        "available_now": sorted(set(available)),
        "available_after_step": {pending[0]: ["agentos.write_file", "agentos.run_command_async"]} if pending else {},
        "human_only": ["agentosctl.approve", "agentosctl.rotate_key", "agentosctl.revoke_session"],
        "blocked": [] if approved else [{"tool": "agentos.write_file", "reason": "task_not_approved"}],
    }
