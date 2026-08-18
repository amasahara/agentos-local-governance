"""Path: .agents/agentos/release_coherence.py
Purpose: Validate that all authoritative AgentOS release metadata resolves to one release identity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CLEAN_MAIN_EXCLUDED_METADATA = {
    "VALIDATION_REPORT.json",
}


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from *path*.

    Input:
        path: JSON file expected to contain an object.
    Output:
        Parsed dictionary.
    Raises:
        ValueError: The JSON root is not an object.
        OSError/json.JSONDecodeError: The file cannot be read or parsed.
    """

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a recursive dictionary merge without mutating either input.

    Kept local so release-coherence can still be loaded standalone by historical
    regression tests without requiring package-relative imports.
    """

    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _finding(code: str, message: str, path: str | None = None) -> dict[str, str]:
    """Create one deterministic coherence finding.

    Input:
        code: Stable machine-readable finding code.
        message: Human-readable explanation.
        path: Optional repository-relative evidence path.
    Output:
        Finding dictionary suitable for validators and tests.
    """

    item = {"code": code, "message": message}
    if path:
        item["path"] = path
    return item


def _contains_identity(text: str, *, version: str, release_name: str) -> bool:
    """Return whether a current-release identity document names both release and release name.

    Input:
        text: UTF-8 document content.
        version: Expected semantic release version without a leading ``v`` requirement.
        release_name: Expected release title from governance policy.
    Output:
        ``True`` when both values occur literally in the document.
    """

    return bool(version and release_name and version in text and release_name in text)


def check_release_metadata_coherence(
    root: Path | str,
    *,
    runtime_version: str | None = None,
    package_version: str | None = None,
    schema_version: int | None = None,
) -> dict[str, Any]:
    """Check AgentOS release metadata for one coherent release identity.

    Input:
        root: Repository root.
        runtime_version: Optional MCP runtime release override for isolated tests.
        package_version: Optional ``agentos.__version__`` override for isolated tests.
        schema_version: Optional schema-version override for isolated tests.
    Output:
        Dictionary containing ``ok``, resolved identity, performed checks, and findings.

    The check is read-only and fail-closed. Missing, malformed, stale, or contradictory
    metadata is reported as a finding instead of being repaired implicitly.
    """

    repo = Path(root).resolve()
    findings: list[dict[str, str]] = []
    checks: list[str] = []

    version_path = repo / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        version = ""
        findings.append(_finding("version_unreadable", str(exc), "VERSION"))
    if not version:
        findings.append(_finding("version_missing", "VERSION must be non-empty", "VERSION"))
    checks.append("VERSION")

    if runtime_version is None:
        try:
            from .mcp_runtime import VERSION as runtime_version  # local import avoids import cycles
        except Exception as exc:  # pragma: no cover - defensive integration boundary
            runtime_version = ""
            findings.append(
                _finding("runtime_version_unreadable", f"cannot resolve MCP runtime VERSION: {exc}", ".agents/agentos/mcp_runtime.py")
            )
    if version and runtime_version != version:
        findings.append(
            _finding(
                "runtime_version_mismatch",
                f"MCP runtime VERSION {runtime_version!r} != repository VERSION {version!r}",
                ".agents/agentos/mcp_runtime.py",
            )
        )
    checks.append("runtime_version")

    if package_version is None:
        try:
            from . import __version__ as package_version
        except Exception as exc:  # pragma: no cover - defensive integration boundary
            package_version = ""
            findings.append(
                _finding("package_runtime_version_unreadable", f"cannot resolve agentos.__version__: {exc}", ".agents/agentos/__init__.py")
            )
    if version and package_version != version:
        findings.append(
            _finding(
                "package_runtime_version_mismatch",
                f"agentos.__version__ {package_version!r} != repository VERSION {version!r}",
                ".agents/agentos/__init__.py",
            )
        )
    checks.append("package_runtime_version")

    if schema_version is None:
        try:
            from .schema_version import CURRENT_SCHEMA_VERSION as schema_version
        except Exception as exc:  # pragma: no cover - defensive integration boundary
            schema_version = -1
            findings.append(
                _finding("schema_version_unreadable", f"cannot resolve CURRENT_SCHEMA_VERSION: {exc}", ".agents/agentos/schema_version.py")
            )
    checks.append("schema_version")

    json_paths = {
        "manifest": repo / "MANIFEST.json",
        "package": repo / "PACKAGE_COMPLETENESS.json",
    }
    payloads: dict[str, dict[str, Any]] = {}
    try:
        governance = _read_json(repo / ".agents/config/governance.json")
        release_policy_path = repo / ".agents/config/release_policy.json"
        if release_policy_path.is_file():
            governance = _deep_merge(governance, _read_json(release_policy_path))
        payloads["governance"] = governance
    except Exception as exc:
        payloads["governance"] = {}
        findings.append(_finding("governance_unreadable", str(exc), ".agents/config/governance.json"))
    checks.append("governance")
    for key, path in json_paths.items():
        try:
            payloads[key] = _read_json(path)
        except Exception as exc:
            payloads[key] = {}
            findings.append(_finding(f"{key}_unreadable", str(exc), str(path.relative_to(repo))))
        checks.append(key)

    governance = payloads["governance"]
    manifest = payloads["manifest"]
    package = payloads["package"]

    if version and governance.get("version") != version:
        findings.append(
            _finding(
                "governance_version_mismatch",
                f"governance.version {governance.get('version')!r} != VERSION {version!r}",
                ".agents/config/governance.json",
            )
        )

    docs_policy = governance.get("documentation_policy")
    if not isinstance(docs_policy, dict):
        docs_policy = {}
        findings.append(
            _finding("documentation_policy_missing", "documentation_policy must be an object", ".agents/config/governance.json")
        )
    release_name = str(docs_policy.get("current_release_name") or "").strip()
    if not release_name:
        findings.append(
            _finding("release_name_missing", "documentation_policy.current_release_name must be non-empty", ".agents/config/governance.json")
        )
    if docs_policy.get("current_schema") != schema_version:
        findings.append(
            _finding(
                "documentation_schema_mismatch",
                f"documentation_policy.current_schema {docs_policy.get('current_schema')!r} != runtime schema {schema_version!r}",
                ".agents/config/governance.json",
            )
        )

    coherence_policy = governance.get("release_metadata_coherence_policy")
    if not isinstance(coherence_policy, dict):
        findings.append(
            _finding(
                "coherence_policy_missing",
                "release_metadata_coherence_policy must be defined",
                ".agents/config/governance.json",
            )
        )
    else:
        if coherence_policy.get("source_of_truth") != "VERSION":
            findings.append(
                _finding(
                    "coherence_source_invalid",
                    "release_metadata_coherence_policy.source_of_truth must be VERSION",
                    ".agents/config/governance.json",
                )
            )
        if coherence_policy.get("fail_closed") is not True:
            findings.append(
                _finding(
                    "coherence_not_fail_closed",
                    "release metadata coherence must be fail-closed",
                    ".agents/config/governance.json",
                )
            )

    if version and manifest.get("release") != version:
        findings.append(
            _finding(
                "manifest_release_mismatch",
                f"MANIFEST release {manifest.get('release')!r} != VERSION {version!r}",
                "MANIFEST.json",
            )
        )
    if version and package.get("release") != version:
        findings.append(
            _finding(
                "package_release_mismatch",
                f"PACKAGE_COMPLETENESS release {package.get('release')!r} != VERSION {version!r}",
                "PACKAGE_COMPLETENESS.json",
            )
        )
    if package.get("schema") != schema_version:
        findings.append(
            _finding(
                "package_schema_mismatch",
                f"PACKAGE_COMPLETENESS schema {package.get('schema')!r} != runtime schema {schema_version!r}",
                "PACKAGE_COMPLETENESS.json",
            )
        )

    manifest_count = manifest.get("file_count")
    package_count = package.get("authoritative_file_count")
    if isinstance(manifest_count, int) and package_count != manifest_count:
        findings.append(
            _finding(
                "package_file_count_mismatch",
                f"PACKAGE_COMPLETENESS authoritative_file_count {package_count!r} != MANIFEST file_count {manifest_count!r}",
                "PACKAGE_COMPLETENESS.json",
            )
        )

    required_top_level = package.get("required_top_level")
    if not isinstance(required_top_level, list):
        findings.append(
            _finding("package_required_top_level_invalid", "required_top_level must be a list", "PACKAGE_COMPLETENESS.json")
        )
        required_top_level = []
    if "PACKAGE_COMPLETENESS.json" not in required_top_level:
        findings.append(
            _finding(
                "package_self_contract_missing",
                "PACKAGE_COMPLETENESS.json must be listed in required_top_level",
                "PACKAGE_COMPLETENESS.json",
            )
        )
    for raw in required_top_level:
        rel = str(raw)
        if rel in CLEAN_MAIN_EXCLUDED_METADATA:
            findings.append(
                _finding(
                    "excluded_metadata_required",
                    f"{rel} is a generated release artifact and cannot be required in clean-main package completeness",
                    "PACKAGE_COMPLETENESS.json",
                )
            )
            continue
        if not (repo / rel).exists():
            findings.append(_finding("required_top_level_missing", f"required top-level file is missing: {rel}", rel))

    identity_files = docs_policy.get("current_release_identity_files")
    if not isinstance(identity_files, list):
        findings.append(
            _finding(
                "identity_files_invalid",
                "documentation_policy.current_release_identity_files must be a list",
                ".agents/config/governance.json",
            )
        )
        identity_files = []
    for raw in identity_files:
        rel = str(raw)
        path = repo / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(_finding("identity_file_unreadable", str(exc), rel))
            continue
        if not _contains_identity(text, version=version, release_name=release_name):
            findings.append(
                _finding(
                    "identity_file_mismatch",
                    f"{rel} must contain current version {version!r} and release name {release_name!r}",
                    rel,
                )
            )

    return {
        "ok": not findings,
        "version": version,
        "schema": schema_version,
        "release_name": release_name,
        "checks": checks,
        "findings": findings,
    }
