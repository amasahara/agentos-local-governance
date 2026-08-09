#!/usr/bin/env python3
"""Validate AgentOS v0.23.2 Context Expansion & Compression Evaluation."""
from __future__ import annotations

import json
import sys
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
EXPECTED_CLI = {
    "context-transport-compile", "context-transport-get", "context-transport-explain",
    "context-expand", "context-requirement-get", "context-token-report",
    "context-transport-evaluate", "context-transport-db-sync",
    "context-model-profiles-list", "context-model-profile-get", "context-budget-history",
    "context-token-calibration-get", "context-token-observation-record",
    "context-expansion-explain", "context-expand-batch", "context-expansion-history",
    "context-compression-evaluate", "context-compression-evaluation-get",
    "context-compression-evaluation-history", "context-compression-compare",
    "context-expansion-evaluation-db-sync",
}
EXPECTED_TABLES = {
    "context_transport_packs", "context_requirement_ledger", "context_expansion_events",
    "context_model_profile_snapshots", "context_budget_decisions", "context_token_observations",
    "context_expansion_sessions", "context_compression_evaluation_runs", "context_compression_comparisons",
}
EXPECTED_EXPANSION_COLUMNS = {
    "session_id", "request_hash", "line_start", "line_end", "returned_tokens",
    "reason_code", "requirement_ids_json", "transport_hash",
}
CONTENTISH = {"excerpt", "content", "raw_content", "prompt", "response", "query", "source_text", "evidence_text", "credential", "secret"}


def _false(d: dict, *keys: str) -> bool:
    return all(d.get(k) is False for k in keys)


