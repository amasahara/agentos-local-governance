"""
File: .agents/agentos/release_integrity.py

Purpose:
    Verify that a release contains both the historical governance core and the
    v0.20-v0.22 extension branch without silent degradation.

Responsibilities:
    - Validate required core files and historical regression coverage.
    - Validate the central schema contract and migration continuity.
    - Detect dead compatibility launchers and committed runtime cache files.
    - Produce deterministic machine-readable integrity findings.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from .schema_version import CURRENT_SCHEMA_VERSION

CORE_FILES = (
    ".agents/agentos/core.py",
    ".agents/agentos/cli.py",
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/db.py",
    ".agents/agentos/policy.py",
    ".agents/agentos/workflow.py",
    ".agents/agentos/proxy.py",
    ".agents/agentos/security.py",
    ".agents/agentos/tooling.py",
    ".agents/agentos/external_audit.py",
    ".agents/agentos/memory.py",
    ".agents/agentos/mcp_server.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/mcp_catalog.py",
    ".agents/tests/test_agentos.py",
    ".agents/bin/agentos",
    ".agents/bin/agentos-mcp",
    ".agents/bin/agentos.cmd",
    ".agents/bin/agentos-mcp.cmd",
)
RELEASE_FILES = (
    ".agents/bin/hooks/pre-commit",
    "tools/apply_v0223.py",
    "tools/apply_v0224.py",
    "tools/apply_v0225.py",
    "tools/build_manifest.py",
    "tools/verify_manifest.py",
    "tools/validate_release.py",
    ".agents/tests/test_governance_enforcement_v0224.py",
    ".agents/tests/test_unified_runtime_v0225.py",
    "UPGRADE_FROM_0.22.3.md",
    "UPGRADE_FROM_0.22.4.md",
    "tools/apply_v0226.py",
    "tools/validate_v0226.py",
    "tools/validate_release.py",
    ".agents/tests/test_secret_lineage_v0226.py",
    "UPGRADE_FROM_0.22.5.md",
    "tools/apply_v0227.py",
    "tools/validate_v0227.py",
    ".agents/tests/test_data_subject_rights_v0227.py",
    "UPGRADE_FROM_0.22.6.md",
    "DATA_SUBJECT_RIGHTS.md",
    ".agents/docs/PRIVACY_BOUNDARY_V0227.md",
    ".agents/docs/USAGE_V0227.md",
    "tools/apply_v0230.py",
    "tools/validate_v0230.py",
    ".agents/tests/test_context_transport_v0230.py",
    "UPGRADE_FROM_0.22.7.md",
    ".agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md",
    "tools/apply_v0231.py",
    "tools/validate_v0231.py",
    ".agents/tests/test_adaptive_budget_v0231.py",
    "UPGRADE_FROM_0.23.0.md",
    ".agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md",
    "ADAPTIVE_TOKEN_BUDGET_BENCHMARK.json",
    "tools/apply_v0232.py",
    "tools/validate_v0232.py",
    ".agents/tests/test_context_expansion_evaluation_v0232.py",
    "UPGRADE_FROM_0.23.1.md",
    ".agents/docs/CONTEXT_EXPANSION_COMPRESSION_EVALUATION_V0232.md",
    "CONTEXT_EXPANSION_EVALUATION_BENCHMARK.json",
    ".agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md",
    "tools/apply_v0233.py",
    "tools/validate_v0233.py",
    ".agents/tests/test_consolidation_cockpit_v0233.py",
    ".agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md",
    "UPGRADE_FROM_0.23.2.md",
    "PERFORMANCE_BASELINE_V0233.json",
    "tools/apply_v0234.py",
    "tools/validate_v0234.py",
    ".agents/tests/test_incremental_index_v0234.py",
    ".agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md",
    "UPGRADE_FROM_0.23.3.md",
    "INDEX_INCREMENTAL_BENCHMARK_V0234.json",
    ".github/workflows/agentos-release-validation.yml",
)
EXTENSION_FILES = (
    ".agents/agentos/project_identity.py",
    ".agents/agentos/project_selection.py",
    ".agents/agentos/project_consolidation.py",
    ".agents/agentos/database_boundary.py",
    ".agents/agentos/schema_mapping.py",
    ".agents/agentos/read_only_extraction.py",
    ".agents/agentos/controlled_target_insert.py",
    ".agents/agentos/identity_resolution.py",
    ".agents/agentos/reconciliation_recovery.py",
    ".agents/agentos/governance_enforcement.py",
    ".agents/agentos/governance_enforcement_cli.py",
    ".agents/agentos/release_manifest.py",
    ".agents/agentos/secret_lineage.py",
    ".agents/agentos/secret_lineage_cli.py",
    ".agents/agentos/mcp_secret_lineage.py",
    ".agents/agentos/data_subject_rights.py",
    ".agents/agentos/data_subject_rights_cli.py",
    ".agents/agentos/mcp_data_subject_rights.py",
    ".agents/agentos/context_transport.py",
    ".agents/agentos/context_transport_cli.py",
    ".agents/agentos/mcp_context_transport.py",
    ".agents/agentos/adaptive_budget.py",
    ".agents/agentos/adaptive_budget_cli.py",
    ".agents/agentos/mcp_adaptive_budget.py",
    ".agents/agentos/context_evaluation.py",
    ".agents/agentos/context_evaluation_cli.py",
    ".agents/agentos/mcp_context_evaluation.py",
    ".agents/agentos/consolidation_cockpit.py",
    ".agents/agentos/performance_baseline.py",
    ".agents/agentos/consolidation_cockpit_cli.py",
    ".agents/agentos/mcp_consolidation_cockpit.py",
    ".agents/agentos/indexing.py",
    ".agents/agentos/incremental_index_benchmark.py",
)
REQUIRED_POLICY_SECTIONS = (
    "language_policy", "instruction_policy", "filesystem_policy", "claim_policy",
    "workflows", "task_context_policy", "workflow_policy", "drift_policy",
    "installation_policy", "tool_policy", "local_override_policy", "proxy_policy",
    "external_audit_policy", "documentation_policy", "concurrency_policy",
    "security_program", "knowledge_runtime", "execution_platform", "evolution_policy",
    "multi_agent_policy", "evaluation_policy", "storage_policy",
    "project_identity_policy", "primary_project_selection_policy",
    "primary_project_consolidation_policy", "database_boundary_policy",
    "schema_mapping_policy", "read_only_extraction_policy",
    "controlled_target_insert_policy", "identity_resolution_policy",
    "reconciliation_recovery_policy", "governance_enforcement_policy",
    "unified_runtime_policy",
    "secret_resolver_policy", "lineage_key_lifecycle_policy",
    "data_subject_rights_policy", "privacy_boundary_policy",
    "context_transport_policy",
    "adaptive_token_budget_policy",
    "context_expansion_evaluation_policy",
    "consolidation_cockpit_policy",
    "incremental_symbol_index_policy",
)


def _finding(code: str, message: str, path: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "path": path}


def _db_contract_findings(root: Path) -> list[dict[str, Any]]:
    path = root / ".agents/agentos/db.py"
    if not path.exists():
        return [_finding("missing_db_module", "central db.py is missing", str(path))]
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [_finding("invalid_db_module", f"db.py syntax error: {exc}", str(path))]
    functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    findings: list[dict[str, Any]] = []
    for name in ("connect", "migrate", "_m1", "_m31"):
        if name not in functions:
            findings.append(_finding("missing_db_symbol", f"db.py missing {name}", str(path)))
    if "CURRENT_SCHEMA_VERSION" not in text or "SCHEMA_VERSION = CURRENT_SCHEMA_VERSION" not in text:
        findings.append(_finding("schema_source_not_central", "db.py does not use CURRENT_SCHEMA_VERSION", str(path)))
    try:
        from .db import _all_migrations
        migrations = _all_migrations()
        if len(migrations) != CURRENT_SCHEMA_VERSION:
            findings.append(_finding("migration_chain_length_mismatch", f"expected {CURRENT_SCHEMA_VERSION} migrations, got {len(migrations)}", str(path)))
    except Exception as exc:
        findings.append(_finding("migration_registry_unloadable", f"cannot load migration registry: {exc}", str(path)))
    for required in ("PRAGMA foreign_keys = ON", "PRAGMA busy_timeout = 5000"):
        if required not in text:
            findings.append(_finding("missing_sqlite_hardening", f"db.py missing {required}", str(path)))
    return findings


def check_release_integrity(root: Path) -> dict[str, Any]:
    """Return a fail-closed package/core reintegration report.

    Args:
        root: AgentOS project root.

    Returns:
        Structured integrity result with findings and schema/version metadata.
    """
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    for rel in (*CORE_FILES, *EXTENSION_FILES, *RELEASE_FILES):
        path = root / rel
        if not path.is_file() or path.stat().st_size == 0:
            findings.append(_finding("missing_required_file", "required release file is missing or empty", rel))
    findings.extend(_db_contract_findings(root))
    try:
        from .performance_baseline import check_performance_baseline
        baseline_result = check_performance_baseline(root)
        for code in baseline_result.get("findings", []):
            findings.append(_finding("performance_baseline_invalid", str(code), "PERFORMANCE_BASELINE_V0233.json"))
    except Exception as exc:
        findings.append(_finding("performance_baseline_unloadable", f"cannot validate performance baseline: {exc}", "PERFORMANCE_BASELINE_V0233.json"))
    try:
        from .incremental_index_benchmark import check_incremental_index_benchmark
        index_benchmark = check_incremental_index_benchmark(root)
        for code in index_benchmark.get("findings", []):
            findings.append(_finding("incremental_index_benchmark_invalid", str(code), "INDEX_INCREMENTAL_BENCHMARK_V0234.json"))
    except Exception as exc:
        findings.append(_finding("incremental_index_benchmark_unloadable", f"cannot validate incremental index benchmark: {exc}", "INDEX_INCREMENTAL_BENCHMARK_V0234.json"))
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else None
    if version != "0.23.4":
        findings.append(_finding("version_mismatch", f"expected VERSION 0.23.4, got {version!r}", "VERSION"))

    policy_path = root / ".agents/config/governance.json"
    if not policy_path.exists():
        findings.append(_finding("missing_governance", "governance.json is missing", str(policy_path)))
    else:
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            missing = sorted(set(REQUIRED_POLICY_SECTIONS) - set(policy))
            if missing:
                findings.append(_finding("missing_policy_sections", f"missing policy sections: {missing}", ".agents/config/governance.json"))
            if policy.get("version") != "0.23.4":
                findings.append(_finding("policy_version_mismatch", "governance.json version must be 0.23.4", ".agents/config/governance.json"))
        except Exception as exc:
            findings.append(_finding("invalid_governance", f"cannot parse governance.json: {exc}", ".agents/config/governance.json"))

    for rel, forbidden in ((".agents/bin/agentos.v0195", "exit 0"), (".agents/bin/agentos-mcp.v0195", "\ncat\n")):
        path = root / rel
        if not path.exists():
            findings.append(_finding("missing_core_compat_launcher", "core compatibility launcher is missing", rel))
        else:
            text = "\n" + path.read_text(encoding="utf-8", errors="replace").strip() + "\n"
            if forbidden in text:
                findings.append(_finding("dead_core_compat_launcher", f"dead compatibility behavior detected: {forbidden.strip()}", rel))

    runtime_wrappers = {
        ".agents/bin/agentos": "agentos.cli_runtime",
        ".agents/bin/agentos.cmd": "agentos.cli_runtime",
        ".agents/bin/agentos-mcp": "agentos.mcp_runtime",
        ".agents/bin/agentos-mcp.cmd": "agentos.mcp_runtime",
    }
    for rel, required_runtime in runtime_wrappers.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if required_runtime not in text:
            findings.append(_finding("runtime_wrapper_mismatch", f"wrapper must execute {required_runtime}", rel))
        if "agentos.v0" in text or "agentos-mcp.v0" in text or "mcp_reconciliation_recovery_gateway" in text:
            findings.append(_finding("legacy_runtime_forwarding_active", "top-level wrapper still uses version/gateway forwarding", rel))

    try:
        from .cli_runtime import command_registry
        commands = command_registry()
        if len(commands) != len(set(commands)):
            findings.append(_finding("duplicate_cli_commands", "unified CLI registry contains duplicate commands"))
    except Exception as exc:
        findings.append(_finding("cli_runtime_unloadable", f"cannot load unified CLI registry: {exc}", ".agents/agentos/cli_runtime.py"))

    try:
        from .mcp_runtime import ALL_TOOLS
        tool_names = [str(item.get("name")) for item in ALL_TOOLS]
        if len(tool_names) != len(set(tool_names)):
            findings.append(_finding("duplicate_mcp_tools", "unified MCP catalog contains duplicate tool names"))
        if "agentos.mcp_health" not in tool_names:
            findings.append(_finding("missing_mcp_health", "unified MCP catalog must expose agentos.mcp_health"))
    except Exception as exc:
        findings.append(_finding("mcp_runtime_unloadable", f"cannot load unified MCP runtime: {exc}", ".agents/agentos/mcp_runtime.py"))

    for rel in (".agents/agentos/cli_runtime.py", ".agents/agentos/mcp_runtime.py"):
        path = root / rel
        if path.exists() and "import subprocess" in path.read_text(encoding="utf-8", errors="replace"):
            findings.append(_finding("runtime_subprocess_forbidden", "unified runtime must not import subprocess", rel))

    # Runtime caches may legitimately be created while running validation. Treat
    # them as a release-integrity failure only when they are actually committed
    # into the authoritative MANIFEST. The manifest builder excludes them.
    manifest_path = root / "MANIFEST.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            bad = []
            for entry in manifest.get("files", []):
                rel = str(entry.get("path", ""))
                parts = Path(rel).parts
                if "__pycache__" in parts or ".pytest_cache" in parts or rel.endswith(".pyc"):
                    bad.append(rel)
            if bad:
                findings.append(_finding("committed_runtime_artifacts", f"runtime cache artifacts are present in MANIFEST: {bad[:20]}"))
        except Exception as exc:
            findings.append(_finding("invalid_manifest", f"cannot inspect MANIFEST.json: {exc}", "MANIFEST.json"))

    return {
        "ok": not findings,
        "version": version,
        "schema": CURRENT_SCHEMA_VERSION,
        "core_file_count": len(CORE_FILES),
        "extension_file_count": len(EXTENSION_FILES),
        "release_file_count": len(RELEASE_FILES),
        "findings": findings,
    }

DOC_FILES = (
    ".agents/docs/PROJECT_IDENTITY.md",
    ".agents/docs/PRIMARY_PROJECT_SELECTION.md",
    ".agents/docs/PRIMARY_PROJECT_CONSOLIDATION.md",
    ".agents/docs/SOURCE_TARGET_DATABASE_BOUNDARY.md",
    ".agents/docs/TARGET_SCHEMA_CONTRACT_AND_FIELD_MAPPING.md",
    ".agents/docs/READ_ONLY_EXTRACTION_AND_DATA_VALIDATION.md",
    ".agents/docs/CONTROLLED_TARGET_INSERT.md",
    ".agents/docs/IDENTITY_RESOLUTION_DEDUPLICATION_LINEAGE.md",
    ".agents/docs/RECONCILIATION_AND_RECOVERY.md",
    ".agents/docs/CORE_REINTEGRATION_V0223.md",
    ".agents/docs/UNIFIED_GOVERNANCE_ENFORCEMENT_V0224.md",
    ".agents/docs/UNIFIED_CLI_MCP_RUNTIME_V0225.md",
    ".agents/docs/SECRET_RESOLVER_LINEAGE_KEY_LIFECYCLE.md",
    ".agents/docs/USAGE_V0226.md",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    "DATA_SUBJECT_RIGHTS.md",
    ".agents/docs/PRIVACY_BOUNDARY_V0227.md",
    ".agents/docs/USAGE_V0227.md",
    ".agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md",
    "tools/apply_v0231.py",
    "tools/validate_v0231.py",
    ".agents/tests/test_adaptive_budget_v0231.py",
    "UPGRADE_FROM_0.23.0.md",
    ".agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md",
    "tools/apply_v0232.py",
    "tools/validate_v0232.py",
    ".agents/tests/test_context_expansion_evaluation_v0232.py",
    "UPGRADE_FROM_0.23.1.md",
    ".agents/docs/CONTEXT_EXPANSION_COMPRESSION_EVALUATION_V0232.md",
    ".agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md",
    ".agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md",
    "UPGRADE_FROM_0.23.2.md",
    "PERFORMANCE_BASELINE_V0233.json",
    ".agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md",
    "UPGRADE_FROM_0.23.3.md",
    "INDEX_INCREMENTAL_BENCHMARK_V0234.json",
)


def docs_check_current(root: Path) -> dict[str, Any]:
    """Run the current release documentation gate without stale node-version checks.

    Older node-specific docs checks intentionally validate their historical release
    numbers and therefore cannot be chained as the current-release gate. v0.23.4
    validates their authoritative documents are present, while the core docs checker
    validates the current VERSION/governance/package synchronization.
    """
    from .core import docs_check as core_docs_check

    root = root.resolve()
    core = core_docs_check(root)
    missing = [rel for rel in DOC_FILES if not (root / rel).is_file()]
    integrity = check_release_integrity(root)
    return {
        "ok": bool(core.get("ok")) and not missing and integrity.get("ok") is True,
        "version": (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else None,
        "core_docs": core,
        "missing_node_docs": missing,
        "release_integrity_ok": integrity.get("ok") is True,
        "release_integrity_findings": integrity.get("findings", []),
    }



# Backward-compatible import name for historical callers.
docs_check_v0223 = docs_check_current
