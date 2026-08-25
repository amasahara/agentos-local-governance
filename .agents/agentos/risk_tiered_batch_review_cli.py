"""
File: .agents/agentos/risk_tiered_batch_review_cli.py

Purpose:
    Expose v0.24.1 Risk-Tiered Batch Review operator commands.
"""
from __future__ import annotations

from .cli_identity import cli_program
import argparse
import json
from pathlib import Path

from .risk_tiered_batch_review import (
    RiskTieredBatchReviewError,
    assess_consolidation_risk,
    create_low_risk_bundle,
    get_batch_bundle,
    get_risk_review_status,
    review_low_risk_bundle,
    review_mapping_individual,
)


def _emit(value: object) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=cli_program())
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("project-consolidation-risk-assess")
    p.add_argument("--consolidation-id", type=int, required=True)

    p = sub.add_parser("project-consolidation-batch-bundle-create")
    p.add_argument("--consolidation-id", type=int, required=True)
    p.add_argument("--mapping-id", action="append", type=int)
    p.add_argument("--created-by", required=True)

    p = sub.add_parser("project-consolidation-batch-bundle-show")
    p.add_argument("--bundle-id", required=True)

    p = sub.add_parser("project-consolidation-batch-review")
    p.add_argument("--bundle-id", required=True)
    p.add_argument("--reviewed-by", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--human-confirmed", action="store_true", required=True)

    p = sub.add_parser("project-consolidation-mapping-review")
    p.add_argument("--consolidation-id", type=int, required=True)
    p.add_argument("--mapping-id", type=int, required=True)
    p.add_argument("--reviewed-by", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--human-confirmed", action="store_true", required=True)

    p = sub.add_parser("project-consolidation-risk-review-show")
    p.add_argument("--consolidation-id", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "project-consolidation-risk-assess":
            return _emit(assess_consolidation_risk(root, args.consolidation_id))
        if args.command == "project-consolidation-batch-bundle-create":
            return _emit(create_low_risk_bundle(root, args.consolidation_id, created_by=args.created_by, mapping_ids=args.mapping_id))
        if args.command == "project-consolidation-batch-bundle-show":
            return _emit(get_batch_bundle(root, args.bundle_id))
        if args.command == "project-consolidation-batch-review":
            return _emit(review_low_risk_bundle(root, args.bundle_id, reviewed_by=args.reviewed_by, reason=args.reason, human_confirmed=args.human_confirmed))
        if args.command == "project-consolidation-mapping-review":
            return _emit(review_mapping_individual(root, args.consolidation_id, args.mapping_id, reviewed_by=args.reviewed_by, reason=args.reason, human_confirmed=args.human_confirmed))
        if args.command == "project-consolidation-risk-review-show":
            return _emit(get_risk_review_status(root, args.consolidation_id))
        raise AssertionError(args.command)
    except RiskTieredBatchReviewError as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    raise SystemExit(main())
