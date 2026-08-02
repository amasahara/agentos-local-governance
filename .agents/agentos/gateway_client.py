"""
File: .agents/agentos/gateway_client.py

Purpose:
    Provide a thin local IPC client for the trusted AgentOS gateway.

Responsibilities:
    - Serialize one request per Unix-domain-socket connection.
    - Avoid direct database or signing-key access in agent-facing clients.
"""
from __future__ import annotations
import json,socket
from pathlib import Path
from .gatewayd import socket_path

def request(root:Path,payload:dict)->dict:
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); client.connect(str(socket_path(root)))
    with client:
        client.sendall((json.dumps(payload,ensure_ascii=False)+'\n').encode()); data=b''
        while not data.endswith(b'\n'):
            chunk=client.recv(65536)
            if not chunk: break
            data+=chunk
    out=json.loads(data.decode())
    if not out.get('ok'): raise RuntimeError(out.get('message','gateway request failed'))
    return out['result']
