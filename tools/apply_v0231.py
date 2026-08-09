#!/usr/bin/env python3
"""Apply the exact AgentOS v0.23.0 -> v0.23.1 upgrade overlay.

File: tools/apply_v0231.py

Purpose:
    Upgrade an exact v0.23.0 AgentOS repository to v0.23.1 while preserving
    historical governance/runtime content and rebuilding full-target release
    integrity metadata.

Responsibilities:
    - Fail closed unless VERSION/schema/transport-policy evidence matches v0.23.0.
    - Back up every replaced file before mutation.
    - Merge only the v0.23.1 context/adaptive-budget policy changes.
    - Install schema 45 adaptive model-profile and token-budget runtime in-process.
    - Reassert protected Control Plane, SOURCE/TARGET, privacy, secret and MCP boundaries.
    - Rebuild full-target MANIFEST.json and CHECKSUMS.sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FROM = "0.23.0"
TO = "0.23.1"
SCHEMA_FROM = 44
SCHEMA_TO = 45

COPY_FILES = (
    ".agents/agentos/__init__.py",
    ".agents/agentos/adaptive_budget.py",
    ".agents/agentos/adaptive_budget_cli.py",
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/context_transport.py",
    ".agents/agentos/context_transport_cli.py",
    ".agents/agentos/db.py",
    ".agents/agentos/mcp_adaptive_budget.py",
    ".agents/agentos/mcp_catalog.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/policy.py",
    ".agents/agentos/release_integrity.py",
    ".agents/agentos/schema_version.py",
    ".agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md",
    ".agents/docs/PROJECT_STRUCTURE.md",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ".agents/docs/USAGE.md",
    ".agents/tests/test_adaptive_budget_v0231.py",
    ".agents/tests/test_context_transport_v0230.py",
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "README.vi.md",
    "README.en.md",
    "RELEASE_NOTES.md",
    "UPGRADE_FROM_0.23.0.md",
    "VERSION",
    "huong_dan.md",
    "huong_dan.vi.md",
    "huong_dan.en.md",
    "VALIDATION_REPORT.json",
    "PACKAGE_COMPLETENESS.json",
    "ADAPTIVE_TOKEN_BUDGET_BENCHMARK.json",
    "tools/apply_v0231.py",
    "tools/validate_v0231.py",
    "tools/validate_release.py",
)

EXECUTABLE_FILES = {
    "tools/apply_v0231.py",
    "tools/validate_v0231.py",
    "tools/validate_release.py",
}

EXCLUDE_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "state", "runtime", "cache",
    "task-workspaces", "downloads", "exports", "validation-artifacts", "tool-artifacts",
}
EXCLUDE_FILES = {"MANIFEST.json", "CHECKSUMS.sha256"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_check(root: Path) -> dict[str, Any]:
    """Validate exact v0.23.0 predecessor evidence before any write."""
    required = [
        root / "VERSION",
        root / ".agents/agentos/schema_version.py",
        root / ".agents/agentos/context_transport.py",
        root / ".agents/agentos/context_transport_cli.py",
        root / ".agents/agentos/mcp_context_transport.py",
        root / ".agents/agentos/cli_runtime.py",
        root / ".agents/agentos/mcp_catalog.py",
        root / ".agents/config/governance.json",
        root / ".agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError(f"v0.23.0 baseline is incomplete; missing: {missing}")

    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if version != FROM:
        raise RuntimeError(f"refusing upgrade: VERSION must be {FROM}, got {version!r}")

    schema_text = (root / ".agents/agentos/schema_version.py").read_text(encoding="utf-8")
    if f"CURRENT_SCHEMA_VERSION = {SCHEMA_FROM}" not in schema_text:
        raise RuntimeError("refusing upgrade: schema_version.py is not schema 44")

    transport_text = (root / ".agents/agentos/context_transport.py").read_text(encoding="utf-8")
    if "MIGRATION_VERSION = 44" not in transport_text or "TRANSPORT_VERSION = 1" not in transport_text:
        raise RuntimeError("refusing upgrade: v0.23.0 transport runtime evidence is missing")
    if (root / ".agents/agentos/adaptive_budget.py").exists():
        raise RuntimeError("refusing upgrade: adaptive_budget.py already exists on v0.23.0 target")

    governance = _read_json(root / ".agents/config/governance.json")
    if str(governance.get("version")) != FROM:
        raise RuntimeError(f"refusing upgrade: governance version must be {FROM}")
    if int(governance.get("documentation_policy", {}).get("current_schema", -1)) != SCHEMA_FROM:
        raise RuntimeError("refusing upgrade: governance current_schema must be 44")
    tp = governance.get("context_transport_policy", {})
    if not (
        int(tp.get("database_schema", -1)) == SCHEMA_FROM
        and tp.get("compiler") == "llm_transport_compiler_v1"
        and tp.get("control_plane_mode") == "lossless"
        and float(tp.get("requirement_preservation_rate_required", 0)) == 1.0
        and tp.get("fail_closed_if_control_plane_exceeds_budget") is True
        and tp.get("mcp_mutation_allowed") is False
    ):
        raise RuntimeError("refusing upgrade: v0.23.0 requirement-preservation policy is not exact/current")

    return {
        "version": version,
        "schema": SCHEMA_FROM,
        "transport_version": 1,
        "control_plane_lossless": True,
        "requirement_preservation_rate": 1.0,
    }


def _merge_governance(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Merge only v0.23.1 policy additions while preserving predecessor sections."""
    target = json.loads(json.dumps(target))
    target["version"] = TO
    if "governance_version" in target:
        target["governance_version"] = TO
    target.setdefault("documentation_policy", {})["current_schema"] = SCHEMA_TO

    for key in ("context_transport_policy", "adaptive_token_budget_policy"):
        if key not in source:
            raise RuntimeError(f"overlay governance missing required section: {key}")
        target[key] = source[key]

    # Reassert v0.23.0 protected-content authority.
    tp = target.setdefault("context_transport_policy", {})
    tp["control_plane_mode"] = "lossless"
    tp["original_user_request_verbatim_required"] = True
    tp["agents_authority_verbatim_required"] = True
    tp["approved_scope_lossless_required"] = True
    tp["requirement_preservation_rate_required"] = 1.0
    tp["fail_closed_if_control_plane_exceeds_budget"] = True
    tp["generative_llm_summarization_allowed"] = False
    tp["protected_content_translation_allowed"] = False
    tp["protected_content_paraphrase_allowed"] = False
    tp["protected_content_summarization_allowed"] = False
    tp["protected_content_token_pruning_allowed"] = False
    tp["protected_content_word_level_deletion_allowed"] = False
    tp["mcp_mutation_allowed"] = False

    adaptive = target.setdefault("adaptive_token_budget_policy", {})
    adaptive["profile_hash_pin_required"] = True
    adaptive["network_model_discovery_allowed"] = False
    adaptive["provider_api_profile_discovery_allowed"] = False
    adaptive["dynamic_profile_code_allowed"] = False
    adaptive["tokenizer_auto_download_allowed"] = False
    adaptive["calibration_numeric_only"] = True
    adaptive["calibration_prompt_content_persist_allowed"] = False
    adaptive["calibration_response_content_persist_allowed"] = False
    adaptive["calibration_can_reduce_safety_margin"] = False
    adaptive["calibration_can_reduce_output_floor"] = False
    adaptive["fail_closed_if_control_plane_exceeds_budget"] = True
    adaptive["model_switching_authority"] = "external_runtime_only"
    adaptive["agentos_budget_profile_must_not_switch_provider_or_model"] = True
    adaptive["mcp_observation_mutation_allowed"] = False
    adaptive["mcp_profile_mutation_allowed"] = False
    adaptive["mcp_budget_mutation_allowed"] = False

    # Reassert predecessor governance/safety boundaries.
    enforcement = target.setdefault("governance_enforcement_policy", {})
    enforcement["mcp_privileged_mutation_exposed"] = False
    runtime = target.setdefault("unified_runtime_policy", {})
    runtime["version_forwarding_runtime_allowed"] = False
    runtime["mcp_subprocess_forwarding_allowed"] = False
    runtime["extension_mutation_tools_exposed_over_mcp"] = False
    dsr = target.setdefault("data_subject_rights_policy", {})
    dsr["mcp_mutation_allowed"] = False
    dsr["target_update_allowed"] = False
    dsr["target_delete_allowed"] = False
    dsr["target_upsert_allowed"] = False
    dsr["target_merge_allowed"] = False
    secret = target.setdefault("secret_resolver_policy", {})
    secret["secret_persist_allowed"] = False
    secret["secret_mcp_allowed"] = False
    secret["secret_llm_allowed"] = False
    return target


