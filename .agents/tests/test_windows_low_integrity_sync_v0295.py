
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid

import pytest

from agentos.proxy import _run_process_command
from agentos.tool_runtime_profiles import (
    build_runtime_environment,
    cleanup_sandbox_workspace,
    create_sandbox_workspace,
)
from agentos.windows_physical_isolation import (
    LOW_INTEGRITY_SID,
    SECURITY_MANDATORY_LOW_RID,
    SECURITY_MANDATORY_MEDIUM_RID,
    inspect_path_mandatory_label,
    run_low_integrity_restricted_contained_capture,
)


ROOT = Path(__file__).resolve().parents[2]


CHILD_TOKEN_SCRIPT = r"""
import ctypes
import json
from ctypes import wintypes

TOKEN_QUERY = 0x0008
TokenType = 8
TokenHasRestrictions = 21
TokenSandBoxInert = 15
TokenIntegrityLevel = 25

class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Sid", wintypes.LPVOID),
        ("Attributes", wintypes.DWORD),
    ]

class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [
        ("Label", SID_AND_ATTRIBUTES),
    ]

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

advapi32.IsValidSid.argtypes = [
    wintypes.LPVOID,
]
advapi32.IsValidSid.restype = wintypes.BOOL

advapi32.GetSidSubAuthorityCount.argtypes = [
    wintypes.LPVOID,
]
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(
    ctypes.c_ubyte
)

advapi32.GetSidSubAuthority.argtypes = [
    wintypes.LPVOID,
    wintypes.DWORD,
]
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(
    wintypes.DWORD
)

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

required = wintypes.DWORD()

advapi32.GetTokenInformation(
    token,
    TokenIntegrityLevel,
    None,
    0,
    ctypes.byref(required),
)

if required.value <= 0:
    raise SystemExit(93)

buffer = ctypes.create_string_buffer(
    int(required.value)
)
returned = wintypes.DWORD()

if not advapi32.GetTokenInformation(
    token,
    TokenIntegrityLevel,
    ctypes.cast(
        buffer,
        wintypes.LPVOID,
    ),
    int(required.value),
    ctypes.byref(returned),
):
    raise SystemExit(94)

label = ctypes.cast(
    ctypes.addressof(buffer),
    ctypes.POINTER(
        TOKEN_MANDATORY_LABEL
    ),
).contents

sid = label.Label.Sid

if not advapi32.IsValidSid(sid):
    raise SystemExit(95)

count = int(
    advapi32.GetSidSubAuthorityCount(
        sid
    ).contents.value
)

rid = int(
    advapi32.GetSidSubAuthority(
        sid,
        count - 1,
    ).contents.value
)

print(
    json.dumps(
        {
            "token_type": q(TokenType),
            "token_has_restrictions": bool(
                q(TokenHasRestrictions)
            ),
            "sandbox_inert": bool(
                q(TokenSandBoxInert)
            ),
            "integrity_rid": rid,
        },
        sort_keys=True,
    )
)
"""


def _physical_policy() -> dict:
    value = json.loads(
        (
            ROOT
            / ".agents/config/release_policy.json"
        ).read_text(
            encoding="utf-8"
        )
    )
    return value[
        "windows_physical_isolation_policy"
    ]


def test_v0295_phase3_policy_progresses_to_sync_and_async_low_integrity():
    section = _physical_policy()
    assert section['sync_execution_enforced'] is True
    assert section['async_execution_enforced'] is True
    assert section['sync_low_integrity_token_required'] is True
    assert section['sync_child_low_integrity_verification_required'] is True
    assert section['sync_restricted_child_verification_required'] is True
    assert section['sync_job_assignment_before_resume_required'] is True
    assert section['sync_fail_closed_without_medium_integrity_fallback'] is True
    assert section['low_integrity_attested'] is True
    assert section['sandbox_low_integrity_label_attested'] is True
    assert section['primary_root_write_up_prevention_attested'] is False

def test_v0295_phase3_spawn_order_is_fail_closed():
    source = (
        ROOT
        / ".agents/agentos/windows_physical_isolation.py"
    ).read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def spawn_low_integrity_restricted_suspended_in_job("
    )
    end = source.index(
        "def run_low_integrity_restricted_contained_capture(",
        start,
    )
    body = source[
        start:end
    ]

    create = body.index(
        "CreateProcessAsUserW("
    )
    restricted_verify = body.index(
        "_verify_child_process_token("
    )
    low_verify = body.index(
        "_verify_child_process_low_integrity("
    )
    assign = body.index(
        "job.assign_process_handle("
    )
    resume = body.index(
        "ResumeThread("
    )

    assert (
        create
        < restricted_verify
        < low_verify
        < assign
        < resume
    )
    assert "CREATE_SUSPENDED" in body
    assert "CreateProcessW(" not in body
    assert "create_restricted_primary_token(" not in body
    assert (
        "create_low_integrity_restricted_primary_token("
        in body
    )
    assert "TerminateProcess(" in body
    assert "raise original_exc" in body


