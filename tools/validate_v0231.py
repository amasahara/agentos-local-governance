#!/usr/bin/env python3
"""Validate AgentOS v0.23.1 Adaptive Token Budget & Model Profiles."""
from __future__ import annotations

import json
import sys
from pathlib import Path

EXPECTED_VERSION = "0.23.1"
EXPECTED_SCHEMA = 45
EXPECTED_CONTEXT_MCP = {
    "agentos.context_transport_get",
    "agentos.context_transport_explain",
    "agentos.context_expand",
    "agentos.context_requirement_get",
    "agentos.context_token_report",
    "agentos.context_model_profiles_get",
    "agentos.context_budget_history_get",
    "agentos.context_token_calibration_get",
}
EXPECTED_CLI = {
    "context-transport-compile",
    "context-transport-get",
    "context-transport-explain",
    "context-expand",
    "context-requirement-get",
    "context-token-report",
    "context-transport-evaluate",
    "context-transport-db-sync",
    "context-model-profiles-list",
    "context-model-profile-get",
    "context-budget-history",
    "context-token-calibration-get",
    "context-token-observation-record",
}
EXPECTED_TABLES = {
    "context_transport_packs",
    "context_requirement_ledger",
    "context_expansion_events",
    "context_transport_evaluations",
    "context_model_profile_snapshots",
    "context_budget_decisions",
    "context_token_observations",
}
EXPECTED_PACK_COLUMNS = {"model_profile_hash", "budget_mode", "budget_decision_id"}
EXPECTED_LADDER = [
    "exact_dedup", "metadata_normalization", "structural_projection",
    "requirement_aware_ranking", "omission_handles", "fail_closed",
]


def _false(d: dict, *keys: str) -> bool:
    return all(d.get(k) is False for k in keys)


