"""Path: .agents/agentos/architecture_compliance_cli.py
Purpose: CLI surface for v0.25.4 Architecture Drift & Compliance.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import Any
from .architecture_compliance import (
    architecture_compliance_check,
    architecture_compliance_findings_get,
    architecture_compliance_get,
    architecture_compliance_status_get,
    architecture_target_check,
)

def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2

def build_parser() -> argparse.ArgumentParser:
    """Build v0.25.4 architecture compliance commands."""
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("architecture-compliance-check")
    p.add_argument("--task-id", default=None)
    p.add_argument("--changed-files", default=None, help="JSON list of project-relative changed paths")
    p.add_argument("--mode", default="manual", choices=["manual", "precommit", "final_report", "release"])
    p.add_argument("--created-by", default="human:operator")
    p.add_argument("--no-refresh-scan", action="store_true")
    p = sub.add_parser("architecture-compliance-show"); p.add_argument("--run-id", type=int, default=None)
    p = sub.add_parser("architecture-compliance-findings"); p.add_argument("--run-id", type=int, default=None); p.add_argument("--severity", choices=["info","warn","block"], default=None)
    sub.add_parser("architecture-compliance-status")
    p = sub.add_parser("architecture-target-check"); p.add_argument("--target", required=True)
    return parser

def main(argv: list[str] | None = None) -> int:
    """Dispatch one v0.25.4 compliance command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "architecture-compliance-check":
            files = json.loads(args.changed_files) if args.changed_files else None
            if files is not None and not isinstance(files, list):
                raise RuntimeError("changed-files must be a JSON list")
            value = architecture_compliance_check(root, task_id=args.task_id, changed_files=files, mode=args.mode, refresh_scan=not args.no_refresh_scan, created_by=args.created_by)
        elif args.command == "architecture-compliance-show":
            value = architecture_compliance_get(root, run_id=args.run_id)
        elif args.command == "architecture-compliance-findings":
            value = architecture_compliance_findings_get(root, run_id=args.run_id, severity=args.severity)
        elif args.command == "architecture-compliance-status":
            value = architecture_compliance_status_get(root)
        elif args.command == "architecture-target-check":
            value = architecture_target_check(root, args.target)
        else:
            raise RuntimeError("unknown architecture compliance command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})

if __name__ == "__main__":
    raise SystemExit(main())
