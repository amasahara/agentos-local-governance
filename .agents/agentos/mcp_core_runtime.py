"""
File: .agents/agentos/mcp_core_runtime.py

Purpose:
    Own active governed MCP core tool definitions and execution without importing
    the historical mcp_server compatibility gateway.

Responsibilities:
    - Preserve the 14 governed core MCP tool schemas.
    - Bind mutation-capable core calls to task/session/session-token context.
    - Route enforcement through trusted gateway_client -> gatewayd.
    - Keep legacy MCP server/version-forwarding modules outside the active import graph.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
from typing import Any

from .gateway_client import request as gateway_request

CORE_TOOLS = [{'name': 'agentos.read_file',
  'description': 'Đọc file qua AgentOS.',
  'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}},
 {'name': 'agentos.write_file',
  'description': 'Ghi file có scope, lease và expected hash.',
  'inputSchema': {'type': 'object',
                  'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}, 'expected_hash': {'type': ['string', 'null']}},
                  'required': ['path', 'content']}},
 {'name': 'agentos.run_command',
  'description': 'Chạy process bị giới hạn.',
  'inputSchema': {'type': 'object', 'properties': {'command': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['command']}},
 {'name': 'agentos.run_command_async',
  'description': 'Khởi chạy job bất đồng bộ có sandbox và audit.',
  'inputSchema': {'type': 'object',
                  'properties': {'command': {'type': 'array', 'items': {'type': 'string'}},
                                 'cwd': {'type': 'string'},
                                 'timeout_seconds': {'type': 'integer'}},
                  'required': ['command']}},
 {'name': 'agentos.http_request',
  'description': 'HTTP có egress policy.',
  'inputSchema': {'type': 'object',
                  'properties': {'url': {'type': 'string'}, 'reason_code': {'type': 'string'}, 'justification': {'type': 'string'}},
                  'required': ['url', 'reason_code', 'justification']}},
 {'name': 'agentos.acquire_resource',
  'description': 'Lấy lease tài nguyên.',
  'inputSchema': {'type': 'object',
                  'properties': {'resource_type': {'type': 'string'},
                                 'resource': {'type': 'string'},
                                 'lease_mode': {'type': 'string'},
                                 'ttl_seconds': {'type': 'integer'}},
                  'required': ['resource_type', 'resource']}},
 {'name': 'agentos.heartbeat_resource',
  'description': 'Gia hạn lease.',
  'inputSchema': {'type': 'object',
                  'properties': {'lease_id': {'type': 'integer'}, 'ttl_seconds': {'type': 'integer'}},
                  'required': ['lease_id']}},
 {'name': 'agentos.release_resource',
  'description': 'Giải phóng lease.',
  'inputSchema': {'type': 'object', 'properties': {'lease_id': {'type': 'integer'}}, 'required': ['lease_id']}},
 {'name': 'agentos.list_resources',
  'description': 'Liệt kê lease.',
  'inputSchema': {'type': 'object', 'properties': {'active_only': {'type': 'boolean'}, 'task_only': {'type': 'boolean'}}}},
 {'name': 'agentos.claim_task', 'description': 'Nhận quyền sở hữu task.', 'inputSchema': {'type': 'object', 'properties': {}}},
 {'name': 'agentos.handoff_task',
  'description': 'Chuyển task từ caller owner sang session khác.',
  'inputSchema': {'type': 'object',
                  'properties': {'to_session': {'type': 'string'}, 'note': {'type': 'string'}},
                  'required': ['to_session', 'note']}},
 {'name': 'agentos.task_heartbeat', 'description': 'Heartbeat task owner.', 'inputSchema': {'type': 'object', 'properties': {}}},
 {'name': 'agentos.task_status', 'description': 'Xem trạng thái task.', 'inputSchema': {'type': 'object', 'properties': {}}},
 {'name': 'agentos.force_reclaim_task',
  'description': 'Reclaim task đã stale.',
  'inputSchema': {'type': 'object', 'properties': {'reason': {'type': 'string'}}, 'required': ['reason']}}]
CORE_TOOL_NAMES = {item["name"] for item in CORE_TOOLS}


def execute_core_tool(
    root: Path,
    task_id: str | None,
    session_id: str | None,
    name: str,
    arguments: dict[str, Any],
    sequence: int,
) -> dict[str, Any]:
    """Execute one governed core MCP tool through the trusted enforcement gateway."""
    if name not in CORE_TOOL_NAMES:
        raise RuntimeError(f"unknown governed core MCP tool: {name}")
    if not task_id or not session_id:
        raise RuntimeError("core MCP proxy tool requires --task-id and --session-id")
    session_token = os.environ.get("AGENTOS_SESSION_TOKEN")
    if not session_token:
        raise RuntimeError("AGENTOS_SESSION_TOKEN is required for governed core MCP tools")
    payload = dict(arguments)
    reason = payload.pop("reason_code", None)
    justification = payload.pop("justification", None)
    target = payload.get("url") if name == "agentos.http_request" else payload.get("path")
    return gateway_request(
        root,
        {
            "action": "execute",
            "task_id": task_id,
            "session_token": session_token,
            "tool_name": name,
            "args": payload,
            "reason_code": reason,
            "justification": justification,
            "target": target,
            "request_id": secrets.token_hex(16),
            "sequence": sequence,
        },
    )
