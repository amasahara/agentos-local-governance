"""
File: .agents/agentos/tool_runtime_profiles.py

Purpose:
    Provide the v0.29.2 preactivation foundation for deterministic tool runtime
    profiles and Windows-oriented sandbox workspace layout.

Scope:
    This module prepares workspace/profile contracts only. It does not claim
    restricted-token execution, Low Integrity, arbitrary host containment, or
    general OS process isolation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

RUNTIME_PROFILE_VERSION = 1
SANDBOX_WORKSPACE_VERSION = 1
SANDBOX_SCOPE = "agentos_mediated_process_execution"

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
_COPY_EXCLUDES = {".agents", ".git", "__pycache__"}

_DEFAULT_RUNTIME_PROFILES: dict[str, dict[str, Any]] = {
    "inspect": {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": "inspect",
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    },
    "test": {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": "test",
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    },
    "build": {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": "build",
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    },
}


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha(value: Any) -> str:
    payload = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_key(value: str, *, label: str) -> str:
    key = str(value or "").strip()
    if not _SAFE_KEY.fullmatch(key) or key in {".", ".."}:
        raise ValueError(f"unsafe_{label}")
    return key


def _reparse_kind(path: Path) -> str | None:
    """Return link/reparse kind without following the filesystem object."""
    if path.is_symlink():
        return "symlink"

    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return "junction"
        except OSError:
            pass

    try:
        info = os.lstat(path)
    except OSError:
        return None

    attributes = int(
        getattr(
            info,
            "st_file_attributes",
            0,
        )
        or 0
    )
    reparse_flag = int(
        getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
    )

    if attributes & reparse_flag:
        return "reparse_point"

    return None


def _assert_not_reparse(
    path: Path,
    *,
    label: str,
) -> None:
    kind = _reparse_kind(path)
    if kind is not None:
        raise RuntimeError(
            f"{label}_reparse_forbidden:"
            f"{kind}:"
            f"{path.name}"
        )


def _bounded_destination(
    root: Path,
    name: str,
) -> Path:
    """
    Build exactly one child path beneath the snapshot root.

    The helper is intentionally stricter than Path.relative_to(): paths such
    as ``root / "../escape"`` are lexically below ``root`` before
    normalization, so a relative_to-only check is insufficient.
    """
    child = Path(name)

    if (
        child.is_absolute()
        or len(child.parts) != 1
        or child.parts[0] in {"", ".", ".."}
    ):
        raise RuntimeError(
            "sandbox_snapshot_destination_escape"
        )

    destination = root / child

    base_resolved = root.resolve(
        strict=False
    )
    destination_resolved = destination.resolve(
        strict=False
    )

    try:
        destination_resolved.relative_to(
            base_resolved
        )
    except ValueError as exc:
        raise RuntimeError(
            "sandbox_snapshot_destination_escape"
        ) from exc

    return destination


def default_runtime_profiles() -> dict[str, dict[str, Any]]:
    """Return a deep data copy of the built-in v0.29.2 profile registry."""
    return json.loads(json.dumps(_DEFAULT_RUNTIME_PROFILES))


def _validate_profile(
    name: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise RuntimeError("tool_runtime_profile_must_be_object")

    expected = {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": name,
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    }

    mismatches = {
        key: {
            "expected": value,
            "actual": profile.get(key),
        }
        for key, value in expected.items()
        if profile.get(key) != value
    }

    if mismatches:
        raise RuntimeError(
            "tool_runtime_profile_invariant_mismatch:"
            + _canonical(mismatches)
        )

    return dict(profile)


def resolve_runtime_profile(
    command_profile: str,
    configured_profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve one runtime profile from the internally selected command profile.

    Caller-supplied runtime-profile override is intentionally not accepted.
    """
    name = str(command_profile or "").strip().lower()
    if name not in _DEFAULT_RUNTIME_PROFILES:
        raise RuntimeError(
            "tool_runtime_profile_unknown_command_profile:"
            + name
        )

    registry = default_runtime_profiles()

    if configured_profiles is not None:
        if not isinstance(configured_profiles, dict):
            raise RuntimeError(
                "tool_runtime_profile_registry_must_be_object"
            )
        for key, value in configured_profiles.items():
            if key not in registry:
                raise RuntimeError(
                    "tool_runtime_profile_unknown_configured_profile:"
                    + str(key)
                )
            if not isinstance(value, dict):
                raise RuntimeError(
                    "tool_runtime_profile_must_be_object"
                )
            merged = dict(registry[key])
            merged.update(value)
            registry[key] = merged

    profile = _validate_profile(
        name,
        registry[name],
    )

    return {
        "name": name,
        "profile_version": RUNTIME_PROFILE_VERSION,
        "profile": profile,
        "profile_hash": _sha(
            {
                "name": name,
                "profile": profile,
            }
        ),
        "scope": SANDBOX_SCOPE,
    }


