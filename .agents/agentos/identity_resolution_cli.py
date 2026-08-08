"""
File: .agents/agentos/identity_resolution_cli.py

Purpose:
    Provide human/operator CLI for v0.22.1 identity resolution, deduplication, and lineage.

Responsibilities:
    - Create/review/approve deterministic identity policies outside MCP.
    - Run/resume identity resolution and record human candidate decisions.
    - Expose privacy-safe readiness and lineage inspection.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

from .identity_resolution import (
    IdentityResolutionError, approve_identity_policy, create_identity_policy,
    create_identity_resolution_run, decide_identity_candidate, docs_check_v0221,
    get_entity_lineage, get_identity_candidate, get_identity_policy,
    get_identity_readiness, get_identity_resolution_run, list_identity_candidates,
    review_identity_policy, run_identity_resolution, sync_identity_resolution_schema,
)


def _emit(value: Any) -> int:
    """Print JSON and return conventional status."""
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build v0.22.1 operator CLI parser."""
    p = argparse.ArgumentParser(prog="agentos identity-resolution")
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="command", required=True)

    x = sub.add_parser("db-identity-policy-create")
    x.add_argument("--consolidation-id", type=int, required=True); x.add_argument("--target-contract-id", type=int, required=True)
    x.add_argument("--target-schema", required=True); x.add_argument("--target-table", required=True)
    x.add_argument("--exact-key-field", action="append", required=True); x.add_argument("--strong-match-field", action="append", default=[])
    x.add_argument("--normalizer", choices=["exact", "trim_casefold"], default="trim_casefold"); x.add_argument("--created-by", required=True)

    x = sub.add_parser("db-identity-policy-show"); x.add_argument("--policy-id", type=int, required=True)
    x = sub.add_parser("db-identity-policy-review"); x.add_argument("--policy-id", type=int, required=True); x.add_argument("--reviewed-by", required=True); x.add_argument("--human-confirmed", action="store_true")
    x = sub.add_parser("db-identity-policy-approve"); x.add_argument("--policy-id", type=int, required=True); x.add_argument("--approved-by", required=True); x.add_argument("--human-confirmed", action="store_true")

    x = sub.add_parser("db-identity-resolution-create"); x.add_argument("--extraction-batch-id", type=int, required=True); x.add_argument("--policy-id", type=int, required=True); x.add_argument("--created-by", required=True)
    for name in ("db-identity-resolution-run", "db-identity-resolution-show", "db-identity-candidates-list"):
        x = sub.add_parser(name); x.add_argument("--resolution-run-id", type=int, required=True)
    x = sub.add_parser("db-identity-candidate-decide"); x.add_argument("--candidate-id", type=int, required=True); x.add_argument("--decision", choices=["confirm", "reject"], required=True); x.add_argument("--decided-by", required=True); x.add_argument("--human-confirmed", action="store_true")
    x = sub.add_parser("db-identity-candidate-show"); x.add_argument("--candidate-id", type=int, required=True)
    x = sub.add_parser("db-identity-readiness"); x.add_argument("--extraction-batch-id", type=int, required=True)
    x = sub.add_parser("db-entity-lineage-show"); x.add_argument("--entity-uuid", required=True)
    sub.add_parser("db-identity-resolution-db-sync")
    sub.add_parser("docs-check-v0221")
    return p


def main(argv: list[str] | None = None) -> int:
    """Execute one v0.22.1 human/operator command."""
    args = build_parser().parse_args(argv); root = Path(args.root).resolve()
    try:
        if args.command == "db-identity-policy-create":
            return _emit(create_identity_policy(root, consolidation_id=args.consolidation_id, target_contract_id=args.target_contract_id,
                target_schema=args.target_schema, target_table=args.target_table, exact_key_fields=args.exact_key_field,
                strong_match_fields=args.strong_match_field, normalizer=args.normalizer, created_by=args.created_by))
        if args.command == "db-identity-policy-show": return _emit(get_identity_policy(root, args.policy_id))
        if args.command == "db-identity-policy-review": return _emit(review_identity_policy(root, args.policy_id, reviewed_by=args.reviewed_by, human_confirmed=args.human_confirmed))
        if args.command == "db-identity-policy-approve": return _emit(approve_identity_policy(root, args.policy_id, approved_by=args.approved_by, human_confirmed=args.human_confirmed))
        if args.command == "db-identity-resolution-create": return _emit(create_identity_resolution_run(root, extraction_batch_id=args.extraction_batch_id, policy_id=args.policy_id, created_by=args.created_by))
        if args.command == "db-identity-resolution-run": return _emit(run_identity_resolution(root, args.resolution_run_id))
        if args.command == "db-identity-resolution-show": return _emit(get_identity_resolution_run(root, args.resolution_run_id))
        if args.command == "db-identity-candidates-list": return _emit(list_identity_candidates(root, args.resolution_run_id))
        if args.command == "db-identity-candidate-decide": return _emit(decide_identity_candidate(root, args.candidate_id, decision=args.decision, decided_by=args.decided_by, human_confirmed=args.human_confirmed))
        if args.command == "db-identity-candidate-show": return _emit(get_identity_candidate(root, args.candidate_id))
        if args.command == "db-identity-readiness": return _emit(get_identity_readiness(root, args.extraction_batch_id))
        if args.command == "db-entity-lineage-show": return _emit(get_entity_lineage(root, args.entity_uuid))
        if args.command == "db-identity-resolution-db-sync": return _emit(sync_identity_resolution_schema(root))
        if args.command == "docs-check-v0221": return _emit(docs_check_v0221(root))
    except IdentityResolutionError as exc:
        return _emit({"ok": False, "error": str(exc)})
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
