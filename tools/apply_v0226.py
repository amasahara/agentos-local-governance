#!/usr/bin/env python3
"""Apply the exact AgentOS v0.22.5 -> v0.22.6 upgrade overlay."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

FROM="0.22.5"; TO="0.22.6"; SCHEMA_FROM=41; SCHEMA_TO=42
RUNTIME_FILES=[
    "db.py","schema_version.py","cli_runtime.py","mcp_catalog.py","mcp_runtime.py","__init__.py",
    "read_only_extraction.py","controlled_target_insert.py","reconciliation_recovery.py","identity_resolution.py",
    "project_identity.py","project_selection.py","release_integrity.py",
    "secret_lineage.py","secret_lineage_cli.py","mcp_secret_lineage.py",
]
ROOT_FILES=[
    "AGENTS.md","README.md","README.vi.md","README.en.md","huong_dan.md","huong_dan.vi.md","huong_dan.en.md",
    "RELEASE_NOTES.md","CHANGELOG.md","UPGRADE_FROM_0.22.5.md",
]
DOC_FILES=["SECRET_RESOLVER_LINEAGE_KEY_LIFECYCLE.md","USAGE_V0226.md"]
TEST_FILES=["test_secret_lineage_v0226.py"]
TOOL_FILES=["apply_v0226.py","validate_v0226.py","validate_release.py"]
METADATA_FILES=["VALIDATION_REPORT.json","PACKAGE_COMPLETENESS.json"]
MANIFEST_FILES=["MANIFEST.json","CHECKSUMS.sha256"]


def patch_governance(data: dict) -> dict:
    """Mutate only v0.22.6 policy fields while retaining all existing policy nodes."""
    if str(data.get("version", data.get("governance_version"))) != FROM:
        raise RuntimeError("governance baseline version is not 0.22.5")
    data["version"]=TO
    if "governance_version" in data: data["governance_version"]=TO
    data.setdefault("documentation_policy", {})["current_schema"]=SCHEMA_TO
    ext=data.setdefault("read_only_extraction_policy", {})
    ext["default_secret_resolver"]="trusted_registry_v1"; ext["external_secret_resolver_injection_allowed"]=False
    ins=data.setdefault("controlled_target_insert_policy", {})
    ins["default_secret_resolver"]="trusted_registry_v1"; ins["external_secret_resolver_injection_allowed"]=False
    rec=data.setdefault("reconciliation_recovery_policy", {})
    rec["default_secret_resolver"]="trusted_registry_v1"; rec["external_secret_resolver_injection_allowed"]=False
    ident=data.setdefault("identity_resolution_policy", {})
    ident.update({
        "lineage_keyring_version":1,"lineage_keyring_schema":SCHEMA_TO,"lineage_key_statuses":["active","retired","revoked"],
        "new_tokens_use_active_key":True,"retired_key_lookup_allowed":True,"revoked_key_lookup_allowed":False,
        "legacy_key_import_preserves_material":True,"historical_automatic_rehmac_allowed":False,
        "rekey_requires_raw_identifier_source_reread":True,"rekey_source_select_governance_required":True,
    })
    data["secret_resolver_policy"]={
        "resolver_version":1,"database_schema":SCHEMA_TO,"registry":"static_trusted_allowlist",
        "allowed_schemes":["env","keychain","vault","secret","file-secret"],
        "dynamic_importlib_resolver_allowed":False,"provider_identity_required":True,"provider_version_required":True,
        "provider_hash_pin_required":True,"operator_approval_required":True,"capability_policy_required":True,
        "missing_or_untrusted_provider_fails_closed":True,"secret_persist_allowed":False,"secret_audit_allowed":False,
        "secret_mcp_allowed":False,"secret_llm_allowed":False,"secret_cache_allowed":False,"memory_only_resolution":True,
        "allowed_capabilities":["db.source.select","db.target.controlled_insert","db.target.reconciliation_select"],
        "aliases":{},"production_callback_injection_allowed":False,
    }
    data["lineage_key_lifecycle_policy"]={
        "keyring_version":1,"database_schema":SCHEMA_TO,"statuses":["active","retired","revoked"],
        "exactly_one_active_key":True,"rotation_human_review_required":True,"rotation_human_approval_required":True,
        "rotation_signed_audit_required":True,"retired_verify_lookup_allowed":True,"revoked_verify_lookup_allowed":False,
        "key_material_repository_allowed":False,"key_material_mcp_allowed":False,"key_material_llm_allowed":False,
        "legacy_single_key_migration":"move_same_material_and_backfill_key_id",
        "read_only_inspection_initializes_keyring":False,"keyring_initialization_is_privileged":True,
        "historical_rehmac_without_raw_identifier_forbidden":True,"rekey_requires_governed_source_select_reread":True,
    }
    enforcement=data.setdefault("governance_enforcement_policy", {})
    caps=enforcement.setdefault("privileged_capabilities", [])
    for cap in [
        "secret.resolver.approve","secret.resolver.revoke","identity.lineage.key.initialize",
        "identity.lineage.key.rotate.plan","identity.lineage.key.rotate.review","identity.lineage.key.rotate.approve",
        "identity.lineage.key.rotate.execute","identity.lineage.key.revoke","identity.lineage.rekey.plan",
        "identity.lineage.rekey.review","identity.lineage.rekey.approve","identity.lineage.rekey.authorize_source_reread",
    ]:
        if cap not in caps: caps.append(cap)
    enforcement["mcp_privileged_mutation_exposed"]=False
    runtime=data.setdefault("unified_runtime_policy", {})
    runtime["version_forwarding_runtime_allowed"]=False
    runtime["mcp_subprocess_forwarding_allowed"]=False
    runtime["extension_mutation_tools_exposed_over_mcp"]=False
    return data


def _copy(src: Path, dest: Path) -> None:
    """Copy one overlay file unless source and target are the same file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dest.resolve():
        return
    shutil.copy2(src, dest)


