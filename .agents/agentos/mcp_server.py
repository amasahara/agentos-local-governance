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
    {"name": "agentos.read_file", "description": "Read a project file through AgentOS policy enforcement.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, "required": ["path"]}},
    {"name": "agentos.write_file", "description": "Write a project file through approval, scope, workflow, and drift gates.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "agentos.run_command", "description": "Run a bounded local process without a shell through AgentOS policy enforcement.", "inputSchema": {"type": "object", "properties": {"command": {"type": "array", "items": {"type": "string"}}, "timeout": {"type": "integer"}}, "required": ["command"]}},
    {"name": "agentos.http_request", "description": "Make an audited HTTP request after network egress policy checks.", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}, "headers": {"type": "object"}, "body": {"type": "string"}, "reason_code": {"type": "string"}, "justification": {"type": "string"}}, "required": ["url", "reason_code", "justification"]}},
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
                _reply(identifier, {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "agentos-mcp-proxy", "version": "0.10.1"}})
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
