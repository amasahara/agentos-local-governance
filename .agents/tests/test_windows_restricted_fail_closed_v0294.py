
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from agentos import windows_restricted_execution as restricted
from agentos.windows_restricted_execution import (
    RestrictedTokenEvidence,
    WindowsRestrictedExecutionError,
    verify_restricted_primary_token,
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



def test_v0294_phase4_fail_closed_contract_progresses_to_release_activation():
    section = _policy_section()

    assert section["restricted_failure_contract_version"] == 1

    for key in (
        "source_token_validation_fail_closed",
        "child_token_validation_fail_closed",
        "job_assignment_failure_fail_closed",
        "resume_failure_fail_closed",
        "unrestricted_sync_fallback_forbidden",
        "unrestricted_async_production_downgrade_forbidden",
        "sandbox_inert_forbidden",
        "unexpected_enabled_privileges_forbidden",
        "negative_test_suite_required",
    ):
        assert section[key] is True

    assert section["restricted_token_attested"] is True
    assert section["low_integrity_attested"] is False

@pytest.mark.parametrize(
    ("evidence", "message"),
    [
        (
            RestrictedTokenEvidence(
                token_type=2,
                token_has_restrictions=True,
                sandbox_inert=False,
                enabled_privileges=(),
                unexpected_enabled_privileges=(),
            ),
            "restricted_token_not_primary",
        ),
        (
            RestrictedTokenEvidence(
                token_type=1,
                token_has_restrictions=False,
                sandbox_inert=False,
                enabled_privileges=(),
                unexpected_enabled_privileges=(),
            ),
            "restricted_token_not_filtered",
        ),
        (
            RestrictedTokenEvidence(
                token_type=1,
                token_has_restrictions=True,
                sandbox_inert=True,
                enabled_privileges=(),
                unexpected_enabled_privileges=(),
            ),
            "restricted_token_sandbox_inert_forbidden",
        ),
        (
            RestrictedTokenEvidence(
                token_type=1,
                token_has_restrictions=True,
                sandbox_inert=False,
                enabled_privileges=(
                    "SeChangeNotifyPrivilege",
                    "SeDebugPrivilege",
                ),
                unexpected_enabled_privileges=(
                    "SeDebugPrivilege",
                ),
            ),
            "restricted_token_unexpected_enabled_privileges",
        ),
    ],
)
def test_v0294_phase4_token_verifier_fails_closed(
    monkeypatch,
    evidence,
    message,
):
    monkeypatch.setattr(
        restricted,
        "inspect_restricted_token",
        lambda _handle: evidence,
    )

    with pytest.raises(
        WindowsRestrictedExecutionError,
        match=message,
    ):
        verify_restricted_primary_token(
            123
        )


def test_v0294_phase4_restricted_flags_forbid_sandbox_inert():
    assert (
        restricted.RESTRICTED_TOKEN_FLAGS
        == (
            restricted.DISABLE_MAX_PRIVILEGE
            | restricted.LUA_TOKEN
        )
    )
    assert (
        restricted.RESTRICTED_TOKEN_FLAGS
        & restricted.SANDBOX_INERT
    ) == 0


def test_v0294_phase4_source_token_is_verified_before_restricted_handle_is_returned():
    source = (
        ROOT
        / ".agents/agentos/windows_restricted_execution.py"
    ).read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def create_restricted_primary_token("
    )
    end = source.index(
        "def _environment_block(",
        start,
    )
    body = source[
        start:end
    ]

    create = body.index(
        "advapi32.CreateRestrictedToken("
    )
    verify = body.index(
        "verify_restricted_primary_token("
    )
    returned = body.index(
        "return RestrictedPrimaryToken("
    )

    assert create < verify < returned
    assert "_close_handle(handle)" in body
    assert "raise" in body


def test_v0294_phase4_child_is_never_resumed_before_verification_and_job_assignment():
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


def test_v0294_phase4_restricted_spawn_has_cleanup_for_all_post_create_failures():
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

    assert "except Exception as original_exc:" in body
    assert "job.terminate(1)" in body
    assert "kernel32.TerminateProcess(" in body
    assert "kernel32.WaitForSingleObject(" in body
    assert "_close_handle(" in body
    assert "raise original_exc" in body


def test_v0294_phase4_sync_production_has_no_unrestricted_downgrade_switch():
    proxy = (
        ROOT
        / ".agents/agentos/proxy.py"
    ).read_text(
        encoding="utf-8"
    )
    restricted_source = (
        ROOT
        / ".agents/agentos/windows_restricted_execution.py"
    ).read_text(
        encoding="utf-8"
    )

    start = proxy.index(
        "def _run_process_command("
    )
    end = proxy.index(
        "def _credential_safe_environment_hash(",
        start,
    )
    helper = proxy[start:end]

    assert (
        "run_restricted_contained_capture("
        in helper
    )
    assert (
        "run_contained_capture("
        not in helper
    )

    start = restricted_source.index(
        "def run_restricted_contained_capture("
    )
    body = restricted_source[start:]

    assert (
        "spawn_restricted_suspended_in_job("
        in body
    )
    assert (
        "spawn_suspended_in_job("
        not in body
    )


def test_v0294_phase4_async_production_cannot_request_unrestricted_worker():
    jobs = (
        ROOT
        / ".agents/agentos/jobs.py"
    ).read_text(
        encoding="utf-8"
    )

    start = jobs.index(
        "def _launch_windows_job_broker("
    )
    end = jobs.index(
        "def _job_dir(",
        start,
    )
    helper = jobs[start:end]

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

    signature = helper.split(
        "):",
        1,
    )[0]
    assert (
        "restricted_execution"
        not in signature
    )


def test_v0294_phase4_broker_rejects_non_boolean_restricted_execution_payload(
    monkeypatch,
):
    from agentos import windows_job_broker
    from agentos.windows_process_tree import (
        async_job_object_name,
    )

    payload = {
        "job_id": "phase4-invalid-bool",
        "job_name": async_job_object_name(
            "phase4-invalid-bool"
        ),
        "command": [
            "python",
            "-c",
            "print(1)",
        ],
        "cwd": str(ROOT),
        "env": {},
        "stdout_path": str(
            ROOT
            / ".agents/runtime/phase4.stdout"
        ),
        "stderr_path": str(
            ROOT
            / ".agents/runtime/phase4.stderr"
        ),
        "restricted_execution": "true",
    }

    monkeypatch.setattr(
        windows_job_broker.sys,
        "stdin",
        io.StringIO(
            json.dumps(payload)
            + "\n"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "windows_job_broker_"
            "restricted_execution_must_be_bool"
        ),
    ):
        windows_job_broker._load_payload()


def test_v0294_phase4_generic_broker_mode_is_not_a_production_downgrade():
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
        '"restricted_execution",'
        in broker
    )
    assert (
        "spawn_suspended_in_job("
        in broker
    )

    start = jobs.index(
        "def _launch_windows_job_broker("
    )
    end = jobs.index(
        "def _job_dir(",
        start,
    )
    production = jobs[start:end]

    assert (
        '"restricted_execution": True'
        in production
    )
    assert (
        '"restricted_token_verified"'
        in production
    )
    assert (
        '"assigned_before_resume"'
        in production
    )



def test_v0294_phase4_scoped_claim_preserves_broad_nonclaims():
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


def test_v0294_phase4_identity_and_schema_progress_to_release():
    assert tuple(int(part) for part in (ROOT / "VERSION").read_text(encoding="utf-8").strip().split(".")) >= (0, 29, 5)
    from agentos import __version__
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert CURRENT_SCHEMA_VERSION >= 62
