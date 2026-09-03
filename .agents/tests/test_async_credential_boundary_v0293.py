from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

from agentos import jobs
from agentos.policy import load_policy
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.tool_runtime_profiles import (
    PROCESS_CREDENTIAL_CAPABILITY,
    resolve_runtime_profile_from_policy,
)


ROOT = Path(__file__).resolve().parents[2]


def configured_policy() -> dict:
    policy = copy.deepcopy(load_policy(ROOT))
    policy[
        "sandbox_workspace_runtime_profile_policy"
    ]["credential_bindings"]["test"] = [
        {
            "binding_id": "async-ci-token",
            "credential_ref": "secret://async-ci-token",
            "target_env": "ASYNC_API_TOKEN",
            "secret_field": "token",
        }
    ]
    return policy


def async_spec(policy: dict) -> dict:
    runtime = resolve_runtime_profile_from_policy(
        "test",
        policy,
    )
    return {
        "profile": "test",
        "runtime_profile_configuration_hash": runtime[
            "configuration_hash"
        ],
        "credential_reference_hash": runtime[
            "credential_reference_hash"
        ],
        "credential_binding_hash": runtime[
            "credential_binding_hash"
        ],
        "credential_binding_count": runtime[
            "credential_binding_count"
        ],
    }


def test_v0293_phase4_policy_is_release_activated():
    section = load_policy(ROOT)["sandbox_workspace_runtime_profile_policy"]

    assert section["async_credential_boundary_enabled"] is True
    assert section["async_credential_environment_projection_enabled"] is True
    assert section["async_credential_resolution_at_launch_only"] is True
    assert section["async_credential_spec_reference_hash_only"] is True
    assert section["async_credential_provider_approval_revalidated"] is True
    assert section["async_credential_output_persistence_disabled"] is True
    assert section["async_credential_environment_hash_secret_independent"] is True
    assert section["credential_environment_projection_enabled"] is True
    assert section["credential_boundary_enabled"] is True
    assert section["credential_boundary_attested"] is True
    assert section["async_credential_boundary_attested"] is True

def test_v0293_phase4_async_resolution_is_launch_time_and_metadata_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    policy = configured_policy()
    runtime = resolve_runtime_profile_from_policy(
        "test",
        policy,
    )
    spec = async_spec(policy)

    monkeypatch.setattr(
        jobs,
        "load_policy",
        lambda *args, **kwargs: policy,
    )

    calls = []

    def fake_resolve(root, ref, *, capability):
        calls.append((ref, capability))
        return {
            "token": "ASYNC_MEMORY_ONLY_SECRET_0293"
        }

    monkeypatch.setattr(
        jobs,
        "resolve_runtime_secret",
        fake_resolve,
    )

    launch, evidence = (
        jobs._resolve_async_credential_environment(
            tmp_path,
            spec,
            runtime,
            {"PATH": "p"},
        )
    )

    assert calls == [
        (
            "secret://async-ci-token",
            PROCESS_CREDENTIAL_CAPABILITY,
        )
    ]
    assert (
        launch["ASYNC_API_TOKEN"]
        == "ASYNC_MEMORY_ONLY_SECRET_0293"
    )
    assert evidence["credential_binding_count"] == 1
    assert evidence["credential_values_included"] is False
    assert evidence["credential_references_included"] is False
    assert evidence["credential_output_persisted"] is False

    serialized = json.dumps(
        evidence,
        sort_keys=True,
    )
    assert "ASYNC_MEMORY_ONLY_SECRET_0293" not in serialized
    assert "secret://async-ci-token" not in serialized


def test_v0293_phase4_async_binding_drift_fails_before_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    policy = configured_policy()
    runtime = resolve_runtime_profile_from_policy(
        "test",
        policy,
    )
    spec = async_spec(policy)
    spec["credential_binding_hash"] = "0" * 64

    monkeypatch.setattr(
        jobs,
        "load_policy",
        lambda *args, **kwargs: policy,
    )
    monkeypatch.setattr(
        jobs,
        "resolve_runtime_secret",
        lambda *args, **kwargs: pytest.fail(
            "resolver must not run after binding drift"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="async_credential_spec_binding_drift",
    ):
        jobs._resolve_async_credential_environment(
            tmp_path,
            spec,
            runtime,
            {},
        )


def test_v0293_phase4_start_job_verifies_spec_hash_before_secret_resolution():
    source = inspect.getsource(jobs.start_job)

    spec_hash_position = source.index(
        "queued job specification hash mismatch"
    )
    resolver_position = source.index(
        "_resolve_async_credential_environment"
    )

    assert spec_hash_position < resolver_position


def test_v0293_phase4_submit_spec_persists_hashes_not_refs():
    source = inspect.getsource(jobs.submit_job)

    assert '"credential_reference_hash"' in source
    assert '"credential_binding_hash"' in source
    assert '"credential_binding_count"' in source
    assert '"credential_values_included"' in source

    assert '"credential_bindings"' not in source
    assert "secret://" not in source
    assert "resolve_runtime_secret" not in source


def test_v0293_phase4_credentialed_async_output_is_not_persisted():
    source = inspect.getsource(jobs.start_job)

    assert "credential_output_suppressed" in source
    assert "os.devnull" in source
    assert "credential_output_persisted" in source


def test_v0293_phase4_windows_file_secret_remains_blocked_and_unattested():
    section = load_policy(ROOT)[
        "sandbox_workspace_runtime_profile_policy"
    ]

    assert (
        section[
            "windows_file_secret_process_projection_attested"
        ]
        is False
    )

    secret_source = (
        ROOT / ".agents/agentos/secret_lineage.py"
    ).read_text(encoding="utf-8")

    assert 'provider.scheme == "file-secret"' in secret_source
    assert 'os.name == "nt"' in secret_source



def test_v0293_phase4_nonclaims_are_preserved_under_successor():
    section = load_policy(ROOT)["sandbox_workspace_runtime_profile_policy"]

    for key in (
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
        "host_filesystem_isolation_attested",
        "os_write_confinement_attested",
        "same_user_host_bypass_resistance_claimed",
    ):
        assert section[key] is False

    current = (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()
    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 3)
    assert CURRENT_SCHEMA_VERSION >= 62