def _candidate_files(root: Path) -> list[str]:
    """Return authoritative target files using the v0.22.5 release-manifest exclusions."""
    out=[]
    for path in root.rglob("*"):
        if not path.is_file(): continue
        rel=path.relative_to(root).as_posix()
        if rel in {"MANIFEST.json","CHECKSUMS.sha256"}: continue
        if rel.startswith((".git/",".agents/runtime/",".agents/state/",".pytest_cache/")): continue
        if "__pycache__" in path.relative_to(root).parts or rel.endswith(".pyc"): continue
        out.append(rel)
    return sorted(out)


def _rebuild_target_manifest(root: Path) -> None:
    """Rebuild the applied tree manifest/checksums without including runtime state or secrets."""
    files=[]
    for rel in _candidate_files(root):
        p=root/rel; digest=hashlib.sha256(p.read_bytes()).hexdigest()
        files.append({"path":rel,"size":p.stat().st_size,"sha256":digest})
    (root/"MANIFEST.json").write_text(json.dumps({"release":TO,"kind":"full","file_count":len(files),"files":files},indent=2)+"\n",encoding="utf-8")
    (root/"CHECKSUMS.sha256").write_text("".join(f"{x['sha256']}  {x['path']}\n" for x in files),encoding="utf-8")


def main() -> int:
    """Validate the exact predecessor, back it up, and apply v0.22.6 in place."""
    ap=argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--dry-run",action="store_true"); args=ap.parse_args()
    root=Path(args.root).resolve(); overlay=Path(__file__).resolve().parents[1]
    version=(root/"VERSION").read_text(encoding="utf-8").strip() if (root/"VERSION").is_file() else ""
    if version!=FROM: raise SystemExit(f"refusing upgrade: expected VERSION {FROM}, found {version or 'missing'}")
    cfg=root/".agents/config/governance.json"
    if not cfg.is_file(): raise SystemExit("refusing upgrade: governance.json missing")
    data=json.loads(cfg.read_text(encoding="utf-8")); patched=patch_governance(data)
    targets=[cfg,root/"VERSION",root/"MANIFEST.json",root/"CHECKSUMS.sha256"]
    targets += [root/".agents/agentos"/f for f in RUNTIME_FILES]
    targets += [root/f for f in ROOT_FILES+METADATA_FILES]
    targets += [root/".agents/docs"/f for f in DOC_FILES]
    targets += [root/".agents/tests"/f for f in TEST_FILES]
    targets += [root/"tools"/f for f in TOOL_FILES]
    if args.dry_run:
        print(json.dumps({"ok":True,"from":FROM,"to":TO,"schema_from":SCHEMA_FROM,"schema_to":SCHEMA_TO,"files":[str(x) for x in targets]},indent=2)); return 0
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); backup=root/".agents/runtime/upgrades"/f"v{TO}-{stamp}"; backup.mkdir(parents=True,exist_ok=True)
    for target in targets:
        if target.exists():
            rel=target.relative_to(root); dest=backup/rel; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,dest)
    for f in RUNTIME_FILES: _copy(overlay/".agents/agentos"/f, root/".agents/agentos"/f)
    for f in ROOT_FILES+METADATA_FILES: _copy(overlay/f,root/f)
    for f in DOC_FILES: _copy(overlay/".agents/docs"/f,root/".agents/docs"/f)
    for f in TEST_FILES: _copy(overlay/".agents/tests"/f,root/".agents/tests"/f)
    for f in TOOL_FILES: _copy(overlay/"tools"/f,root/"tools"/f)
    cfg.write_text(json.dumps(patched,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (root/"VERSION").write_text(TO+"\n",encoding="utf-8")
    _rebuild_target_manifest(root)
    print(json.dumps({
        "ok":True,"upgraded_to":TO,"schema_target":SCHEMA_TO,"backup":str(backup),
        "next":["agentos secret-lineage-db-sync","agentos runtime-health","agentos docs-check","python3 tools/validate_v0226.py .","python3 tools/validate_release.py .","pytest -q .agents/tests"],
    },indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
