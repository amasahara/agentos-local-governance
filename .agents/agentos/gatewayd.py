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
import argparse,ctypes,hashlib,json,os,secrets,socket
from multiprocessing.connection import Listener
from pathlib import Path
from .db import connect
from .proxy import proxy_execute,proxy_submit_job
from .security import authenticate_request,issue_session_token,revoke_session,reconcile_state
from .jobs import cancel_job, job_status

def socket_path(root:Path)->Path: return Path(os.environ.get('AGENTOS_GATEWAY_SOCKET',str(root/'.agents/runtime/agentos-gateway.sock')))

def pipe_address(root:Path)->str:
    explicit=os.environ.get('AGENTOS_GATEWAY_PIPE')
    if explicit:
        return explicit
    digest=hashlib.sha256(str(root.resolve()).casefold().encode('utf-8')).hexdigest()[:24]
    return rf'\\.\pipe\agentos-gateway-{digest}'

def gateway_authkey_path(root:Path)->Path:
    return root/'.agents/runtime/agentos-gateway.auth'

def ipc_family()->str:
    if os.name=='nt':
        return 'AF_PIPE'
    if hasattr(socket,'AF_UNIX'):
        return 'AF_UNIX'
    raise RuntimeError('no supported local AgentOS gateway IPC transport')

def _register_gateway(root:Path)->None:
    with connect(root) as c:
        c.execute("INSERT OR REPLACE INTO gateway_state(singleton,instance_id,security_profile) VALUES(1,?,?)",(secrets.token_hex(12),os.environ.get('AGENTOS_SECURITY_PROFILE','advisory')))

def _encode_response(root:Path,data:bytes)->bytes:
    try:
        out={'ok':True,'result':dispatch(root,json.loads(data.decode()))}
    except Exception as exc:
        out={'ok':False,'error':type(exc).__name__,'message':str(exc)}
    return (json.dumps(out,ensure_ascii=False)+'\n').encode()

def _windows_error(message:str,code:int|None=None)->RuntimeError:
    value=ctypes.get_last_error() if code is None else int(code)
    detail=ctypes.FormatError(value).strip() if value else 'unknown Windows error'
    return RuntimeError(f'{message}: [{value}] {detail}')

def _windows_current_user_sid()->str:
    if os.name!='nt':
        raise RuntimeError('Windows execution identity SID requested on non-Windows host')
    advapi32=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    HANDLE=ctypes.c_void_p
    DWORD=ctypes.c_ulong
    BOOL=ctypes.c_int
    LPVOID=ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes=[HANDLE,DWORD,ctypes.POINTER(HANDLE)]
    advapi32.OpenProcessToken.restype=BOOL
    advapi32.GetTokenInformation.argtypes=[HANDLE,ctypes.c_uint,LPVOID,DWORD,ctypes.POINTER(DWORD)]
    advapi32.GetTokenInformation.restype=BOOL
    advapi32.ConvertSidToStringSidW.argtypes=[LPVOID,ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype=BOOL
    kernel32.GetCurrentProcess.argtypes=[]
    kernel32.GetCurrentProcess.restype=HANDLE
    kernel32.CloseHandle.argtypes=[HANDLE]
    kernel32.CloseHandle.restype=BOOL
    kernel32.LocalFree.argtypes=[LPVOID]
    kernel32.LocalFree.restype=LPVOID
    token=HANDLE()
    TOKEN_QUERY=0x0008
    TOKEN_USER_CLASS=1
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(),TOKEN_QUERY,ctypes.byref(token)):
        raise _windows_error('cannot open Windows process token')
    try:
        needed=DWORD()
        ctypes.set_last_error(0)
        advapi32.GetTokenInformation(token,TOKEN_USER_CLASS,None,0,ctypes.byref(needed))
        if needed.value==0:
            raise _windows_error('cannot size Windows token user information')
        buffer=ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token,TOKEN_USER_CLASS,buffer,needed,ctypes.byref(needed)):
            raise _windows_error('cannot read Windows token user information')
        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_=[('Sid',LPVOID),('Attributes',DWORD)]
        class TOKEN_USER(ctypes.Structure):
            _fields_=[('User',SID_AND_ATTRIBUTES)]
        token_user=ctypes.cast(buffer,ctypes.POINTER(TOKEN_USER)).contents
        sid_text=ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(token_user.User.Sid,ctypes.byref(sid_text)):
            raise _windows_error('cannot convert Windows execution identity SID')
        try:
            sid=sid_text.value or ''
        finally:
            if sid_text:
                kernel32.LocalFree(ctypes.cast(sid_text,LPVOID))
        if not sid.startswith('S-1-'):
            raise RuntimeError('invalid Windows execution identity SID')
        return sid
    finally:
        kernel32.CloseHandle(token)