def _authoritative_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.as_posix() in EXCLUDE_FILES or path.name.endswith(".pyc"):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rebuild_integrity_metadata(root: Path) -> dict[str, Any]:
    """Rebuild full-target manifest/checksums excluding generated runtime state."""
    entries: list[dict[str, Any]] = []
    checksum_lines: list[str] = []
    for path in _authoritative_files(root):
        rel = path.relative_to(root).as_posix()
        digest = _sha256(path)
        entries.append({"path": rel, "size": path.stat().st_size, "sha256": digest})
        checksum_lines.append(f"{digest}  {rel}")
    manifest = {"release": TO, "kind": "full", "file_count": len(entries), "files": entries}
    (root / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    overlay = Path(__file__).resolve().parents[1]

    evidence = _baseline_check(root)
    for rel in COPY_FILES:
        if not (overlay / rel).is_file():
            raise RuntimeError(f"upgrade overlay is incomplete: missing {rel}")
    if not (overlay / ".agents/config/governance.json").is_file():
        raise RuntimeError("upgrade overlay is incomplete: missing governance.json")

    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "from": FROM,
            "to": TO,
            "schema_from": SCHEMA_FROM,
            "schema_to": SCHEMA_TO,
            "baseline": evidence,
            "copy_file_count": len(COPY_FILES),
        }, ensure_ascii=False, indent=2))
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / ".agents/runtime/upgrade-backups" / f"v0230-to-v0231-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)

    backup_rels = list(COPY_FILES) + [".agents/config/governance.json", "MANIFEST.json", "CHECKSUMS.sha256"]
    for rel in backup_rels:
        src = root / rel
        if src.is_file():
            dst = backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    for rel in COPY_FILES:
        src = overlay / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if rel in EXECUTABLE_FILES:
            dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    target_policy_path = root / ".agents/config/governance.json"
    target_policy = _read_json(target_policy_path)
    overlay_policy = _read_json(overlay / ".agents/config/governance.json")
    merged = _merge_governance(target_policy, overlay_policy)
    target_policy_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = rebuild_integrity_metadata(root)
    print(json.dumps({
        "ok": True,
        "from": FROM,
        "to": TO,
        "schema_from": SCHEMA_FROM,
        "schema_to": SCHEMA_TO,
        "backup": str(backup),
        "manifest_file_count": manifest["file_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
