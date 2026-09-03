from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentos.db import connect
from agentos.policy import load_policy
from agentos import proxy
from agentos.schema_version import CURRENT_SCHEMA_VERSION
from agentos.secret_lineage import (
    ALLOWED_SECRET_CAPABILITIES,
    SecretLineageError,
    approve_provider,
    resolve_runtime_secret,
)
from agentos.tool_runtime_profiles import (
    PROCESS_CREDENTIAL_CAPABILITY,
    credential_bindings_for_profile,
    resolve_runtime_profile_from_policy,
)


ROOT = Path(__file__).resolve().parents[2]


def configured_policy() -> dict:
    policy = copy.deepcopy(
        load_policy(ROOT)
    )
    section = policy[
        "sandbox_workspace_runtime_profile_policy"
    ]
    section[
        "credential_bindings"
    ][
        "test"
    ] = [
        {
            "binding_id": "ci-token",
            "credential_ref": "secret://ci-token",
            "target_env": "CI_API_TOKEN",
            "secret_field": "token",
        }
    ]
    return policy


def metadata_for(
    policy: dict,
) -> dict:
    runtime = resolve_runtime_profile_from_policy(
        "test",
        policy,
    )
    return {
        "command_profile": "test",
        "runtime_profile": "test",
        "runtime_profile_hash": runtime[
            "profile_hash"
        ],
        "runtime_profile_version": runtime[
            "profile_version"
        ],
        "runtime_profile_scope": runtime[
            "scope"
        ],
        "runtime_profile_configuration_hash": runtime[
            "configuration_hash"
        ],
        "runtime_profile_configuration_version": runtime[
            "configuration_version"
        ],
        "runtime_profile_configuration_source": runtime[
            "configuration_source"
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
        "cwd": ".",
        "sandbox_profile": "tool-runtime-profile-v1",
        "workspace_bound": False,
        "host_filesystem_isolation_attested": False,
        "os_write_confinement_attested": False,
    }


def test_v0293_phase3_process_credential_capability_is_allowlisted():
    assert (
        PROCESS_CREDENTIAL_CAPABILITY
        == "process.exec.credential"
    )
    assert (
        PROCESS_CREDENTIAL_CAPABILITY
        in ALLOWED_SECRET_CAPABILITIES
    )


def test_v0293_phase3_existing_secret_resolver_handles_process_alias_memory_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    secret_value = "SYNC_ONLY_DO_NOT_PERSIST_0293"
    monkeypatch.setenv(
        "AGENTOS_V0293_SYNC_SECRET",
        json.dumps(
            {
                "token": secret_value,
            }
        ),
    )

    cfg = (
        tmp_path
        / ".agents/config/governance.json"
    )
    cfg.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    cfg.write_text(
        json.dumps(
            {
                "secret_resolver_policy": {
                    "aliases": {
                        "sync-ci": (
                            "env://AGENTOS_V0293_SYNC_SECRET"
                        )
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    approve_provider(
        tmp_path,
        "env",
        capabilities=[
            PROCESS_CREDENTIAL_CAPABILITY
        ],
        approved_by="operator",
        human_confirmed=True,
    )

    resolved = resolve_runtime_secret(
        tmp_path,
        "secret://sync-ci",
        capability=(
            PROCESS_CREDENTIAL_CAPABILITY
        ),
    )

    assert resolved["token"] == secret_value

    db_bytes = (
        tmp_path
        / ".agents/state/agentos.db"
    ).read_bytes()
    assert secret_value.encode() not in db_bytes


def test_v0293_phase3_environment_fingerprint_is_independent_of_secret_value():
    first = proxy._credential_safe_environment_hash(
        {
            "PATH": "p",
            "CI_API_TOKEN": "first-secret",
        },
        {
            "CI_API_TOKEN",
        },
    )
    second = proxy._credential_safe_environment_hash(
        {
            "PATH": "p",
            "CI_API_TOKEN": "second-secret",
        },
        {
            "CI_API_TOKEN",
        },
    )
    changed_nonsecret = proxy._credential_safe_environment_hash(
        {
            "PATH": "different",
            "CI_API_TOKEN": "second-secret",
        },
        {
            "CI_API_TOKEN",
        },
    )

    assert first == second
    assert first != changed_nonsecret


def test_v0293_phase3_exact_secret_output_redaction():
    secret = "VERY_UNIQUE_SECRET_0293"

    result = proxy._redact_projected_secret_values(
        "prefix "
        + secret
        + " suffix "
        + secret,
        [secret],
    )

    assert secret not in result
    assert result.count(
        "<redacted-secret>"
    ) == 2


def test_v0293_phase3_sync_projection_resolves_only_at_launch_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    policy = configured_policy()
    runtime = resolve_runtime_profile_from_policy(
        "test",
        policy,
    )

    calls: list[
        tuple[str, str]
    ] = []

    def fake_resolve(
        root,
        ref,
        *,
        capability,
    ):
        calls.append(
            (
                ref,
                capability,
            )
        )
        return {
            "token": "MEMORY_ONLY_TOKEN_0293"
        }

    monkeypatch.setattr(
        proxy,
        "resolve_runtime_secret",
        fake_resolve,
    )

    launch, evidence, secret_values = (
        proxy._resolve_sync_credential_environment(
            tmp_path,
            policy,
            runtime,
            {
                "PATH": "p",
            },
        )
    )

    assert calls == [
        (
            "secret://ci-token",
            PROCESS_CREDENTIAL_CAPABILITY,
        )
    ]
    assert (
        launch["CI_API_TOKEN"]
        == "MEMORY_ONLY_TOKEN_0293"
    )
    assert secret_values == [
        "MEMORY_ONLY_TOKEN_0293"
    ]
    assert evidence[
        "secret_values_included"
    ] is False
    assert (
        "MEMORY_ONLY_TOKEN_0293"
        not in json.dumps(
            evidence,
            sort_keys=True,
        )
    )


def test_v0293_phase3_sync_adapter_projects_then_redacts_and_does_not_persist_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = tmp_path / "project"
    root.mkdir()
    (
        root
        / "source.txt"
    ).write_text(
        "hello\n",
        encoding="utf-8",
    )

    policy = configured_policy()

    monkeypatch.setattr(
        proxy,
        "load_policy",
        lambda *args, **kwargs: policy,
    )

    from agentos import multi_agent_workspace

    monkeypatch.setattr(
        multi_agent_workspace,
        "workspace_execution_root",
        lambda *args, **kwargs: root,
    )

    secret_value = "SYNC_PROCESS_SECRET_0293"

    monkeypatch.setattr(
        proxy,
        "resolve_runtime_secret",
        lambda *args, **kwargs: {
            "token": secret_value
        },
    )

    captured = {}

    def fake_run(
        command,
        *,
        cwd,
        env,
        timeout,
    ):
        captured["env"] = dict(env)
        return (
            SimpleNamespace(
                returncode=0,
                stdout=(
                    "stdout:"
                    + secret_value
                ),
                stderr=(
                    "stderr:"
                    + secret_value
                ),
            ),
            {
                "process_tree_contained": True,
                "process_tree_containment_profile": (
                    "test-containment"
                ),
                "process_tree_containment_scope": (
                    "agentos_mediated_process_execution"
                ),
            },
        )

    monkeypatch.setattr(
        proxy,
        "_run_process_command",
        fake_run,
    )

    success, output = proxy._execute_adapter(
        root,
        "task-1",
        "session-1",
        "process.exec",
        {
            "command": [
                "python",
                "-m",
                "pytest",
            ],
            "cwd": ".",
            "timeout": 30,
            "env": {},
        },
        metadata_for(
            policy
        ),
    )

    assert success is True
    assert (
        captured["env"]["CI_API_TOKEN"]
        == secret_value
    )
    assert secret_value not in output[
        "stdout"
    ]
    assert secret_value not in output[
        "stderr"
    ]
    assert output[
        "credential_values_included"
    ] is False
    assert output[
        "credential_binding_count"
    ] == 1

    db_bytes = (
        root
        / ".agents/state/agentos.db"
    ).read_bytes()
    assert secret_value.encode() not in db_bytes


def test_v0293_phase3_async_submission_gate_is_released_only_by_phase4_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    policy = configured_policy()
    section = policy[
        "sandbox_workspace_runtime_profile_policy"
    ]

    assert section["async_credential_boundary_enabled"] is True
    assert (
        section[
            "async_credential_environment_projection_enabled"
        ]
        is True
    )

    source = (
        ROOT / ".agents/agentos/proxy.py"
    ).read_text(encoding="utf-8")

    assert "async_credential_projection_not_enabled" in source
    assert (
        "async_credential_environment_projection_enabled"
        in source
    )

def test_v0293_phase3_windows_file_secret_process_projection_is_not_attested():
    policy = load_policy(ROOT)
    section = policy[
        "sandbox_workspace_runtime_profile_policy"
    ]

    assert (
        section[
            "windows_file_secret_process_projection_attested"
        ]
        is False
    )

    source = (
        ROOT
        / ".agents/agentos/secret_lineage.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'capability\n        == "process.exec.credential"'
        in source
    )
    assert (
        'provider.scheme == "file-secret"'
        in source
    )
    assert 'os.name == "nt"' in source



def test_v0293_phase3_sync_boundary_is_preserved_under_successor():
    policy = load_policy(ROOT)
    section = policy["sandbox_workspace_runtime_profile_policy"]

    for key in (
        "sync_credential_boundary_enabled",
        "sync_credential_environment_projection_enabled",
        "async_credential_boundary_enabled",
        "async_credential_environment_projection_enabled",
        "credential_environment_projection_enabled",
        "credential_boundary_enabled",
        "credential_boundary_attested",
        "sync_credential_boundary_attested",
        "async_credential_boundary_attested",
    ):
        assert section[key] is True

    for key in (
        "credential_isolation_attested",
        "restricted_token_attested",
        "low_integrity_attested",
    ):
        assert section[key] is False

    current = (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()
    assert tuple(int(part) for part in current.split(".")) >= (0, 29, 3)
    assert CURRENT_SCHEMA_VERSION >= 62
