#!/usr/bin/env python3
"""Validate the AgentOS v0.23.0 release tree and package metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

EXPECTED_VERSION = "0.23.0"
EXPECTED_SCHEMA = 44
REQUIRED_TRANSPORT_TABLES = {
    "context_transport_packs",
    "context_requirement_ledger",
    "context_expansion_events",
    "context_transport_evaluations",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_manifest(root: Path) -> dict:
    """Verify MANIFEST.json and CHECKSUMS.sha256 without external helper scripts."""
    manifest_path = root / "MANIFEST.json"
    checksums_path = root / "CHECKSUMS.sha256"
    if not manifest_path.is_file() or not checksums_path.is_file():
        return {"ok": False, "reason": "manifest_or_checksums_missing"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    findings = []
    seen = set()
    for entry in manifest.get("files", []):
        rel = str(entry.get("path", ""))
        if not rel or rel in seen:
            findings.append({"path": rel, "reason": "duplicate_or_empty"})
            continue
        seen.add(rel)
        path = root / rel
        if not path.is_file():
            findings.append({"path": rel, "reason": "missing"})
            continue
        actual = _sha256(path)
        if actual != entry.get("sha256") or path.stat().st_size != int(entry.get("size", -1)):
            findings.append({"path": rel, "reason": "hash_or_size_mismatch"})
    checksum_map = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        checksum_map[rel] = digest
    if set(checksum_map) != seen:
        findings.append({"reason": "checksum_manifest_path_set_mismatch"})
    else:
        for rel in seen:
            if checksum_map[rel] != _sha256(root / rel):
                findings.append({"path": rel, "reason": "checksum_mismatch"})
    return {
        "ok": not findings,
        "release": manifest.get("release"),
        "kind": manifest.get("kind"),
        "file_count": len(seen),
        "findings": findings,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("root", nargs="?", default=".", type=Path)
    p.add_argument("--skip-manifest", action="store_true")
    args = p.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / ".agents"))

    from agentos.db import SCHEMA_VERSION, connect
    from agentos.policy import load_policy
    from agentos.cli_runtime import command_registry
    from agentos.mcp_runtime import ALL_TOOLS
    from agentos.release_integrity import check_release_integrity

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    report = {"ok": True, "version": version, "schema": SCHEMA_VERSION}
    report["ok"] &= version == EXPECTED_VERSION and SCHEMA_VERSION == EXPECTED_SCHEMA

    integrity = check_release_integrity(root)
    report["release_integrity"] = integrity
    report["ok"] &= integrity.get("ok") is True

    try:
        policy = load_policy(root)
        report["policy_loaded"] = True
        report["policy_version"] = policy.get("version")
        report["ok"] &= policy.get("version") == EXPECTED_VERSION
    except Exception as exc:
        report["policy_loaded"] = False
        report["policy_error"] = str(exc)
        report["ok"] = False

    # Validate a clean migration independently of the release working database.
    with tempfile.TemporaryDirectory() as td:
        clean = Path(td) / "project"
        (clean / ".agents/state").mkdir(parents=True)
        (clean / ".agents/config").mkdir(parents=True)
        with connect(clean) as conn:
            versions = [int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
            tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        report["migration_versions"] = versions
        report["foreign_keys_on"] = fk == 1
        report["transport_tables_present"] = REQUIRED_TRANSPORT_TABLES <= tables
        report["ok"] &= versions == list(range(1, EXPECTED_SCHEMA + 1)) and fk == 1 and report["transport_tables_present"]

    commands = command_registry()
    tools = [str(t["name"]) for t in ALL_TOOLS]
    report["cli_count"] = len(commands)
    report["cli_unique"] = len(commands) == len(set(commands))
    report["mcp_count"] = len(tools)
    report["mcp_unique"] = len(tools) == len(set(tools))
    report["context_mcp_tools"] = sorted(t for t in tools if t.startswith("agentos.context_"))
    report["ok"] &= report["cli_unique"] and report["mcp_unique"] and len(report["context_mcp_tools"]) == 5

    if not args.skip_manifest:
        manifest = verify_manifest(root)
        report["manifest"] = manifest
        report["ok"] &= manifest["ok"] and manifest.get("release") == EXPECTED_VERSION

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()
