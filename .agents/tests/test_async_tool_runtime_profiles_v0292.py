from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agentos import jobs
from agentos import proxy
from agentos.tool_runtime_profiles import (
    build_runtime_environment,
    cleanup_sandbox_workspace,
    create_sandbox_workspace,
    resolve_runtime_profile,
    sandbox_workspace_hash,
)


def _make_spec(
    root: Path,
    *,
    profile_name: str = "test",
) -> tuple[dict, dict[str, str]]:
    source = root / "source"
    source.mkdir()
    (source / "sample.txt").write_text(
        "hello\n",
        encoding="utf-8",
    )

    sandbox = create_sandbox_workspace(
        root,
        source,
        "task-1",
        "session-1",
        "job-1",
        profile_name,
    )

    clean_env = jobs._filtered_env({})
    clean_env.pop(
        "PYTHONPATH",
        None,
    )
    launch_env = build_runtime_environment(
        clean_env,
        sandbox,
    )

    resolved = resolve_runtime_profile(
        profile_name
    )

    spec = {
        "job_id": "job-1",
        "task_id": "task-1",
        "session_id": "session-1",
        "command": [
            "python",
            "-m",
            "pytest",
        ],
        "cwd": ".",
        "workspace": sandbox["workspace"],
        "timeout_seconds": 30,
        "profile": profile_name,
        "runtime_profile": resolved["name"],
        "runtime_profile_hash": resolved["profile_hash"],
        "runtime_profile_version": resolved["profile_version"],
        "runtime_profile_scope": resolved["scope"],
        "sandbox": sandbox,
        "snapshot_hash": sandbox["snapshot_hash"],
        "network_policy": "none",
        "environment_hash": hashlib.sha256(
            json.dumps(
                launch_env,
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }

    return spec, launch_env


def test_v0292_async_jobs_no_longer_import_legacy_workspace():
    jobs_source = Path(
        jobs.__file__
    ).read_text(
        encoding="utf-8"
    )
    proxy_source = Path(
        proxy.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert "_isolated_workspace" not in jobs_source
    assert "def _isolated_workspace(" not in proxy_source
    assert "create_sandbox_workspace(" in jobs_source
    assert "sandbox_workspace_hash(" in jobs_source
    assert "runtime_profile_hash" in jobs_source


def test_v0292_async_runtime_spec_current_snapshot_is_accepted(
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()

    spec, expected_env = _make_spec(
        root
    )

    launch_env, profile = (
        jobs._assert_async_runtime_spec_current(
            spec,
            {},
        )
    )

    assert launch_env == expected_env
    assert profile["name"] == "test"
    assert (
        profile["profile_hash"]
        == spec["runtime_profile_hash"]
    )

    cleanup_sandbox_workspace(
        root,
        Path(spec["sandbox"]["root"]),
    )


def test_v0292_async_snapshot_mutation_fails_closed(
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()

    spec, _ = _make_spec(
        root
    )

    workspace = Path(
        spec["workspace"]
    )
    (
        workspace / "sample.txt"
    ).write_text(
        "mutated\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match="sandbox_snapshot_hash_mismatch",
    ):
        jobs._assert_async_runtime_spec_current(
            spec,
            {},
        )

    cleanup_sandbox_workspace(
        root,
        Path(spec["sandbox"]["root"]),
    )


def test_v0292_async_runtime_profile_hash_drift_fails_closed(
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()

    spec, _ = _make_spec(
        root
    )
    spec[
        "runtime_profile_hash"
    ] = "0" * 64

    with pytest.raises(
        RuntimeError,
        match="runtime_profile_hash_drift",
    ):
        jobs._assert_async_runtime_spec_current(
            spec,
            {},
        )

    cleanup_sandbox_workspace(
        root,
        Path(spec["sandbox"]["root"]),
    )


def test_v0292_sandbox_workspace_hash_is_deterministic_and_mutation_sensitive(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "a.txt").write_text(
        "a\n",
        encoding="utf-8",
    )
    (workspace / "sub").mkdir()
    (
        workspace
        / "sub"
        / "b.txt"
    ).write_text(
        "b\n",
        encoding="utf-8",
    )

    first = sandbox_workspace_hash(
        workspace
    )
    second = sandbox_workspace_hash(
        workspace
    )

    assert first == second
    assert len(first) == 64

    (
        workspace
        / "sub"
        / "b.txt"
    ).write_text(
        "changed\n",
        encoding="utf-8",
    )

    third = sandbox_workspace_hash(
        workspace
    )

    assert third != first


def test_v0292_async_submit_source_pins_profile_and_snapshot_before_persist():
    source = Path(
        jobs.__file__
    ).read_text(
        encoding="utf-8"
    )

    submit_start = source.index(
        "def submit_job("
    )
    start_start = source.index(
        "\ndef start_job(",
        submit_start,
    )
    submit_source = source[
        submit_start:start_start
    ]

    assert (
        "job_id = uuid.uuid4().hex"
        in submit_source
    )
    assert (
        "create_sandbox_workspace("
        in submit_source
    )
    assert (
        '"runtime_profile_hash"'
        in submit_source
    )
    assert (
        '"snapshot_hash"'
        in submit_source
    )
    assert (
        '"sandbox"'
        in submit_source
    )
    assert (
        "build_runtime_environment("
        in submit_source
    )

def test_v0292_legacy_async_spec_without_runtime_profile_is_rejected(
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()

    source = root / "src"
    source.mkdir()

    spec = {
        "job_id": "legacy",
        "task_id": "T1",
        "session_id": "S1",
        "command": [
            "python",
            "-m",
            "pytest",
        ],
        "cwd": ".",
        "workspace": str(source),
        "timeout_seconds": 30,
        "profile": "test",
        "network_policy": "none",
        "environment_hash": hashlib.sha256(
            json.dumps(
                jobs._filtered_env({}),
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }

    with pytest.raises(
        RuntimeError,
        match="runtime_profile_hash_drift",
    ):
        jobs._assert_async_runtime_spec_current(
            spec,
            {},
        )