def sandbox_base(primary_root: Path) -> Path:
    """
    Return the project-specific sandbox base outside the governed repository.

    The physical separation is a workspace boundary only. It is not an OS ACL
    or token isolation claim.
    """
    root = primary_root.resolve()
    digest = _sha(str(root))[:12]
    return (
        root.parent
        / f".{root.name}.agentos-sandboxes"
        / digest
    ).resolve()


def sandbox_layout(
    primary_root: Path,
    task_id: str,
    session_id: str,
    execution_id: str,
    command_profile: str,
) -> dict[str, Path | str]:
    task = _safe_key(task_id, label="task_id")
    session = _safe_key(session_id, label="session_id")
    execution = _safe_key(
        execution_id,
        label="execution_id",
    )
    profile = _safe_key(
        command_profile,
        label="command_profile",
    )

    root = (
        sandbox_base(primary_root)
        / task
        / session
        / execution
    ).resolve()

    return {
        "root": root,
        "workspace": root / "workspace",
        "home": root / "home",
        "temp": root / "temp",
        "cache": root / "cache",
        "logs": root / "logs",
        "command_profile": profile,
    }


def _copy_snapshot_tree(
    source: Path,
    target: Path,
) -> None:
    """
    Copy one source tree without following symlinks, junctions, or reparse
    points.
    """
    _assert_not_reparse(
        source,
        label="sandbox_source",
    )

    target.mkdir(
        parents=True,
        exist_ok=False,
    )

    for entry in source.iterdir():
        if entry.name in _COPY_EXCLUDES:
            continue

        _assert_not_reparse(
            entry,
            label="sandbox_source_entry",
        )

        destination = _bounded_destination(
            target,
            entry.name,
        )

        if entry.is_dir():
            _copy_snapshot_tree(
                entry,
                destination,
            )
        elif entry.is_file():
            shutil.copy2(
                entry,
                destination,
            )


def create_sandbox_workspace(
    primary_root: Path,
    source_root: Path,
    task_id: str,
    session_id: str,
    execution_id: str,
    command_profile: str,
) -> dict[str, Any]:
    """
    Materialize a deterministic sandbox layout and source snapshot.

    source_root is expected to have already been resolved by AgentOS against
    the governed primary root or an exact bound worker worktree.
    """
    primary = primary_root.resolve()

    _assert_not_reparse(
        source_root,
        label="sandbox_source_root",
    )

    source = source_root.resolve()

    if not source.is_dir():
        raise RuntimeError(
            "sandbox_source_root_missing"
        )

    primary_agents = (
        primary
        / ".agents"
    ).resolve()

    try:
        source.relative_to(
            primary_agents
        )
    except ValueError:
        pass
    else:
        raise RuntimeError(
            "sandbox_source_must_not_be_agentos_managed_root"
        )

    resolved = resolve_runtime_profile(
        command_profile
    )
    layout = sandbox_layout(
        primary,
        task_id,
        session_id,
        execution_id,
        command_profile,
    )

    root = Path(layout["root"])

    if root.exists():
        raise FileExistsError(
            "sandbox_workspace_already_exists"
        )

    root.mkdir(
        parents=True,
        exist_ok=False,
    )

    try:
        for name in (
            "home",
            "temp",
            "cache",
            "logs",
        ):
            Path(layout[name]).mkdir(
                parents=True,
                exist_ok=False,
            )

        _copy_snapshot_tree(
            source,
            Path(layout["workspace"]),
        )
    except Exception:
        shutil.rmtree(
            root,
            ignore_errors=True,
        )
        raise

    snapshot_hash = sandbox_workspace_hash(
        Path(layout["workspace"])
    )

    return {
        "sandbox_version": SANDBOX_WORKSPACE_VERSION,
        "scope": SANDBOX_SCOPE,
        "profile_name": resolved["name"],
        "profile_hash": resolved["profile_hash"],
        "profile_version": resolved["profile_version"],
        "root": str(root),
        "workspace": str(layout["workspace"]),
        "home": str(layout["home"]),
        "temp": str(layout["temp"]),
        "cache": str(layout["cache"]),
        "logs": str(layout["logs"]),
        "snapshot_hash": snapshot_hash,
        "source_root_hash": _sha(
            str(source)
        ),
        "primary_root_hash": _sha(
            str(primary)
        ),
    }


