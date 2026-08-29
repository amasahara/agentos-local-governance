"""
File: .agents/agentos/release_integrity.py

Purpose:
    Verify the normalized current AgentOS distribution without requiring
    superseded version-specific release artifacts.

Responsibilities:
    - Validate current core files and required regression coverage.
    - Validate the central schema contract and migration continuity.
    - Detect dead compatibility launchers and committed runtime cache files.
    - Exclude superseded version-specific artifacts from the current payload.
    - Produce deterministic machine-readable integrity findings.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from .schema_version import CURRENT_SCHEMA_VERSION

ROOT_AGENTOS_README_V0260_HASHES = {
    "README.md": "3b014b598954ce7a6d4ae1ea5c73ec0c21500ffb98f5fd285a53cae717f0b193",
    "README.vi.md": "eda433acc61df7ab3eb01e16262ae49e991d5142e15608ca027218f450c85d72",
    "README.en.md": "2d9d032110e4ecd1dc2129ab94f422a884b1d3f8ed9c2eddead378638ef31af0",
}
ROOT_AGENTOS_README_V0261_HASHES = {
    "README.md": "81a382816cacf5af6be6c34b3dbb08a35d2cc7274b29fe3c73a43a09f7dc5117",
    "README.vi.md": "60eb367e7490c52f116321a66e872e12ecf45e9a21b583c3ac109dd702c39de3",
    "README.en.md": "280e4af2eaf9ded80bfc7eb6b524eb08c64feac07ecce9bf6d18a16fd76cc6cc",
}

CORE_FILES = (
    ".agents/agentos/core.py",
    ".agents/agentos/cli.py",
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/cli_identity.py",
    ".agents/agentos/privileged_control_plane.py",
    ".agents/agentos/db.py",
    ".agents/agentos/policy.py",
    ".agents/agentos/workflow.py",
    ".agents/agentos/proxy.py",
    ".agents/agentos/security.py",
    ".agents/agentos/tooling.py",
    ".agents/agentos/enforcement_attestation.py",
    ".agents/agentos/external_audit.py",
    ".agents/agentos/memory.py",
    ".agents/agentos/mcp_server.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/mcp_feature_runtime.py",
    ".agents/agentos/mcp_core_runtime.py",
    ".agents/agentos/mcp_catalog.py",
    ".agents/tests/test_agentos.py",
    ".agents/bin/agentos",
    ".agents/bin/agentos-mcp",
    ".agents/bin/agentos.cmd",
    ".agents/bin/agentos-admin",
    ".agents/bin/agentos-admin.cmd",
    ".agents/bin/agentos-mcp.cmd",
    ".agents/agentos/completion_verification.py",
    ".agents/agentos/completion_surface.py",
    ".agents/agentos/completion_cli.py",
    ".agents/agentos/mcp_v0290.py",
    ".agents/agentos/windows_process_tree.py",
    ".agents/agentos/windows_job_broker.py",
)
RELEASE_FILES = (
    ".agents/tests/test_release_line_endings_v0242.py",
    ".gitattributes",
    ".agents/bin/hooks/pre-commit",
    ".agents/tests/test_adaptive_budget_v0231.py",
    ".agents/tests/test_agentos.py",
    ".agents/tests/test_consolidation_cockpit_v0233.py",
    ".agents/tests/test_context_expansion_evaluation_v0232.py",
    ".agents/tests/test_context_transport_v0230.py",
    ".agents/tests/test_data_subject_rights_v0227.py",
    ".agents/tests/test_db_aware_context_projection_v0242.py",
    ".agents/tests/test_governance_enforcement_v0224.py",
    ".agents/tests/test_incremental_index_v0234.py",
    ".agents/tests/test_risk_tiered_batch_review_v0241.py",
    ".agents/tests/test_release_hardening_v0242.py",
    ".agents/tests/test_secret_lineage_v0226.py",
    ".agents/tests/test_unified_runtime_v0225.py",
    ".agents/tests/test_privileged_control_plane_v0283.py",
    ".agents/tests/test_tool_exclusivity_v0284.py",
    ".agents/tests/test_enforcement_attestation_v0284.py",
    ".github/workflows/agentos-release-validation.yml",
    "RELEASE_NOTES.md",
    "tools/build_manifest.py",
    "tools/repository_release_cleanup.py",
    "tools/validate_release.py",
    "tools/verify_manifest.py",
    ".agents/tests/test_mcp_feature_runtime_v0243.py",
    ".agents/tests/test_schema_bootstrap_v0250.py",
    ".agents/schema/bootstrap_v46.sql",
    ".agents/schema/bootstrap_v46.json",
    ".agents/tests/test_release_metadata_coherence_v0251.py",
    ".agents/tests/test_architecture_discovery_v0253.py",
    ".agents/tests/test_architecture_compliance_v0254.py",
    ".agents/tests/test_architecture_change_v0255.py",
    ".agents/tests/test_architecture_planning_v0260.py",
    ".agents/tests/test_architecture_structural_v0261.py",
    ".agents/tests/test_architecture_runtime_v0262.py",
    ".agents/tests/test_architecture_quality_v0263.py",
    ".agents/tests/test_governed_skill_contract_v0270.py",
    ".agents/tests/test_architecture_aware_skill_selection_v0271.py",
    ".agents/tests/test_multi_agent_supervisor_v0272.py",
    ".agents/tests/test_isolated_workspace_integration_v0273.py",
    ".agents/tests/test_architecture_agent_command_center_v0280.py",
    ".agents/tests/test_optional_web_control_plane_v0281.py",
    ".agents/config/release_policy.json",
    ".agents/docs/GOVERNED_SKILL_CONTRACT_V0270.md",
    ".agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md",
    ".agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md",
    ".agents/docs/ISOLATED_WORKSPACE_CONTROLLED_INTEGRATION_V0273.md",
    ".agents/docs/ARCHITECTURE_AGENT_COMMAND_CENTER_V0280.md",
    ".agents/docs/OPTIONAL_LOCAL_WEB_CONTROL_PLANE_V0281.md",
    ".agents/docs/INSTALL_LATEST_RELEASE.md",
    ".agents/config/update_ownership.v0253.json",
    ".agents/config/update_ownership.v0254.json",
    ".agents/config/update_ownership.v0255.json",
    ".agents/config/update_ownership.v0260.json",
    ".agents/config/update_ownership.v0261.json",
    ".agents/tests/test_completion_verification_v0290.py",
    ".agents/tests/test_workflow_completion_v0290.py",
    ".agents/tests/test_completion_surface_v0290.py",
    ".agents/tests/test_completion_attestation_v0290.py",
    ".agents/tests/test_completion_activation_v0290.py",
    ".agents/tests/test_windows_process_tree_v0291.py",
    ".agents/tests/test_windows_process_exec_containment_v0291.py",
    ".agents/tests/test_windows_job_broker_v0291.py",
    ".agents/tests/test_windows_async_job_containment_v0291.py",
    ".agents/tests/test_windows_async_timeout_v0291.py",
    ".agents/tests/test_windows_process_tree_attestation_v0291.py",
    ".agents/docs/WINDOWS_PROCESS_TREE_CONTAINMENT_V0291.md",
    ".agents/tests/test_windows_process_tree_activation_v0291.py",
    ".agents/tests/test_windows_ci_gate_v0291.py",
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
    ".agents/agentos/release_coherence.py",
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
    ".agents/agentos/risk_tiered_batch_review.py",
    ".agents/agentos/risk_tiered_batch_review_cli.py",
    ".agents/agentos/mcp_risk_tiered_batch_review.py",
    ".agents/agentos/db_aware_context_projection.py",
    ".agents/agentos/db_aware_context_projection_cli.py",
    ".agents/agentos/mcp_db_aware_context_projection.py",
    ".agents/agentos/mcp_feature_handlers.py",
    ".agents/agentos/schema_bootstrap.py",
    ".agents/agentos/architecture_contract.py",
    ".agents/agentos/architecture_contract_cli.py",
    ".agents/agentos/human_decision.py",
    ".agents/agentos/human_decision_cli.py",
    ".agents/agentos/mcp_v0252.py",
    ".agents/agentos/architecture_discovery.py",
    ".agents/agentos/architecture_discovery_cli.py",
    ".agents/agentos/mcp_v0253.py",
    ".agents/agentos/update_preservation.py",
    ".agents/agentos/architecture_compliance.py",
    ".agents/agentos/architecture_compliance_cli.py",
    ".agents/agentos/mcp_v0254.py",
    ".agents/agentos/architecture_change.py",
    ".agents/agentos/architecture_change_cli.py",
    ".agents/agentos/mcp_v0255.py",
    ".agents/agentos/architecture_planning.py",
    ".agents/agentos/architecture_planning_cli.py",
    ".agents/agentos/mcp_v0260.py",
    ".agents/agentos/architecture_structural.py",
    ".agents/agentos/architecture_structural_cli.py",
    ".agents/agentos/mcp_v0261.py",
    ".agents/agentos/architecture_runtime.py",
    ".agents/agentos/architecture_runtime_cli.py",
    ".agents/agentos/mcp_v0262.py",
    ".agents/agentos/architecture_quality.py",
    ".agents/agentos/architecture_quality_cli.py",
    ".agents/agentos/mcp_v0263.py",
    ".agents/agentos/skill_contract_v2.py",
    ".agents/agentos/mcp_v0270.py",
    ".agents/agentos/skill_selection.py",
    ".agents/agentos/skill_selection_cli.py",
    ".agents/agentos/mcp_v0271.py",
    ".agents/agentos/multi_agent_supervisor.py",
    ".agents/agentos/multi_agent_supervisor_cli.py",
    ".agents/agentos/mcp_v0272.py",
    ".agents/agentos/multi_agent_workspace.py",
    ".agents/agentos/multi_agent_workspace_cli.py",
    ".agents/agentos/mcp_v0273.py",
    ".agents/agentos/command_center.py",
    ".agents/agentos/command_center_cli.py",
    ".agents/agentos/mcp_v0280.py",
    ".agents/agentos/web_control_plane.py",
    ".agents/agentos/web_control_plane_cli.py",
)
REQUIRED_POLICY_SECTIONS = (
    "language_policy",
    "instruction_policy",
    "filesystem_policy",
    "claim_policy",
    "workflows",
    "task_context_policy",
    "workflow_policy",
    "drift_policy",
    "installation_policy",
    "tool_policy",
    "local_override_policy",
    "proxy_policy",
    "external_audit_policy",
    "documentation_policy",
    "concurrency_policy",
    "security_program",
    "knowledge_runtime",
    "execution_platform",
    "evolution_policy",
    "multi_agent_policy",
    "evaluation_policy",
    "storage_policy",
    "project_identity_policy",
    "primary_project_selection_policy",
    "primary_project_consolidation_policy",
    "database_boundary_policy",
    "schema_mapping_policy",
    "read_only_extraction_policy",
    "controlled_target_insert_policy",
    "identity_resolution_policy",
    "reconciliation_recovery_policy",
    "governance_enforcement_policy",
    "unified_runtime_policy",
    "secret_resolver_policy",
    "lineage_key_lifecycle_policy",
    "data_subject_rights_policy",
    "privacy_boundary_policy",
    "context_transport_policy",
    "adaptive_token_budget_policy",
    "context_expansion_evaluation_policy",
    "consolidation_cockpit_policy",
    "incremental_symbol_index_policy",
    "risk_tiered_batch_review_policy",
    "db_aware_context_projection_policy",
    "mcp_feature_runtime_policy",
    "schema_bootstrap_policy",
    "release_metadata_coherence_policy",
    "architecture_contract_policy",
    "human_clarification_policy",
    "architecture_discovery_policy",
    "update_preservation_policy",
    "architecture_compliance_policy",
    "architecture_change_policy",
    "architecture_planning_policy",
    "architecture_structural_policy",
    "architecture_runtime_policy",
    "architecture_quality_policy",
    "command_center_policy",
    "web_control_plane_policy",
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
    for name in ("connect", "connect_read_only", "migrate", "migrate_with_report", "_m1", "_m31"):
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



def _windows_ci_contract(root: Path) -> dict:
    workflow_path = (
        root
        / ".github/workflows/agentos-release-validation.yml"
    )
    if not workflow_path.is_file():
        return {
            "ok": False,
            "workflow": str(workflow_path.relative_to(root)),
            "runner": "windows-latest",
            "missing_markers": ["workflow_missing"],
        }

    text = workflow_path.read_text(encoding="utf-8")
    focused_tests = (
        "test_windows_process_tree_v0291.py",
        "test_windows_process_exec_containment_v0291.py",
        "test_windows_job_broker_v0291.py",
        "test_windows_async_job_containment_v0291.py",
        "test_windows_async_timeout_v0291.py",
        "test_windows_process_tree_attestation_v0291.py",
        "test_windows_process_tree_activation_v0291.py",
    )
    required_markers = (
        "validate-windows:",
        "runs-on: windows-latest",
        "python-version: '3.13'",
        "python tools/validate_release.py . --skip-manifest",
        "python tools/verify_manifest.py .",
        r".\.agents\bin\agentos.cmd runtime-health",
        r".\.agents\bin\agentos.cmd docs-check",
        r".\.agents\bin\agentos.cmd instruction-check",
        *focused_tests,
        "python -m pytest -q .agents/tests -rs",
    )
    missing = [
        marker
        for marker in required_markers
        if marker not in text
    ]
    return {
        "ok": not missing,
        "workflow": ".github/workflows/agentos-release-validation.yml",
        "runner": "windows-latest",
        "focused_containment_suite": not any(
            marker in missing
            for marker in focused_tests
        ),
        "activation_suite": (
            "test_windows_process_tree_activation_v0291.py"
            not in missing
        ),
        "full_regression_suite": (
            "python -m pytest -q .agents/tests -rs"
            not in missing
        ),
        "missing_markers": missing,
    }


def check_release_integrity(root: Path) -> dict[str, Any]:
    """Return a fail-closed package/core reintegration report.

    Args:
        root: AgentOS project root.

    Returns:
        Structured integrity result with findings and schema/version metadata.
    """
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    attestation_report: dict[str, Any] | None = None
    for rel in (*CORE_FILES, *EXTENSION_FILES, *RELEASE_FILES):
        path = root / rel
        if not path.is_file() or path.stat().st_size == 0:
            findings.append(_finding("missing_required_file", "required release file is missing or empty", rel))
    findings.extend(_db_contract_findings(root))
    # v0.25.0 schema-bootstrap artifact gate.
    try:
        from .schema_bootstrap import (
            BASELINE_SCHEMA_VERSION,
            bootstrap_artifact_status,
        )
        bootstrap_status = bootstrap_artifact_status()
        if BASELINE_SCHEMA_VERSION != 46:
            findings.append(_finding(
                "schema_bootstrap_baseline_mismatch",
                f"expected schema bootstrap baseline 46, got {BASELINE_SCHEMA_VERSION}",
                ".agents/agentos/schema_bootstrap.py",
            ))
        if bootstrap_status.get("ok") is not True:
            findings.append(_finding(
                "schema_bootstrap_artifact_invalid",
                f"bootstrap artifact validation failed: {bootstrap_status}",
                ".agents/schema/bootstrap_v46.sql",
            ))
        if bootstrap_status.get("historical_migrations_invoked") != 0:
            findings.append(_finding(
                "schema_bootstrap_replay_detected",
                "fresh bootstrap artifact path must not invoke historical migrations",
                ".agents/agentos/schema_bootstrap.py",
            ))
    except Exception as exc:
        findings.append(_finding(
            "schema_bootstrap_unloadable",
            f"cannot validate schema bootstrap baseline: {exc}",
            ".agents/agentos/schema_bootstrap.py",
        ))
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else None
    if not version:
        findings.append(_finding("version_missing", "VERSION must be non-empty", "VERSION"))

    # Root README files remain project-owned. We only govern byte-identical AgentOS
    # release documents: the known stale v0.26.0 copies must not survive this upgrade,
    # while custom README content is preserved and ignored by this release gate.
    for rel in ("README.md", "README.vi.md", "README.en.md"):
        path = root / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == ROOT_AGENTOS_README_V0260_HASHES[rel]:
            findings.append(_finding("root_readme_release_stale", f"{rel} is still the official v0.26.0 README and must be reconciled for v0.26.1", rel))
            continue
        if digest != ROOT_AGENTOS_README_V0261_HASHES[rel]:
            continue
        text = raw.decode("utf-8", errors="replace")
        if version and version not in text[:1200]:
            findings.append(_finding("root_readme_version_stale", f"{rel} must identify current release {version}", rel))
        schema_markers = (f"Database schema: **{CURRENT_SCHEMA_VERSION}**", f"Database schema: **{CURRENT_SCHEMA_VERSION}**.")
        if not any(marker in text[:1600] for marker in schema_markers):
            findings.append(_finding("root_readme_schema_stale", f"{rel} must identify database schema {CURRENT_SCHEMA_VERSION}", rel))

    policy_path = root / ".agents/config/governance.json"
    if not policy_path.exists():
        findings.append(_finding("missing_governance", "governance.json is missing", str(policy_path)))
    else:
        try:
            from .policy import load_release_policy
            policy = load_release_policy(root)
            required_policy_sections = set(REQUIRED_POLICY_SECTIONS)
            try:
                release_version = tuple(int(part) for part in str(policy.get("version") or version or "0.0.0").split("."))
            except ValueError:
                release_version = (0, 0, 0)
            if release_version >= (0, 27, 0):
                required_policy_sections.add("governed_skill_contract_policy")
            if release_version >= (0, 27, 1):
                required_policy_sections.add("architecture_aware_skill_selection_policy")
            if release_version >= (0, 27, 2):
                required_policy_sections.add("multi_agent_supervisor_policy")
            if release_version >= (0, 27, 3):
                required_policy_sections.add("isolated_workspace_integration_policy")
            if release_version >= (0, 28, 3):
                required_policy_sections.add("privileged_control_plane_policy")
                if release_version >= (0, 29, 1):
                    required_policy_sections.add("windows_process_tree_containment_policy")
            missing = sorted(required_policy_sections - set(policy))
            if missing:
                findings.append(_finding("missing_policy_sections", f"missing policy sections: {missing}", ".agents/config/governance.json"))
            if policy.get("version") != version:
                findings.append(_finding("policy_version_mismatch", f"effective governance version must equal VERSION {version!r}", ".agents/config/release_policy.json"))
            install = policy.get("installation_policy") or {}
            if install.get("distribution_model") != "download_latest_full_release" or install.get("updater_script_required") is not False:
                findings.append(_finding("distribution_model_invalid", "v0.27.0+ must use latest full release without updater scripts", ".agents/config/release_policy.json"))
        except Exception as exc:
            findings.append(_finding("invalid_governance", f"cannot load effective governance: {exc}", ".agents/config/governance.json"))

    # v0.28.4 tool-exclusivity structural attestation gate.
    #
    # During development on VERSION 0.28.3, the structural report must
    # already be green while policy_declared_attested remains false.
    # Once VERSION becomes 0.28.4, the release declaration itself also
    # becomes mandatory.
    try:
        from .enforcement_attestation import (
            ATTESTATION_SCOPE,
            attest_enforcement,
        )

        attestation_report = attest_enforcement(root)

        if (
            attestation_report.get("ok") is not True
            or attestation_report.get("attestation_ready") is not True
            or attestation_report.get("tool_exclusivity") is not True
        ):
            findings.append(
                _finding(
                    "enforcement_attestation_failed",
                    "tool-exclusivity structural attestation is not green: "
                    f"{attestation_report.get('findings', [])}",
                    ".agents/agentos/enforcement_attestation.py",
                )
            )

        if attestation_report.get("scope") != ATTESTATION_SCOPE:
            findings.append(
                _finding(
                    "enforcement_attestation_scope_invalid",
                    "enforcement attestation scope is missing or invalid",
                    ".agents/agentos/enforcement_attestation.py",
                )
            )

        try:
            attested_release_version = tuple(
                int(part)
                for part in str(version or "0.0.0").split(".")
            )
        except ValueError:
            attested_release_version = (0, 0, 0)

        if attested_release_version >= (0, 28, 4):
            if (
                attestation_report.get("policy_declared_attested")
                is not True
            ):
                findings.append(
                    _finding(
                        "tool_exclusivity_policy_not_activated",
                        "v0.28.4+ requires policy-declared tool exclusivity",
                        ".agents/config/release_policy.json",
                    )
                )

            non_claims = (
                attestation_report.get("non_claims")
                or {}
            )

            required_non_claims = (
                "same_user_host_bypass_resistance",
                "os_level_process_isolation_attested",
                "arbitrary_host_process_containment",
            )

            invalid_non_claims = [
                key
                for key in required_non_claims
                if non_claims.get(key) is not False
            ]

            if invalid_non_claims:
                findings.append(
                    _finding(
                        "enforcement_attestation_overclaim",
                        "v0.28.4 security scope overclaims host/OS "
                        f"isolation: {invalid_non_claims}",
                        ".agents/agentos/enforcement_attestation.py",
                    )
                )

        process_tree_attestation = (
            attestation_report.get(
                "windows_process_tree_containment"
            )
            or {}
        )
        required_process_tree_assertions = (
            "structurally_attested",
            "sync_enforced",
            "async_enforced",
            "assignment_before_resume",
            "timeout_tree_termination",
            "cancellation_tree_termination",
            "broker_fail_closed",
            "completion_evidence_bound",
            "broad_nonclaims_preserved",
            "windows_only",
        )
        invalid_process_tree_assertions = [
            key
            for key in required_process_tree_assertions
            if process_tree_attestation.get(key) is not True
        ]
        if invalid_process_tree_assertions:
            findings.append(
                _finding(
                    "windows_process_tree_attestation_failed",
                    "Windows process-tree structural attestation is not green: "
                    f"{invalid_process_tree_assertions}",
                    ".agents/agentos/enforcement_attestation.py",
                )
            )

        if attested_release_version >= (0, 29, 1):
            if (
                process_tree_attestation.get(
                    "policy_declared_attested"
                )
                is not True
            ):
                findings.append(
                    _finding(
                        "windows_process_tree_policy_not_activated",
                        "v0.29.1+ requires policy-declared Windows process-tree containment attestation",
                        ".agents/config/release_policy.json",
                    )
                )

            if (
                process_tree_attestation.get("policy_scope")
                != "agentos_mediated_process_execution"
            ):
                findings.append(
                    _finding(
                        "windows_process_tree_scope_invalid",
                        "v0.29.1 containment scope must remain bounded to AgentOS-mediated process execution",
                        ".agents/config/release_policy.json",
                    )
                )
        windows_ci_validation = (
            _windows_ci_contract(root)
        )

        if (
            attested_release_version
            >= (0, 29, 1)
            and windows_ci_validation.get("ok")
            is not True
        ):
            findings.append(
                _finding(
                    "windows_ci_validation_missing",
                    "v0.29.1+ requires a Windows GitHub Actions validation job with focused containment and full regression coverage: "
                    f"{windows_ci_validation.get('missing_markers', [])}",
                    ".github/workflows/agentos-release-validation.yml",
                )
            )
        completion_attestation = (
            attestation_report.get("completion_verification")
            or {}
        )
        required_completion_assertions = (
            "structurally_attested",
            "producer_independent",
            "evidence_bound",
            "freshness_bound",
            "workflow_enforced",
            "worker_enforced",
            "integration_enforced",
            "cli_agent_plane_only",
            "mcp_read_only",
        )
        invalid_completion_assertions = [
            key
            for key in required_completion_assertions
            if completion_attestation.get(key) is not True
        ]
        if invalid_completion_assertions:
            findings.append(
                _finding(
                    "completion_attestation_failed",
                    "independent-completion structural attestation is not green: "
                    f"{invalid_completion_assertions}",
                    ".agents/agentos/enforcement_attestation.py",
                )
            )

        if attested_release_version >= (0, 29, 0):
            if (
                completion_attestation.get("policy_declared_attested")
                is not True
            ):
                findings.append(
                    _finding(
                        "completion_attestation_policy_not_activated",
                        "v0.29.0+ requires policy-declared independent completion attestation",
                        ".agents/config/release_policy.json",
                    )
                )

            completion_non_claims = (
                attestation_report.get("non_claims")
                or {}
            )
            required_completion_non_claims = (
                "semantic_correctness_guaranteed",
                "model_provider_independence_attested",
                "human_review_replaced",
                "human_approval_replaced",
            )
            invalid_completion_non_claims = [
                key
                for key in required_completion_non_claims
                if completion_non_claims.get(key) is not False
            ]
            if invalid_completion_non_claims:
                findings.append(
                    _finding(
                        "completion_attestation_overclaim",
                        "v0.29.0 completion scope overclaims semantic, provider, or human-authority guarantees: "
                        f"{invalid_completion_non_claims}",
                        ".agents/agentos/enforcement_attestation.py",
                    )
                )

    except Exception as exc:
        findings.append(
            _finding(
                "enforcement_attestation_unloadable",
                f"cannot execute enforcement attestation: {exc}",
                ".agents/agentos/enforcement_attestation.py",
            )
        )

    try:
        from .release_coherence import check_release_metadata_coherence
        coherence = check_release_metadata_coherence(root)
        for item in coherence.get("findings", []):
            findings.append(_finding(
                "release_metadata_incoherent",
                f"{item.get('code')}: {item.get('message')}",
                item.get("path"),
            ))
    except Exception as exc:
        findings.append(_finding(
            "release_metadata_coherence_unloadable",
            f"cannot validate release metadata coherence: {exc}",
            ".agents/agentos/release_coherence.py",
        ))
    legacy_launchers = sorted(
        p.relative_to(root).as_posix()
        for pattern in (".agents/bin/agentos.v*", ".agents/bin/agentos-mcp.v*")
        for p in root.glob(pattern)
        if p.is_file()
    )
    if legacy_launchers:
        findings.append(_finding(
            "legacy_versioned_launcher_present",
            f"versioned compatibility launchers belong in Git tags/releases: {legacy_launchers}",
        ))
    runtime_wrappers = {
        ".agents/bin/agentos": "agentos.cli_runtime",
        ".agents/bin/agentos.cmd": "agentos.cli_runtime",
        ".agents/bin/agentos-admin": "agentos.privileged_control_plane",
        ".agents/bin/agentos-admin.cmd": "agentos.privileged_control_plane",
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
        from .cli_runtime import (
            DUAL_PLANE_COMMANDS,
            agent_command_registry,
            command_registry,
            privileged_command_registry,
        )

        commands = command_registry()
        if len(commands) != len(set(commands)):
            findings.append(
                _finding(
                    "duplicate_cli_commands",
                    "canonical CLI registry contains duplicate commands",
                )
            )

        agent_commands = set(agent_command_registry())
        privileged_commands = set(privileged_command_registry())

        unexpected_overlap = sorted(
            (agent_commands & privileged_commands)
            - set(DUAL_PLANE_COMMANDS)
        )

        if unexpected_overlap:
            findings.append(
                _finding(
                    "privileged_control_plane_overlap",
                    "agent and privileged registries overlap outside "
                    f"the dual-plane allowlist: {unexpected_overlap}",
                    ".agents/agentos/cli_runtime.py",
                )
            )

        if not privileged_commands:
            findings.append(
                _finding(
                    "privileged_control_plane_empty",
                    "privileged control-plane registry must not be empty",
                    ".agents/agentos/cli_runtime.py",
                )
            )

    except Exception as exc:
        findings.append(
            _finding(
                "cli_runtime_unloadable",
                f"cannot load separated CLI registries: {exc}",
                ".agents/agentos/cli_runtime.py",
            )
        )

    try:
        from .mcp_runtime import ALL_TOOLS
        tool_names = [str(item.get("name")) for item in ALL_TOOLS]
        if len(tool_names) != len(set(tool_names)):
            findings.append(_finding("duplicate_mcp_tools", "unified MCP catalog contains duplicate tool names"))
        if "agentos.mcp_health" not in tool_names:
            findings.append(_finding("missing_mcp_health", "unified MCP catalog must expose agentos.mcp_health"))
    except Exception as exc:
        findings.append(_finding("mcp_runtime_unloadable", f"cannot load unified MCP runtime: {exc}", ".agents/agentos/mcp_runtime.py"))

    # v0.24.3 MCP feature-runtime active import graph gate.
    active_mcp_modules = (
        ".agents/agentos/mcp_runtime.py",
        ".agents/agentos/mcp_core_runtime.py",
        ".agents/agentos/mcp_feature_runtime.py",
        ".agents/agentos/mcp_feature_handlers.py",
        ".agents/agentos/mcp_catalog.py",
    )
    legacy_mcp_imports = {
        "mcp_identity_gateway",
        "mcp_selection_gateway",
        "mcp_consolidation_gateway",
        "mcp_database_boundary_gateway",
        "mcp_schema_mapping_gateway",
        "mcp_read_only_extraction_gateway",
        "mcp_controlled_target_insert_gateway",
        "mcp_identity_resolution_gateway",
        "mcp_reconciliation_recovery_gateway",
        "mcp_server",
    }
    for rel in active_mcp_modules:
        path = root / rel
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[-1])
                elif isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[-1] for alias in node.names)
            forbidden = sorted(imported & legacy_mcp_imports)
            if forbidden:
                findings.append(_finding(
                    "mcp_feature_runtime_legacy_import",
                    f"active MCP runtime imports legacy gateway modules: {forbidden}",
                    rel,
                ))
            if "subprocess" in imported:
                findings.append(_finding(
                    "mcp_feature_runtime_subprocess_forbidden",
                    "active MCP runtime must not import subprocess",
                    rel,
                ))
        except Exception as exc:
            findings.append(_finding(
                "mcp_feature_runtime_import_graph_unreadable",
                f"cannot inspect active MCP imports: {exc}",
                rel,
            ))
    try:
        from .mcp_feature_runtime import feature_runtime_health
        feature_health = feature_runtime_health()
        if feature_health.get("legacy_gateway_handler_count") != 0:
            findings.append(_finding(
                "mcp_feature_runtime_legacy_handler_active",
                f"legacy gateway handlers still active: {feature_health.get('legacy_gateway_handler_names')}",
                ".agents/agentos/mcp_feature_runtime.py",
            ))
        if feature_health.get("runtime_native_migrated_tool_count") != 37:
            findings.append(_finding(
                "mcp_feature_runtime_migration_count_mismatch",
                f"expected 37 migrated runtime-native handlers, got {feature_health.get('runtime_native_migrated_tool_count')}",
                ".agents/agentos/mcp_feature_runtime.py",
            ))
        from .mcp_runtime import (
            ALL_TOOLS,
            CORE_TOOL_NAMES,
            FEATURE_TOOL_NAMES,
            V0252_TOOL_NAMES,
            V0253_TOOL_NAMES,
            V0254_TOOL_NAMES,
            V0255_TOOL_NAMES,
            V0260_TOOL_NAMES,
            V0261_TOOL_NAMES,
            V0262_TOOL_NAMES,
            V0263_TOOL_NAMES,
            V0270_TOOL_NAMES,
            V0271_TOOL_NAMES,
            V0272_TOOL_NAMES,
            V0273_TOOL_NAMES,
            V0280_TOOL_NAMES,
        )
        if (
            len(CORE_TOOL_NAMES) != 14
            or len(FEATURE_TOOL_NAMES) != 63
            or len(V0252_TOOL_NAMES) != 6
            or len(V0253_TOOL_NAMES) != 4
            or len(V0254_TOOL_NAMES) != 3
            or len(V0255_TOOL_NAMES) != 4
            or len(V0260_TOOL_NAMES) != 3
            or len(V0261_TOOL_NAMES) != 3
            or len(V0262_TOOL_NAMES) != 3
            or len(V0263_TOOL_NAMES) != 3
            or len(V0270_TOOL_NAMES) != 3
            or len(V0271_TOOL_NAMES) != 3
            or len(V0272_TOOL_NAMES) != 3
            or len(V0273_TOOL_NAMES) != 4
            or len(V0280_TOOL_NAMES) != 3
            or len(ALL_TOOLS) != 124
        ):
            findings.append(_finding(
                "mcp_tool_surface_changed",
                f"expected 14 core + 63 feature + 6 v0.25.2 + 4 v0.25.3 + 3 v0.25.4 + 4 v0.25.5 + 3 v0.26.0 + 3 v0.26.1 + 3 v0.26.2 + 3 v0.26.3 + 3 v0.27.0 + 3 v0.27.1 + 3 v0.27.2 + 4 v0.27.3 + 3 v0.28.0 + 1 v0.29.0 + health = 124 tools, got {len(CORE_TOOL_NAMES)} + {len(FEATURE_TOOL_NAMES)} + {len(V0252_TOOL_NAMES)} + {len(V0253_TOOL_NAMES)} + {len(V0254_TOOL_NAMES)} + {len(V0255_TOOL_NAMES)} + {len(V0260_TOOL_NAMES)} + {len(V0261_TOOL_NAMES)} + {len(V0262_TOOL_NAMES)} + {len(V0263_TOOL_NAMES)} + {len(V0270_TOOL_NAMES)} + {len(V0271_TOOL_NAMES)} + {len(V0272_TOOL_NAMES)} + {len(V0273_TOOL_NAMES)} + {len(V0280_TOOL_NAMES)} / {len(ALL_TOOLS)}",
                ".agents/agentos/mcp_runtime.py",
            ))
    except Exception as exc:
        findings.append(_finding(
            "mcp_feature_runtime_health_unloadable",
            f"cannot validate v0.24.3 MCP feature runtime: {exc}",
            ".agents/agentos/mcp_feature_runtime.py",
        ))
    for rel in (".agents/agentos/cli_runtime.py", ".agents/agentos/mcp_runtime.py"):
        path = root / rel
        if path.exists() and "import subprocess" in path.read_text(encoding="utf-8", errors="replace"):
            findings.append(_finding("runtime_subprocess_forbidden", "unified runtime must not import subprocess", rel))

    # Runtime caches may legitimately be created while running validation. Treat
    # them as a release-integrity failure only when they are actually committed
    # into the authoritative MANIFEST. The manifest builder excludes them.
    # Clean-main release packaging gate.
    release_clutter_globs = ('apply_v*.py', 'apply_v*.py.sha256', 'tools/apply_v*.py', 'tools/validate_v*.py', 'CHECKSUMS_V*.sha256', 'VALIDATION_REPORT*.json', '*.zip', '*.zip.sha256', '.agents/bin/agentos.v*', '.agents/bin/agentos-mcp.v*', '.agents/docs/RELEASE_NOTES_V*.md', '.agents/docs/USAGE_V*.md', '.agents/docs/GITHUB_READY_FULL_RELEASE_V*.md', '.agents/docs/archive/*', '.agents/docs/archive/**', 'HOTFIX_INFO.txt', 'UPGRADE_FROM_0.22*.md', 'UPGRADE_FROM_0.23*.md', 'UPGRADE_FROM_0.24.0.md', 'UPGRADE_FROM_0.24.1.md', 'UPGRADE_FROM_0.24.2.md', 'UPGRADE_FROM_0.24.3.md')
    release_clutter = sorted({
        p.relative_to(root).as_posix()
        for pattern in release_clutter_globs
        for p in root.glob(pattern)
        if p.is_file()
    })
    if release_clutter:
        findings.append(_finding(
            "release_clutter_present",
            f"historical release packaging files must not be present on main: {release_clutter[:50]}",
        ))
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
        "enforcement_attestation": (
            None
            if attestation_report is None
            else {
                "ok": attestation_report.get("ok"),
                "attestation_ready": attestation_report.get(
                    "attestation_ready"
                ),
                "tool_exclusivity": attestation_report.get(
                    "tool_exclusivity"
                ),
                "scope": attestation_report.get("scope"),
                "policy_declared_attested": attestation_report.get(
                    "policy_declared_attested"
                ),
                "completion_verification": attestation_report.get(
                    "completion_verification"
                ),
                "windows_process_tree_containment": attestation_report.get(
                    "windows_process_tree_containment"
                ),
                "windows_ci_validation": windows_ci_validation,
                "finding_count": len(
                    attestation_report.get("findings", [])
                ),
            }
        ),
        "findings": findings,
    }

DOC_FILES = (
    ".agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md",
    ".agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md",
    ".agents/docs/CONTEXT_EXPANSION_COMPRESSION_EVALUATION_V0232.md",
    ".agents/docs/CONTROLLED_TARGET_INSERT.md",
    ".agents/docs/CORE_REINTEGRATION_V0223.md",
    ".agents/docs/DB_AWARE_CONTEXT_PROJECTION_V0242.md",
    ".agents/docs/IDENTITY_RESOLUTION_DEDUPLICATION_LINEAGE.md",
    ".agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md",
    ".agents/docs/PRIMARY_PROJECT_CONSOLIDATION.md",
    ".agents/docs/PRIMARY_PROJECT_SELECTION.md",
    ".agents/docs/PRIVACY_BOUNDARY_V0227.md",
    ".agents/docs/PROJECT_IDENTITY.md",
    ".agents/docs/PROJECT_STRUCTURE.md",
    ".agents/docs/READ_ONLY_EXTRACTION_AND_DATA_VALIDATION.md",
    ".agents/docs/RECONCILIATION_AND_RECOVERY.md",
    ".agents/docs/REPOSITORY_RELEASE_POLICY.md",
    ".agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md",
    ".agents/docs/RISK_TIERED_BATCH_REVIEW_V0241.md",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ".agents/docs/SECRET_RESOLVER_LINEAGE_KEY_LIFECYCLE.md",
    ".agents/docs/SOURCE_TARGET_DATABASE_BOUNDARY.md",
    ".agents/docs/TARGET_SCHEMA_CONTRACT_AND_FIELD_MAPPING.md",
    ".agents/docs/UNIFIED_CLI_MCP_RUNTIME_V0225.md",
    ".agents/docs/UNIFIED_GOVERNANCE_ENFORCEMENT_V0224.md",
    ".agents/docs/GOVERNED_SKILL_CONTRACT_V0270.md",
    ".agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md",
    ".agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md",
    ".agents/docs/ISOLATED_WORKSPACE_CONTROLLED_INTEGRATION_V0273.md",
    ".agents/docs/ARCHITECTURE_AGENT_COMMAND_CENTER_V0280.md",
    ".agents/docs/OPTIONAL_LOCAL_WEB_CONTROL_PLANE_V0281.md",
    ".agents/docs/INSTALL_LATEST_RELEASE.md",
    "CHANGELOG.md",
    "README.en.md",
    "README.md",
    "README.vi.md",
    "RELEASE_NOTES.md",
    "huong_dan.en.md",
    "huong_dan.md",
    "huong_dan.vi.md",
    ".agents/docs/MCP_FEATURE_RUNTIME_REFACTOR_V0243.md",
    ".agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md",
    ".agents/docs/RELEASE_METADATA_COHERENCE_V0251.md",
    ".agents/docs/ARCHITECTURE_CONTRACT_HUMAN_CLARIFICATION_V0252.md",
    ".agents/docs/ARCHITECTURE_DISCOVERY_EVIDENCE_V0253.md",
    ".agents/docs/ARCHITECTURE_DRIFT_COMPLIANCE_V0254.md",
    ".agents/docs/ARCHITECTURE_CHANGE_PROPOSAL_ADR_V0255.md",
    ".agents/docs/ARCHITECTURE_AWARE_TASK_PLANNING_V0260.md",
    ".agents/docs/ARCHITECTURE_STRUCTURAL_ENFORCEMENT_V0261.md",
    ".agents/docs/RUNTIME_DATA_API_BUSINESS_ENFORCEMENT_V0262.md",
    ".agents/docs/QUALITY_OPERATIONAL_ENFORCEMENT_V0263.md",
    ".agents/docs/UPGRADE_FROM_0.26.2.md",
    ".agents/docs/UPGRADE_FROM_0.26.1.md",
    ".agents/docs/UPGRADE_FROM_0.25.3.md",
    ".agents/docs/UPGRADE_FROM_0.25.4.md",
    ".agents/docs/UPGRADE_FROM_0.25.5.md",
    ".agents/docs/UPGRADE_FROM_0.26.0.md",
)


def docs_check_current(root: Path) -> dict[str, Any]:
    """Run the current release documentation gate without stale node-version checks.

    Historical regression tests keep their version-specific assertions, while this
    current-release gate validates only authoritative current docs plus clean-main
    release integrity.
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
