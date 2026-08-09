#!/usr/bin/env python3
"""Apply the exact AgentOS v0.22.7 -> v0.23.0 upgrade overlay.

File: tools/apply_v0230.py

Purpose:
    Upgrade an exact v0.22.7 AgentOS repository to v0.23.0 while preserving
    all historical governance files and rebuilding target release integrity
    metadata after the change.

Responsibilities:
    - Fail closed unless VERSION/schema/runtime evidence matches v0.22.7.
    - Back up every replaced file before mutation.
    - Merge the v0.23.0 context transport policy without deleting old policy.
    - Install the v0.23.0 runtime, tests, docs, and validator in-process.
    - Rebuild full-target MANIFEST.json and CHECKSUMS.sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FROM = "0.22.7"
TO = "0.23.0"
SCHEMA_FROM = 43
SCHEMA_TO = 44

# Files are copied from the overlay only when they implement or document v0.23.0.
COPY_FILES = (
    ".agents/agentos/__init__.py",
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/context_transport.py",
    ".agents/agentos/context_transport_cli.py",
    ".agents/agentos/db.py",
    ".agents/agentos/mcp_catalog.py",
    ".agents/agentos/mcp_context_transport.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/policy.py",
    ".agents/agentos/release_integrity.py",
    ".agents/agentos/schema_version.py",
    ".agents/docs/PROJECT_STRUCTURE.md",
    ".agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ".agents/docs/USAGE.md",
    ".agents/tests/test_context_transport_v0230.py",
    ".agents/tests/test_data_subject_rights_v0227.py",
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "README.vi.md",
    "README.en.md",
    "RELEASE_NOTES.md",
    "UPGRADE_FROM_0.22.7.md",
    "VERSION",
    "huong_dan.md",
    "huong_dan.vi.md",
    "huong_dan.en.md",
    "VALIDATION_REPORT.json",
    "PACKAGE_COMPLETENESS.json",
    "CONTEXT_TRANSPORT_BENCHMARK.json",
    "tools/apply_v0230.py",
    "tools/validate_v0230.py",
    "tools/validate_release.py",
)

EXECUTABLE_FILES = {
    "tools/apply_v0230.py",
    "tools/validate_v0230.py",
    "tools/validate_release.py",
}

EXCLUDE_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "state", "runtime", "cache",
    "task-workspaces", "downloads", "exports", "validation-artifacts", "tool-artifacts",
}
EXCLUDE_FILES = {"MANIFEST.json", "CHECKSUMS.sha256"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_check(root: Path) -> dict[str, Any]:
    """Validate exact predecessor evidence before any write."""
    required = [
        root / "VERSION",
        root / ".agents/agentos/schema_version.py",
        root / ".agents/agentos/data_subject_rights.py",
        root / ".agents/agentos/cli_runtime.py",
        root / ".agents/agentos/mcp_catalog.py",
        root / ".agents/config/governance.json",
        root / "DATA_SUBJECT_RIGHTS.md",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError(f"v0.22.7 baseline is incomplete; missing: {missing}")

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if version != FROM:
        raise RuntimeError(f"refusing upgrade: VERSION must be {FROM}, got {version!r}")

    schema_text = (root / ".agents/agentos/schema_version.py").read_text(encoding="utf-8")
    if f"CURRENT_SCHEMA_VERSION = {SCHEMA_FROM}" not in schema_text:
        raise RuntimeError("refusing upgrade: schema_version.py is not schema 43")

    cli_text = (root / ".agents/agentos/cli_runtime.py").read_text(encoding="utf-8")
    mcp_text = (root / ".agents/agentos/mcp_catalog.py").read_text(encoding="utf-8")
    if "data_subject_rights_cli" not in cli_text or "mcp_data_subject_rights" not in mcp_text:
        raise RuntimeError("refusing upgrade: v0.22.7 privacy runtime evidence is missing")
    if (root / ".agents/agentos/context_transport.py").exists():
        raise RuntimeError("refusing upgrade: context_transport.py already exists on v0.22.7 target")

    governance = _read_json(root / ".agents/config/governance.json")
    if str(governance.get("version")) != FROM:
        raise RuntimeError(f"refusing upgrade: governance version must be {FROM}")
    if int(governance.get("documentation_policy", {}).get("current_schema", -1)) != SCHEMA_FROM:
        raise RuntimeError("refusing upgrade: governance current_schema must be 43")
    dsr = governance.get("data_subject_rights_policy", {})
    if not (dsr.get("local_execution_only") is True and dsr.get("mcp_mutation_allowed") is False):
        raise RuntimeError("refusing upgrade: v0.22.7 privacy safety invariants are not present")

    return {
        "version": version,
        "schema": SCHEMA_FROM,
        "privacy_runtime": True,
        "governance_version": governance.get("version"),
    }


def _merge_governance(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Merge only v0.23.0 policy additions while preserving predecessor sections."""
    target = json.loads(json.dumps(target))
    target["version"] = TO
    if "governance_version" in target:
        target["governance_version"] = TO
    target.setdefault("documentation_policy", {})["current_schema"] = SCHEMA_TO
    # These are the only policy sections intentionally changed by v0.23.0.
    for key in ("knowledge_runtime", "context_transport_policy"):
        if key not in source:
            raise RuntimeError(f"overlay governance missing required section: {key}")
        if key == "knowledge_runtime":
            merged = dict(target.get(key, {}))
            merged.update(source[key])
            target[key] = merged
        else:
            target[key] = source[key]

    # Reassert non-negotiable predecessor boundaries instead of trusting docs alone.
    enforcement = target.setdefault("governance_enforcement_policy", {})
    enforcement["mcp_privileged_mutation_exposed"] = False
    runtime = target.setdefault("unified_runtime_policy", {})
    runtime["version_forwarding_runtime_allowed"] = False
    runtime["mcp_subprocess_forwarding_allowed"] = False
    runtime["extension_mutation_tools_exposed_over_mcp"] = False
    dsr = target.setdefault("data_subject_rights_policy", {})
    dsr["mcp_mutation_allowed"] = False
    dsr["target_update_allowed"] = False
    dsr["target_delete_allowed"] = False
    dsr["target_upsert_allowed"] = False
    dsr["target_merge_allowed"] = False
    secret = target.setdefault("secret_resolver_policy", {})
    secret["secret_persist_allowed"] = False
    secret["secret_mcp_allowed"] = False
    secret["secret_llm_allowed"] = False
    return target


