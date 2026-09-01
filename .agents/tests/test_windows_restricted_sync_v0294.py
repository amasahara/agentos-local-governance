
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from agentos.enforcement_attestation import attest_enforcement
from agentos.proxy import _run_process_command
from agentos.windows_process_tree import run_contained_capture


ROOT = Path(__file__).resolve().parents[2]


CHILD_TOKEN_SCRIPT = r"""
import ctypes
import json
from ctypes import wintypes

TOKEN_QUERY = 0x0008
TokenType = 8
TokenSandBoxInert = 15
TokenHasRestrictions = 21

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

kernel32.GetCurrentProcess.argtypes = []
kernel32.GetCurrentProcess.restype = wintypes.HANDLE

advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
advapi32.OpenProcessToken.restype = wintypes.BOOL

advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
advapi32.GetTokenInformation.restype = wintypes.BOOL

token = wintypes.HANDLE()
if not advapi32.OpenProcessToken(
    kernel32.GetCurrentProcess(),
    TOKEN_QUERY,
    ctypes.byref(token),
):
    raise SystemExit(91)

def q(info_class):
    value = wintypes.DWORD()
    returned = wintypes.DWORD()
    if not advapi32.GetTokenInformation(
        token,
        info_class,
        ctypes.byref(value),
        ctypes.sizeof(value),
        ctypes.byref(returned),
    ):
        raise SystemExit(92)
    return int(value.value)

print(json.dumps({
    "token_type": q(TokenType),
    "token_has_restrictions": bool(q(TokenHasRestrictions)),
    "sandbox_inert": bool(q(TokenSandBoxInert)),
}, sort_keys=True))
"""


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


def _assert_child_restricted(stdout: str) -> None:
    value = json.loads(stdout.strip())
    assert value["token_type"] == 1
    assert value["token_has_restrictions"] is True
    assert value["sandbox_inert"] is False




def test_v0294_phase2_policy_progresses_to_scoped_release_activation():
    section = _policy_section()

    assert section["sync_execution_enforced"] is True
    assert section["async_execution_enforced"] is True

    for key in (
        "sync_launch_uses_create_process_as_user",
        "sync_child_token_verification_required",
        "sync_create_suspended_required",
        "sync_job_assignment_before_resume_required",
        "sync_fail_closed_without_unrestricted_fallback",
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

def test_v0294_phase2_restricted_spawn_orders_verification_containment_resume():
    source = (
        ROOT
        / ".agents/agentos/windows_restricted_execution.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def spawn_restricted_suspended_in_job("
    )
    source = source[start:]

    create = source.index(
        "advapi32.CreateProcessAsUserW("
    )
    child_verify = source.index(
        "_verify_child_process_token("
    )
    assign = source.index(
        "job.assign_process_handle("
    )
    resume = source.index(
        "kernel32.ResumeThread("
    )

    assert create < child_verify < assign < resume
    assert "CREATE_SUSPENDED" in source
    assert "CreateProcessW(" not in source




def test_v0294_phase2_keeps_legacy_job_helper_and_adds_restricted_production_wrapper():
    tree = (
        ROOT
        / ".agents/agentos/windows_process_tree.py"
    ).read_text(encoding="utf-8")
    restricted = (
        ROOT
        / ".agents/agentos/windows_restricted_execution.py"
    ).read_text(encoding="utf-8")

    legacy_start = tree.index(
        "def run_contained_capture("
    )
    legacy_end = tree.index(
        "def async_job_object_name(",
        legacy_start,
    )
    legacy = tree[
        legacy_start:legacy_end
    ]

    assert "spawn_suspended_in_job(" in legacy
    assert (
        "spawn_restricted_suspended_in_job("
        not in legacy
    )
    assert "terminate_tree(" in legacy
    assert "subprocess.TimeoutExpired(" in legacy

    start = restricted.index(
        "def run_restricted_contained_capture("
    )
    current = restricted[start:]

    assert (
        "spawn_restricted_suspended_in_job("
        in current
    )
    assert "spawn_suspended_in_job(" not in current
    assert "terminate_tree(" in current
    assert "subprocess.TimeoutExpired(" in current
    assert "proc.close()" in current


def test_v0294_phase2_proxy_selects_canonical_restricted_sync_execution():
    source = (
        ROOT
        / ".agents/agentos/proxy.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def _run_process_command("
    )
    end = source.index(
        "def _credential_safe_environment_hash(",
        start,
    )
    source = source[start:end]

    assert (
        "run_restricted_contained_capture("
        in source
    )
    assert '"restricted_execution": True' in source
    assert '"restricted_token_verified": True' in source

    posix_return = source.rsplit(
        "return result, {",
        1,
    )[1]
    assert (
        '"restricted_execution"'
        not in posix_return
    )
    assert (
        '"restricted_token_verified"'
        not in posix_return
    )


def test_v0294_phase2_async_path_progresses_to_restricted_broker_worker():
    broker = (
        ROOT
        / ".agents/agentos/windows_job_broker.py"
    ).read_text(
        encoding="utf-8"
    )
    jobs = (
        ROOT
        / ".agents/agentos/jobs.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "spawn_restricted_suspended_in_job"
        in broker
    )
    assert (
        'payload["restricted_execution"]'
        in broker
    )
    assert (
        '"restricted_execution": True'
        in jobs
    )

    # Broker remains trusted AgentOS lifecycle owner.
    assert "subprocess.Popen(" in jobs
    assert "agentos.windows_job_broker" in jobs

@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows synchronous restricted execution",
)