def _harden_windows_authkey_acl(path:Path)->None:
    if os.name!='nt':
        return
    sid=_windows_current_user_sid()
    advapi32=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
    LPVOID=ctypes.c_void_p
    DWORD=ctypes.c_ulong
    BOOL=ctypes.c_int
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[
        ctypes.c_wchar_p,DWORD,ctypes.POINTER(LPVOID),ctypes.POINTER(DWORD)
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype=BOOL
    advapi32.GetSecurityDescriptorDacl.argtypes=[
        LPVOID,ctypes.POINTER(BOOL),ctypes.POINTER(LPVOID),ctypes.POINTER(BOOL)
    ]
    advapi32.GetSecurityDescriptorDacl.restype=BOOL
    advapi32.SetNamedSecurityInfoW.argtypes=[
        ctypes.c_wchar_p,ctypes.c_uint,DWORD,LPVOID,LPVOID,LPVOID,LPVOID
    ]
    advapi32.SetNamedSecurityInfoW.restype=DWORD
    kernel32.LocalFree.argtypes=[LPVOID]
    kernel32.LocalFree.restype=LPVOID
    sddl=f'D:P(A;;FA;;;{sid})(A;;FA;;;SY)(A;;FA;;;BA)'
    descriptor=LPVOID()
    descriptor_size=DWORD()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl,1,ctypes.byref(descriptor),ctypes.byref(descriptor_size)
    ):
        raise _windows_error('cannot build AgentOS gateway auth key security descriptor')
    try:
        present=BOOL()
        defaulted=BOOL()
        dacl=LPVOID()
        if not advapi32.GetSecurityDescriptorDacl(
            descriptor,ctypes.byref(present),ctypes.byref(dacl),ctypes.byref(defaulted)
        ):
            raise _windows_error('cannot obtain AgentOS gateway auth key DACL')
        if not present.value or not dacl:
            raise RuntimeError('AgentOS gateway auth key DACL is missing')
        SE_FILE_OBJECT=1
        DACL_SECURITY_INFORMATION=0x00000004
        PROTECTED_DACL_SECURITY_INFORMATION=0x80000000
        result=advapi32.SetNamedSecurityInfoW(
            str(path),SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,
            None,None,dacl,None,
        )
        if result!=0:
            raise _windows_error('cannot harden AgentOS gateway auth key ACL',result)
    finally:
        kernel32.LocalFree(descriptor)

def _write_pipe_authkey(root:Path,key:bytes)->Path:
    path=gateway_authkey_path(root)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(f'{path.name}.{os.getpid()}.tmp')
    try:
        tmp.write_text(key.hex(),encoding='ascii')
        if os.name=='nt':
            _harden_windows_authkey_acl(tmp)
        else:
            os.chmod(tmp,0o600)
        os.replace(tmp,path)
        if os.name=='nt':
            _harden_windows_authkey_acl(path)
        return path
    except Exception:
        tmp.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
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
def _serve_unix(root:Path)->None:
    path=socket_path(root); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): path.unlink()
    srv=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); srv.bind(str(path)); os.chmod(path,0o600); srv.listen(16)
    _register_gateway(root)
    try:
        while True:
            conn,_=srv.accept()
            with conn:
                data=b''
                while not data.endswith(b'\n'):
                    chunk=conn.recv(65536)
                    if not chunk: break
                    data+=chunk
                conn.sendall(_encode_response(root,data))
    finally:
        srv.close(); path.unlink(missing_ok=True)

def _serve_windows_pipe(root:Path,max_requests:int|None=None)->None:
    key=secrets.token_bytes(32)
    listener=Listener(pipe_address(root),family='AF_PIPE',authkey=key)
    key_path:Path|None=None
    try:
        key_path=_write_pipe_authkey(root,key)
        _register_gateway(root)
        handled=0
        while True:
            conn=listener.accept()
            try:
                data=conn.recv_bytes()
                conn.send_bytes(_encode_response(root,data))
            finally:
                conn.close()
            handled+=1
            if max_requests is not None and handled>=max_requests:
                break
    finally:
        listener.close()
        if key_path is not None:
            key_path.unlink(missing_ok=True)

def serve(root:Path):
    family=ipc_family()
    if family=='AF_PIPE':
        _serve_windows_pipe(root)
        return
    if family=='AF_UNIX':
        _serve_unix(root)
        return
    raise RuntimeError(f'unsupported AgentOS gateway IPC family: {family}')
def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',default='.'); args=p.parse_args(); serve(Path(args.root).resolve())
if __name__=='__main__': main()
