"""
File: .agents/agentos/mcp_server.py

Purpose:
    Expose the AgentOS enforcement proxy through MCP-compatible JSON-RPC over stdio.

Responsibilities:
    - Advertise only governed proxy tools to an agent client.
    - Bind calls to a configured project, task, and session.
    - Route tools/call requests through proxy_execute.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .proxy import proxy_execute

TOOLS = [
    {"name":"agentos.read_file","description":"Đọc file qua AgentOS.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
    {"name":"agentos.write_file","description":"Ghi file có scope, lease và expected hash.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"expected_hash":{"type":["string","null"]}},"required":["path","content"]}},
    {"name":"agentos.run_command","description":"Chạy process bị giới hạn.","inputSchema":{"type":"object","properties":{"command":{"type":"array","items":{"type":"string"}}},"required":["command"]}},
    {"name":"agentos.http_request","description":"HTTP có egress policy.","inputSchema":{"type":"object","properties":{"url":{"type":"string"},"reason_code":{"type":"string"},"justification":{"type":"string"}},"required":["url","reason_code","justification"]}},
    {"name":"agentos.acquire_resource","description":"Lấy lease tài nguyên.","inputSchema":{"type":"object","properties":{"resource_type":{"type":"string"},"resource":{"type":"string"},"lease_mode":{"type":"string"},"ttl_seconds":{"type":"integer"}},"required":["resource_type","resource"]}},
    {"name":"agentos.heartbeat_resource","description":"Gia hạn lease.","inputSchema":{"type":"object","properties":{"lease_id":{"type":"integer"},"ttl_seconds":{"type":"integer"}},"required":["lease_id"]}},
    {"name":"agentos.release_resource","description":"Giải phóng lease.","inputSchema":{"type":"object","properties":{"lease_id":{"type":"integer"}},"required":["lease_id"]}},
    {"name":"agentos.list_resources","description":"Liệt kê lease.","inputSchema":{"type":"object","properties":{"active_only":{"type":"boolean"},"task_only":{"type":"boolean"}}}},
    {"name":"agentos.claim_task","description":"Nhận quyền sở hữu task.","inputSchema":{"type":"object","properties":{}}},
    {"name":"agentos.handoff_task","description":"Chuyển task từ caller owner sang session khác.","inputSchema":{"type":"object","properties":{"to_session":{"type":"string"},"note":{"type":"string"}},"required":["to_session","note"]}},
    {"name":"agentos.task_heartbeat","description":"Heartbeat task owner.","inputSchema":{"type":"object","properties":{}}},
    {"name":"agentos.task_status","description":"Xem trạng thái task.","inputSchema":{"type":"object","properties":{}}},
    {"name":"agentos.force_reclaim_task","description":"Reclaim task đã stale.","inputSchema":{"type":"object","properties":{"reason":{"type":"string"}},"required":["reason"]}},
]


def _reply(identifier: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    message = {"jsonrpc": "2.0", "id": identifier}
    if error is not None: message["error"] = error
    else: message["result"] = result
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n"); sys.stdout.flush()


def serve(root: Path, task_id: str, session_id: str) -> None:
    """Serve MCP-style JSON-RPC messages from stdin.

    Args:
        root: Governed project root.
        task_id: Bound task identifier.
        session_id: Bound session identifier.

    Returns:
        None.
    """
    for line in sys.stdin:
        try:
            request = json.loads(line); method = request.get("method"); identifier = request.get("id")
            if method == "initialize":
                _reply(identifier, {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "agentos-mcp-proxy", "version": "0.13.0"}})
            elif method == "tools/list":
                _reply(identifier, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params", {}); name = params.get("name"); arguments = params.get("arguments", {})
                reason = arguments.pop("reason_code", None); justification = arguments.pop("justification", None)
                target = arguments.get("url") if name == "agentos.http_request" else arguments.get("path")
                result = proxy_execute(root, task_id, session_id, name, arguments, reason, justification, target)
                _reply(identifier, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": not result.get("success", result.get("allowed", True))})
            elif method == "notifications/initialized":
                continue
            else:
                _reply(identifier, error={"code": -32601, "message": f"method not found: {method}"})
        except Exception as exc:
            _reply(request.get("id") if isinstance(request, dict) else None, error={"code": -32000, "message": str(exc)})


def main() -> int:
    """Run the stdio MCP enforcement gateway.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("--task-id", required=True); parser.add_argument("--session-id", required=True)
    args = parser.parse_args(); serve(Path(args.root).resolve(), args.task_id, args.session_id); return 0


if __name__ == "__main__":
    raise SystemExit(main())
