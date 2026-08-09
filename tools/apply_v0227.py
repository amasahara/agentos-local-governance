#!/usr/bin/env python3
"""Apply the exact AgentOS v0.22.6 -> v0.22.7 upgrade overlay."""
from __future__ import annotations
import argparse, json, shutil
from datetime import datetime, timezone
from pathlib import Path

FROM='0.22.6'; TO='0.22.7'; SCHEMA_FROM=42; SCHEMA_TO=43
RUNTIME_FILES=['db.py','schema_version.py','cli_runtime.py','mcp_catalog.py','mcp_runtime.py','__init__.py','data_subject_rights.py','data_subject_rights_cli.py','mcp_data_subject_rights.py']
ROOT_FILES=['AGENTS.md','README.md','README.vi.md','README.en.md','huong_dan.md','huong_dan.vi.md','huong_dan.en.md','DATA_SUBJECT_RIGHTS.md','RELEASE_NOTES.md','CHANGELOG.md','UPGRADE_FROM_0.22.6.md']
DOC_FILES=['PRIVACY_BOUNDARY_V0227.md','USAGE_V0227.md']


def patch_governance(data: dict) -> dict:
    """Merge v0.22.7 privacy policy without removing earlier governance nodes."""
    if str(data.get('version',data.get('governance_version'))) != FROM:
        raise RuntimeError('governance baseline version is not 0.22.6')
    data['version']=TO
    if 'governance_version' in data: data['governance_version']=TO
    data.setdefault('documentation_policy',{})['current_schema']=SCHEMA_TO
    data['data_subject_rights_policy']={
        'version':1,'database_schema':SCHEMA_TO,
        'immutable_erasure_request':True,'immutable_erasure_plan':True,
        'human_review_required':True,'human_approval_required':True,'signed_audit_required':True,
        'local_execution_only':True,'idempotent_execution_required':True,
        'canonical_tombstone_required':True,'remove_relinkable_identity_bindings':True,
        'remove_local_target_lineage':True,'purge_related_staging':True,'purge_related_cache':True,
        'purge_related_memory_embeddings':True,'purge_related_index_entries':True,
        'retention_mode':'minimal_non_relinkable_audit_evidence',
        'target_update_allowed':False,'target_delete_allowed':False,'target_upsert_allowed':False,'target_merge_allowed':False,
        'external_target_erasure_signaled_only':True,
        'block_active_identity_or_extraction':True,'block_active_or_in_doubt_target_operation':True,
        'block_active_reconciliation_or_recovery':True,
        'raw_identifier_persistence_allowed':False,'raw_record_persistence_allowed':False,
        'mcp_mutation_allowed':False,
    }
    privacy=data.setdefault('privacy_boundary_policy',{})
    privacy.update({
        'data_subject_rights_version':'0.22.7','local_erasure_authority_only':True,
        'external_target_erasure_requires_external_authority':True,
        'historical_signed_audit_rewrite_forbidden':True,
        'unnecessary_relinkable_retention_forbidden':True,
    })
    enforcement=data.setdefault('governance_enforcement_policy',{})
    caps=enforcement.setdefault('privileged_capabilities',[])
    for cap in ['privacy.erasure.request','privacy.erasure.plan','privacy.erasure.review','privacy.erasure.approve','privacy.erasure.execute']:
        if cap not in caps: caps.append(cap)
    enforcement['mcp_privileged_mutation_exposed']=False
    runtime=data.setdefault('unified_runtime_policy',{})
    runtime['version_forwarding_runtime_allowed']=False; runtime['mcp_subprocess_forwarding_allowed']=False; runtime['extension_mutation_tools_exposed_over_mcp']=False
    # Re-assert database safety boundaries instead of replacing the existing sections.
    data.setdefault('database_boundary_policy',{})['source_mutation_allowed']=False
    target=data.setdefault('controlled_target_insert_policy',{})
    target['update_allowed']=False; target['delete_allowed']=False; target['upsert_allowed']=False; target['merge_allowed']=False
    return data


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('root'); ap.add_argument('--dry-run',action='store_true'); args=ap.parse_args()
    root=Path(args.root).resolve(); overlay=Path(__file__).resolve().parents[1]
    version=(root/'VERSION').read_text(encoding='utf-8').strip() if (root/'VERSION').is_file() else ''
    if version!=FROM: raise SystemExit(f'refusing upgrade: expected VERSION {FROM}, found {version or "missing"}')
    cfg=root/'.agents/config/governance.json'
    if not cfg.is_file(): raise SystemExit('refusing upgrade: governance.json missing')
    patched=patch_governance(json.loads(cfg.read_text(encoding='utf-8')))
    plan=[cfg,root/'VERSION']+[root/'.agents/agentos'/f for f in RUNTIME_FILES]+[root/f for f in ROOT_FILES]+[root/'.agents/docs'/f for f in DOC_FILES]
    if args.dry_run:
        print(json.dumps({'ok':True,'from':FROM,'to':TO,'schema_from':SCHEMA_FROM,'schema_to':SCHEMA_TO,'files':[str(x) for x in plan]},indent=2)); return 0
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); backup=root/'.agents/runtime/upgrades'/f'v{TO}-{stamp}'; backup.mkdir(parents=True,exist_ok=True)
    for target in plan:
        if target.exists():
            dest=backup/target.relative_to(root); dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,dest)
    (root/'.agents/agentos').mkdir(parents=True,exist_ok=True); (root/'.agents/docs').mkdir(parents=True,exist_ok=True)
    for f in RUNTIME_FILES: shutil.copy2(overlay/'.agents/agentos'/f,root/'.agents/agentos'/f)
    for f in ROOT_FILES: shutil.copy2(overlay/f,root/f)
    for f in DOC_FILES: shutil.copy2(overlay/'.agents/docs'/f,root/'.agents/docs'/f)
    cfg.write_text(json.dumps(patched,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); (root/'VERSION').write_text(TO+'\n',encoding='utf-8')
    print(json.dumps({'ok':True,'upgraded_to':TO,'backup':str(backup),'next':['agentos data-subject-rights-db-sync','agentos runtime-health','agentos docs-check','pytest -q .agents/tests']},indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
