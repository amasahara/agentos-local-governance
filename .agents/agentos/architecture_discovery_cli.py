"""Path: .agents/agentos/architecture_discovery_cli.py
Purpose: CLI surface for v0.25.3 architecture discovery and evidence inspection.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .architecture_discovery import (
    architecture_discrepancies_get,
    architecture_evidence_get,
    architecture_observations_get,
    architecture_scan,
    architecture_scan_get,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.25.3 feature command parser."""
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("architecture-scan")
    p.add_argument("--source-root", default=None)
    p.add_argument("--created-by", required=True)

    p = sub.add_parser("architecture-scan-show")
    p.add_argument("--scan-id", type=int, default=None)

    for command in ("architecture-observations", "architecture-evidence", "architecture-discrepancies"):
        p = sub.add_parser(command)
        p.add_argument("--scan-id", type=int, required=True)
        p.add_argument("--section-id", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one v0.25.3 discovery/evidence CLI command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "architecture-scan":
            value = architecture_scan(root, source_root=args.source_root, created_by=args.created_by)
        elif args.command == "architecture-scan-show":
            value = architecture_scan_get(root, scan_id=args.scan_id)
        elif args.command == "architecture-observations":
            value = architecture_observations_get(root, scan_id=args.scan_id, section_id=args.section_id)
        elif args.command == "architecture-evidence":
            value = architecture_evidence_get(root, scan_id=args.scan_id, section_id=args.section_id)
        elif args.command == "architecture-discrepancies":
            value = architecture_discrepancies_get(root, scan_id=args.scan_id, section_id=args.section_id)
        else:
            raise RuntimeError("unknown architecture discovery command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
