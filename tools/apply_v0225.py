#!/usr/bin/env python3
"""
File: tools/apply_v0225.py

Purpose:
    Upgrade an exact AgentOS v0.22.4 tree to v0.22.5 unified CLI/MCP runtime.

Responsibilities:
    - Verify the v0.22.4 baseline and manifest before mutation.
    - Backup every replaced file with hashes.
    - Copy only the explicit v0.22.5 allowlist into the active project root.
    - Verify runtime parity, release integrity, documentation, and schema 41 post-upgrade.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

BASELINE = "0.22.4"
TARGET = "0.22.5"
TARGET_SCHEMA = 41

OVERLAY_FILES = (
    ".agents/agentos/__init__.py",
    ".agents/agentos/cli.py",
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/project_identity_cli.py",
    ".agents/agentos/project_selection_cli.py",
    ".agents/agentos/mcp_catalog.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/policy.py",
    ".agents/agentos/release_integrity.py",
    ".agents/agentos/release_manifest.py",
    ".agents/bin/agentos",
    ".agents/bin/agentos.cmd",
    ".agents/bin/agentos-mcp",
    ".agents/bin/agentos-mcp.cmd",
    ".agents/config/governance.json",
    ".agents/docs/PROJECT_STRUCTURE.md",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ".agents/docs/UNIFIED_CLI_MCP_RUNTIME_V0225.md",
    ".agents/docs/USAGE.md",
    ".agents/tests/test_agentos.py",
    ".agents/tests/test_core_reintegration_v0223.py",
    ".agents/tests/test_unified_runtime_v0225.py",
    "AGENTS.md",
    "README.en.md",
    "README.md",
    "README.vi.md",
    "RELEASE_NOTES.md",
    "UPGRADE_FROM_0.22.4.md",
    "VALIDATION_REPORT.json",
    "VERSION",
    "huong_dan.en.md",
    "huong_dan.md",
    "huong_dan.vi.md",
    "tools/apply_v0225.py",
    "tools/verify_manifest.py",
    "tools/validate_release.py",
)

GENERATED_RELEASE_FILES = ("MANIFEST.json", "CHECKSUMS.sha256")

EXECUTABLES = {
    ".agents/bin/agentos",
    ".agents/bin/agentos-mcp",
    "tools/apply_v0225.py",
    "tools/verify_manifest.py",
    "tools/validate_release.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(root: Path, argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / ".agents") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=timeout)


def _require_overlay(overlay: Path) -> None:
    missing = [rel for rel in OVERLAY_FILES if not (overlay / rel).is_file()]
    if missing:
        raise RuntimeError(f"v0.22.5 overlay incomplete: {missing}")
    if (overlay / "VERSION").read_text(encoding="utf-8").strip() != TARGET:
        raise RuntimeError("overlay VERSION is not 0.22.5")


def _preflight(root: Path) -> dict[str, object]:
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else None
    if version != BASELINE:
        raise RuntimeError(f"baseline VERSION must be exactly {BASELINE}, got {version!r}")
    required = (
        "AGENTS.md",
        ".agents/agentos/core.py",
        ".agents/agentos/db.py",
        ".agents/agentos/policy.py",
        ".agents/agentos/governance_enforcement.py",
        ".agents/agentos/release_integrity.py",
        ".agents/tests/test_governance_enforcement_v0224.py",
        ".agents/bin/agentos",
        ".agents/bin/agentos-mcp",
        ".agents/config/governance.json",
        "tools/verify_manifest.py",
    )
    missing = [rel for rel in required if not (root / rel).is_file()]
    if missing:
        raise RuntimeError(f"v0.22.4 baseline incomplete: {missing}")
    cp = _run(root, [str(root / ".agents/bin/agentos"), "release-integrity-check"])
    if cp.returncode != 0:
        raise RuntimeError("v0.22.4 release-integrity-check failed:\n" + (cp.stdout + cp.stderr).strip())
    integrity = json.loads(cp.stdout)
    if not integrity.get("ok") or integrity.get("version") != BASELINE or integrity.get("schema") != TARGET_SCHEMA:
        raise RuntimeError(f"unexpected baseline integrity result: {integrity}")
    manifest_verified = False
    if (root / "MANIFEST.json").is_file() and (root / "CHECKSUMS.sha256").is_file():
        mp = _run(root, [sys.executable, str(root / "tools/verify_manifest.py"), str(root)])
        if mp.returncode != 0:
            raise RuntimeError("baseline MANIFEST/CHECKSUMS verification failed:\n" + (mp.stdout + mp.stderr).strip())
        manifest_verified = True
    return {"version": BASELINE, "schema": TARGET_SCHEMA, "release_integrity": True, "manifest_verified": manifest_verified}


def _backup(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = root / ".agents/runtime/upgrade-backups" / f"v0.22.5-{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    for rel in (*OVERLAY_FILES, *GENERATED_RELEASE_FILES):
        src = root / rel
        if not src.is_file():
            records.append({"path": rel, "existed": False})
            continue
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        records.append({"path": rel, "existed": True, "sha256": _sha256(src), "mode": oct(stat.S_IMODE(src.stat().st_mode))})
    (backup_root / "backup-manifest.json").write_text(json.dumps({"from": BASELINE, "to": TARGET, "created_at": datetime.now(timezone.utc).isoformat(), "files": records, "external_projects_touched": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return backup_root


def _copy_overlay(overlay: Path, root: Path) -> None:
    for rel in OVERLAY_FILES:
        src, dst = overlay / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in EXECUTABLES:
        path = root / rel
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _postflight(root: Path) -> dict[str, object]:
    if (root / "VERSION").read_text(encoding="utf-8").strip() != TARGET:
        raise RuntimeError("post-upgrade VERSION is not 0.22.5")
    checks: dict[str, object] = {}
    build = _run(root, [sys.executable, str(root / "tools/build_manifest.py"), str(root), "--kind", "full"])
    if build.returncode != 0:
        raise RuntimeError("post-upgrade manifest rebuild failed:\n" + (build.stdout + build.stderr).strip())
    manifest = _run(root, [sys.executable, str(root / "tools/verify_manifest.py"), str(root)])
    checks["manifest"] = {"rc": manifest.returncode, "stdout": manifest.stdout.strip(), "stderr": manifest.stderr.strip()}
    if manifest.returncode != 0:
        raise RuntimeError("post-upgrade manifest verification failed:\n" + (manifest.stdout + manifest.stderr).strip())
    commands = (
        ("runtime_health", [str(root / ".agents/bin/agentos"), "runtime-health"]),
        ("release_integrity", [str(root / ".agents/bin/agentos"), "release-integrity-check"]),
        ("docs", [str(root / ".agents/bin/agentos"), "docs-check"]),
        ("instruction", [str(root / ".agents/bin/agentos"), "instruction-check"]),
    )
    for name, argv in commands:
        cp = _run(root, argv)
        checks[name] = {"rc": cp.returncode, "stdout": cp.stdout.strip(), "stderr": cp.stderr.strip()}
        if cp.returncode != 0:
            raise RuntimeError(f"post-upgrade {name} failed:\n{(cp.stdout + cp.stderr).strip()}")
    code = (
        "from pathlib import Path; from agentos.db import connect, SCHEMA_VERSION; import json; "
        f"r=Path({str(root)!r}); cm=connect(r); c=cm.__enter__(); "
        "v=[x['version'] for x in c.execute('SELECT version FROM schema_migrations ORDER BY version')]; "
        "fk=c.execute('PRAGMA foreign_keys').fetchone()[0]; cm.__exit__(None,None,None); "
        "print(json.dumps({'schema':SCHEMA_VERSION,'versions':v,'foreign_keys':fk}))"
    )
    cp = _run(root, [sys.executable, "-c", code])
    if cp.returncode != 0:
        raise RuntimeError("post-upgrade schema verification failed:\n" + (cp.stdout + cp.stderr).strip())
    state = json.loads(cp.stdout)
    if state["schema"] != TARGET_SCHEMA or state["versions"] != list(range(1, TARGET_SCHEMA + 1)) or state["foreign_keys"] != 1:
        raise RuntimeError(f"post-upgrade schema state invalid: {state}")
    checks["schema"] = state
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Upgrade AgentOS v0.22.4 to v0.22.5")
    parser.add_argument("root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    overlay = Path(__file__).resolve().parents[1]
    _require_overlay(overlay)
    baseline = _preflight(root)
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "from": BASELINE, "to": TARGET, "target_schema": TARGET_SCHEMA, "baseline": baseline, "file_count": len(OVERLAY_FILES), "files": list(OVERLAY_FILES), "external_projects_touched": False}, indent=2, sort_keys=True))
        return 0
    backup_root = _backup(root)
    _copy_overlay(overlay, root)
    postflight = _postflight(root)
    print(json.dumps({"ok": True, "dry_run": False, "from": BASELINE, "to": TARGET, "schema": TARGET_SCHEMA, "backup": str(backup_root), "external_projects_touched": False, "postflight": postflight}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
