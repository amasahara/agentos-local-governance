"""
File: .agents/agentos/concurrency.py
Purpose: Enforce multi-session ownership, leases, stale recovery, and atomic file writes.
"""
from __future__ import annotations
import hashlib, json, os, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from .core import check_write
from .db import connect
from .policy import load_policy

def _now(): return datetime.now(timezone.utc)
def _iso(v): return v.isoformat().replace('+00:00','Z')
def file_hash(path: Path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def normalize_resource(root: Path, resource_type: str, resource: str):
    policy=load_policy(root).get('concurrency_policy',{})
    if resource_type not in {'file','directory','symbol','governance'}: raise RuntimeError('unsupported resource type')
    if resource_type=='symbol':
        if not policy.get('symbol_leases',False): raise RuntimeError('symbol leases are disabled by policy')
        if '::' not in resource: raise RuntimeError('symbol resource must use path::qualname')
        fp, q=resource.split('::',1); _, rel=normalize_resource(root,'file',fp); return resource_type,f'{rel}::{q}'
    base=root.resolve(); cand=Path(resource); resolved=cand.resolve() if cand.is_absolute() else (base/cand).resolve()
    try: rel=resolved.relative_to(base).as_posix()
    except ValueError as exc: raise RuntimeError('resource is outside project root') from exc
    return resource_type,rel

def _expire(c, root: Path):
    now=_iso(_now())
    c.execute("UPDATE resource_leases SET status='expired',expired_at=?,release_reason='ttl_expired' WHERE status='active' AND expires_at<=?",(now,now))
    pol=load_policy(root).get('concurrency_policy',{}); stale=int(pol.get('task_stale_after_seconds',120))+int(pol.get('expired_lease_grace_seconds',60))
    cutoff=_iso(_now()-timedelta(seconds=stale))
    c.execute("UPDATE tasks SET task_state='stale',stale_at=COALESCE(stale_at,?) WHERE owner_session_id IS NOT NULL AND task_state='active' AND last_heartbeat IS NOT NULL AND last_heartbeat<=?",(now,cutoff))

def _paths_overlap(a_type,a,b_type,b):
    if a_type not in {'file','directory'} or b_type not in {'file','directory'}: return a_type==b_type and a==b
    pa,pb=Path(a),Path(b)
    return pa==pb or (a_type=='directory' and pa in pb.parents) or (b_type=='directory' and pb in pa.parents)

def acquire_resource(root,task_id,session_id,resource_type,resource,mode='exclusive_write',ttl_seconds=None,base_hash=None,metadata=None):
    if mode not in {'shared_read','intent_write','exclusive_write'}: raise RuntimeError('invalid lease mode')
    pol=load_policy(root)['concurrency_policy']; ttl=max(10,min(int(ttl_seconds or pol.get('default_write_lease_seconds',300)),int(pol.get('max_lease_seconds',3600))))
    rtype,key=normalize_resource(root,resource_type,resource)
    if mode!='shared_read' and pol.get('write_lease_requires_approved_scope',True) and rtype in {'file','directory'}:
        decision=check_write(root,task_id,key)
        if not decision['allowed']: return {'acquired':False,'blocked':True,'reason':decision['reason'],'resource':f'{rtype}:{key}'}
    now=_now(); exp=now+timedelta(seconds=ttl); warnings=[]
    with connect(root,immediate=True) as c:
        _expire(c,root)
        task=c.execute('SELECT owner_session_id,task_state FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not task: raise RuntimeError(f'task not found: {task_id}')
        if task['owner_session_id'] and task['owner_session_id']!=session_id and pol.get('task_single_writer',True) and mode!='shared_read': return {'acquired':False,'blocked':True,'reason':'task_owned_by_other_session','owner_session_id':task['owner_session_id']}
        rows=c.execute("SELECT id,resource_type,resource_key,task_id,session_id,lease_mode,expires_at FROM resource_leases WHERE status='active'").fetchall(); incompatible=[]
        for row in rows:
            if not _paths_overlap(rtype,key,row['resource_type'],row['resource_key']): continue
            same=row['task_id']==task_id and row['session_id']==session_id; compatible=mode=='shared_read' and row['lease_mode']=='shared_read'
            if same or compatible: continue
            item=dict(row)
            exact=(rtype==row['resource_type'] and key==row['resource_key'])
            if not exact and pol.get('directory_scope_conflict','warn')=='warn': warnings.append(item)
            else: incompatible.append(item)
        if incompatible: return {'acquired':False,'blocked':True,'reason':'resource_lease_conflict','resource':f'{rtype}:{key}','conflicts':incompatible,'overlap_warnings':warnings}
        cur=c.execute("INSERT INTO resource_leases(resource_type,resource_key,task_id,session_id,lease_mode,status,acquired_at,expires_at,heartbeat_at,base_hash,metadata_json,overlap_warning_json) VALUES(?,?,?,?,?,'active',?,?,?,?,?,?)",(rtype,key,task_id,session_id,mode,_iso(now),_iso(exp),_iso(now),base_hash,json.dumps(metadata or {},sort_keys=True),json.dumps(warnings,sort_keys=True)))
        lid=int(cur.lastrowid); c.execute("UPDATE tasks SET owner_session_id=COALESCE(owner_session_id,?),task_state='active',last_heartbeat=?,stale_at=NULL WHERE id=?",(session_id,_iso(now),task_id))
    return {'acquired':True,'lease_id':lid,'resource':f'{rtype}:{key}','mode':mode,'expires_at':_iso(exp),'base_hash':base_hash,'overlap_warnings':warnings}

def heartbeat_resource(root,lease_id,task_id,session_id,ttl_seconds=None):
    pol=load_policy(root)['concurrency_policy']; ttl=max(10,min(int(ttl_seconds or pol.get('default_write_lease_seconds',300)),int(pol.get('max_lease_seconds',3600)))); now=_now(); exp=now+timedelta(seconds=ttl)
    with connect(root,immediate=True) as c:
        _expire(c,root); cur=c.execute("UPDATE resource_leases SET heartbeat_at=?,expires_at=? WHERE id=? AND task_id=? AND session_id=? AND status='active'",(_iso(now),_iso(exp),lease_id,task_id,session_id))
        if cur.rowcount!=1: raise RuntimeError('lease is missing, expired, or owned by another session')
        c.execute("UPDATE tasks SET last_heartbeat=?,task_state='active',stale_at=NULL WHERE id=? AND owner_session_id=?",(_iso(now),task_id,session_id))
    return {'renewed':True,'lease_id':lease_id,'expires_at':_iso(exp)}

def release_resource(root,lease_id,task_id,session_id,reason='released_by_owner'):
    with connect(root,immediate=True) as c:
        _expire(c,root); cur=c.execute("UPDATE resource_leases SET status='released',released_at=CURRENT_TIMESTAMP,release_reason=? WHERE id=? AND task_id=? AND session_id=? AND status='active'",(reason,lease_id,task_id,session_id))
        if cur.rowcount!=1: raise RuntimeError('active lease not found for task/session')
    return {'released':True,'lease_id':lease_id,'reason':reason}

def list_resources(root,task_id=None,active_only=True):
    with connect(root,immediate=True) as c:
        _expire(c,root); where=[]; params=[]
        if task_id: where.append('task_id=?'); params.append(task_id)
        if active_only: where.append("status='active'")
        sql='SELECT * FROM resource_leases'+((' WHERE '+' AND '.join(where)) if where else '')+' ORDER BY id'
        return [dict(r) for r in c.execute(sql,params).fetchall()]

def claim_task(root,task_id,session_id):
    with connect(root,immediate=True) as c:
        _expire(c,root); row=c.execute('SELECT owner_session_id,task_state FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row: raise RuntimeError(f'task not found: {task_id}')
        if row['owner_session_id'] and row['owner_session_id']!=session_id: return {'claimed':False,'blocked':True,'reason':'task_owned_by_other_session','owner_session_id':row['owner_session_id'],'task_state':row['task_state']}
        c.execute("UPDATE tasks SET owner_session_id=?,task_state='active',last_heartbeat=?,stale_at=NULL WHERE id=?",(session_id,_iso(_now()),task_id))
    return {'claimed':True,'task_id':task_id,'owner_session_id':session_id}

def handoff_task(root,task_id,caller_session,to_session,note):
    if not note.strip(): raise RuntimeError('handoff note is required')
    with connect(root,immediate=True) as c:
        _expire(c,root); row=c.execute('SELECT owner_session_id FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row: raise RuntimeError(f'task not found: {task_id}')
        if row['owner_session_id']!=caller_session: raise RuntimeError('handoff caller is not the current task owner')
        c.execute("UPDATE tasks SET owner_session_id=?,task_state='active',last_heartbeat=?,stale_at=NULL WHERE id=?",(to_session,_iso(_now()),task_id)); c.execute("UPDATE resource_leases SET session_id=? WHERE task_id=? AND session_id=? AND status='active'",(to_session,task_id,caller_session)); c.execute("INSERT INTO task_handoffs(task_id,from_session_id,to_session_id,note) VALUES(?,?,?,?)",(task_id,caller_session,to_session,note))
    return {'handed_off':True,'task_id':task_id,'from_session_id':caller_session,'to_session_id':to_session}

def task_heartbeat(root,task_id,session_id):
    with connect(root,immediate=True) as c:
        _expire(c,root); cur=c.execute("UPDATE tasks SET last_heartbeat=?,task_state='active',stale_at=NULL WHERE id=? AND owner_session_id=?",(_iso(_now()),task_id,session_id))
        if cur.rowcount!=1: raise RuntimeError('task is not owned by caller session')
    return {'heartbeat':True,'task_id':task_id,'session_id':session_id}

def task_status(root,task_id):
    with connect(root,immediate=True) as c:
        _expire(c,root); row=c.execute('SELECT id,owner_session_id,task_state,last_heartbeat,stale_at,reclaim_status,reclaim_requested_by FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row: raise RuntimeError(f'task not found: {task_id}')
        return dict(row)

def force_reclaim_task(root,task_id,caller_session,reason):
    if not reason.strip(): raise RuntimeError('reclaim reason is required')
    with connect(root,immediate=True) as c:
        _expire(c,root); row=c.execute('SELECT owner_session_id,task_state FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row: raise RuntimeError(f'task not found: {task_id}')
        if row['task_state']!='stale': raise RuntimeError('force reclaim requires a stale task')
        old=row['owner_session_id']; c.execute("UPDATE tasks SET owner_session_id=?,task_state='active',last_heartbeat=?,stale_at=NULL,reclaim_status='completed',reclaim_requested_by=? WHERE id=?",(caller_session,_iso(_now()),caller_session,task_id)); c.execute("UPDATE resource_leases SET session_id=? WHERE task_id=? AND status='active'",(caller_session,task_id)); c.execute("INSERT INTO task_reclaims(task_id,old_owner_session_id,new_owner_session_id,requested_by_session_id,reason,status,resolved_at) VALUES(?,?,?,?,?,'completed',CURRENT_TIMESTAMP)",(task_id,old,caller_session,caller_session,reason))
    return {'reclaimed':True,'task_id':task_id,'old_owner_session_id':old,'new_owner_session_id':caller_session}

def atomic_write(root,task_id,session_id,target,content,expected_hash,encoding='utf-8'):
    pol=load_policy(root)['concurrency_policy']; base=root.resolve(); path=(base/target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
    try: rel=path.relative_to(base).as_posix()
    except ValueError as exc: raise RuntimeError('write target is outside project root') from exc
    if pol.get('file_write_requires_expected_hash',True) and expected_hash is None and path.exists(): raise RuntimeError('expected_hash is required for existing files')
    lease=acquire_resource(root,task_id,session_id,'file',rel,'exclusive_write',base_hash=expected_hash)
    if not lease.get('acquired'): return lease
    try:
        current=file_hash(path)
        if expected_hash is not None and current!=expected_hash:
            with connect(root) as c: latest=c.execute('SELECT task_id,session_id,content_hash AS new_hash,created_at FROM file_versions WHERE path=? ORDER BY id DESC LIMIT 1',(rel,)).fetchone()
            return {'allowed':False,'blocked':True,'reason':'stale_write_conflict','path':rel,'expected_hash':expected_hash,'current_hash':current,'changed_by':dict(latest) if latest else None,'lease_id':lease['lease_id'],'atomic':True}
        path.parent.mkdir(parents=True,exist_ok=True); payload=content.encode(encoding); fd,tmp=tempfile.mkstemp(prefix=f'.{path.name}.agentos-',suffix='.tmp',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as h: h.write(payload); h.flush(); os.fsync(h.fileno())
            os.replace(tmp,path)
            try:
                d=os.open(path.parent,os.O_RDONLY); os.fsync(d); os.close(d)
            except OSError: pass
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        nh=hashlib.sha256(payload).hexdigest()
        with connect(root,immediate=True) as c:
            v=c.execute('SELECT COALESCE(MAX(version),0)+1 AS v FROM file_versions WHERE path=?',(rel,)).fetchone()['v']; c.execute('INSERT INTO file_versions(path,version,content_hash,previous_hash,task_id,session_id,lease_id) VALUES(?,?,?,?,?,?,?)',(rel,v,nh,current,task_id,session_id,lease['lease_id']))
        return {'allowed':True,'path':rel,'bytes_written':len(payload),'previous_hash':current,'content_hash':nh,'version':v,'lease_id':lease['lease_id'],'atomic':True}
    finally:
        try: release_resource(root,lease['lease_id'],task_id,session_id,'atomic_write_complete')
        except RuntimeError: pass
