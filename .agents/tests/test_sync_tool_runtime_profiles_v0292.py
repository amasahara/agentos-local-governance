from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentos import multi_agent_workspace
from agentos import proxy
from agentos.tool_runtime_profiles import (
    resolve_runtime_profile,
    sandbox_base,
)


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.calls.append(
            (
                str(sql),
                tuple(params),
            )
        )
        return None


def _metadata(profile_name: str = "test") -> dict:
    resolved = resolve_runtime_profile(
        profile_name
    )

    return {
        "command_profile": profile_name,
        "runtime_profile": resolved["name"],
        "runtime_profile_hash": resolved["profile_hash"],
        "runtime_profile_version": resolved["profile_version"],
        "runtime_profile_scope": resolved["scope"],
        "cwd": ".",
        "sandbox_profile": "tool-runtime-profile-v1",
        "host_filesystem_isolation_attested": False,
        "os_write_confinement_attested": False,
    }


def _policy() -> dict:
    return {
        "proxy_policy": {
            "process_exec": {
                "max_timeout_seconds": 600,
                "max_output_bytes": 65536,
            }
        }
    }


def test_v0292_sync_proxy_source_uses_runtime_profile_sandbox():
    source = Path(
        proxy.__file__
    ).read_text(
        encoding="utf-8"
    )

    # Phase 2 keeps the helper only as an async compatibility bridge.
    # The synchronous adapter itself must not call it.
    start = source.index("def _execute_adapter(")
    end = source.find("\ndef ", start + 1)
    adapter_source = (
        source[start:]
        if end < 0
        else source[start:end]
    )
    assert "_isolated_workspace(" not in adapter_source
    assert "create_sandbox_workspace(" in source
    assert "build_runtime_environment(" in source
    assert "cleanup_sandbox_workspace(" in source
    assert "runtime_profile_hash" in source
    assert "tool-runtime-profile-v1" in source


def test_v0292_sync_preflight_binds_command_profile_to_runtime_profile(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()

    monkeypatch.setattr(
        proxy,
        "drift_check",
        lambda *args, **kwargs: {
            "baseline_state": "initialized",
            "drift_detected": False,
        },
    )
    monkeypatch.setattr(
        proxy,
        "local_override_status",
        lambda *args, **kwargs: {
            "sensitive": False,
            "status": "none",
        },
    )
    monkeypatch.setattr(
        proxy,
        "load_policy",
        lambda *args, **kwargs: {
            "proxy_policy": {
                "block_on_uninitialized_baseline": True,
                "block_on_drift": True,
                "process_exec": {
                    "allowed_executables": ["python"],
                    "denied_executables": [],
                    "allowed_python_modules": ["pytest"],
                    "require_known_command_profile": True,
                },
            }
        },
    )
    monkeypatch.setattr(
        proxy,
        "_steps",
        lambda *args, **kwargs: {
            "approve_task": "done",
            "prepare_change": "done",
        },
    )
    monkeypatch.setattr(
        multi_agent_workspace,
        "workspace_execution_root",
        lambda *args, **kwargs: root,
    )
    monkeypatch.setattr(
        multi_agent_workspace,
        "workspace_binding",
        lambda *args, **kwargs: None,
    )

    metadata = proxy._preflight(
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
        },
    )

    resolved = resolve_runtime_profile(
        "test"
    )

    assert metadata["command_profile"] == "test"
    assert metadata["runtime_profile"] == "test"
    assert (
        metadata["runtime_profile_hash"]
        == resolved["profile_hash"]
    )
    assert (
        metadata["sandbox_profile"]
        == "tool-runtime-profile-v1"
    )
    assert (
        metadata["host_filesystem_isolation_attested"]
        is False
    )
    assert (
        metadata["os_write_confinement_attested"]
        is False
    )


