from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from agentos.tool_runtime_profiles import (
    SANDBOX_SCOPE,
    SANDBOX_WORKSPACE_VERSION,
    build_runtime_environment,
    cleanup_sandbox_workspace,
    create_sandbox_workspace,
    default_runtime_profiles,
    resolve_runtime_profile,
    sandbox_base,
    sandbox_layout,
)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".agents").mkdir()
    return root


def test_v0292_runtime_profiles_are_data_only_and_hash_pinned():
    first = resolve_runtime_profile("test")
    second = resolve_runtime_profile("test")

    assert first == second
    assert first["profile_hash"] == second["profile_hash"]
    assert len(first["profile_hash"]) == 64
    assert first["scope"] == SANDBOX_SCOPE

    registry = default_runtime_profiles()

    assert set(registry) == {
        "inspect",
        "test",
        "build",
    }

    for name, item in registry.items():
        assert item["command_profile"] == name
        assert item["network_policy"] == "none"
        assert item["writable_scope"] == "sandbox_only"
        assert item["persistent_workspace_writes"] is False


def test_v0292_runtime_profile_caller_override_surface_does_not_exist():
    with pytest.raises(TypeError):
        resolve_runtime_profile(
            "test",
            configured_profiles=None,
            caller_profile="build",  # type: ignore[call-arg]
        )


def test_v0292_runtime_profile_unknown_or_weakened_profile_fails_closed():
    with pytest.raises(
        RuntimeError,
        match="unknown_command_profile",
    ):
        resolve_runtime_profile(
            "custom"
        )

    with pytest.raises(
        RuntimeError,
        match="invariant_mismatch",
    ):
        resolve_runtime_profile(
            "test",
            {
                "test": {
                    "network_policy": "allow",
                }
            },
        )


def test_v0292_sandbox_base_is_project_specific_and_outside_repo(
    tmp_path: Path,
):
    root = _root(tmp_path)
    base = sandbox_base(root)

    with pytest.raises(ValueError):
        base.relative_to(root)

    assert root.name in base.parent.name
    assert len(base.name) == 12


def test_v0292_sandbox_layout_is_deterministic_and_bounded(
    tmp_path: Path,
):
    root = _root(tmp_path)

    first = sandbox_layout(
        root,
        "task-1",
        "session-1",
        "exec-1",
        "test",
    )
    second = sandbox_layout(
        root,
        "task-1",
        "session-1",
        "exec-1",
        "test",
    )

    assert first == second

    base = sandbox_base(root)
    Path(first["root"]).relative_to(base)

    for name in (
        "workspace",
        "home",
        "temp",
        "cache",
        "logs",
    ):
        Path(first[name]).relative_to(
            Path(first["root"])
        )


def test_v0292_workspace_snapshot_excludes_agentos_and_git(
    tmp_path: Path,
):
    root = _root(tmp_path)
    (root / ".git").mkdir()
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text(
        "print('ok')\n",
        encoding="utf-8",
    )
    (root / ".agents" / "secret.txt").write_text(
        "not copied",
        encoding="utf-8",
    )
    (root / ".git" / "config").write_text(
        "not copied",
        encoding="utf-8",
    )

    sandbox = create_sandbox_workspace(
        root,
        root,
        "task-1",
        "session-1",
        "exec-1",
        "test",
    )

    workspace = Path(
        sandbox["workspace"]
    )

    assert (
        workspace
        / "src"
        / "a.py"
    ).is_file()
    assert not (
        workspace
        / ".agents"
    ).exists()
    assert not (
        workspace
        / ".git"
    ).exists()
    assert sandbox["sandbox_version"] == SANDBOX_WORKSPACE_VERSION
    assert sandbox["scope"] == SANDBOX_SCOPE

    cleanup_sandbox_workspace(
        root,
        Path(sandbox["root"]),
    )


def test_v0292_runtime_environment_redirects_mutable_tool_paths(
    tmp_path: Path,
):
    root = _root(tmp_path)
    sandbox = create_sandbox_workspace(
        root,
        root,
        "task-1",
        "session-1",
        "exec-env",
        "build",
    )

    env = build_runtime_environment(
        {
            "PATH": os.environ.get(
                "PATH",
                "",
            ),
            "LANG": "C.UTF-8",
        },
        sandbox,
    )

    assert env["HOME"] == sandbox["home"]
    assert env["USERPROFILE"] == sandbox["home"]
    assert env["TMP"] == sandbox["temp"]
    assert env["TEMP"] == sandbox["temp"]
    assert env["TMPDIR"] == sandbox["temp"]

    cache = Path(
        sandbox["cache"]
    )

    assert Path(
        env["PIP_CACHE_DIR"]
    ).parent == cache
    assert Path(
        env["npm_config_cache"]
    ).parent == cache
    assert Path(
        env["PYTHONPYCACHEPREFIX"]
    ).parent == cache

    cleanup_sandbox_workspace(
        root,
        Path(sandbox["root"]),
    )


def test_v0292_cleanup_cannot_escape_project_sandbox_base(
    tmp_path: Path,
):
    root = _root(tmp_path)

    with pytest.raises(
        RuntimeError,
        match="cleanup_path_escape",
    ):
        cleanup_sandbox_workspace(
            root,
            tmp_path,
        )


def test_v0292_source_under_agentos_is_rejected(
    tmp_path: Path,
):
    root = _root(tmp_path)
    source = root / ".agents" / "runtime"
    source.mkdir(
        parents=True,
    )

    with pytest.raises(
        RuntimeError,
        match="must_not_be_agentos_managed_root",
    ):
        create_sandbox_workspace(
            root,
            source,
            "task-1",
            "session-1",
            "exec-2",
            "inspect",
        )

def test_v0292_source_root_symlink_is_rejected_before_resolve(
    tmp_path: Path,
):
    root = _root(tmp_path)
    real = tmp_path / "real-source"
    real.mkdir()
    (real / "a.txt").write_text(
        "content\n",
        encoding="utf-8",
    )
    link = tmp_path / "source-link"

    try:
        link.symlink_to(
            real,
            target_is_directory=True,
        )
    except (OSError, NotImplementedError):
        pytest.skip(
            "directory symlink creation unavailable"
        )

    with pytest.raises(
        RuntimeError,
        match="source_root_reparse_forbidden",
    ):
        create_sandbox_workspace(
            root,
            link,
            "task-1",
            "session-1",
            "exec-symlink",
            "inspect",
        )


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows junction/reparse contract",
)
def test_v0292_windows_junction_inside_snapshot_is_rejected(
    tmp_path: Path,
):
    root = _root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(
        "must not traverse\n",
        encoding="utf-8",
    )

    junction = root / "junction-out"

    result = subprocess.run(
        [
            "cmd",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(junction),
            str(outside),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        pytest.skip(
            "Windows junction creation unavailable: "
            + result.stderr.strip()
        )

    with pytest.raises(
        RuntimeError,
        match="reparse_forbidden",
    ):
        create_sandbox_workspace(
            root,
            root,
            "task-1",
            "session-1",
            "exec-junction",
            "test",
        )


def test_v0292_snapshot_destination_builder_is_bounded():
    import agentos.tool_runtime_profiles as profiles

    root = Path("sandbox-root")

    normal = profiles._bounded_destination(
        root,
        "src",
    )
    assert normal == root / "src"

    with pytest.raises(
        RuntimeError,
        match="destination_escape",
    ):
        profiles._bounded_destination(
            root,
            "../escape",
        )
