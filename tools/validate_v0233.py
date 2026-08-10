#!/usr/bin/env python3
"""Validate the structural v0.23.3 upgrade and measured baseline readiness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERSION = "0.23.3"
SCHEMA = 46


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root: Path) -> dict[str, object]:
    """Validate v0.23.3 structural synchronization and release-baseline readiness."""
    root = root.resolve()
    findings: list[str] = []
    version_path = root / "VERSION"
    if not version_path.is_file() or version_path.read_text(encoding="utf-8").strip() != VERSION:
        findings.append("version")

    policy_path = root / ".agents/config/governance.json"
    policy: dict[str, Any] = {}
    if not policy_path.is_file():
        findings.append("missing:governance")
    else:
        try:
            policy = _read_json(policy_path)
        except Exception:
            findings.append("invalid:governance")
    if policy and policy.get("version") != VERSION:
        findings.append("governance_version")
    cockpit_policy = policy.get("consolidation_cockpit_policy") if policy else None
    if not isinstance(cockpit_policy, dict):
        findings.append("cockpit_policy")
    elif cockpit_policy.get("schema_change") != "none":
        findings.append("cockpit_policy_schema_change")

    required = (
        ".agents/agentos/consolidation_cockpit.py",
        ".agents/agentos/performance_baseline.py",
        ".agents/agentos/consolidation_cockpit_cli.py",
        ".agents/agentos/mcp_consolidation_cockpit.py",
        ".agents/tests/test_consolidation_cockpit_v0233.py",
        ".agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md",
        "UPGRADE_FROM_0.23.2.md",
        "PERFORMANCE_BASELINE_V0233.json",
    )
    for rel in required:
        if not (root / rel).is_file():
            findings.append(f"missing:{rel}")

    cli_path = root / ".agents/agentos/cli_runtime.py"
    mcp_path = root / ".agents/agentos/mcp_catalog.py"
    integrity_path = root / ".agents/agentos/release_integrity.py"
    if cli_path.is_file():
        cli = cli_path.read_text(encoding="utf-8")
        if 'VERSION = "0.23.3"' not in cli:
            findings.append("cli_version")
        if "consolidation_cockpit_cli" not in cli:
            findings.append("cli_registration")
    else:
        findings.append("missing:cli_runtime")
    if mcp_path.is_file():
        mcp = mcp_path.read_text(encoding="utf-8")
        if "mcp_consolidation_cockpit" not in mcp:
            findings.append("mcp_registration")
    else:
        findings.append("missing:mcp_catalog")
    if integrity_path.is_file():
        integrity_text = integrity_path.read_text(encoding="utf-8")
        if "check_performance_baseline" not in integrity_text:
            findings.append("release_gate_registration")
        if "expected VERSION 0.23.3" not in integrity_text:
            findings.append("release_integrity_version")
    else:
        findings.append("missing:release_integrity")

    schema_path = root / ".agents/agentos/schema_version.py"
    if not schema_path.is_file() or "CURRENT_SCHEMA_VERSION = 46" not in schema_path.read_text(encoding="utf-8"):
        findings.append("schema_version")

    baseline_status = "missing"
    baseline_findings: list[str] = []
    baseline_path = root / "PERFORMANCE_BASELINE_V0233.json"
    if baseline_path.is_file():
        try:
            baseline = _read_json(baseline_path)
            baseline_status = str(baseline.get("measurement_status") or "unknown")
            if baseline.get("version") != VERSION:
                baseline_findings.append("baseline_version_mismatch")
            if int(baseline.get("schema_version", -1)) != SCHEMA:
                baseline_findings.append("baseline_schema_mismatch")
            if baseline_status != "measured":
                baseline_findings.append("baseline_not_measured")
            contract = baseline.get("regression_contract") or {}
            if contract.get("project_state_mutation_allowed") is not False:
                baseline_findings.append("baseline_must_be_non_destructive")
            for section, field in (
                (baseline.get("migration", {}).get("fresh_database", {}), "median_ms"),
                (baseline.get("symbol_index_current_design", {}), "median_ms"),
                (baseline.get("cockpit", {}), "median_ms"),
            ):
                if not isinstance(section.get(field), (int, float)):
                    baseline_findings.append(f"missing_timing:{field}")
        except Exception as exc:
            baseline_status = "invalid"
            baseline_findings.append(f"invalid_baseline:{type(exc).__name__}")

    structural_ok = not findings
    release_ready = structural_ok and not baseline_findings
    return {
        "ok": structural_ok,
        "release_ready": release_ready,
        "version": VERSION,
        "schema": SCHEMA,
        "measurement_status": baseline_status,
        "findings": findings,
        "baseline_findings": baseline_findings,
        "note": "Structural upgrade can pass before performance capture; release readiness requires a measured baseline.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    args = parser.parse_args(argv)
    result = validate(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
