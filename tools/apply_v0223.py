#!/usr/bin/env python3
"""Apply AgentOS v0.22.3 Core Reintegration & Release Integrity to v0.22.2."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, stat, sys
from datetime import datetime, timezone
from pathlib import Path

BASELINE="0.22.2"; TARGET="0.22.3"
FEATURE_MODULES=("project_identity.py","project_selection.py","project_consolidation.py","database_boundary.py","schema_mapping.py","read_only_extraction.py","controlled_target_insert.py","identity_resolution.py","reconciliation_recovery.py")
SCHEMA_LINES={"project_identity.py":32,"project_selection.py":33,"project_consolidation.py":34,"database_boundary.py":35,"schema_mapping.py":36,"read_only_extraction.py":37,"controlled_target_insert.py":38,"identity_resolution.py":39,"reconciliation_recovery.py":40}

def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def backup(root:Path, paths:list[str])->Path:
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); out=root/".agents/runtime/upgrade-backups"/f"v0.22.3-{stamp}"; out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for rel in paths:
        p=root/rel
        if p.exists() and p.is_file():
            q=out/rel; q.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,q); manifest.append({"path":rel,"sha256":sha(p)})
    (out/"backup-manifest.json").write_text(json.dumps({"from":BASELINE,"to":TARGET,"files":manifest},indent=2)+"\n")
    return out

def preflight(root:Path)->None:
    if (root/"VERSION").read_text().strip()!=BASELINE: raise RuntimeError("target VERSION must be exactly 0.22.2")
    required=["AGENTS.md",".agents/agentos/core.py",".agents/agentos/policy.py",".agents/agentos/db.py",".agents/agentos/proxy.py",".agents/agentos/tooling.py",".agents/agentos/external_audit.py",".agents/agentos/mcp_server.py",".agents/tests/test_agentos.py",".agents/config/governance.json",".agents/bin/agentos.v0195",".agents/bin/agentos-mcp.v0195"]
    missing=[x for x in required if not (root/x).is_file()]
    if missing: raise RuntimeError(f"GitHub v0.22.2 core baseline incomplete: {missing}")
    db=(root/".agents/agentos/db.py").read_text()
    if "MIGRATIONS = [_m32" not in db or "def connect(" in db: raise RuntimeError("db.py no longer matches the known v0.22.2 broken registry; inspect manually")
    if "exit 0" not in (root/".agents/bin/agentos.v0195").read_text(): raise RuntimeError("agentos.v0195 baseline differs; inspect manually")
    if (root/".agents/bin/agentos-mcp.v0195").read_text().strip() != "#!/bin/sh\ncat": raise RuntimeError("agentos-mcp.v0195 baseline differs; inspect manually")

def patch_feature_schema(root:Path)->None:
    """Rename per-feature node constants; CURRENT schema lives only in db/schema_version."""
    for name,oldv in SCHEMA_LINES.items():
        p=root/".agents/agentos"/name; text=p.read_text()
        needle=f"SCHEMA_VERSION = {oldv}"
        if needle not in text: raise RuntimeError(f"{name}: expected schema constant {oldv} not found")
        text=text.replace(needle, f"MIGRATION_VERSION = {oldv}", 1)
        text=text.replace('"schema": SCHEMA_VERSION', '"schema": MIGRATION_VERSION')
        p.write_text(text)

def patch_init(root:Path)->None:
    p=root/".agents/agentos/__init__.py"; t=p.read_text()
    if '__version__ = "0.22.2"' in t: t=t.replace('__version__ = "0.22.2"','__version__ = "0.22.3"',1)
    elif t.strip()=='__version__ = "0.22.2"': t='__version__ = "0.22.3"\n'
    else: raise RuntimeError("unexpected __init__.py version form")
    p.write_text(t)

def append_changelog(root:Path, overlay:Path)->None:
    p=root/".agents/docs/RULES_WORKFLOW_CHANGELOG.md"; frag=(overlay/"RULES_WORKFLOW_CHANGELOG.v0223.md").read_text()
    text=p.read_text() if p.exists() else "# Rules & Workflow Changelog\n"
    if "v0.22.3 — Core Reintegration" not in text: p.write_text(text.rstrip()+"\n"+frag)

def cleanup(root:Path)->None:
    for p in list(root.rglob("__pycache__"))+list(root.rglob(".pytest_cache")):
        if ".agents/runtime" in p.as_posix(): continue
        if p.is_dir(): shutil.rmtree(p,ignore_errors=True)
    for p in root.rglob("*.pyc"):
        if ".agents/runtime" not in p.as_posix(): p.unlink(missing_ok=True)
    gi=root/".gitignore"; text=gi.read_text() if gi.exists() else ""
    for line in ("__pycache__/","*.pyc",".pytest_cache/"):
        if line not in text.splitlines(): text += ("\n" if text and not text.endswith("\n") else "")+line+"\n"
    gi.write_text(text)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("target",type=Path); ap.add_argument("--dry-run",action="store_true"); args=ap.parse_args(); root=args.target.resolve(); overlay=Path(__file__).resolve().parents[1]
    preflight(root)
    changed=["VERSION","AGENTS.md","README.md","README.vi.md","README.en.md","huong_dan.md","huong_dan.vi.md","huong_dan.en.md","RELEASE_NOTES.md",".gitignore",".agents/agentos/__init__.py",".agents/agentos/db.py",".agents/agentos/policy.py",".agents/config/governance.json",".agents/tests/test_agentos.py",".agents/bin/agentos",".agents/bin/agentos.v0222",".agents/bin/agentos.v0195",".agents/bin/agentos-mcp.v0195",".agents/bin/hooks/pre-commit",".agents/docs/RULES_WORKFLOW_CHANGELOG.md",".agents/docs/PROJECT_STRUCTURE.md",".agents/docs/USAGE.md"]+[f".agents/agentos/{x}" for x in FEATURE_MODULES]
    if args.dry_run:
        print(json.dumps({"ok":True,"dry_run":True,"from":BASELINE,"to":TARGET,"schema":40,"will_modify":changed},indent=2)); return
    out=backup(root,changed)
    # Preserve the v0.22.2 top-level POSIX dispatcher as the next compatibility layer.
    v0222 = root/".agents/bin/agentos.v0222"
    if v0222.exists():
        raise RuntimeError("agentos.v0222 already exists; refusing ambiguous dispatcher chain")
    shutil.copy2(root/".agents/bin/agentos", v0222)
    v0222.chmod(v0222.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # authoritative replacements
    replacements={
      "AGENTS.md":"AGENTS.md","README.md":"README.md","README.vi.md":"README.vi.md","README.en.md":"README.en.md","huong_dan.md":"huong_dan.md","huong_dan.vi.md":"huong_dan.vi.md","huong_dan.en.md":"huong_dan.en.md","RELEASE_NOTES.md":"RELEASE_NOTES.md","UPGRADE_FROM_0.22.2.md":"UPGRADE_FROM_0.22.2.md",
      ".agents/agentos/db.py":".agents/agentos/db.py",".agents/agentos/schema_version.py":".agents/agentos/schema_version.py",".agents/agentos/release_integrity.py":".agents/agentos/release_integrity.py",".agents/agentos/release_integrity_cli.py":".agents/agentos/release_integrity_cli.py",".agents/agentos/policy.py":".agents/agentos/policy.py",".agents/config/governance.json":".agents/config/governance.json",".agents/tests/test_agentos.py":".agents/tests/test_agentos.py",".agents/tests/test_core_reintegration_v0223.py":".agents/tests/test_core_reintegration_v0223.py",".agents/bin/agentos":".agents/bin/agentos",".agents/bin/agentos.v0195":".agents/bin/agentos.v0195",".agents/bin/agentos-mcp.v0195":".agents/bin/agentos-mcp.v0195",".agents/bin/agentos.v0223":".agents/bin/agentos.v0223",".agents/bin/hooks/pre-commit":".agents/bin/hooks/pre-commit",".agents/docs/CORE_REINTEGRATION_V0223.md":".agents/docs/CORE_REINTEGRATION_V0223.md",".agents/docs/USAGE_V0223.md":".agents/docs/USAGE_V0223.md",".agents/docs/RELEASE_NOTES_V0223.md":".agents/docs/RELEASE_NOTES_V0223.md",".agents/docs/UPGRADE_FROM_0.22.2.md":".agents/docs/UPGRADE_FROM_0.22.2.md",".agents/docs/PROJECT_STRUCTURE.md":".agents/docs/PROJECT_STRUCTURE.md",".agents/docs/USAGE.md":".agents/docs/USAGE.md","tools/verify_manifest.py":"tools/verify_manifest.py","tools/build_manifest.py":"tools/build_manifest.py","tools/validate_release.py":"tools/validate_release.py","tools/apply_v0223.py":"tools/apply_v0223.py",
    }
    for rel,src in replacements.items():
        s=overlay/src; d=root/rel; d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(s,d)
    patch_feature_schema(root); patch_init(root); (root/"VERSION").write_text(TARGET+"\n"); append_changelog(root,overlay); cleanup(root)
    for rel in (".agents/bin/agentos",".agents/bin/agentos.v0222",".agents/bin/agentos.v0195",".agents/bin/agentos-mcp.v0195",".agents/bin/agentos.v0223",".agents/bin/hooks/pre-commit","tools/apply_v0223.py","tools/verify_manifest.py","tools/build_manifest.py","tools/validate_release.py"):
        (root/rel).chmod((root/rel).stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(json.dumps({"ok":True,"from":BASELINE,"to":TARGET,"schema":40,"backup":str(out)},indent=2))
if __name__=="__main__": main()
