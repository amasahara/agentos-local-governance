
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agentos.windows_physical_isolation import (
    DESCRIPTOR,
    LOW_INTEGRITY_PROFILE,
    LOW_INTEGRITY_SID,
    LOW_INTEGRITY_SOURCE_TOKEN_ACCESS,
    PHYSICAL_ISOLATION_SCOPE,
    PHYSICAL_ISOLATION_VERSION,
    SECURITY_MANDATORY_LOW_RID,
    SE_GROUP_INTEGRITY,
    TOKEN_ADJUST_DEFAULT,
    TOKEN_ASSIGN_PRIMARY,
    TOKEN_DUPLICATE,
    TOKEN_QUERY,
    TokenIntegrityLevel,
    WindowsPhysicalIsolationUnavailable,
    create_low_integrity_restricted_primary_token,
    inspect_token_integrity,
)


ROOT = Path(__file__).resolve().parents[2]


def _policy() -> dict:
    return json.loads(
        (ROOT / ".agents/config/release_policy.json").read_text(
            encoding="utf-8"
        )
    )




def test_v0295_phase1_descriptor_progresses_to_async_low_integrity():
    assert PHYSICAL_ISOLATION_VERSION == 1
    assert PHYSICAL_ISOLATION_SCOPE == 'agentos_mediated_process_execution'
    assert LOW_INTEGRITY_PROFILE == 'restricted_low_integrity_v1'
    assert DESCRIPTOR.restricted_token_preserved is True
    assert DESCRIPTOR.low_integrity_token_primitive_present is True
    assert DESCRIPTOR.token_integrity_level_verified is True
    assert DESCRIPTOR.sandbox_mandatory_label_enforced is True
    assert DESCRIPTOR.sync_execution_enforced is True
    assert DESCRIPTOR.async_execution_enforced is True
    assert DESCRIPTOR.low_integrity_attested is True
    assert DESCRIPTOR.host_filesystem_isolation_attested is False
    assert DESCRIPTOR.os_write_confinement_attested is False
    assert DESCRIPTOR.same_user_host_bypass_resistance_claimed is False
    assert DESCRIPTOR.desktop_isolation_attested is False

def test_v0295_phase1_win32_constants_are_exact():
    assert TokenIntegrityLevel == 25
    assert TOKEN_ADJUST_DEFAULT == 0x0080
    assert SECURITY_MANDATORY_LOW_RID == 0x00001000
    assert LOW_INTEGRITY_SID == "S-1-16-4096"
    assert SE_GROUP_INTEGRITY == 0x00000020
    assert LOW_INTEGRITY_SOURCE_TOKEN_ACCESS == (
        TOKEN_ASSIGN_PRIMARY
        | TOKEN_DUPLICATE
        | TOKEN_QUERY
        | TOKEN_ADJUST_DEFAULT
    )




def test_v0295_phase1_policy_progresses_to_async_low_integrity():
    policy = _policy()
    section = policy['windows_physical_isolation_policy']
    assert section['enabled'] is True
    assert section['physical_isolation_version'] == 1
    assert section['scope'] == 'agentos_mediated_process_execution'
    assert section['low_integrity_profile'] == 'restricted_low_integrity_v1'
    assert section['low_integrity_token_primitive_present'] is True
    assert section['token_integrity_level_verification_required'] is True
    assert section['sandbox_mandatory_label_enforced'] is True
    assert section['sandbox_low_integrity_label_runtime_verified'] is True
    assert section['sync_execution_enforced'] is True
    assert section['async_execution_enforced'] is True
    assert section['low_integrity_attested'] is True
    for key in ('host_filesystem_isolation_attested', 'os_write_confinement_attested', 'same_user_host_bypass_resistance_claimed', 'desktop_isolation_attested'):
        assert section[key] is False
    restricted = policy['windows_restricted_execution_policy']
    assert restricted['restricted_token_attested'] is True
    assert restricted['low_integrity_enabled'] is False
    assert restricted['low_integrity_attested'] is False

def test_v0295_phase1_policy_sources_match():
    release = _policy()
    layered = json.loads(
        (ROOT / ".agents/config/policy/20-release.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        release["windows_physical_isolation_policy"]
        == layered["windows_physical_isolation_policy"]
    )


@pytest.mark.skipif(
    os.name == "nt",
    reason="non-Windows fail-closed contract",
)
def test_v0295_phase1_non_windows_fails_closed():
    with pytest.raises(WindowsPhysicalIsolationUnavailable):
        create_low_integrity_restricted_primary_token()


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows Low Integrity live token probe",
)
def test_v0295_phase1_live_restricted_low_integrity_token():
    with create_low_integrity_restricted_primary_token() as token:
        assert token.restricted_evidence.verified is True
        assert token.restricted_evidence.primary_token is True
        assert token.integrity_evidence.verified is True
        assert token.integrity_evidence.sid == LOW_INTEGRITY_SID
        assert token.integrity_evidence.rid == SECURITY_MANDATORY_LOW_RID

        queried = inspect_token_integrity(token.handle)
        assert queried.verified is True
        assert queried.sid == LOW_INTEGRITY_SID
        assert queried.rid == SECURITY_MANDATORY_LOW_RID


def test_v0295_phase1_release_identity_and_schema_v0295():
    assert (ROOT / 'VERSION').read_text(encoding='utf-8').strip() == '0.29.5'
    from agentos import __version__
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    assert __version__ == '0.29.5'
    assert CURRENT_SCHEMA_VERSION == 62
