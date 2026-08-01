"""
File: .agents/agentos/audit_daemon.py

Purpose:
    Provide a minimal append-only HTTP sink for signed AgentOS audit records.

Responsibilities:
    - Accept authenticated signed audit records over HTTP.
    - Validate required fields and monotonic project sequence numbers.
    - Append records to daemon-owned JSONL files without update or delete APIs.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REQUIRED = {"schema", "project_id", "sequence", "event_type", "previous_hash", "event_hash", "key_id", "signature"}


def _store() -> Path:
    path = Path(os.environ.get("AGENTOS_AUDIT_DAEMON_HOME", "~/.agentos/audit-daemon")).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _append(record: dict[str, Any]) -> dict[str, Any]:
    """Validate sequence continuity and append one immutable record."""
    missing = sorted(REQUIRED - record.keys())
    if missing:
        raise RuntimeError(f"missing audit fields: {missing}")
    path = _store() / f"{record['project_id']}.jsonl"
    previous, sequence = None, 1
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            last = json.loads(lines[-1]); previous = last["event_hash"]; sequence = int(last["sequence"]) + 1
    if int(record["sequence"]) != sequence or record.get("previous_hash") != previous:
        raise RuntimeError("audit sequence or previous_hash mismatch")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush(); os.fsync(handle.fileno())
    return {"ok": True, "sequence": sequence, "path": str(path)}


class Handler(BaseHTTPRequestHandler):
    """Serve append-only audit ingestion requests."""

    def do_POST(self) -> None:  # noqa: N802
        """Accept one authenticated JSON audit record."""
        if self.path != "/v1/events":
            self.send_error(404); return
        expected = os.environ.get("AGENTOS_AUDIT_DAEMON_TOKEN", "")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if expected and not hmac.compare_digest(expected, supplied):
            self.send_error(401); return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 2_000_000)
            record = json.loads(self.rfile.read(length))
            result = _append(record)
            payload = json.dumps(result).encode()
            self.send_response(201); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
        except Exception as exc:
            payload = json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}).encode()
            self.send_response(409); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default request logs to avoid leaking headers."""
        return


def main() -> None:
    """Run the append-only audit daemon."""
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(); ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
