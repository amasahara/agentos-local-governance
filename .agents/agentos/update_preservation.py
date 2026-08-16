"""Path: .agents/agentos/update_preservation.py
Purpose: Ownership classification and fail-closed hash gates for AgentOS updates.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Iterable

PROJECT_OWNED_PATTERNS = (
    "AGENTS.md",
    ".agents/config/governance.local.json",
    ".agents/config/project.id",
    ".agents/config/project.purpose.json",
    ".agents/architecture/**",
    ".agents/state/**",
    ".agents/runtime/**",
    ".agents/cache/**",
    ".agents/skills/**",
    ".agents/workflows/**",
)


def sha256_file(path: Path) -> str:
    """Return SHA-256 of one file without mutating it."""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_rel(relative_path: str) -> str:
    rel = relative_path.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def is_project_owned(relative_path: str) -> bool:
    """Return whether a path is explicitly owned by the consuming project/user."""
    rel = _normalize_rel(relative_path)
    return any(fnmatch.fnmatch(rel, pattern) for pattern in PROJECT_OWNED_PATTERNS)


def classify_path(relative_path: str, baseline_manifest_paths: Iterable[str]) -> str:
    """Classify a path as PROJECT_OWNED or DISTRIBUTION_MANAGED.

    Unknown paths are project-owned by default. A known distribution path is managed only
    when it is not in the explicit project-owned set.
    """
    rel = _normalize_rel(relative_path)
    if is_project_owned(rel):
        return "PROJECT_OWNED"
    known = {_normalize_rel(p) for p in baseline_manifest_paths}
    return "DISTRIBUTION_MANAGED" if rel in known else "PROJECT_OWNED"


def snapshot_paths(root: Path, relative_paths: Iterable[str]) -> dict[str, str | None]:
    """Snapshot selected project-owned paths as hash-or-absence."""
    result: dict[str, str | None] = {}
    for rel in sorted(set(relative_paths)):
        path = root / rel
        result[rel] = sha256_file(path) if path.is_file() else None
    return result


def verify_snapshot_unchanged(root: Path, before: dict[str, str | None]) -> list[str]:
    """Return paths whose bytes/absence differ from the pre-update snapshot."""
    changed: list[str] = []
    for rel, expected in sorted(before.items()):
        path = root / rel
        actual = sha256_file(path) if path.is_file() else None
        if actual != expected:
            changed.append(rel)
    return changed


def verify_distribution_hashes(root: Path, expected_hashes: dict[str, str], paths_to_replace: Iterable[str]) -> list[dict[str, str | None]]:
    """Fail-closed preflight for distribution-managed files before replacement."""
    conflicts: list[dict[str, str | None]] = []
    for rel in sorted(set(paths_to_replace)):
        expected = expected_hashes.get(rel)
        path = root / rel
        actual = sha256_file(path) if path.is_file() else None
        if expected is None or actual != expected:
            conflicts.append({"path": rel, "expected": expected, "actual": actual})
    return conflicts


def load_distribution_lock(root: Path) -> dict[str, object]:
    """Load the internal AgentOS distribution ownership lock.

    The lock is metadata for future AgentOS updates, not project architecture authority.
    """
    path = root / ".agents/config/agentos_distribution.lock.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("managed_files"), list):
        raise ValueError("invalid_agentos_distribution_lock")
    return value


def distribution_hashes_from_lock(root: Path) -> dict[str, str]:
    """Return path->SHA256 for distribution-managed files in the internal update lock."""
    value = load_distribution_lock(root)
    result: dict[str, str] = {}
    for item in value["managed_files"]:
        if not isinstance(item, dict):
            raise ValueError("invalid_agentos_distribution_lock_entry")
        rel = _normalize_rel(str(item.get("path") or ""))
        digest = str(item.get("sha256") or "")
        if not rel or len(digest) != 64 or is_project_owned(rel):
            raise ValueError("invalid_agentos_distribution_lock_entry")
        result[rel] = digest
    return result


def verify_distribution_lock(root: Path) -> list[dict[str, str | None]]:
    """Verify every managed file against the last installed distribution lock."""
    expected = distribution_hashes_from_lock(root)
    return verify_distribution_hashes(root, expected, expected)