def main(root_s: str) -> int:
    root = Path(root_s).resolve()
    sys.path.insert(0, str(root / ".agents"))
    from agentos.db import connect
    from agentos.cli_runtime import command_registry
    from agentos.mcp_runtime import ALL_TOOLS

    with connect(root) as conn:
        schema = int(conn.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0])
        versions = [int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expansion_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(context_expansion_events)")}
        session_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(context_expansion_sessions)")}
        eval_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(context_compression_evaluation_runs)")}
        compare_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(context_compression_comparisons)")}

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    policy = json.loads((root / ".agents/config/governance.json").read_text(encoding="utf-8"))
    tp = policy.get("context_transport_policy", {})
    ce = policy.get("context_expansion_evaluation_policy", {})
    ab = policy.get("adaptive_token_budget_policy", {})
    boundary = policy.get("database_boundary_policy", {})
    target = policy.get("controlled_target_insert_policy", {})
    dsr = policy.get("data_subject_rights_policy", {})
    secret = policy.get("secret_resolver_policy", {})
    runtime = policy.get("unified_runtime_policy", {})
    enforcement = policy.get("governance_enforcement_policy", {})

    cli = command_registry()
    cli_names = set(cli)
    mcp_names_list = [str(item["name"]) for item in ALL_TOOLS]
    mcp_names = set(mcp_names_list)
    context_mcp = {n for n in mcp_names if n.startswith("agentos.context_")}
    forbidden_mcp = sorted(n for n in context_mcp if n in {
        "agentos.context_transport_compile", "agentos.context_transport_evaluate",
        "agentos.context_compression_evaluate", "agentos.context_evaluation_persist",
        "agentos.context_compression_compare_persist", "agentos.context_token_observation_record",
        "agentos.context_requirement_mutate", "agentos.context_model_switch",
    })

    no_content_columns = not ((session_columns | eval_columns | compare_columns) & CONTENTISH)
    hard = ce.get("hard_gates", {}) if isinstance(ce.get("hard_gates"), dict) else {}
    checks = {
        "version": version == EXPECTED_VERSION,
        "schema": schema == EXPECTED_SCHEMA,
        "migration_1_to_current": versions == list(range(1, EXPECTED_SCHEMA + 1)),
        "foreign_keys": fk == 1,
        "tables": EXPECTED_TABLES <= tables,
        "expansion_event_columns": EXPECTED_EXPANSION_COLUMNS <= expansion_columns,
        "new_tables_no_raw_content_columns": no_content_columns,
        "governance_version": policy.get("version") == EXPECTED_VERSION,
        "governance_schema": policy.get("documentation_policy", {}).get("current_schema") == EXPECTED_SCHEMA,
        "transport_schema": tp.get("database_schema") == EXPECTED_SCHEMA and int(tp.get("version", 0)) >= 3,
        "lossless_control_plane": (
            tp.get("control_plane_mode") == "lossless"
            and tp.get("original_user_request_verbatim_required") is True
            and tp.get("agents_authority_verbatim_required") is True
            and tp.get("approved_scope_lossless_required") is True
            and float(tp.get("requirement_preservation_rate_required", 0.0)) == 1.0
            and tp.get("fail_closed_if_control_plane_exceeds_budget") is True
            and _false(tp, "protected_content_translation_allowed", "protected_content_paraphrase_allowed", "protected_content_summarization_allowed", "protected_content_token_pruning_allowed", "protected_content_word_level_deletion_allowed")
        ),
        "expansion_read_only_ephemeral": (
            ce.get("database_schema") == EXPECTED_SCHEMA
            and ce.get("expansion_read_only") is True
            and ce.get("source_hash_pin_required") is True
            and ce.get("transport_hash_pin_required") is True
            and _false(ce, "expanded_content_persistence_allowed", "expanded_content_audit_allowed", "arbitrary_query_content_persistence_allowed", "llm_may_persist_expansion_telemetry", "llm_may_persist_evaluation", "llm_may_mutate_transport")
        ),
        "evaluation_hard_gates": (
            float(hard.get("requirement_preservation_rate", 0.0)) == 1.0
            and int(hard.get("unaccounted_candidate_count", -1)) == 0
            and float(hard.get("handle_integrity_rate", 0.0)) == 1.0
            and hard.get("transport_within_input_budget") is True
            and hard.get("transport_integrity_required") is True
            and hard.get("source_freshness_required") is True
        ),
        "compression_target_advisory": (
            float(ce.get("compression_target_min", 0.0)) == 2.0
            and float(ce.get("compression_target_max", 0.0)) == 4.0
            and ce.get("compression_target_enforcement") == "advisory"
        ),
        "adaptive_budget_preserved": ab.get("database_schema") == 45 and ab.get("profile_hash_pin_required") is True,
        "source_read_only": _false(boundary, "source_insert_allowed", "source_update_allowed", "source_delete_allowed", "source_merge_allowed", "source_ddl_allowed"),
        "target_safety": _false(target, "raw_target_insert_allowed", "arbitrary_sql_allowed", "source_write_allowed", "update_allowed", "delete_allowed", "upsert_allowed", "merge_allowed", "mcp_may_execute_insert"),
        "privacy_preserved": _false(dsr, "mcp_mutation_allowed", "target_update_allowed", "target_delete_allowed", "target_upsert_allowed", "target_merge_allowed"),
        "secret_boundary_preserved": _false(secret, "secret_persist_allowed", "secret_mcp_allowed", "secret_llm_allowed"),
        "unified_runtime_preserved": _false(runtime, "version_forwarding_runtime_allowed", "mcp_subprocess_forwarding_allowed", "extension_mutation_tools_exposed_over_mcp"),
        "privileged_mcp_mutation_absent": enforcement.get("mcp_privileged_mutation_exposed") is False,
        "cli_unique": len(cli) == len(cli_names),
        "cli_complete": EXPECTED_CLI <= cli_names,
        "mcp_unique": len(mcp_names_list) == len(mcp_names),
        "mcp_context_exact": context_mcp == EXPECTED_CONTEXT_MCP,
        "forbidden_mcp_absent": not forbidden_mcp,
    }
    result = {
        "ok": all(checks.values()),
        "version": version,
        "schema": schema,
        "foreign_keys": fk,
        "cli_count": len(cli),
        "mcp_count": len(mcp_names_list),
        "context_mcp": sorted(context_mcp),
        "forbidden_mcp": forbidden_mcp,
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