@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows synchronous restricted execution",
)

@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows synchronous restricted execution",
)
def test_v0294_phase2_direct_sync_child_is_restricted():
    from agentos.windows_restricted_execution import (
        run_restricted_contained_capture,
    )

    result = run_restricted_contained_capture(
        [
            sys.executable,
            "-c",
            CHILD_TOKEN_SCRIPT,
        ],
        cwd=ROOT,
        env=dict(os.environ),
        timeout=15,
    )

    assert result.returncode == 0
    _assert_child_restricted(result.stdout)

@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows proxy synchronous restricted execution",
)
def test_v0294_phase2_proxy_child_is_restricted():
    result, metadata = _run_process_command(
        [
            sys.executable,
            "-c",
            CHILD_TOKEN_SCRIPT,
        ],
        cwd=ROOT,
        env=dict(os.environ),
        timeout=15,
    )

    assert result.returncode == 0
    _assert_child_restricted(result.stdout)

    assert metadata["process_tree_contained"] is True
    assert metadata["restricted_execution"] is True
    assert metadata["restricted_token_verified"] is True
    assert metadata["restricted_token_attested"] is False
    assert metadata["low_integrity_attested"] is False


def test_v0294_phase2_inherited_v0291_attestation_remains_green():
    report = attest_enforcement(ROOT)

    assert report["ok"], report["findings"]

    containment = report[
        "windows_process_tree_containment"
    ]
    assert containment["structurally_attested"] is True
    assert containment["sync_enforced"] is True



def test_v0294_phase2_identity_and_schema_progress_to_release():
    assert (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip() == "0.29.4"

    from agentos import __version__
    from agentos.schema_version import CURRENT_SCHEMA_VERSION

    assert __version__ == "0.29.4"
    assert CURRENT_SCHEMA_VERSION == 62

@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows restricted execution sandbox access",
)
def test_v0294_phase2_restricted_process_can_read_and_write_real_agentos_sandbox(tmp_path):
    """
    Prove the restricted production runner can use the actual v0.29.2
    external sandbox layout. This intentionally does not require access to
    pytest's updater temp directory from the restricted child.
    """
    import uuid

    from agentos.tool_runtime_profiles import (
        build_runtime_environment,
        cleanup_sandbox_workspace,
        create_sandbox_workspace,
    )
    from agentos.windows_restricted_execution import (
        run_restricted_contained_capture,
    )

    source = tmp_path / "sandbox-source"
    source.mkdir()
    script = source / "rw_probe.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('restricted-write.txt').write_text("
        "'ok', encoding='utf-8')\n"
        "print(Path(__file__).read_text(encoding='utf-8')[:4])\n",
        encoding="utf-8",
        newline="\n",
    )

    key = uuid.uuid4().hex
    sandbox = create_sandbox_workspace(
        ROOT,
        source,
        "v0294-phase2",
        "restricted-access",
        key,
        "test",
    )

    try:
        workspace = Path(
            sandbox["workspace"]
        )
        runtime_env = (
            build_runtime_environment(
                dict(os.environ),
                sandbox,
            )
        )

        result = (
            run_restricted_contained_capture(
                [
                    sys.executable,
                    str(
                        workspace
                        / "rw_probe.py"
                    ),
                ],
                cwd=workspace,
                env=runtime_env,
                timeout=15,
            )
        )

        assert result.returncode == 0, (
            result.stderr
        )
        assert (
            workspace
            / "restricted-write.txt"
        ).read_text(
            encoding="utf-8"
        ) == "ok"

    finally:
        cleanup_sandbox_workspace(
            ROOT,
            Path(sandbox["root"]),
        )