def _authoritative_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.as_posix() in EXCLUDE_FILES or path.name.endswith(".pyc"):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rebuild_integrity_metadata(root: Path) -> dict[str, Any]:
    """Rebuild full-target manifest/checksums excluding runtime/generated state."""
    entries = []
    checksum_lines = []
    for path in _authoritative_files(root):
        rel = path.relative_to(root).as_posix()
        digest = _sha256(path)
        entries.append({"path": rel, "size": path.stat().st_size, "sha256": digest})
        checksum_lines.append(f"{digest}  {rel}")
    manifest = {
        "release": TO,
        "kind": "full",
        "file_count": len(entries),
        "files": entries,
    }
    (root / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    overlay = Path(__file__).resolve().parents[1]

    evidence = _baseline_check(root)
    for rel in COPY_FILES:
        if not (overlay / rel).is_file():
            raise RuntimeError(f"upgrade overlay is incomplete: missing {rel}")
    if not (overlay / ".agents/config/governance.json").is_file():
        raise RuntimeError("upgrade overlay is incomplete: missing governance.json")

    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "from": FROM,
            "to": TO,
            "schema_from": SCHEMA_FROM,
            "schema_to": SCHEMA_TO,
            "baseline": evidence,
            "copy_file_count": len(COPY_FILES),
        }, ensure_ascii=False, indent=2))
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / ".agents/runtime/upgrade-backups" / f"v0227-to-v0230-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    # Backup every file that will be overwritten plus governance/integrity metadata.
    backup_rels = list(COPY_FILES) + [".agents/config/governance.json", "MANIFEST.json", "CHECKSUMS.sha256"]
    for rel in backup_rels:
        src = root / rel
        if src.is_file():
            dst = backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    for rel in COPY_FILES:
        src = overlay / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if rel in EXECUTABLE_FILES:
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    target_policy_path = root / ".agents/config/governance.json"
    target_policy = _read_json(target_policy_path)
    overlay_policy = _read_json(overlay / ".agents/config/governance.json")
    merged = _merge_governance(target_policy, overlay_policy)
    target_policy_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = rebuild_integrity_metadata(root)
    print(json.dumps({
        "ok": True,
        "from": FROM,
        "to": TO,
        "schema_from": SCHEMA_FROM,
        "schema_to": SCHEMA_TO,
        "backup": str(backup),
        "manifest_file_count": manifest["file_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
