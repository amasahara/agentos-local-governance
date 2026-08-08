"""
File: .agents/agentos/reconciliation_recovery_cli.py

Purpose:
    Provide human/operator CLI for AgentOS v0.22.2 reconciliation and recovery.

Responsibilities:
    - Create/run read-only TARGET reconciliation outside MCP mutation paths.
    - Inspect end-to-end reconciliation summaries and recovery checkpoints.
    - Discover uncertain commit/lineage recovery cases.
    - Require explicit human confirmation for commit-outcome and lineage recovery decisions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .reconciliation_recovery import (
    ReconciliationRecoveryError,
    build_reconciliation_spec,
    create_reconciliation_run,
    docs_check_v0222,
    get_reconciliation_run,
    get_reconciliation_summary,
    get_recovery_readiness,
    list_recovery_cases,
    list_recovery_checkpoints,
    recover_pending_lineage,
    resolve_commit_outcome,
    run_reconciliation,
    scan_recovery_cases,
    sync_reconciliation_recovery_schema,
)


def _emit(value: Any) -> int:
    """Print JSON and return conventional status."""
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.22.2 operator CLI parser."""
    parser = argparse.ArgumentParser(prog="agentos reconciliation-recovery")
    parser.add_argument("--root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("db-reconciliation-create")
    cmd.add_argument("--insert-run-id", type=int, required=True)
    cmd.add_argument("--created-by", required=True)

    cmd = sub.add_parser("db-reconciliation-run")
    cmd.add_argument("--reconciliation-run-id", type=int, required=True)

    for name in ("db-reconciliation-show", "db-reconciliation-summary", "db-reconciliation-spec"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--reconciliation-run-id", type=int, required=True)

    sub.add_parser("db-recovery-scan")
    cmd = sub.add_parser("db-recovery-cases-list")
    cmd.add_argument("--status")

    cmd = sub.add_parser("db-recovery-readiness")
    cmd.add_argument("--insert-run-id", type=int, required=True)

    cmd = sub.add_parser("db-recovery-checkpoints-list")
    cmd.add_argument("--insert-run-id", type=int, required=True)

    cmd = sub.add_parser("db-recovery-commit-decide")
    cmd.add_argument("--recovery-case-id", type=int, required=True)
    cmd.add_argument("--decision", choices=["committed_verified", "not_committed_verified", "manual_intervention"], required=True)
    cmd.add_argument("--decided-by", required=True)
    cmd.add_argument("--human-confirmed", action="store_true")

    cmd = sub.add_parser("db-recovery-lineage-finalize")
    cmd.add_argument("--recovery-case-id", type=int, required=True)
    cmd.add_argument("--recovered-by", required=True)
    cmd.add_argument("--human-confirmed", action="store_true")

    sub.add_parser("db-reconciliation-recovery-db-sync")
    sub.add_parser("docs-check-v0222")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute one v0.22.2 human/operator command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "db-reconciliation-create":
            return _emit(create_reconciliation_run(root, insert_run_id=args.insert_run_id, created_by=args.created_by))
        if args.command == "db-reconciliation-run":
            return _emit(run_reconciliation(root, args.reconciliation_run_id))
        if args.command == "db-reconciliation-show":
            return _emit(get_reconciliation_run(root, args.reconciliation_run_id))
        if args.command == "db-reconciliation-summary":
            return _emit(get_reconciliation_summary(root, args.reconciliation_run_id))
        if args.command == "db-reconciliation-spec":
            return _emit(build_reconciliation_spec(root, args.reconciliation_run_id))
        if args.command == "db-recovery-scan":
            return _emit(scan_recovery_cases(root))
        if args.command == "db-recovery-cases-list":
            return _emit(list_recovery_cases(root, status=args.status))
        if args.command == "db-recovery-readiness":
            return _emit(get_recovery_readiness(root, args.insert_run_id))
        if args.command == "db-recovery-checkpoints-list":
            return _emit(list_recovery_checkpoints(root, args.insert_run_id))
        if args.command == "db-recovery-commit-decide":
            return _emit(resolve_commit_outcome(root, args.recovery_case_id, decision=args.decision, decided_by=args.decided_by, human_confirmed=args.human_confirmed))
        if args.command == "db-recovery-lineage-finalize":
            return _emit(recover_pending_lineage(root, args.recovery_case_id, recovered_by=args.recovered_by, human_confirmed=args.human_confirmed))
        if args.command == "db-reconciliation-recovery-db-sync":
            return _emit(sync_reconciliation_recovery_schema(root))
        if args.command == "docs-check-v0222":
            return _emit(docs_check_v0222(root))
    except ReconciliationRecoveryError as exc:
        return _emit({"ok": False, "error": str(exc)})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