def test_v0295_phase3_proxy_selects_successor_sync_runner():
    source = (
        ROOT
        / ".agents/agentos/proxy.py"
    ).read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def _run_process_command("
    )
    end = source.index(
        "def _credential_safe_environment_hash(",
        start,
    )
    body = source[
        start:end
    ]

    assert (
        "run_low_integrity_restricted_contained_capture "
        "as run_restricted_contained_capture"
        in body
    )
    assert (
        "run_restricted_contained_capture("
        in body
    )
    assert (
        '"low_integrity_execution": True'
        in body
    )
    assert (
        '"low_integrity_token_verified": True'
        in body
    )
    assert (
        '"low_integrity_attested": False'
        in body
    )


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows synchronous Low Integrity execution",
)
def test_v0295_phase3_direct_child_is_restricted_and_low():
    result = (
        run_low_integrity_restricted_contained_capture(
            [
                sys.executable,
                "-c",
                CHILD_TOKEN_SCRIPT,
            ],
            cwd=ROOT,
            env=dict(
                os.environ
            ),
            timeout=15,
        )
    )

    assert result.returncode == 0, (
        result.stderr
    )

    value = json.loads(
        result.stdout.strip()
    )

    assert value["token_type"] == 1
    assert value[
        "token_has_restrictions"
    ] is True
    assert value[
        "sandbox_inert"
    ] is False
    assert (
        value[
            "integrity_rid"
        ]
        == SECURITY_MANDATORY_LOW_RID
    )


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows Low Integrity sandbox/write-up probe",
)
def test_v0295_phase3_sync_writes_low_sandbox_and_denies_medium_target(
    tmp_path,
):
    primary = tmp_path / "primary"
    source = primary / "source"
    source.mkdir(
        parents=True
    )

    medium_target = (
        tmp_path
        / "medium-target.txt"
    )
    medium_target.write_text(
        "before",
        encoding="utf-8",
    )

    before = (
        inspect_path_mandatory_label(
            medium_target
        )
    )

    assert (
        before.rid
        >= SECURITY_MANDATORY_MEDIUM_RID
    )
    assert before.low_integrity is False

    probe = source / "probe.py"
    probe.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path('sandbox-write.txt').write_text('ok', encoding='utf-8')\n"
        f"target = Path({str(medium_target)!r})\n"
        "try:\n"
        "    target.write_text('forbidden', encoding='utf-8')\n"
        "except PermissionError:\n"
        "    print('MEDIUM_WRITE_DENIED')\n"
        "else:\n"
        "    print('MEDIUM_WRITE_UNEXPECTEDLY_ALLOWED')\n"
        "    raise SystemExit(88)\n",
        encoding="utf-8",
        newline="\n",
    )

    sandbox = (
        create_sandbox_workspace(
            primary_root=primary,
            source_root=source,
            task_id="v0295-phase3",
            session_id="sync-low",
            execution_id=uuid.uuid4().hex,
            command_profile="test",
        )
    )

    try:
        workspace = Path(
            sandbox[
                "workspace"
            ]
        )
        runtime_env = (
            build_runtime_environment(
                dict(
                    os.environ
                ),
                sandbox,
            )
        )

        result, metadata = (
            _run_process_command(
                [
                    sys.executable,
                    str(
                        workspace
                        / "probe.py"
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
            "MEDIUM_WRITE_DENIED"
            in result.stdout
        )

        assert (
            workspace
            / "sandbox-write.txt"
        ).read_text(
            encoding="utf-8"
        ) == "ok"

        assert medium_target.read_text(
            encoding="utf-8"
        ) == "before"

        assert metadata[
            "restricted_execution"
        ] is True
        assert metadata[
            "restricted_token_verified"
        ] is True
        assert metadata[
            "low_integrity_execution"
        ] is True
        assert metadata[
            "low_integrity_token_verified"
        ] is True
        assert metadata[
            "sandbox_low_integrity_boundary_required"
        ] is True
        assert metadata[
            "low_integrity_attested"
        ] is False
        assert metadata[
            "host_filesystem_isolation_attested"
        ] is False
        assert metadata[
            "os_write_confinement_attested"
        ] is False

    finally:
        cleanup_sandbox_workspace(
            primary,
            Path(
                sandbox[
                    "root"
                ]
            ),
        )


def test_v0295_phase3_release_identity_and_schema_v0295():
    assert (ROOT / 'VERSION').read_text(encoding='utf-8').strip() == '0.29.5'
    from agentos import __version__
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    assert __version__ == '0.29.5'
    assert CURRENT_SCHEMA_VERSION == 62
