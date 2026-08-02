"""
File: .agents/agentos/security.py

Purpose:
    Provide authenticated capability sessions and verifiable state reconciliation.

Responsibilities:
    - Issue, validate, rotate, and revoke hashed session credentials.
    - Prevent request replay with monotonic sequences and request identifiers.
    - Link security-relevant database state to externally signed audit events.
"""
from __future__ import annotations
import hashlib,hmac,json,secrets
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Any
from .db import connect
from .external_audit import append_signed_event, verify_external_log

def _now(): return datetime.now(timezone.utc)
def _iso(value): return value.isoformat()
def _hash(token:str)->str: return hashlib.sha256(token.encode()).hexdigest()

def default_capabilities(scope:list[str]|None=None)->list[str]:
    caps=['task.read','task.heartbeat','coordination.*','process.exec:test','filesystem.read']
    caps += [f'filesystem.write:{x}' for x in (scope or [])]
    return caps

def issue_session_token(root:Path,task_id:str,session_id:str,capabilities:list[str]|None=None,ttl_seconds:int=900)->dict[str,Any]:
    token=secrets.token_urlsafe(32); token_id=secrets.token_hex(12); expires=_now()+timedelta(seconds=max(60,ttl_seconds))
    with connect(root) as c:
        task=c.execute('SELECT approved_scope FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not task: raise RuntimeError('task not found')
        caps=capabilities or default_capabilities(json.loads(task['approved_scope']))
        c.execute('INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES(?,?,?,?,?,?)',(_hash(token),token_id,session_id,task_id,json.dumps(caps),_iso(expires)))
    event=append_signed_event(root,'security.session_issued',{'token_id':token_id,'task_id':task_id,'session_id':session_id,'capabilities':caps,'expires_at':_iso(expires)},task_id,session_id)
    return {'session_token':token,'token_id':token_id,'session_id':session_id,'task_id':task_id,'capabilities':caps,'expires_at':_iso(expires),'external_event_hash':event['event_hash']}

def _capability_allowed(granted:list[str],required:str,args:dict[str,Any])->bool:
    if required.startswith('coordination.') and 'coordination.*' in granted: return True
    if required=='filesystem.read' and 'filesystem.read' in granted: return True
    if required=='process.exec' and any(x.startswith('process.exec:') for x in granted): return True
    if required=='network.http' and 'network.http' in granted: return True
    if required=='filesystem.write':
        path=str(args.get('path','')).replace('\\','/')
        return any(x.startswith('filesystem.write:') and (path==x.split(':',1)[1].rstrip('/') or path.startswith(x.split(':',1)[1].rstrip('/')+'/')) for x in granted)
    return required in granted

def authenticate_request(root:Path,token:str,task_id:str,required_capability:str,args:dict[str,Any],request_id:str,sequence:int)->dict[str,Any]:
    digest=_hash(token); body_hash=hashlib.sha256(json.dumps(args,sort_keys=True,default=str).encode()).hexdigest()
    with connect(root,immediate=True) as c:
        row=c.execute('SELECT * FROM session_tokens WHERE token_hash=?',(digest,)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'],digest): raise RuntimeError('invalid_session_token')
        if row['revoked_at']: raise RuntimeError('revoked_session_token')
        if datetime.fromisoformat(row['expires_at']) <= _now(): raise RuntimeError('expired_session_token')
        if row['task_id']!=task_id: raise RuntimeError('session_task_mismatch')
        if sequence<=int(row['last_sequence']): raise RuntimeError('replayed_request_sequence')
        if c.execute('SELECT 1 FROM authenticated_requests WHERE request_id=?',(request_id,)).fetchone(): raise RuntimeError('replayed_request_id')
        caps=json.loads(row['capability_set_json'])
        if not _capability_allowed(caps,required_capability,args): raise RuntimeError('missing_capability')
        c.execute('UPDATE session_tokens SET last_sequence=? WHERE token_hash=?',(sequence,digest))
        c.execute('INSERT INTO authenticated_requests(request_id,token_id,task_id,session_id,sequence,body_hash,decision) VALUES(?,?,?,?,?,?,?)',(request_id,row['token_id'],task_id,row['session_id'],sequence,body_hash,'allowed'))
    return {'token_id':row['token_id'],'session_id':row['session_id'],'capabilities':caps}

def revoke_session(root:Path,token_id:str,revoked_by:str,reason:str)->dict[str,Any]:
    with connect(root,immediate=True) as c:
        row=c.execute('SELECT task_id,session_id FROM session_tokens WHERE token_id=?',(token_id,)).fetchone()
        if not row: raise RuntimeError('session token not found')
        c.execute('UPDATE session_tokens SET revoked_at=CURRENT_TIMESTAMP WHERE token_id=?',(token_id,))
    event=append_signed_event(root,'security.session_revoked',{'token_id':token_id,'revoked_by':revoked_by,'reason':reason},row['task_id'],row['session_id'])
    with connect(root) as c: c.execute('INSERT INTO session_revocations(token_id,revoked_by,reason,external_event_hash) VALUES(?,?,?,?)',(token_id,revoked_by,reason,event['event_hash']))
    return {'ok':True,'token_id':token_id,'external_event_hash':event['event_hash']}

def link_signed_state(root:Path,table_name:str,row_key:str,event_hash:str)->None:
    with connect(root) as c: c.execute('INSERT OR IGNORE INTO signed_state_index(table_name,row_key,external_event_hash) VALUES(?,?,?)',(table_name,row_key,event_hash))

def reconcile_state(root:Path)->dict[str,Any]:
    audit=verify_external_log(root); invalid=[]; checked=0
    with connect(root) as c:
        rows=c.execute("SELECT task_id,workflow_name,step_name,status,external_event_hash FROM workflow_steps WHERE status IN ('done','skipped') AND step_name!='receive_request'").fetchall()
        for r in rows:
            checked+=1; key=f"{r['task_id']}:{r['workflow_name']}:{r['step_name']}"
            idx=c.execute("SELECT 1 FROM signed_state_index WHERE table_name='workflow_steps' AND row_key=? AND external_event_hash=?",(key,r['external_event_hash'])).fetchone() if r['external_event_hash'] else None
            verified=bool(idx and audit.get('ok'))
            c.execute("UPDATE workflow_steps SET verification_status=? WHERE task_id=? AND workflow_name=? AND step_name=?",('verified' if verified else 'unverifiable',r['task_id'],r['workflow_name'],r['step_name']))
            if not verified: invalid.append(key)
        details={'invalid':invalid,'audit_ok':audit.get('ok',False)}
        c.execute('INSERT INTO state_reconciliation_runs(ok,checked_rows,unverifiable_rows,details_json,latest_external_hash) VALUES(?,?,?,?,?)',(int(not invalid and audit.get('ok',False)),checked,len(invalid),json.dumps(details),audit.get('last_event_hash')))
    return {'ok':not invalid and audit.get('ok',False),'checked_rows':checked,'unverifiable_rows':invalid,'external_audit':audit}
