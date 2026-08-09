"""
File: .agents/agentos/governance_enforcement_cli.py

Purpose:
    Expose read-only v0.22.4 governed-operation inspection.

Responsibilities:
    - Return redacted governed-operation status.
    - Never expose execution tokens or privileged mutation endpoints.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .governance_enforcement import governed_operation_status


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(prog="agentos governance-enforcement")
    p.add_argument("--root", type=Path, required=True)
    sub=p.add_subparsers(dest="command", required=True)
    show=sub.add_parser("governed-operation-show")
    show.add_argument("--operation-id", required=True)
    args=p.parse_args(argv)
    result=governed_operation_status(args.root.resolve(), args.operation_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