def test_v0292_sync_execution_runs_from_external_sandbox_and_redirects_env(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()
    (root / "source.txt").write_text(
        "hello\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        proxy,
        "load_policy",
        lambda *args, **kwargs: _policy(),
    )
    monkeypatch.setattr(
        multi_agent_workspace,
        "workspace_execution_root",
        lambda *args, **kwargs: root,
    )

    fake_db = _FakeConnection()

    monkeypatch.setattr(
        proxy,
        "connect",
        lambda *args, **kwargs: fake_db,
    )

    calls: list[dict] = []

    def fake_run(
        command,
        *,
        cwd,
        env,
        timeout,
    ):
        calls.append(
            {
                "command": list(command),
                "cwd": Path(cwd),
                "env": dict(env),
                "timeout": timeout,
            }
        )
        assert (
            Path(cwd)
            / "source.txt"
        ).is_file()

        return (
            SimpleNamespace(
                returncode=0,
                stdout="ok",
                stderr="",
            ),
            {
                "process_tree_contained": True,
                "process_tree_containment_profile": "test-containment",
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
        _metadata("test"),
    )

    assert success is True
    assert output["exit_code"] == 0
    assert output["runtime_profile"] == "test"
    assert (
        output["runtime_profile_hash"]
        == resolve_runtime_profile(
            "test"
        )["profile_hash"]
    )
    assert (
        output["host_filesystem_isolation_attested"]
        is False
    )
    assert (
        output["os_write_confinement_attested"]
        is False
    )

    assert len(calls) == 1
    call = calls[0]

    with pytest.raises(ValueError):
        call["cwd"].relative_to(root)

    assert (
        call["env"]["HOME"]
        == call["env"]["USERPROFILE"]
    )
    assert (
        Path(call["env"]["HOME"]).parent
        == call["cwd"].parent
    )
    assert (
        Path(call["env"]["TEMP"]).parent
        == call["cwd"].parent
    )
    assert (
        Path(call["env"]["PIP_CACHE_DIR"]).parents[1]
        == call["cwd"].parent
    )

    assert not call["cwd"].exists()

    assert any(
        "INSERT INTO execution_manifests"
        in sql
        for sql, _ in fake_db.calls
    )


def test_v0292_sync_runtime_profile_hash_drift_fails_closed(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()

    monkeypatch.setattr(
        proxy,
        "load_policy",
        lambda *args, **kwargs: _policy(),
    )
    monkeypatch.setattr(
        multi_agent_workspace,
        "workspace_execution_root",
        lambda *args, **kwargs: root,
    )

    metadata = _metadata("test")
    metadata["runtime_profile_hash"] = "0" * 64

    with pytest.raises(
        RuntimeError,
        match="runtime_profile_hash_drift",
    ):
        proxy._execute_adapter(
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
            metadata,
        )


def test_v0292_sync_sandbox_is_cleaned_when_runner_raises(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()
    (root / "source.txt").write_text(
        "hello\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        proxy,
        "load_policy",
        lambda *args, **kwargs: _policy(),
    )
    monkeypatch.setattr(
        multi_agent_workspace,
        "workspace_execution_root",
        lambda *args, **kwargs: root,
    )

    captured: dict[str, Path] = {}
    real_create = proxy.create_sandbox_workspace

    def capture_create(*args, **kwargs):
        result = real_create(
            *args,
            **kwargs,
        )
        captured["root"] = Path(
            result["root"]
        )
        return result

    monkeypatch.setattr(
        proxy,
        "create_sandbox_workspace",
        capture_create,
    )

    def fail_run(*args, **kwargs):
        raise RuntimeError(
            "synthetic_runner_failure"
        )

    monkeypatch.setattr(
        proxy,
        "_run_process_command",
        fail_run,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic_runner_failure",
    ):
        proxy._execute_adapter(
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
            _metadata("test"),
        )

    assert "root" in captured
    assert not captured["root"].exists()


def test_v0292_sync_cleanup_prunes_empty_sandbox_scaffolding(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()

    monkeypatch.setattr(
        proxy,
        "load_policy",
        lambda *args, **kwargs: _policy(),
    )
    monkeypatch.setattr(
        multi_agent_workspace,
        "workspace_execution_root",
        lambda *args, **kwargs: root,
    )
    monkeypatch.setattr(
        proxy,
        "connect",
        lambda *args, **kwargs: _FakeConnection(),
    )
    monkeypatch.setattr(
        proxy,
        "_run_process_command",
        lambda *args, **kwargs: (
            SimpleNamespace(
                returncode=0,
                stdout="",
                stderr="",
            ),
            {
                "process_tree_contained": True,
                "process_tree_containment_profile": "test",
                "process_tree_containment_scope": (
                    "agentos_mediated_process_execution"
                ),
            },
        ),
    )

    base = sandbox_base(root)

    success, _ = proxy._execute_adapter(
        root,
        "task-clean",
        "session-clean",
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
        _metadata("test"),
    )

    assert success is True
    assert not base.exists()
