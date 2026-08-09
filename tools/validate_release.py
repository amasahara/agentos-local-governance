#!/usr/bin/env python3
"""Validate the complete AgentOS Local Governance v0.23.2 release tree."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

EXPECTED_VERSION = "0.23.2"
EXPECTED_SCHEMA = 46
EXPECTED_CONTEXT_MCP = {
    "agentos.context_transport_get",
    "agentos.context_transport_explain",
    "agentos.context_expand",
    "agentos.context_requirement_get",
    "agentos.context_token_report",
    "agentos.context_model_profiles_get",
    "agentos.context_budget_history_get",
    "agentos.context_token_calibration_get",
    "agentos.context_expansion_explain",
    "agentos.context_expand_batch",
    "agentos.context_expansion_history_get",
    "agentos.context_compression_evaluation_get",
    "agentos.context_compression_compare",
}
REQUIRED_TABLES = {
    "context_transport_packs",
    "context_requirement_ledger",
    "context_expansion_events",
    "context_transport_evaluations",
    "context_model_profile_snapshots",
    "context_budget_decisions",
    "context_token_observations",
    "context_expansion_sessions",
    "context_compression_evaluation_runs",
    "context_compression_comparisons",
    "data_subject_erasure_requests",
    "data_subject_erasure_plans",
    "privacy_tombstones",
}
REQUIRED_POLICY_SECTIONS = {
    "language_policy", "installation_policy", "security_program", "execution_platform",
    "evolution_policy", "multi_agent_policy", "evaluation_policy", "storage_policy",
    "knowledge_runtime_fixes", "secret_resolver_policy", "lineage_key_lifecycle_policy",
    "data_subject_rights_policy", "privacy_boundary_policy", "context_transport_policy",
    "adaptive_token_budget_policy", "context_expansion_evaluation_policy",
}
FORBIDDEN_MCP_FRAGMENTS = {
    "credential_resolve", "secret_resolve", "key_rotate", "key_revoke",
    "identity_candidate_decide", "erasure_execute", "erasure_approve", "erasure_review",
    "target_update", "target_delete", "target_insert_execute", "recovery_commit_decide",
    "context_transport_compile", "context_compression_evaluate",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--skip-manifest", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / ".agents"))

    from agentos.cli_runtime import command_registry
    from agentos.core import docs_check, instruction_check
    from agentos.db import SCHEMA_VERSION, connect
    from agentos.mcp_runtime import ALL_TOOLS, VERSION as MCP_VERSION
    from agentos.policy import load_policy
    from agentos.release_integrity import check_release_integrity
    from agentos.release_manifest import verify_manifest

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    policy = load_policy(root)
    commands = command_registry()
    tools = [str(item["name"]) for item in ALL_TOOLS]
    context_tools = {name for name in tools if name.startswith("agentos.context_")}
    forbidden_tools = sorted(
        name for name in tools
        if any(fragment in name for fragment in FORBIDDEN_MCP_FRAGMENTS)
    )

    report: dict[str, object] = {
        "version": version,
        "schema": SCHEMA_VERSION,
        "mcp_version": MCP_VERSION,
        "cli_count": len(commands),
        "mcp_count": len(tools),
        "checks": {},
    }
    checks: dict[str, bool] = report["checks"]  # type: ignore[assignment]
    checks["version"] = version == EXPECTED_VERSION
    checks["schema"] = SCHEMA_VERSION == EXPECTED_SCHEMA
    checks["mcp_version"] = MCP_VERSION == EXPECTED_VERSION
    checks["policy_version"] = policy.get("version") == EXPECTED_VERSION
    checks["policy_schema"] = policy.get("documentation_policy", {}).get("current_schema") == EXPECTED_SCHEMA
    checks["historical_policy_sections_restored"] = REQUIRED_POLICY_SECTIONS <= set(policy)
    checks["cli_unique"] = len(commands) == len(set(commands))
    checks["mcp_unique"] = len(tools) == len(set(tools))
    checks["context_mcp_exact"] = context_tools == EXPECTED_CONTEXT_MCP
    checks["privileged_mcp_mutation_absent"] = not forbidden_tools

    with tempfile.TemporaryDirectory() as td:
        fresh = Path(td) / "project"
        (fresh / ".agents").mkdir(parents=True)
        with connect(fresh) as conn:
            versions = [int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
            secure_delete = int(conn.execute("PRAGMA secure_delete").fetchone()[0])
            tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            request_cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(data_subject_erasure_requests)")}
            triggers = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        checks["migration_1_to_46"] = versions == list(range(1, EXPECTED_SCHEMA + 1))
        checks["foreign_keys_on"] = fk == 1
        checks["secure_delete_on"] = secure_delete == 1
        checks["required_tables"] = REQUIRED_TABLES <= tables
        checks["privacy_one_way_locator_column"] = "entity_locator_hash" in request_cols
        checks["privacy_immutability_triggers"] = {
            "trg_erasure_request_immutable_update",
            "trg_erasure_request_immutable_delete",
            "trg_erasure_plan_immutable_update",
            "trg_erasure_plan_immutable_delete",
        } <= triggers

    integrity = check_release_integrity(root)
    docs = docs_check(root)
    instructions = instruction_check(root)
    report["release_integrity"] = integrity
    report["docs_check"] = docs
    report["instruction_check"] = instructions
    report["forbidden_mcp_tools"] = forbidden_tools
    checks["release_integrity"] = integrity.get("ok") is True
    checks["docs_check"] = docs.get("ok") is True
    checks["instruction_check"] = instructions.get("ok") is True

    if not args.skip_manifest:
        manifest = verify_manifest(root)
        report["manifest"] = manifest
        checks["manifest"] = manifest.get("ok") is True and manifest.get("release") == EXPECTED_VERSION

    report["ok"] = all(checks.values())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()
