"""
File: .agents/agentos/gateway_client.py

Purpose:
    Provide a thin local IPC client for the trusted AgentOS gateway.

Responsibilities:
    - Serialize one JSON request per local IPC connection.
    - Use AF_UNIX on POSIX and authenticated AF_PIPE on Windows.
    - Avoid direct database or signing-key access in agent-facing clients.
"""
from __future__ import annotations
import json,socket
from multiprocessing.connection import Client
from pathlib import Path
from .gatewayd import gateway_authkey_path,ipc_family,pipe_address,socket_path

def _unwrap(data:bytes)->dict:
    out=json.loads(data.decode())
    if not out.get('ok'):
        raise RuntimeError(out.get('message','gateway request failed'))
    return out['result']

def _request_unix(root:Path,payload:dict)->dict:
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); client.connect(str(socket_path(root)))
    with client:
        client.sendall((json.dumps(payload,ensure_ascii=False)+'\n').encode()); data=b''
        while not data.endswith(b'\n'):
            chunk=client.recv(65536)
            if not chunk: break
            data+=chunk
    return _unwrap(data)

def _pipe_authkey(root:Path)->bytes:
    path=gateway_authkey_path(root)
    if not path.exists():
        raise RuntimeError('AgentOS gateway authentication key is missing')
    try:
        raw=path.read_text(encoding='ascii').strip()
        key=bytes.fromhex(raw)
    except (OSError,ValueError) as exc:
        raise RuntimeError('AgentOS gateway authentication key is invalid') from exc
    if len(key)<32:
        raise RuntimeError('AgentOS gateway authentication key is invalid')
    return key

def _request_pipe(root:Path,payload:dict)->dict:
    client=Client(pipe_address(root),family='AF_PIPE',authkey=_pipe_authkey(root))
    try:
        client.send_bytes((json.dumps(payload,ensure_ascii=False)+'\n').encode())
        data=client.recv_bytes()
    finally:
        client.close()
    return _unwrap(data)

def request(root:Path,payload:dict)->dict:
    family=ipc_family()
    if family=='AF_PIPE':
        return _request_pipe(root,payload)
    if family=='AF_UNIX':
        return _request_unix(root,payload)
    raise RuntimeError(f'unsupported AgentOS gateway IPC family: {family}')
