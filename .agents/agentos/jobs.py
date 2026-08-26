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

_FINAL = {"succeeded", "failed", "cancelled", "timed_out"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            kwargs["start_new_session"] = True

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
        except Exception:
            stdout.close()
            stderr.close()
            raise

        c.execute(
            "UPDATE async_jobs "
            "SET state='running',pid=?,started_at=? "
            "WHERE job_id=?",
            (
                proc.pid,
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
                        "pid": proc.pid,
                        "spec_hash": row["spec_hash"],
                    }
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


def job_status(root: Path, job_id: str) -> dict[str, Any]:
    """Poll one job and materialize terminal state when possible.

    Args:
        root: Governed project root.
        job_id: Job identifier.

    Returns:
        Current job record and output summaries.
    """
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM async_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise RuntimeError("job not found")
        state = row["state"]
        if state == "running" and row["pid"] and not _pid_alive(int(row["pid"])):
            state = "succeeded"
            c.execute("UPDATE async_jobs SET state=?,exit_code=0,finished_at=? WHERE job_id=?", (state, _now(), job_id))
            c.execute("INSERT INTO job_events(job_id,event_type,details_json) VALUES(?,?,?)", (job_id, state, "{}"))
        row = c.execute("SELECT * FROM async_jobs WHERE job_id=?", (job_id,)).fetchone()
    result = dict(row)
    for field in ("stdout_path", "stderr_path"):
        path = Path(result[field])
        result[field.replace("_path", "_tail")] = path.read_text(encoding="utf-8", errors="replace")[-4000:] if path.exists() else ""
    result["spec"] = json.loads(result.pop("spec_json"))
    return result


def cancel_job(root: Path, job_id: str, requested_by: str, reason: str) -> dict[str, Any]:
    """Cancel a queued or running job and record signed evidence."""
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM async_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise RuntimeError("job not found")
        if row["state"] in _FINAL:
            return dict(row)
        if row["pid"]:
            try:
                if os.name == "posix": os.killpg(int(row["pid"]), signal.SIGTERM)
                else: os.kill(int(row["pid"]), signal.SIGTERM)
            except OSError:
                pass
        c.execute("UPDATE async_jobs SET state='cancelled',finished_at=?,cancel_reason=? WHERE job_id=?", (_now(), reason, job_id))
        c.execute("INSERT INTO job_events(job_id,event_type,details_json) VALUES(?,?,?)", (job_id, "cancelled", json.dumps({"requested_by": requested_by, "reason": reason})))
    event = append_signed_event(root, "job.cancelled", {"job_id": job_id, "requested_by": requested_by, "reason": reason}, row["task_id"], row["session_id"])
    return {**job_status(root, job_id), "cancellation_event_hash": event["event_hash"]}


def recover_jobs(root: Path) -> dict[str, Any]:
    """Mark running jobs with missing processes as orphaned for operator review."""
    recovered: list[str] = []
    with connect(root, immediate=True) as c:
        rows = c.execute("SELECT job_id,pid FROM async_jobs WHERE state='running'").fetchall()
        for row in rows:
            if not row["pid"] or not _pid_alive(int(row["pid"])):
                c.execute("UPDATE async_jobs SET state='orphaned',finished_at=? WHERE job_id=?", (_now(), row["job_id"]))
                c.execute("INSERT INTO job_events(job_id,event_type,details_json) VALUES(?,?,?)", (row["job_id"], "orphaned", "{}"))
                recovered.append(row["job_id"])
    return {"ok": True, "orphaned_jobs": recovered, "count": len(recovered)}


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
