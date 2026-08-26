"""
File: .agents/agentos/gatewayd.py

Purpose:
    Run the trusted AgentOS local gateway as an independent long-lived process.

Responsibilities:
    - Own database mutations and signing operations.
    - Authenticate capability-bearing requests over local IPC.
    - Dispatch all agent tool calls through the policy proxy.
"""
from __future__ import annotations
import argparse,json,os,secrets,socket
from pathlib import Path
from .db import connect
from .proxy import proxy_execute,proxy_submit_job
from .security import authenticate_request,issue_session_token,revoke_session,reconcile_state
from .jobs import cancel_job, job_status

def socket_path(root:Path)->Path: return Path(os.environ.get('AGENTOS_GATEWAY_SOCKET',str(root/'.agents/runtime/agentos-gateway.sock')))
def dispatch(root:Path,req:dict):
    action=req.get('action')
    if action=='health': return {'ok':True,'service':'agentos-gatewayd'}
    if action=='issue_session': return issue_session_token(root,req['task_id'],req['session_id'],req.get('capabilities'),int(req.get('ttl_seconds',900)))
    if action=='revoke_session': return revoke_session(root,req['token_id'],req['revoked_by'],req['reason'])
    if action=='reconcile': return reconcile_state(root)
    if action=='job_status': return job_status(root,req['job_id'])
    if action=='job_cancel': return cancel_job(root,req['job_id'],req.get('requested_by','gateway'),req['reason'])
    if action=='execute':
        from .proxy import normalize_capability
        cap=normalize_capability(req['tool_name'])
        auth=authenticate_request(root,req['session_token'],req['task_id'],cap,req.get('args',{}),req['request_id'],int(req['sequence']))
        if req['tool_name']=='agentos.run_command_async':
            args=req.get('args',{})
            return proxy_submit_job(root,req['task_id'],auth['session_id'],args['command'],args.get('cwd','.'),int(args.get('timeout_seconds',900)),args.get('env'),True)
        return proxy_execute(root,req['task_id'],auth['session_id'],req['tool_name'],req.get('args',{}),req.get('reason_code'),req.get('justification'),req.get('target'))
    raise RuntimeError('unsupported gateway action')
def serve(root:Path):
    path=socket_path(root); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): path.unlink()
    srv=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); srv.bind(str(path)); os.chmod(path,0o600); srv.listen(16)
    with connect(root) as c:
        c.execute("INSERT OR REPLACE INTO gateway_state(singleton,instance_id,security_profile) VALUES(1,?,?)",(secrets.token_hex(12),os.environ.get('AGENTOS_SECURITY_PROFILE','advisory')))
    try:
        while True:
            conn,_=srv.accept()
            with conn:
                data=b''
                while not data.endswith(b'\n'):
                    chunk=conn.recv(65536)
                    if not chunk: break
                    data+=chunk
                try: out={'ok':True,'result':dispatch(root,json.loads(data.decode()))}
                except Exception as exc: out={'ok':False,'error':type(exc).__name__,'message':str(exc)}
                conn.sendall((json.dumps(out,ensure_ascii=False)+'\n').encode())
    finally:
        srv.close(); path.unlink(missing_ok=True)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',default='.'); args=p.parse_args(); serve(Path(args.root).resolve())
if __name__=='__main__': main()
