#!/usr/bin/env python3
"""
File: tools/validate_release.py

Purpose:
    Validate the currently materialized AgentOS release without pinning the
    validator to a historical version number.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


def validate(root: Path, *, skip_manifest: bool = False) -> dict[str, object]:
    root = root.resolve()
    sys.path.insert(0, str(root / ".agents"))

    from agentos.cli_runtime import command_registry
    from agentos.core import instruction_check
    from agentos.db import SCHEMA_VERSION, connect, migrate_with_report
    from agentos.mcp_runtime import ALL_TOOLS, VERSION as MCP_VERSION
    from agentos.policy import load_policy
    from agentos.release_integrity import check_release_integrity, docs_check_current
    from agentos.schema_bootstrap import BASELINE_SCHEMA_VERSION
    from agentos.release_manifest import verify_manifest

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    policy = load_policy(root)
    commands = command_registry()
    tools = [str(item.get("name")) for item in ALL_TOOLS]

    checks: dict[str, bool] = {}
    checks["version_nonempty"] = bool(version)
    checks["mcp_version"] = MCP_VERSION == version
    checks["policy_version"] = policy.get("version") == version
    checks["policy_schema"] = int(
        (policy.get("documentation_policy") or {}).get("current_schema", -1)
    ) == int(SCHEMA_VERSION)
    checks["cli_unique"] = len(commands) == len(set(commands))
    checks["mcp_unique"] = len(tools) == len(set(tools))
    checks["mcp_health"] = "agentos.mcp_health" in tools

    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "project"
        (fresh / ".agents").mkdir(parents=True)
        with connect(fresh) as conn:
            versions = [
                int(row[0])
                for row in conn.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
            foreign_keys = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        checks["migration_chain"] = versions == list(range(1, int(SCHEMA_VERSION) + 1))
        checks["foreign_keys_on"] = foreign_keys == 1

    bootstrap_probe = sqlite3.connect(":memory:")
    bootstrap_probe.row_factory = sqlite3.Row
    try:
        bootstrap_report = migrate_with_report(bootstrap_probe)
    finally:
        bootstrap_probe.close()
    checks["fresh_bootstrap_path"] = (
        bootstrap_report.get("mode") == "bootstrap"
        and bootstrap_report.get("bootstrap_version")
            == BASELINE_SCHEMA_VERSION
            == 46
        and bootstrap_report.get("applied_migrations") == [47, 48, 49]
        and (bootstrap_report.get("bootstrap") or {}).get(
            "historical_migrations_invoked"
        ) == 0
    )

    integrity = check_release_integrity(root)
    docs = docs_check_current(root)
    instructions = instruction_check(root)
    checks["release_integrity"] = integrity.get("ok") is True
    checks["docs_check"] = docs.get("ok") is True
    checks["instruction_check"] = instructions.get("ok") is True

    manifest = None
    if not skip_manifest:
        manifest = verify_manifest(root)
        checks["manifest"] = (
            manifest.get("ok") is True and manifest.get("release") == version
        )

    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    return {
        "ok": all(checks.values()),
        "version": version,
        "schema": int(SCHEMA_VERSION),
        "mcp_version": MCP_VERSION,
        "cli_count": len(commands),
        "mcp_count": len(tools),
        "checks": checks,
        "failed_checks": failed_checks,
        "release_integrity": integrity,
        "docs_check": docs,
        "instruction_check": instructions,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--skip-manifest", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.root), skip_manifest=args.skip_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["ok"] and __import__("os").environ.get("GITHUB_ACTIONS") == "true":
        failed = ", ".join(result.get("failed_checks") or ["unknown"])
        print(f"::error title=AgentOS release validation failed::Failed checks: {failed}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