def _snapshot_hash_tree(
    root: Path,
    current: Path,
    digest,
) -> None:
    for entry in sorted(
        current.iterdir(),
        key=lambda item: item.name,
    ):
        _assert_not_reparse(
            entry,
            label="sandbox_snapshot_entry",
        )

        relative = entry.relative_to(
            root
        ).as_posix()

        if entry.is_dir():
            digest.update(
                b"D\0"
            )
            digest.update(
                relative.encode(
                    "utf-8"
                )
            )
            digest.update(
                b"\0"
            )
            _snapshot_hash_tree(
                root,
                entry,
                digest,
            )
        elif entry.is_file():
            digest.update(
                b"F\0"
            )
            digest.update(
                relative.encode(
                    "utf-8"
                )
            )
            digest.update(
                b"\0"
            )

            with entry.open(
                "rb"
            ) as handle:
                while True:
                    chunk = handle.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    digest.update(
                        chunk
                    )

            digest.update(
                b"\0"
            )


def sandbox_workspace_hash(
    workspace_root: Path,
) -> str:
    """
    Hash the materialized sandbox snapshot deterministically.

    The hash binds relative paths, entry types, and exact file bytes. Reparse
    points are rejected before traversal.
    """
    root = workspace_root.resolve()

    if not root.is_dir():
        raise RuntimeError(
            "sandbox_workspace_missing"
        )

    _assert_not_reparse(
        workspace_root,
        label="sandbox_workspace_root",
    )

    digest = hashlib.sha256()
    _snapshot_hash_tree(
        root,
        root,
        digest,
    )
    return digest.hexdigest()


def build_runtime_environment(
    base_env: dict[str, str],
    sandbox: dict[str, Any],
) -> dict[str, str]:
    """
    Redirect tool-local mutable runtime paths into the sandbox.

    Credential filtering remains the responsibility of the existing AgentOS
    environment filter until the dedicated credential-boundary release.
    """
    env = {
        str(key): str(value)
        for key, value in base_env.items()
    }

    home = str(sandbox["home"])
    temp = str(sandbox["temp"])
    cache = str(sandbox["cache"])

    env.update(
        {
            "HOME": home,
            "USERPROFILE": home,
            "TMP": temp,
            "TEMP": temp,
            "TMPDIR": temp,
            "XDG_CACHE_HOME": cache,
            "PIP_CACHE_DIR": str(
                Path(cache)
                / "pip"
            ),
            "npm_config_cache": str(
                Path(cache)
                / "npm"
            ),
            "PYTHONPYCACHEPREFIX": str(
                Path(cache)
                / "pycache"
            ),
        }
    )

    return env


def cleanup_sandbox_workspace(
    primary_root: Path,
    sandbox_root: Path,
) -> None:
    """
    Remove one sandbox only when it is inside the project-specific sandbox base.
    """
    base = sandbox_base(
        primary_root
    )
    target = sandbox_root.resolve()

    try:
        target.relative_to(base)
    except ValueError as exc:
        raise RuntimeError(
            "sandbox_cleanup_path_escape"
        ) from exc

    if target == base:
        raise RuntimeError(
            "sandbox_cleanup_base_forbidden"
        )

    shutil.rmtree(
        target,
        ignore_errors=False,
    )

    # Prune empty execution scaffolding without touching active sibling
    # sandboxes. rmdir() fails safely when a directory is not empty.
    container = base.parent
    candidate = target.parent

    while True:
        if candidate == container.parent:
            break

        try:
            candidate.relative_to(
                container
            )
        except ValueError:
            break

        try:
            candidate.rmdir()
        except OSError:
            break

        if candidate == container:
            break

        candidate = candidate.parent
