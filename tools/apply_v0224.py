#!/usr/bin/env python3
"""Apply AgentOS v0.22.4 Unified Governance Enforcement & Signed Audit.

The upgrader is intentionally allowlist-based: only files required by the
v0.22.4 node are copied from the upgrade overlay into an exact v0.22.3
baseline. Existing files are backed up with hashes before replacement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASELINE = "0.22.3"
TARGET = "0.22.4"
TARGET_SCHEMA = 41

OVERLAY_FILES = (
    ".agents/agentos/__init__.py",
    ".agents/agentos/controlled_target_insert.py",
    ".agents/agentos/database_boundary.py",
    ".agents/agentos/db.py",
    ".agents/agentos/governance_enforcement.py",
    ".agents/agentos/governance_enforcement_cli.py",
    ".agents/agentos/identity_resolution.py",
    ".agents/agentos/policy.py",
    ".agents/agentos/read_only_extraction.py",
    ".agents/agentos/reconciliation_recovery.py",
    ".agents/agentos/release_integrity.py",
    ".agents/agentos/release_integrity_cli.py",
    ".agents/agentos/schema_mapping.py",
    ".agents/agentos/schema_version.py",
    ".agents/agentos/tooling.py",
    ".agents/bin/agentos",
    ".agents/bin/agentos.v0224",
    ".agents/config/governance.json",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ".agents/docs/UNIFIED_GOVERNANCE_ENFORCEMENT_V0224.md",
    ".agents/docs/USAGE.md",
    ".agents/tests/test_agentos.py",
    ".agents/tests/test_core_reintegration_v0223.py",
    ".agents/tests/test_governance_enforcement_v0224.py",
    "AGENTS.md",
    "README.en.md",
    "README.md",
    "README.vi.md",
    "RELEASE_NOTES.md",
    "UPGRADE_FROM_0.22.3.md",
    "VERSION",
    "huong_dan.en.md",
    "huong_dan.md",
    "huong_dan.vi.md",
    "tools/apply_v0224.py",
    "tools/validate_release.py",
)

EXECUTABLES = {
    ".agents/bin/agentos",
    ".agents/bin/agentos.v0224",
    "tools/apply_v0224.py",
    "tools/validate_release.py",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(root: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / ".agents") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        argv,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _require_overlay(overlay: Path) -> None:
    missing = [rel for rel in OVERLAY_FILES if not (overlay / rel).is_file()]
    if missing:
        raise RuntimeError(f"v0.22.4 overlay incomplete: {missing}")
    if (overlay / "VERSION").read_text(encoding="utf-8").strip() != TARGET:
        raise RuntimeError("overlay VERSION is not 0.22.4")


def _preflight(root: Path) -> dict[str, object]:
    version_file = root / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else None
    if version != BASELINE:
        raise RuntimeError(f"baseline VERSION must be exactly {BASELINE}, got {version!r}")

    required = (
        "AGENTS.md",
        ".agents/agentos/core.py",
        ".agents/agentos/db.py",
        ".agents/agentos/policy.py",
        ".agents/agentos/proxy.py",
        ".agents/agentos/tooling.py",
        ".agents/agentos/external_audit.py",
        ".agents/agentos/database_boundary.py",
        ".agents/agentos/schema_mapping.py",
        ".agents/agentos/read_only_extraction.py",
        ".agents/agentos/controlled_target_insert.py",
        ".agents/agentos/identity_resolution.py",
        ".agents/agentos/reconciliation_recovery.py",
        ".agents/agentos/release_integrity.py",
        ".agents/tests/test_agentos.py",
        ".agents/tests/test_core_reintegration_v0223.py",
        ".agents/bin/agentos",
        ".agents/bin/agentos.v0223",
        ".agents/config/governance.json",
        "tools/verify_manifest.py",
    )
    missing = [rel for rel in required if not (root / rel).is_file()]
    if missing:
        raise RuntimeError(f"v0.22.3 baseline incomplete: {missing}")

    # Verify the trusted v0.22.3 integrity gate before modifying anything.
    cp = _run(root, [str(root / ".agents/bin/agentos"), "release-integrity-check"])
    if cp.returncode != 0:
        raise RuntimeError(
            "v0.22.3 release-integrity-check failed before upgrade:\n"
            + (cp.stdout + cp.stderr).strip()
        )
    try:
        integrity = json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("baseline release-integrity-check did not return JSON") from exc
    if not integrity.get("ok") or integrity.get("version") != BASELINE or integrity.get("schema") != 40:
        raise RuntimeError(f"unexpected baseline integrity result: {integrity}")

    # The original manifest, when present, must be valid before mutation.
    manifest_verified = False
    if (root / "MANIFEST.json").is_file() and (root / "CHECKSUMS.sha256").is_file():
        mp = _run(root, [sys.executable, str(root / "tools/verify_manifest.py"), str(root)])
        if mp.returncode != 0:
            raise RuntimeError("baseline MANIFEST/CHECKSUMS verification failed:\n" + (mp.stdout + mp.stderr).strip())
        manifest_verified = True

    return {
        "version": BASELINE,
        "schema": 40,
        "release_integrity": True,
        "manifest_verified": manifest_verified,
    }


def _backup(root: Path) -> tuple[Path, list[dict[str, object]]]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = root / ".agents/runtime/upgrade-backups" / f"v0.22.4-{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    for rel in OVERLAY_FILES:
        src = root / rel
        if not src.is_file():
            records.append({"path": rel, "existed": False})
            continue
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        records.append(
            {
                "path": rel,
                "existed": True,
                "sha256": _sha256(src),
                "mode": oct(stat.S_IMODE(src.stat().st_mode)),
            }
        )
    (backup_root / "backup-manifest.json").write_text(
        json.dumps(
            {
                "from": BASELINE,
                "to": TARGET,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": records,
                "external_projects_touched": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return backup_root, records


def _copy_overlay(overlay: Path, root: Path) -> None:
    for rel in OVERLAY_FILES:
        src = overlay / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in EXECUTABLES:
        p = root / rel
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _postflight(root: Path) -> dict[str, object]:
    if (root / "VERSION").read_text(encoding="utf-8").strip() != TARGET:
        raise RuntimeError("post-upgrade VERSION is not 0.22.4")

    checks: dict[str, object] = {}
    for name, argv in (
        ("release_integrity", [str(root / ".agents/bin/agentos"), "release-integrity-check"]),
        ("docs", [str(root / ".agents/bin/agentos"), "docs-check"]),
        ("instruction", [str(root / ".agents/bin/agentos"), "instruction-check"]),
    ):
        cp = _run(root, argv)
        checks[name] = {"rc": cp.returncode, "stdout": cp.stdout.strip(), "stderr": cp.stderr.strip()}
        if cp.returncode != 0:
            raise RuntimeError(f"post-upgrade {name} check failed:\n{(cp.stdout + cp.stderr).strip()}")

    # Force/open the governance DB through the central connection and prove schema/FK state.
    code = (
        "from pathlib import Path; from agentos.db import connect, SCHEMA_VERSION; import json; "
        f"r=Path({str(root)!r}); "
        "cm=connect(r); c=cm.__enter__(); "
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
    parser = argparse.ArgumentParser(description="Upgrade AgentOS v0.22.3 to v0.22.4")
    parser.add_argument("root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    overlay = Path(__file__).resolve().parents[1]
    _require_overlay(overlay)
    baseline = _preflight(root)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "from": BASELINE,
                    "to": TARGET,
                    "target_schema": TARGET_SCHEMA,
                    "baseline": baseline,
                    "will_write_only_primary_root": True,
                    "external_projects_touched": False,
                    "file_count": len(OVERLAY_FILES),
                    "files": list(OVERLAY_FILES),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    backup_root, _ = _backup(root)
    _copy_overlay(overlay, root)
    postflight = _postflight(root)
    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": False,
                "from": BASELINE,
                "to": TARGET,
                "schema": TARGET_SCHEMA,
                "backup": str(backup_root),
                "external_projects_touched": False,
                "postflight": postflight,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
