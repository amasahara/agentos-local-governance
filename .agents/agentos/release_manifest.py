"""
File: .agents/agentos/release_manifest.py

Purpose:
    Provide in-process release manifest verification for CLI and tooling.

Responsibilities:
    - Recompute authoritative file hashes and sizes.
    - Cross-check MANIFEST.json with CHECKSUMS.sha256.
    - Reject missing or unexpected authoritative files.
"""
from __future__ import annotations

import hashlib
import fnmatch
import json
from pathlib import Path
from typing import Any

EXCLUDE = {"MANIFEST.json", "CHECKSUMS.sha256"}
EXCLUDE_PREFIXES = (".git/", ".agents/runtime/", ".agents/state/", ".agents/cache/", ".pytest_cache/", ".vscode/", ".idea/")
EXCLUDE_PARTS = {"__pycache__"}
EXCLUDE_GLOBS = (
    "apply_v*.py",
    "apply_v*.py.sha256",
    "tools/apply_v*.py",
    "tools/validate_v*.py",
    "CHECKSUMS_V*.sha256",
    "VALIDATION_REPORT*.json",
    "*.zip",
    "*.zip.sha256",
    ".agents/bin/agentos.v*",
    ".agents/bin/agentos-mcp.v*",
    ".agents/docs/RELEASE_NOTES_V*.md",
    ".agents/docs/USAGE_V*.md",
    ".agents/docs/GITHUB_READY_FULL_RELEASE_V*.md",
    ".agents/docs/archive/*",
    ".agents/docs/archive/**",
)

def _excluded_local_release_artifact(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in EXCLUDE_GLOBS)


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _candidate_files(root: Path) -> set[str]:
    out: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in EXCLUDE or rel.startswith(EXCLUDE_PREFIXES):
            continue
        if any(part in EXCLUDE_PARTS for part in path.relative_to(root).parts) or rel.endswith(".pyc"):
            continue
        if _excluded_local_release_artifact(rel):
            continue
        out.add(rel)
    return out


def verify_manifest(root: Path) -> dict[str, Any]:
    """Verify MANIFEST.json and CHECKSUMS.sha256 against the filesystem."""
    root = root.resolve()
    manifest_path = root / "MANIFEST.json"
    checksums_path = root / "CHECKSUMS.sha256"
    if not manifest_path.exists() or not checksums_path.exists():
        return {"ok": False, "findings": [{"code": "missing_manifest_files", "message": "MANIFEST.json and CHECKSUMS.sha256 are required"}]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {item["path"]: item for item in manifest.get("files", [])}
    checksum_entries: dict[str, str] = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, rel = line.split(None, 1)
            checksum_entries[rel.strip()] = digest
    findings: list[dict[str, Any]] = []
    for rel, entry in sorted(entries.items()):
        path = root / rel
        if not path.is_file():
            findings.append({"code": "missing_file", "path": rel})
            continue
        digest = _hash(path)
        if digest != entry.get("sha256"):
            findings.append({"code": "manifest_hash_mismatch", "path": rel})
        if path.stat().st_size != entry.get("size"):
            findings.append({"code": "manifest_size_mismatch", "path": rel})
        if checksum_entries.get(rel) != digest:
            findings.append({"code": "checksum_mismatch", "path": rel})
    if set(entries) != set(checksum_entries):
        findings.append({"code": "manifest_checksum_set_mismatch", "message": "manifest/checksum path sets differ"})
    unexpected = sorted(_candidate_files(root) - set(entries))
    if unexpected:
        findings.append({"code": "unexpected_files", "paths": unexpected[:100]})
    return {"ok": not findings, "release": manifest.get("release"), "kind": manifest.get("kind"), "file_count": len(entries), "findings": findings}