def main(root_s: str) -> int:
    root = Path(root_s).resolve()
    sys.path.insert(0, str(root / ".agents"))
    from agentos.db import connect
    from agentos.cli_runtime import command_registry
    from agentos.mcp_runtime import ALL_TOOLS
    from agentos.adaptive_budget import model_profiles_get

    with connect(root) as conn:
        schema = int(conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0)
        versions = [int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        pack_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(context_transport_packs)")}
        observation_columns = {str(r[1]) for r in conn.execute("PRAGMA table_info(context_token_observations)")}

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    policy = json.loads((root / ".agents/config/governance.json").read_text(encoding="utf-8"))
    tp = policy.get("context_transport_policy", {})
    ab = policy.get("adaptive_token_budget_policy", {})
    dsr = policy.get("data_subject_rights_policy", {})
    secret = policy.get("secret_resolver_policy", {})
    lineage = policy.get("lineage_key_lifecycle_policy", {})
    boundary = policy.get("database_boundary_policy", {})
    target = policy.get("controlled_target_insert_policy", {})
    runtime = policy.get("unified_runtime_policy", {})
    enforcement = policy.get("governance_enforcement_policy", {})

    cli = command_registry()
    cli_set = set(cli)
    mcp_names = [str(item["name"]) for item in ALL_TOOLS]
    mcp_set = set(mcp_names)
    context_mcp = {n for n in mcp_set if n.startswith("agentos.context_")}
    forbidden_fragments = (
        "context_transport_compile", "context_transport_evaluate", "context_mutate",
        "context_token_observation_record", "context_profile_set", "context_budget_set", "context_model_switch",
        "credential", "secret_resolve", "lineage_key_rotate", "erasure_execute",
        "identity_candidate_decide", "target_insert_execute", "target_update", "target_delete", "recovery_commit",
    )
    forbidden_mcp = sorted(n for n in mcp_names if any(x in n for x in forbidden_fragments))

    profile_result = model_profiles_get(root)
    profiles = profile_result.get("profiles", []) if isinstance(profile_result, dict) else []
    profile_hashes_ok = bool(profiles) and all(
        isinstance(p, dict) and len(str(p.get("profile_hash", ""))) == 64 for p in profiles
    )

    contentish = {
        "prompt", "prompt_text", "response", "response_text", "content", "raw_content",
        "request_text", "evidence_text", "credential", "secret",
    }
    observation_numeric_only = not (observation_columns & contentish)

    protected_false = (
        "protected_content_translation_allowed",
        "protected_content_paraphrase_allowed",
        "protected_content_summarization_allowed",
        "protected_content_token_pruning_allowed",
        "protected_content_word_level_deletion_allowed",
    )
    checks = {
        "version": version == EXPECTED_VERSION,
        "schema": schema == EXPECTED_SCHEMA,
        "migration_1_to_current": versions == list(range(1, EXPECTED_SCHEMA + 1)),
        "foreign_keys": fk == 1,
        "adaptive_tables": EXPECTED_TABLES <= tables,
        "transport_pack_budget_columns": EXPECTED_PACK_COLUMNS <= pack_columns,
        "governance_version": policy.get("version") == EXPECTED_VERSION,
        "governance_schema": policy.get("documentation_policy", {}).get("current_schema") == EXPECTED_SCHEMA,
        "transport_v2": tp.get("database_schema") == EXPECTED_SCHEMA and tp.get("compiler") == "llm_transport_compiler_v2",
        "lossless_control_plane": (
            tp.get("control_plane_mode") == "lossless"
            and tp.get("original_user_request_verbatim_required") is True
            and tp.get("agents_authority_verbatim_required") is True
            and tp.get("approved_scope_lossless_required") is True
            and float(tp.get("requirement_preservation_rate_required", 0)) == 1.0
            and tp.get("fail_closed_if_control_plane_exceeds_budget") is True
            and _false(tp, *protected_false)
        ),
        "deterministic_evidence_only": (
            tp.get("evidence_plane_mode") == "deterministic_extractable"
            and tp.get("compression_ladder") == EXPECTED_LADDER
            and tp.get("generative_llm_summarization_allowed") is False
            and tp.get("gzip_base64_minify_as_semantic_compression_allowed") is False
        ),
        "adaptive_enabled": (
            tp.get("adaptive_token_budget_enabled") is True
            and tp.get("model_profile_hash_pin_required") is True
            and tp.get("budget_decision_persistence_required") is True
            and ab.get("default_mode") == "adaptive"
            and set(ab.get("allowed_modes", [])) == {"adaptive", "fixed"}
            and ab.get("algorithm") == "adaptive_budget_v1"
        ),
        "profile_registry_local_data_only": (
            ab.get("profile_registry") == "local_data_only"
            and ab.get("profile_hash_pin_required") is True
            and _false(ab, "network_model_discovery_allowed", "provider_api_profile_discovery_allowed", "dynamic_profile_code_allowed", "tokenizer_auto_download_allowed")
        ),
        "calibration_privacy_and_monotonic_safety": (
            ab.get("calibration_enabled") is True
            and ab.get("calibration_numeric_only") is True
            and set(ab.get("observation_sources", [])) == {
                "runtime_report", "provider_usage", "tokenizer_probe",
                "operator_verified", "benchmark", "local_runtime",
            }
            and _false(ab, "calibration_prompt_content_persist_allowed", "calibration_response_content_persist_allowed", "calibration_can_reduce_safety_margin", "calibration_can_reduce_output_floor")
            and observation_numeric_only
        ),
        "model_switching_outside_agentos": (
            ab.get("model_switching_authority") == "external_runtime_only"
            and ab.get("agentos_budget_profile_must_not_switch_provider_or_model") is True
        ),
        "mcp_adaptive_mutation_forbidden": _false(ab, "mcp_observation_mutation_allowed", "mcp_profile_mutation_allowed", "mcp_budget_mutation_allowed"),
        "profile_hashes_present": profile_hashes_ok,
        "privacy_preserved": (
            dsr.get("local_execution_only") is True
            and dsr.get("mcp_mutation_allowed") is False
            and dsr.get("target_update_allowed") is False
            and dsr.get("target_delete_allowed") is False
        ),
        "secret_lineage_preserved": (
            secret.get("secret_persist_allowed") is False
            and secret.get("secret_mcp_allowed") is False
            and lineage.get("historical_rehmac_without_raw_identifier_forbidden") is True
        ),
        "source_read_only": _false(boundary, "source_insert_allowed", "source_update_allowed", "source_delete_allowed", "source_merge_allowed", "source_ddl_allowed"),
        "target_safety": _false(target, "raw_target_insert_allowed", "arbitrary_sql_allowed", "source_write_allowed", "update_allowed", "delete_allowed", "upsert_allowed", "merge_allowed", "mcp_may_execute_insert"),
        "unified_runtime": _false(runtime, "version_forwarding_runtime_allowed", "mcp_subprocess_forwarding_allowed", "extension_mutation_tools_exposed_over_mcp"),
        "mcp_privileged_mutation_absent": enforcement.get("mcp_privileged_mutation_exposed") is False,
        "cli_unique": len(cli) == len(cli_set),
        "cli_complete": EXPECTED_CLI <= cli_set,
        "mcp_unique": len(mcp_names) == len(mcp_set),
        "mcp_context_exact": context_mcp == EXPECTED_CONTEXT_MCP,
        "forbidden_mcp_absent": not forbidden_mcp,
    }
    result = {
        "ok": all(checks.values()),
        "version": version,
        "schema": schema,
        "foreign_keys": fk,
        "cli_count": len(cli),
        "mcp_count": len(mcp_names),
        "context_mcp": sorted(context_mcp),
        "forbidden_mcp": forbidden_mcp,
        "model_profile_count": len(profiles),
        "observation_columns": sorted(observation_columns),
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
