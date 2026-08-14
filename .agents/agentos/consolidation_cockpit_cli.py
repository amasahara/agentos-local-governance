"""
File: .agents/agentos/consolidation_cockpit_cli.py

Purpose:
    Expose v0.23.3 consolidation cockpit and performance-baseline operator commands.

Responsibilities:
    - Keep cockpit inspection read-only.
    - Run write-heavy performance measurements only against temporary fixtures.
    - Emit deterministic JSON suitable for automation and regression capture.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .consolidation_cockpit import consolidation_status
from .performance_baseline import (
    BASELINE_SCHEMA_VERSION,
    DEFAULT_BASELINE_FILE,
    check_performance_baseline,
    run_performance_baseline,
)
from .schema_version import CURRENT_SCHEMA_VERSION


def _emit(value: object) -> int:
    """Emit JSON and derive a process exit code from an optional `ok` field."""
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.23.3 extension command parser."""
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("consolidation-status")
    status.add_argument("--consolidation-id", type=int)
    status.add_argument("--candidate-set-id", type=int)
    status.add_argument("--project-consolidation-id", type=int)

    run = sub.add_parser("performance-baseline-run")
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--output", default="PERFORMANCE_BASELINE_V0233.json")

    check = sub.add_parser("performance-baseline-check")
    check.add_argument("--baseline")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch v0.23.3 cockpit/performance CLI commands."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "consolidation-status":
        return _emit(
            consolidation_status(
                root,
                args.consolidation_id,
                candidate_set_id=args.candidate_set_id,
                project_consolidation_id=args.project_consolidation_id,
            )
        )
    if args.command == "performance-baseline-run":
        if CURRENT_SCHEMA_VERSION != BASELINE_SCHEMA_VERSION and args.output == DEFAULT_BASELINE_FILE:
            return _emit({
                "ok": False,
                "error": "historical_baseline_is_frozen",
                "historical_baseline": DEFAULT_BASELINE_FILE,
                "historical_schema": BASELINE_SCHEMA_VERSION,
                "current_schema": CURRENT_SCHEMA_VERSION,
                "message": "Use an explicit non-historical --output for diagnostics; do not overwrite the v0.23.3 baseline artifact.",
            })
        result = run_performance_baseline(root, repeats=max(1, args.repeats))
        target = root / args.output
        target.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        emitted = dict(result)
        emitted["written_to"] = args.output
        return _emit(emitted)
    if args.command == "performance-baseline-check":
        return _emit(check_performance_baseline(root, args.baseline))
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
