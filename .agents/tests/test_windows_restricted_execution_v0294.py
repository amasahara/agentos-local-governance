from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

from agentos.windows_restricted_execution import (
    ALLOWED_ENABLED_PRIVILEGES,
    DESCRIPTOR,
    DISABLE_MAX_PRIVILEGE,
    LUA_TOKEN,
    RESTRICTED_EXECUTION_SCOPE,
    RESTRICTED_EXECUTION_VERSION,
    RESTRICTED_TOKEN_FLAGS,
    RESTRICTED_TOKEN_PROFILE,
    SANDBOX_INERT,
    WindowsRestrictedExecutionUnavailable,
    create_restricted_primary_token,
)

ROOT = Path(__file__).resolve().parents[2]


def _release_policy() -> dict:
    return json.loads(
        (ROOT / ".agents/config/release_policy.json").read_text(encoding="utf-8")
    )





def test_v0294_phase1_descriptor_progresses_to_scoped_release_activation():
    assert RESTRICTED_EXECUTION_VERSION == 1
    assert RESTRICTED_EXECUTION_SCOPE == "agentos_mediated_process_execution"
    assert RESTRICTED_TOKEN_PROFILE == "disable_max_privilege_lua_v1"
    assert DESCRIPTOR.disable_max_privilege is True
    assert DESCRIPTOR.lua_token is True
    assert DESCRIPTOR.sandbox_inert is False
    assert DESCRIPTOR.sync_execution_enforced is True
    assert DESCRIPTOR.async_execution_enforced is True
    assert DESCRIPTOR.restricted_token_attested is True
    assert DESCRIPTOR.low_integrity_attested is False
    assert DESCRIPTOR.host_filesystem_isolation_attested is False
    assert DESCRIPTOR.os_write_confinement_attested is False
    assert DESCRIPTOR.same_user_host_bypass_resistance_claimed is False

def test_v0294_phase1_flags_never_enable_sandbox_inert():
    assert RESTRICTED_TOKEN_FLAGS == (DISABLE_MAX_PRIVILEGE | LUA_TOKEN)
    assert (RESTRICTED_TOKEN_FLAGS & SANDBOX_INERT) == 0


def test_v0294_phase1_privilege_allowlist_is_narrow():
    assert ALLOWED_ENABLED_PRIVILEGES == frozenset({"SeChangeNotifyPrivilege"})


def test_v0294_phase1_win32_abi_and_verification_markers_present():
    source = (ROOT / ".agents/agentos/windows_restricted_execution.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        "OpenProcessToken", "CreateRestrictedToken", "GetTokenInformation",
        "TokenHasRestrictions", "TokenSandBoxInert", "TokenPrivileges",
        "LookupPrivilegeNameW", "CreateProcessAsUserW", "DISABLE_MAX_PRIVILEGE",
        "LUA_TOKEN", "sandbox_inert_must_never_be_enabled",
        "restricted_token_not_primary", "restricted_token_not_filtered",
        "restricted_token_unexpected_enabled_privileges",
    ):
        assert marker in source
    assert "SetTokenInformation" not in source
    assert "TokenIntegrityLevel" not in source





def test_v0294_phase1_policy_progresses_to_scoped_release_activation():
    policy = json.loads((ROOT / '.agents/config/release_policy.json').read_text(encoding='utf-8'))
    section = _release_policy()['windows_restricted_execution_policy']
    assert tuple(int(part) for part in policy["version"].split(".")) >= (0, 29, 5)
    assert section['enabled'] is True
    assert section['restricted_execution_version'] == 1
    assert section['database_schema'] == 62
    assert section['scope'] == 'agentos_mediated_process_execution'
    assert section['sync_execution_enforced'] is True
    assert section['async_execution_enforced'] is True
    assert section['restricted_token_attested'] is True
    assert section['activation_complete'] is True
    assert section['activation_version'] == '0.29.4'
    for key in ('low_integrity_attested', 'desktop_isolation_attested', 'host_filesystem_isolation_attested', 'os_write_confinement_attested', 'same_user_host_bypass_resistance_claimed'):
        assert section[key] is False

def test_v0294_phase1_policy_sources_match():
    release = _release_policy()["windows_restricted_execution_policy"]
    layered = json.loads(
        (ROOT / ".agents/config/policy/20-release.json").read_text(encoding="utf-8")
    )["windows_restricted_execution_policy"]
    assert release == layered






def test_v0294_phase1_foundation_progresses_to_sync_and_async_restricted_execution():
    proxy = (
        ROOT
        / ".agents/agentos/proxy.py"
    ).read_text(
        encoding="utf-8"
    )
    tree = (
        ROOT
        / ".agents/agentos/windows_process_tree.py"
    ).read_text(
        encoding="utf-8"
    )
    restricted = (
        ROOT
        / ".agents/agentos/windows_restricted_execution.py"
    ).read_text(
        encoding="utf-8"
    )
    jobs = (
        ROOT
        / ".agents/agentos/jobs.py"
    ).read_text(
        encoding="utf-8"
    )
    broker = (
        ROOT
        / ".agents/agentos/windows_job_broker.py"
    ).read_text(
        encoding="utf-8"
    )

    # Sync production route is restricted.
    assert (
        "run_restricted_contained_capture("
        in proxy
    )

    # The inherited v0.29.1 generic Job helper remains available.
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
    assert (
        "spawn_suspended_in_job("
        in legacy
    )
    assert (
        "spawn_restricted_suspended_in_job("
        not in legacy
    )

    # Restricted sync/async worker creation shares one verified primitive.
    restricted_start = restricted.index(
        "def spawn_restricted_suspended_in_job("
    )
    restricted_spawn = restricted[
        restricted_start:
    ]
    assert (
        "advapi32.CreateProcessAsUserW("
        in restricted_spawn
    )
    assert (
        "_verify_child_process_token("
        in restricted_spawn
    )
    assert (
        "job.assign_process_handle("
        in restricted_spawn
    )
    assert (
        "kernel32.ResumeThread("
        in restricted_spawn
    )

    # Async production route now requires the restricted worker.
    assert (
        '"restricted_execution": True'
        in jobs
    )
    assert (
        '"restricted_token_verified"'
        in jobs
    )
    assert (
        "from .windows_restricted_execution import ("
        in broker
    )
    assert (
        "spawn_restricted_suspended_in_job("
        in broker
    )

@pytest.mark.skipif(os.name != "nt", reason="Win32 restricted-token runtime verification")
def test_v0294_phase1_creates_real_verified_restricted_primary_token():
    with create_restricted_primary_token() as token:
        evidence = token.evidence
        assert evidence.verified is True
        assert evidence.primary_token is True
        assert evidence.token_has_restrictions is True
        assert evidence.sandbox_inert is False
        assert evidence.unexpected_enabled_privileges == ()
        assert set(evidence.enabled_privileges).issubset(ALLOWED_ENABLED_PRIVILEGES)
        assert token.handle > 0


def test_v0294_phase1_non_windows_fails_closed():
    if os.name == "nt":
        pytest.skip("non-Windows fail-closed contract")
    with pytest.raises(WindowsRestrictedExecutionUnavailable):
        create_restricted_primary_token()



def test_v0294_phase1_identity_and_schema_progress_to_release():
    assert tuple(int(part) for part in (ROOT / "VERSION").read_text(encoding="utf-8").strip().split(".")) >= (0, 29, 5)
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    source = (ROOT / '.agents/agentos/schema_version.py').read_text(encoding='utf-8')
    assert f"CURRENT_SCHEMA_VERSION = {CURRENT_SCHEMA_VERSION}" in source
