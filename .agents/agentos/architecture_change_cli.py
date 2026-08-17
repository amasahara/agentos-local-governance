"""Path: .agents/agentos/architecture_change_cli.py
Purpose: CLI surface for v0.25.5 Architecture Change Proposal & ADR lifecycle.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .architecture_change import (
    approve_change_proposal,
    architecture_adr_get,
    architecture_change_proposal_get,
    architecture_change_proposals_list,
    architecture_change_status,
    bind_change_proposal_baseline,
    create_change_proposal,
    reject_change_proposal,
    review_change_proposal,
    submit_change_proposal,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _json(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def build_parser() -> argparse.ArgumentParser:
    """Build v0.25.5 proposal/ADR commands."""
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("architecture-proposal-create")
    p.add_argument("--title", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--rationale", required=True)
    p.add_argument("--affected-sections", required=True, help="JSON list of ARCH-01..ARCH-27 ids")
    p.add_argument("--proposed-changes", required=True, help="JSON object/list")
    p.add_argument("--impact-analysis", default="{}")
    p.add_argument("--validation-plan", default="{}")
    p.add_argument("--rollback-plan", default="{}")
    p.add_argument("--adr-alternatives", default="[]")
    p.add_argument("--compliance-run-id", type=int, default=None)
    p.add_argument("--finding-ids", default=None, help="Optional JSON list of finding ids from the selected run")
    p.add_argument("--created-by", default="ai:proposal-drafter")

    p = sub.add_parser("architecture-proposal-submit")
    p.add_argument("--proposal-id", type=int, required=True)
    p.add_argument("--proposal-hash", required=True)
    p.add_argument("--submitted-by", default="ai:proposal-drafter")

    p = sub.add_parser("architecture-proposal-review")
    p.add_argument("--proposal-id", type=int, required=True)
    p.add_argument("--proposal-hash", required=True)
    p.add_argument("--reviewed-by", required=True)
    p.add_argument("--human-confirmed", action="store_true")

    p = sub.add_parser("architecture-proposal-approve")
    p.add_argument("--proposal-id", type=int, required=True)
    p.add_argument("--proposal-hash", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--human-confirmed", action="store_true")

    p = sub.add_parser("architecture-proposal-reject")
    p.add_argument("--proposal-id", type=int, required=True)
    p.add_argument("--proposal-hash", required=True)
    p.add_argument("--rejected-by", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--human-confirmed", action="store_true")

    p = sub.add_parser("architecture-proposal-bind-baseline")
    p.add_argument("--proposal-id", type=int, required=True)
    p.add_argument("--proposal-hash", required=True)
    p.add_argument("--target-baseline-id", type=int, required=True)
    p.add_argument("--target-baseline-hash", required=True)
    p.add_argument("--bound-by", required=True)
    p.add_argument("--human-confirmed", action="store_true")

    p = sub.add_parser("architecture-proposal-show")
    p.add_argument("--proposal-id", type=int, default=None)
    p = sub.add_parser("architecture-proposals")
    p.add_argument("--status", choices=["draft","submitted","reviewed","approved","rejected","withdrawn"], default=None)
    p.add_argument("--limit", type=int, default=100)
    p = sub.add_parser("architecture-adr-show")
    p.add_argument("--adr-id", type=int, default=None)
    p.add_argument("--proposal-id", type=int, default=None)
    sub.add_parser("architecture-change-status")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one proposal/ADR lifecycle command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "architecture-proposal-create":
            affected = _json(args.affected_sections, [])
            findings = _json(args.finding_ids, None)
            if not isinstance(affected, list):
                raise RuntimeError("affected-sections must be a JSON list")
            if findings is not None and not isinstance(findings, list):
                raise RuntimeError("finding-ids must be a JSON list")
            value = create_change_proposal(
                root,
                title=args.title,
                summary=args.summary,
                rationale=args.rationale,
                affected_sections=affected,
                proposed_changes=_json(args.proposed_changes, {}),
                impact_analysis=_json(args.impact_analysis, {}),
                validation_plan=_json(args.validation_plan, {}),
                rollback_plan=_json(args.rollback_plan, {}),
                adr_alternatives=_json(args.adr_alternatives, []),
                compliance_run_id=args.compliance_run_id,
                finding_ids=findings,
                created_by=args.created_by,
            )
        elif args.command == "architecture-proposal-submit":
            value = submit_change_proposal(root, args.proposal_id, args.proposal_hash, args.submitted_by)
        elif args.command == "architecture-proposal-review":
            value = review_change_proposal(root, args.proposal_id, args.proposal_hash, args.reviewed_by, args.human_confirmed)
        elif args.command == "architecture-proposal-approve":
            value = approve_change_proposal(root, args.proposal_id, args.proposal_hash, args.approved_by, args.human_confirmed)
        elif args.command == "architecture-proposal-reject":
            value = reject_change_proposal(root, args.proposal_id, args.proposal_hash, args.rejected_by, args.reason, args.human_confirmed)
        elif args.command == "architecture-proposal-bind-baseline":
            value = bind_change_proposal_baseline(root, args.proposal_id, args.proposal_hash, args.target_baseline_id, args.target_baseline_hash, args.bound_by, args.human_confirmed)
        elif args.command == "architecture-proposal-show":
            value = architecture_change_proposal_get(root, proposal_id=args.proposal_id)
        elif args.command == "architecture-proposals":
            value = architecture_change_proposals_list(root, status=args.status, limit=args.limit)
        elif args.command == "architecture-adr-show":
            value = architecture_adr_get(root, adr_id=args.adr_id, proposal_id=args.proposal_id)
        elif args.command == "architecture-change-status":
            value = architecture_change_status(root)
        else:
            raise RuntimeError("unknown architecture change command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
