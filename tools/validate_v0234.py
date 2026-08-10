#!/usr/bin/env python3
"""Validate AgentOS v0.23.4 Incremental Symbol Index release structure."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

VERSION = "0.23.4"
SCHEMA = 47


def validate(root: Path) -> dict[str, object]:
    root = root.resolve()
    findings: list[str] = []
    required = (
        ".agents/agentos/indexing.py",
        ".agents/agentos/incremental_index_benchmark.py",
        ".agents/tests/test_incremental_index_v0234.py",
        ".agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md",
        "UPGRADE_FROM_0.23.3.md",
        "RELEASE_NOTES_V0234.md",
        "INDEX_INCREMENTAL_BENCHMARK_V0234.json",
    )
    version_path = root / "VERSION"
    if not version_path.is_file() or version_path.read_text(encoding="utf-8").strip() != VERSION:
        findings.append("version")
    schema_path = root / ".agents/agentos/schema_version.py"
    if not schema_path.is_file() or "CURRENT_SCHEMA_VERSION = 47" not in schema_path.read_text(encoding="utf-8"):
        findings.append("schema")
    for rel in required:
        if not (root / rel).is_file():
            findings.append(f"missing:{rel}")
    index_text = (root / ".agents/agentos/indexing.py").read_text(encoding="utf-8") if (root / ".agents/agentos/indexing.py").is_file() else ""
    for marker in ("symbol_index_files", "bootstrap_full_rebuild", "files_unchanged", "force_full"):
        if marker not in index_text:
            findings.append(f"index_marker:{marker}")
    db_text = (root / ".agents/agentos/db.py").read_text(encoding="utf-8") if (root / ".agents/agentos/db.py").is_file() else ""
    if "migration_47" not in db_text:
        findings.append("migration_47_registration")
    policy_path = root / ".agents/config/governance.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        if policy.get("version") != VERSION:
            findings.append("governance_version")
        if int((policy.get("documentation_policy") or {}).get("current_schema", -1)) != SCHEMA:
            findings.append("governance_schema")
        index_policy = policy.get("incremental_symbol_index_policy") or {}
        if index_policy.get("unchanged_file_ast_parse") != "forbidden":
            findings.append("index_policy")
    except Exception:
        findings.append("governance_invalid")
    benchmark_findings: list[str] = []
    try:
        bench = json.loads((root / "INDEX_INCREMENTAL_BENCHMARK_V0234.json").read_text(encoding="utf-8"))
        if bench.get("version") != VERSION or int(bench.get("schema_version", -1)) != SCHEMA:
            benchmark_findings.append("benchmark_version_schema")
        if bench.get("measurement_status") != "measured" or bench.get("ok") is not True:
            benchmark_findings.append("benchmark_not_measured")
    except Exception as exc:
        benchmark_findings.append(f"benchmark_invalid:{type(exc).__name__}")
    return {
        "ok": not findings and not benchmark_findings,
        "version": VERSION,
        "schema": SCHEMA,
        "findings": findings,
        "benchmark_findings": benchmark_findings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    result = validate(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
