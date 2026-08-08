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
    ".agents/agentos/db.py",
    ".agents/agentos/policy.py",
    ".agents/agentos/workflow.py",
    ".agents/agentos/proxy.py",
    ".agents/agentos/security.py",
    ".agents/agentos/tooling.py",
    ".agents/agentos/external_audit.py",
    ".agents/agentos/memory.py",
    ".agents/agentos/mcp_server.py",
    ".agents/tests/test_agentos.py",
    ".agents/bin/agentos",
    ".agents/bin/agentos-mcp",
    ".agents/bin/agentos.cmd",
)
RELEASE_FILES = (
    ".agents/bin/hooks/pre-commit",
    "tools/apply_v0223.py",
    "tools/build_manifest.py",
    "tools/verify_manifest.py",
    "tools/validate_release.py",
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
    "reconciliation_recovery_policy",
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
    for version in range(32, 41):
        if f"migration_{version}" not in text or f"_m{version}" not in text:
            findings.append(_finding("missing_extension_migration", f"migration {version} is not registered", str(path)))
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

    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else None
    if version != "0.22.3":
        findings.append(_finding("version_mismatch", f"expected VERSION 0.22.3, got {version!r}", "VERSION"))

    policy_path = root / ".agents/config/governance.json"
    if not policy_path.exists():
        findings.append(_finding("missing_governance", "governance.json is missing", str(policy_path)))
    else:
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            missing = sorted(set(REQUIRED_POLICY_SECTIONS) - set(policy))
            if missing:
                findings.append(_finding("missing_policy_sections", f"missing policy sections: {missing}", ".agents/config/governance.json"))
            if policy.get("version") != "0.22.3":
                findings.append(_finding("policy_version_mismatch", "governance.json version must be 0.22.3", ".agents/config/governance.json"))
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
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
)


def docs_check_v0223(root: Path) -> dict[str, Any]:
    """Run the current release documentation gate without stale node-version checks.

    Older node-specific docs checks intentionally validate their historical release
    numbers and therefore cannot be chained as the current-release gate. v0.22.3
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

