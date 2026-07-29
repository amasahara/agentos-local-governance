"""
File: .agents/agentos/tooling.py

Purpose:
    Enforce local-first tool access and record sanitized audit events.

Responsibilities:
    - Classify tools.
    - Require justification and local evidence for network calls.
    - Apply budgets and duplicate-call limits.
    - Record execution outcomes and egress attempts.
"""
import hashlib,json,re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from .db import connect
from .policy import load

def classify_tool(root:Path,tool_name:str)->dict[str,Any]:
    """Return a tool classification snapshot.

    Args:
        root: Absolute project root.
        tool_name: Requested tool adapter name.

    Returns:
        Classification and registration state.
    """
    p=load(root)['tool_policy']; configured=p.get('tools',{}).get(tool_name); result=dict(configured or p['default_classification']); result.update(name=tool_name,registered=configured is not None); return result

def guard_tool(root:Path,task_id:str,tool_name:str,args:Any,justification:dict[str,str]|None=None,target:str|None=None)->dict[str,Any]:
    """Decide whether a tool may execute.

    Args:
        root: Absolute project root.
        task_id: Stable task identifier.
        tool_name: Requested tool adapter.
        args: Tool arguments.
        justification: Structured reason code and detail for network tools.
        target: Optional remote target.

    Returns:
        Stable decision object with classification and budget.
    """
    cfg=load(root); policy=cfg['tool_policy']; ex=cfg['tool_execution_policy']; cls=classify_tool(root,tool_name); norm=normalize_args(args)
    with connect(root) as c:
        used=c.execute('SELECT COUNT(*) n FROM tool_calls WHERE task_id=?',(task_id,)).fetchone()['n']
        same=c.execute('SELECT COUNT(*) n FROM tool_calls WHERE task_id=? AND tool_name=? AND normalized_args=?',(task_id,tool_name,norm)).fetchone()['n']
        local=c.execute("SELECT COUNT(*) n FROM tool_events WHERE task_id=? AND success=1 AND json_extract(classification_json,'$.location')='local'",(task_id,)).fetchone()['n']
    decision='execute'; allowed=True; reason='within_policy'
    if not cls['registered'] and policy['mode']=='enforce': decision,allowed,reason='deny',False,'unclassified_tool_fail_closed'
    elif cls.get('egress') is True:
        rc=(justification or {}).get('reason_code'); detail=(justification or {}).get('detail','').strip()
        if rc not in policy['justification_reason_codes'] or not detail: decision,allowed,reason='require_justification',False,'network_call_missing_valid_justification'
        elif policy.get('network_requires_local_attempt') and local==0: decision,allowed,reason='deny',False,'network_call_requires_local_attempt'
    if allowed and used>=ex['max_tool_calls_per_work_unit']: decision,allowed,reason='stop_budget_exhausted',False,'tool_call_budget_exhausted'
    if allowed and same>=ex['max_identical_tool_calls']: decision,allowed,reason='deny',False,'identical_tool_call_already_used'
    _event(root,task_id,tool_name,'guard_allowed' if allowed else 'guard_denied',cls,norm,decision,reason,None)
    if cls.get('egress') is True: _egress(root,task_id,tool_name,target,(justification or {}).get('reason_code'),(justification or {}).get('detail'),'allowed' if allowed else 'denied',None)
    return {'decision':decision,'allowed':allowed,'tool':cls,'budget':{'used':used,'limit':ex['max_tool_calls_per_work_unit'],'remaining':max(0,ex['max_tool_calls_per_work_unit']-used)},'reason':reason}

def record_tool_execution(root:Path,task_id:str,tool_name:str,args:Any,success:bool,output_summary:str='',error:str|None=None)->dict[str,Any]:
    """Persist a completed tool call.

    Args:
        root: Absolute project root.
        task_id: Stable task identifier.
        tool_name: Executed tool adapter.
        args: Executed arguments.
        success: Whether execution succeeded.
        output_summary: Bounded result summary.
        error: Raw error on failure.

    Returns:
        Persisted call identifier and failure signature.
    """
    norm=normalize_args(args); sig=hashlib.sha256((error or '').encode()).hexdigest()[:20] if not success else None; cls=classify_tool(root,tool_name)
    with connect(root) as c: cur=c.execute('INSERT INTO tool_calls(task_id,tool_name,normalized_args,success,failure_signature,output_summary) VALUES(?,?,?,?,?,?)',(task_id,tool_name,norm,int(success),sig,redact(output_summary)[:2000])); cid=int(cur.lastrowid)
    _event(root,task_id,tool_name,'execution_succeeded' if success else 'execution_failed',cls,norm,'executed','completed',success)
    return {'recorded':True,'tool_call_id':cid,'failure_signature':sig}

def egress_report(root:Path,task_id:str)->list[dict[str,Any]]:
    """Return sanitized egress events.

    Args:
        root: Absolute project root.
        task_id: Stable task identifier.

    Returns:
        Ordered egress event dictionaries.
    """
    with connect(root) as c: return [dict(r) for r in c.execute('SELECT tool_name,target,reason_code,justification,decision,success,created_at FROM egress_events WHERE task_id=? ORDER BY id',(task_id,)).fetchall()]

def normalize_args(args:Any)->str:
    """Normalize and redact tool arguments.

    Args:
        args: Tool argument object or command string.

    Returns:
        Stable sanitized string.
    """
    return redact(re.sub(r'\s+',' ',args.strip()) if isinstance(args,str) else json.dumps(args,ensure_ascii=False,sort_keys=True))
def redact(value:str|None)->str:
    """Redact common credentials.

    Args:
        value: Text that may contain secrets.

    Returns:
        Sanitized text.
    """
    if not value:return ''
    out=value
    for p in [r'(?i)(authorization\s*[:=]\s*)([^\s,;]+)',r'(?i)(bearer\s+)([A-Za-z0-9._~+/=-]+)',r'(?i)((?:api[_-]?key|token|password|cookie|secret)\s*[:=]\s*)([^\s,;]+)']:
        out=re.sub(p,lambda m:f'{m.group(1)}<redacted>',out)
    return re.sub(r'gh[pousr]_[A-Za-z0-9]{20,}','<redacted>',out)
def _target(t):
    if not t:return None
    try:
        p=urlsplit(t)
        if not p.scheme or not p.netloc:return redact(t)
        q=[(k,'<redacted>' if re.search(r'(?i)token|key|secret|password|auth',k) else v) for k,v in parse_qsl(p.query,keep_blank_values=True)]
        return urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),''))
    except ValueError:return redact(t)
def _event(root,task,tool,etype,cls,norm,decision,reason,success):
    with connect(root) as c:c.execute('INSERT INTO tool_events(task_id,tool_name,event_type,classification_json,args_hash,decision,reason,success) VALUES(?,?,?,?,?,?,?,?)',(task,tool,etype,json.dumps(cls,sort_keys=True),hashlib.sha256(norm.encode()).hexdigest(),decision,redact(reason),None if success is None else int(success)))
def _egress(root,task,tool,target,code,justification,decision,success):
    with connect(root) as c:c.execute('INSERT INTO egress_events(task_id,tool_name,target,reason_code,justification,decision,success) VALUES(?,?,?,?,?,?,?)',(task,tool,_target(target),code,redact(justification),decision,None if success is None else int(success)))
