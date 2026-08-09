#!/usr/bin/env python3
"""Apply the exact AgentOS v0.23.1 -> v0.23.2 upgrade overlay.

File: tools/apply_v0232.py

Purpose:
    Upgrade an exact v0.23.1/schema-45 AgentOS repository to v0.23.2 while
    preserving all earlier governance/runtime invariants.

Responsibilities:
    - Fail closed unless predecessor version/schema/context policy is v0.23.1.
    - Back up every replaced file before mutation.
    - Add schema 46 Context Expansion & Compression Evaluation runtime.
    - Merge only v0.23.2 policy changes into the predecessor governance file.
    - Reassert lossless Control Plane, read-only MCP, privacy, secret, and DB boundaries.
    - Rebuild full-target MANIFEST.json and CHECKSUMS.sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FROM = "0.23.1"
TO = "0.23.2"
SCHEMA_FROM = 45
SCHEMA_TO = 46

COPY_FILES = (
    "VERSION",
    ".agents/agentos/__init__.py",
    ".agents/agentos/schema_version.py",
    ".agents/agentos/db.py",
    ".agents/agentos/context_transport.py",
    ".agents/agentos/context_transport_cli.py",
    ".agents/agentos/context_evaluation.py",
    ".agents/agentos/context_evaluation_cli.py",
    ".agents/agentos/mcp_context_transport.py",
    ".agents/agentos/mcp_context_evaluation.py",
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/mcp_catalog.py",
    ".agents/agentos/release_integrity.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/data_subject_rights.py",
    ".agents/tests/test_data_subject_rights_v0227.py",
    ".agents/tests/test_agentos.py",
    ".agents/tests/test_core_reintegration_v0223.py",
    ".agents/tests/test_governance_enforcement_v0224.py",
    ".agents/tests/test_unified_runtime_v0225.py",
    ".agents/tests/test_identity_resolution_v0221.py",
    ".agents/tests/test_adaptive_budget_v0231.py",
    ".agents/tests/test_context_expansion_evaluation_v0232.py",
    ".agents/docs/CONTEXT_EXPANSION_COMPRESSION_EVALUATION_V0232.md",
    ".agents/docs/PROJECT_STRUCTURE.md",
    ".agents/docs/USAGE.md",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ".agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md",
    ".github/workflows/agentos-release-validation.yml",
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "README.vi.md",
    "README.en.md",
    "huong_dan.md",
    "huong_dan.vi.md",
    "huong_dan.en.md",
    "RELEASE_NOTES.md",
    "UPGRADE_FROM_0.22.3.md",
    "UPGRADE_FROM_0.22.4.md",
    "UPGRADE_FROM_0.22.5.md",
    "UPGRADE_FROM_0.22.6.md",
    "UPGRADE_FROM_0.22.7.md",
    "UPGRADE_FROM_0.23.1.md",
    "CONTEXT_EXPANSION_EVALUATION_BENCHMARK.json",
    "tools/apply_v0232.py",
    "tools/validate_v0232.py",
    "tools/validate_release.py",
)

EXECUTABLE_FILES = {"tools/apply_v0232.py", "tools/validate_v0232.py", "tools/validate_release.py"}
EXCLUDE_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "state", "runtime", "cache",
    "task-workspaces", "downloads", "exports", "validation-artifacts", "tool-artifacts",
}
EXCLUDE_FILES = {"MANIFEST.json", "CHECKSUMS.sha256"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_check(root: Path) -> dict[str, Any]:
    required = [
        root / "VERSION",
        root / ".agents/agentos/schema_version.py",
        root / ".agents/agentos/context_transport.py",
        root / ".agents/agentos/adaptive_budget.py",
        root / ".agents/agentos/mcp_adaptive_budget.py",
        root / ".agents/agentos/cli_runtime.py",
        root / ".agents/agentos/mcp_catalog.py",
        root / ".agents/config/governance.json",
        root / ".agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError(f"v0.23.1 baseline is incomplete; missing: {missing}")
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if version != FROM:
        raise RuntimeError(f"refusing upgrade: VERSION must be {FROM}, got {version!r}")
    schema_text = (root / ".agents/agentos/schema_version.py").read_text(encoding="utf-8")
    if f"CURRENT_SCHEMA_VERSION = {SCHEMA_FROM}" not in schema_text:
        raise RuntimeError("refusing upgrade: schema_version.py is not schema 45")
    transport_text = (root / ".agents/agentos/context_transport.py").read_text(encoding="utf-8")
    if "MIGRATION_VERSION = 45" not in transport_text or "TRANSPORT_VERSION = 2" not in transport_text:
        raise RuntimeError("refusing upgrade: v0.23.1 transport runtime evidence is missing")
    if (root / ".agents/agentos/context_evaluation.py").exists():
        raise RuntimeError("refusing upgrade: context_evaluation.py already exists")
    policy = _read_json(root / ".agents/config/governance.json")
    tp = policy.get("context_transport_policy", {})
    ab = policy.get("adaptive_token_budget_policy", {})
    if str(policy.get("version")) != FROM:
        raise RuntimeError("refusing upgrade: governance version must be 0.23.1")
    if int(policy.get("documentation_policy", {}).get("current_schema", -1)) != SCHEMA_FROM:
        raise RuntimeError("refusing upgrade: governance current_schema must be 45")
    if not (
        int(tp.get("database_schema", -1)) == SCHEMA_FROM
        and int(tp.get("version", -1)) == 2
        and tp.get("control_plane_mode") == "lossless"
        and float(tp.get("requirement_preservation_rate_required", 0.0)) == 1.0
        and tp.get("fail_closed_if_control_plane_exceeds_budget") is True
        and tp.get("mcp_mutation_allowed") is False
        and tp.get("adaptive_token_budget_enabled") is True
        and int(ab.get("database_schema", -1)) == SCHEMA_FROM
        and ab.get("profile_hash_pin_required") is True
    ):
        raise RuntimeError("refusing upgrade: v0.23.1 transport/adaptive policy is not exact/current")
    return {"version": version, "schema": SCHEMA_FROM, "transport_version": 2}


def _merge_governance(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(target))
    out["version"] = TO
    if "governance_version" in out:
        out["governance_version"] = TO
    out.setdefault("documentation_policy", {})["current_schema"] = SCHEMA_TO

    src_tp = source.get("context_transport_policy", {})
    dst_tp = out.setdefault("context_transport_policy", {})
    # Preserve locally configured model profiles while installing the v0.23.2 contract.
    local_profiles = dst_tp.get("model_profiles")
    for key, value in src_tp.items():
        if key != "model_profiles":
            dst_tp[key] = value
    if local_profiles is not None:
        dst_tp["model_profiles"] = local_profiles
    else:
        dst_tp["model_profiles"] = src_tp.get("model_profiles", {})
    out["context_expansion_evaluation_policy"] = source["context_expansion_evaluation_policy"]

    # Restore historical policy sections that were accidentally dropped by overlay-only
    # v0.23.x materializations. Source values come from the full release tree; existing
    # operator-local values are preserved when already present.
    for key in (
        "language_policy", "installation_policy", "security_program", "execution_platform",
        "evolution_policy", "multi_agent_policy", "evaluation_policy", "storage_policy",
        "knowledge_runtime_fixes",
    ):
        if key not in out and key in source:
            out[key] = json.loads(json.dumps(source[key]))

    # Reassert protected v0.23.0/v0.23.1 invariants.
    dst_tp["control_plane_mode"] = "lossless"
    dst_tp["original_user_request_verbatim_required"] = True
    dst_tp["agents_authority_verbatim_required"] = True
    dst_tp["approved_scope_lossless_required"] = True
    dst_tp["requirement_preservation_rate_required"] = 1.0
    dst_tp["fail_closed_if_control_plane_exceeds_budget"] = True
    dst_tp["generative_llm_summarization_allowed"] = False
    for key in (
        "protected_content_translation_allowed", "protected_content_paraphrase_allowed",
        "protected_content_summarization_allowed", "protected_content_token_pruning_allowed",
        "protected_content_word_level_deletion_allowed", "mcp_mutation_allowed",
        "expansion_content_persistence_allowed",
    ):
        dst_tp[key] = False

    ce = out["context_expansion_evaluation_policy"]
    ce["expansion_read_only"] = True
    ce["expanded_content_persistence_allowed"] = False
    ce["expanded_content_audit_allowed"] = False
    ce["source_hash_pin_required"] = True
    ce["transport_hash_pin_required"] = True
    ce["mcp_evaluation_persistence_allowed"] = False
    ce["mcp_comparison_persistence_allowed"] = False
    ce["llm_may_persist_expansion_telemetry"] = False
    ce["llm_may_persist_evaluation"] = False
    ce["llm_may_mutate_transport"] = False

    # Reassert earlier authority boundaries if those sections exist.
    out.setdefault("governance_enforcement_policy", {})["mcp_privileged_mutation_exposed"] = False
    runtime = out.setdefault("unified_runtime_policy", {})
    runtime["version_forwarding_runtime_allowed"] = False
    runtime["mcp_subprocess_forwarding_allowed"] = False
    runtime["extension_mutation_tools_exposed_over_mcp"] = False
    dsr = out.setdefault("data_subject_rights_policy", {})
    dsr["mcp_mutation_allowed"] = False
    for key in ("target_update_allowed", "target_delete_allowed", "target_upsert_allowed", "target_merge_allowed"):
        dsr[key] = False
    secret = out.setdefault("secret_resolver_policy", {})
    secret["secret_persist_allowed"] = False
    secret["secret_mcp_allowed"] = False
    secret["secret_llm_allowed"] = False
    return out


def _backup_file(root: Path, backup: Path, rel: str) -> None:
    src = root / rel
    if src.exists():
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.name + ".v0232.tmp")
    shutil.copy2(src, temp)
    os.replace(temp, dst)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".v0232.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


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
    entries: list[dict[str, Any]] = []
    checksum_lines: list[str] = []
    for path in _authoritative_files(root):
        rel = path.relative_to(root).as_posix()
        digest = _sha256(path)
        entries.append({"path": rel, "size": path.stat().st_size, "sha256": digest})
        checksum_lines.append(f"{digest}  {rel}")
    manifest = {
        "release": TO,
        "kind": "full_target_after_upgrade",
        "from": FROM,
        "to": TO,
        "file_count": len(entries),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": entries,
    }
    (root / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return {"file_count": len(entries)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    target = Path(args.target).resolve()
    overlay = Path(__file__).resolve().parents[1]
    baseline = _baseline_check(target)
    result: dict[str, Any] = {"ok": True, "from": FROM, "to": TO, "baseline": baseline, "dry_run": args.dry_run}
    if args.dry_run:
        result["would_copy"] = list(COPY_FILES)
        result["would_merge_governance"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target / ".agents/runtime/upgrade-backups" / f"v0232-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for rel in (*COPY_FILES, ".agents/config/governance.json", "MANIFEST.json", "CHECKSUMS.sha256"):
        _backup_file(target, backup, rel)

    for rel in COPY_FILES:
        src = overlay / rel
        if not src.is_file():
            raise RuntimeError(f"overlay missing required file: {rel}")
        _atomic_copy(src, target / rel)
        if rel in EXECUTABLE_FILES:
            (target / rel).chmod((target / rel).stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    merged = _merge_governance(
        _read_json(backup / ".agents/config/governance.json"),
        _read_json(overlay / ".agents/config/governance.json"),
    )
    _atomic_json(target / ".agents/config/governance.json", merged)

    sys.path.insert(0, str(target / ".agents"))
    from agentos.db import connect
    with connect(target) as c:
        schema = int(c.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0])
        fk = int(c.execute("PRAGMA foreign_keys").fetchone()[0])
    if schema != SCHEMA_TO or fk != 1:
        raise RuntimeError(f"post-upgrade database contract failed: schema={schema}, foreign_keys={fk}")

    result["backup"] = str(backup)
    result["schema"] = schema
    result["foreign_keys"] = fk
    result["integrity"] = rebuild_integrity_metadata(target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
