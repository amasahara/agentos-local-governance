#!/usr/bin/env python3
"""
File: tools/build_manifest.py

Purpose:
    Synchronize release package metadata, then build deterministic MANIFEST.json
    and CHECKSUMS.sha256 from the current authoritative source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from verify_manifest import _candidate_files


def digest(path: Path) -> str:
    """Return the SHA-256 digest of one file."""

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _write_text_lf(path: Path, text: str) -> None:
    """Write UTF-8 text with deterministic LF newlines on every platform."""

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _load_package(path: Path) -> dict[str, object]:
    """Load the existing package-completeness object without silently accepting non-objects."""

    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError("PACKAGE_COMPLETENESS.json root must be an object")
    return value


def _sync_package_completeness(root: Path, *, release: str, schema: int) -> None:
    """Synchronize generated package identity before release-file hashes are calculated."""

    path = root / "PACKAGE_COMPLETENESS.json"
    package = _load_package(path)
    required = package.get("required_top_level")
    if not isinstance(required, list):
        required = []
    required = [str(item) for item in required if str(item) != "VALIDATION_REPORT.json"]
    for rel in (
        "VERSION",
        "AGENTS.md",
        "README.md",
        "README.vi.md",
        "README.en.md",
        "huong_dan.md",
        "huong_dan.vi.md",
        "huong_dan.en.md",
        "CHANGELOG.md",
        "RELEASE_NOTES.md",
        "MANIFEST.json",
        "CHECKSUMS.sha256",
        "PACKAGE_COMPLETENESS.json",
    ):
        if rel not in required:
            required.append(rel)
    package["release"] = release
    package["schema"] = int(schema)
    package["coherence_contract_version"] = 1
    package["required_top_level"] = required
    # Candidate membership does not depend on PACKAGE_COMPLETENESS contents, so this
    # count is stable before the package file itself is re-hashed below.
    package["authoritative_file_count"] = len(_candidate_files(root))
    _write_text_lf(path, json.dumps(package, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    """Build coherent release package metadata and deterministic hash artifacts."""

    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--kind", default="full")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / ".agents"))
    from agentos.schema_version import CURRENT_SCHEMA_VERSION

    release = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not release:
        raise SystemExit("VERSION must be non-empty")
    _sync_package_completeness(root, release=release, schema=int(CURRENT_SCHEMA_VERSION))

    files = []
    for rel in sorted(_candidate_files(root)):
        path = root / rel
        files.append({"path": rel, "size": path.stat().st_size, "sha256": digest(path)})
    manifest = {
        "release": release,
        "kind": args.kind,
        "file_count": len(files),
        "files": files,
    }
    _write_text_lf(
        root / "MANIFEST.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    _write_text_lf(
        root / "CHECKSUMS.sha256",
        "".join(f"{item['sha256']}  {item['path']}\n" for item in files),
    )


if __name__ == "__main__":
    main()
