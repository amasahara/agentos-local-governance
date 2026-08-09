#!/usr/bin/env python3
"""Validate the v0.22.6 Secret Resolver & Lineage Key Lifecycle release tree."""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

def main() -> None:
    """Run current release-integrity, policy, migration and manifest gates."""
    p=argparse.ArgumentParser(); p.add_argument("root",nargs="?",default=".",type=Path); p.add_argument("--skip-manifest",action="store_true"); args=p.parse_args(); root=args.root.resolve()
    sys.path.insert(0,str(root/".agents"))
    from agentos.release_integrity import check_release_integrity
    from agentos.db import SCHEMA_VERSION, connect
    from agentos.policy import load_policy
    report={"ok":True,"version":(root/"VERSION").read_text().strip(),"schema":SCHEMA_VERSION}
    integ=check_release_integrity(root); report["release_integrity"]=integ; report["ok"] &= integ["ok"]
    try:
        pol=load_policy(root); report["policy_loaded"]=True; report["policy_version"]=pol.get("version")
    except Exception as exc:
        report["policy_loaded"]=False; report["policy_error"]=str(exc); report["ok"]=False
    with tempfile.TemporaryDirectory() as td:
        r=Path(td)/"p"; (r/".agents/state").mkdir(parents=True); (r/".agents/config").mkdir(parents=True)
        with connect(r) as c:
            versions=[x["version"] for x in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
            fk=c.execute("PRAGMA foreign_keys").fetchone()[0]
            tables={x["name"] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        report["migration_versions"]=versions; report["foreign_keys_on"]=fk==1
        report["core_tables_present"]={"tasks","tool_calls","audit_events"} <= tables
        report["extension_tables_present"]={"project_identity","db_connections","db_reconciliation_runs","secret_resolver_approvals","lineage_keys"} <= tables
        report["ok"] &= versions==list(range(1,43)) and fk==1 and report["core_tables_present"] and report["extension_tables_present"]
    if not args.skip_manifest:
        cp=subprocess.run([sys.executable,str(root/"tools/verify_manifest.py"),str(root)],capture_output=True,text=True)
        report["manifest_verify_rc"]=cp.returncode; report["manifest_verify_output"]=cp.stdout.strip(); report["ok"] &= cp.returncode==0
    print(json.dumps(report,indent=2,sort_keys=True)); raise SystemExit(0 if report["ok"] else 2)

if __name__=="__main__": main()
