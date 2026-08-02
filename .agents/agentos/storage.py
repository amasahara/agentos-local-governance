"""
File: .agents/agentos/storage.py

Purpose:
    Provide retention, archive, backup, restore validation, and derived-state rebuild operations.

Responsibilities:
    - Prune observability data without deleting active evidence.
    - Archive verified audit segments instead of breaking hash chains.
    - Classify authoritative, rebuildable, and ephemeral state.
"""
from __future__ import annotations
import hashlib,json,shutil,sqlite3,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
from .db import connect
from .external_audit import verify_external_log

def prune_observability(root:Path,older_than_days:int=30)->dict[str,Any]:
    cutoff=(datetime.now(timezone.utc)-timedelta(days=older_than_days)).isoformat(); deleted=0
    with connect(root) as c:
        for table in ("knowledge_retrieval_events","rag_retrieval_events"):
            cur=c.execute(f"DELETE FROM {table} WHERE created_at < ?",(cutoff,)); deleted+=cur.rowcount
        retained=sum(c.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"] for t in ("knowledge_retrieval_events","rag_retrieval_events"))
        c.execute("INSERT INTO retention_runs(category,deleted_count,retained_count,parameters_json) VALUES('observability',?,?,?)",(deleted,retained,json.dumps({"older_than_days":older_than_days})))
    return {"deleted":deleted,"retained":retained,"older_than_days":older_than_days}

def archive_audit_segment(root:Path,max_events:int=10000)->dict[str,Any]:
    check=verify_external_log(root)
    if not check.get("ok"): raise RuntimeError("external audit verification failed")
    with connect(root) as c:
        rows=c.execute("SELECT * FROM audit_events ORDER BY id LIMIT ?",(max_events,)).fetchall()
    if not rows: return {"archived":0}
    payload=[dict(r) for r in rows]; raw=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode(); digest=hashlib.sha256(raw).hexdigest()
    out=root/".agents/runtime/audit-archives"/f"segment-{rows[0]['id']}-{rows[-1]['id']}-{digest[:12]}.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(raw)
    with connect(root) as c:
        c.execute("INSERT INTO audit_segments(first_event_id,last_event_id,event_count,first_event_hash,last_event_hash,segment_hash,archive_path,signature) VALUES(?,?,?,?,?,?,?,?)",(rows[0]["id"],rows[-1]["id"],len(rows),rows[0]["event_hash"],rows[-1]["event_hash"],digest,out.relative_to(root).as_posix(),check.get("last_hash")))
    return {"archived":len(rows),"archive_path":out.relative_to(root).as_posix(),"segment_hash":digest,"database_rows_deleted":0}

def backup_create(root:Path,output:str)->dict[str,Any]:
    out=(root/output).resolve(); out.relative_to(root.resolve()); out.parent.mkdir(parents=True,exist_ok=True)
    authoritative=["VERSION","AGENTS.md","README.md","huong_dan.md",".agents/config/governance.json",".agents/state/agentos.db",".agents/skills"]
    rebuildable=[".agents/runtime",".agents/state/index"]
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        for rel in authoritative:
            p=root/rel
            if p.is_file(): z.write(p,rel)
            elif p.is_dir():
                for f in p.rglob('*'):
                    if f.is_file(): z.write(f,f.relative_to(root))
        manifest={"authoritative":authoritative,"rebuildable":rebuildable,"created_at":datetime.now(timezone.utc).isoformat()}
        z.writestr("BACKUP_MANIFEST.json",json.dumps(manifest,indent=2))
    h=hashlib.sha256(out.read_bytes()).hexdigest()
    with connect(root) as c: c.execute("INSERT INTO backup_manifests(backup_path,manifest_hash,authoritative_json,rebuildable_json,status) VALUES(?,?,?,?, 'created')",(out.relative_to(root).as_posix(),h,json.dumps(authoritative),json.dumps(rebuildable)))
    return {"ok":True,"path":out.relative_to(root).as_posix(),"manifest_hash":h}

def backup_verify(root:Path,path:str)->dict[str,Any]:
    p=(root/path).resolve(); p.relative_to(root.resolve())
    try:
        with zipfile.ZipFile(p) as z: bad=z.testzip(); names=set(z.namelist())
        return {"ok":bad is None and "BACKUP_MANIFEST.json" in names,"bad_member":bad}
    except Exception as exc: return {"ok":False,"error":str(exc)}
