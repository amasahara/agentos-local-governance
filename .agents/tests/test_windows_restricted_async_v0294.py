
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from agentos.enforcement_attestation import (
    attest_enforcement,
)
from agentos.tool_runtime_profiles import (
    build_runtime_environment,
    cleanup_sandbox_workspace,
    create_sandbox_workspace,
)


ROOT = Path(__file__).resolve().parents[2]


def _policy_section() -> dict:
    policy = json.loads(
        (
            ROOT
            / ".agents/config/release_policy.json"
        ).read_text(
            encoding="utf-8"
        )
    )
    return policy[
        "windows_restricted_execution_policy"
    ]



def test_v0294_phase3_policy_progresses_to_scoped_release_activation():
    section = _policy_section()

    assert section["sync_execution_enforced"] is True
    assert section["async_execution_enforced"] is True

    for key in (
        "async_broker_restricted_worker_required",
        "async_payload_requires_restricted_execution",
        "async_ready_requires_restricted_token_verification",
        "async_create_suspended_required",
        "async_job_assignment_before_resume_required",
        "async_fail_closed_without_unrestricted_worker_fallback",
    ):
        assert section[key] is True

    assert section["restricted_token_attested"] is True
    assert section["low_integrity_attested"] is False

def test_v0294_phase3_production_jobs_require_restricted_ready_evidence():
    source = (
        ROOT / ".agents/agentos/jobs.py"
    ).read_text(
        encoding="utf-8"
    )
    start = source.index(
        "def _launch_windows_job_broker("
    )
    end = source.index(
        "def _job_dir(",
        start,
    )
    helper = source[start:end]

    assert (
        '"restricted_execution": True'
        in helper
    )
    assert (
        '"restricted_token_verified"'
        in helper
    )
    assert (
        '"assigned_before_resume"'
        in helper
    )
    assert "subprocess.Popen(" in helper
    assert "agentos.windows_job_broker" in helper
    assert "shell=False" in helper


def test_v0294_phase3_broker_restricted_mode_uses_restricted_worker():
    source = (
        ROOT
        / ".agents/agentos/windows_job_broker.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "spawn_restricted_suspended_in_job"
        in source
    )
    assert "spawn_suspended_in_job" in source
    assert (
        'payload["restricted_execution"]'
        in source
    )
    assert (
        '"restricted_token_verified"'
        in source
    )
    assert (
        '"restricted_token_attested": False'
        in source
    )
    assert (
        '"low_integrity_attested": False'
        in source
    )


def test_v0294_phase3_restricted_worker_keeps_verify_assign_resume_order():
    source = (
        ROOT
        / ".agents/agentos/windows_restricted_execution.py"
    ).read_text(
        encoding="utf-8"
    )
    start = source.index(
        "def spawn_restricted_suspended_in_job("
    )
    body = source[start:]

    create = body.index(
        "advapi32.CreateProcessAsUserW("
    )
    verify = body.index(
        "_verify_child_process_token("
    )
    assign = body.index(
        "job.assign_process_handle("
    )
    resume = body.index(
        "kernel32.ResumeThread("
    )

    assert create < verify < assign < resume
    assert "CREATE_SUSPENDED" in body
    assert "CreateProcessW(" not in body


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows async restricted worker runtime",
)
def test_v0294_phase3_real_broker_restricted_worker_can_use_agentos_sandbox(
    tmp_path,
):
    from agentos.windows_process_tree import (
        async_job_object_name,
    )

    source = tmp_path / "source"
    source.mkdir()
    (source / "input.txt").write_text(
        "restricted-async-ok",
        encoding="utf-8",
        newline="\n",
    )

    job_id = (
        "v0294phase3"
        + uuid.uuid4().hex[:12]
    )

    sandbox = create_sandbox_workspace(
        ROOT,
        source,
        "v0294-phase3",
        "restricted-async",
        job_id,
        "test",
    )
    workspace = Path(
        sandbox["workspace"]
    )
    runtime_env = build_runtime_environment(
        dict(os.environ),
        sandbox,
    )

    stdout_path = (
        tmp_path / "worker.stdout.log"
    )
    stderr_path = (
        tmp_path / "worker.stderr.log"
    )
    ready_path = (
        tmp_path / "worker.ready.json"
    )
    completion_path = (
        tmp_path / "worker.completion.json"
    )

    worker_code = (
        "from pathlib import Path;"
        "value=Path('input.txt').read_text(encoding='utf-8');"
        "Path('async-restricted-write.txt').write_text(value,encoding='utf-8');"
        "print(value)"
    )

    payload = {
        "job_id": job_id,
        "job_name": async_job_object_name(
            job_id
        ),
        "command": [
            sys.executable,
            "-c",
            worker_code,
        ],
        "cwd": str(workspace),
        "env": runtime_env,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "ready_path": str(ready_path),
        "completion_path": str(
            completion_path
        ),
        "restricted_execution": True,
    }

    broker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agentos.windows_job_broker",
        ],
        cwd=ROOT,
        env=dict(os.environ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )

    try:
        assert broker.stdin is not None
        assert broker.stdout is not None
        assert broker.stderr is not None

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
            raise AssertionError(
                "restricted broker did not produce READY: "
                + broker.stderr.read()
            )

        ready = json.loads(
            ready_line
        )

        assert ready["ok"] is True
        assert (
            ready["restricted_execution"]
            is True
        )
        assert (
            ready["restricted_token_verified"]
            is True
        )
        assert (
            ready["restricted_token_attested"]
            is False
        )
        assert (
            ready["low_integrity_attested"]
            is False
        )
        assert (
            ready["assigned_before_resume"]
            is True
        )

        broker.wait(timeout=15)
        assert broker.returncode == 0, (
            broker.stderr.read()
        )

        deadline = time.monotonic() + 5
        while (
            time.monotonic() < deadline
            and not completion_path.exists()
        ):
            time.sleep(0.05)

        completion = json.loads(
            completion_path.read_text(
                encoding="utf-8"
            )
        )

        assert (
            completion[
                "restricted_execution"
            ]
            is True
        )
        assert (
            completion[
                "restricted_token_verified"
            ]
            is True
        )
        assert (
            completion[
                "worker_exit_code"
            ]
            == 0
        )

        assert (
            workspace
            / "async-restricted-write.txt"
        ).read_text(
            encoding="utf-8"
        ) == "restricted-async-ok"

        assert (
            "restricted-async-ok"
            in stdout_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

    finally:
        if broker.poll() is None:
            broker.terminate()
            try:
                broker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                broker.kill()
                broker.wait(timeout=5)

        cleanup_sandbox_workspace(
            ROOT,
            Path(sandbox["root"]),
        )


def test_v0294_phase3_inherited_process_tree_attestation_remains_green():
    report = attest_enforcement(ROOT)
    assert report["ok"], report[
        "findings"
    ]
    assert (
        report[
            "windows_process_tree_containment"
        ]["async_enforced"]
        is True
    )



def test_v0294_phase3_scoped_claim_preserves_broad_nonclaims():
    section = _policy_section()

    assert section["restricted_token_attested"] is True

    for key in (
        "low_integrity_attested",
        "desktop_isolation_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    ):
        assert section[key] is False


def test_v0294_phase3_identity_and_schema_progress_to_release():
    assert tuple(int(part) for part in (ROOT / "VERSION").read_text(encoding="utf-8").strip().split(".")) >= (0, 29, 5)
    from agentos import __version__
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert CURRENT_SCHEMA_VERSION >= 62
