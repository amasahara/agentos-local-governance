"""
File: .agents/agentos/schema_mapping_cli.py

Purpose:
    Expose v0.21.1 Target Schema Contract and Cross-DB Field Mapping operator commands.

Responsibilities:
    - Register metadata-only SOURCE/TARGET schema snapshots from JSON manifests.
    - Create, review, and approve target schema contracts.
    - Create, confirm, reject, list, and suggest directional field mappings.
    - Expose readiness for v0.21.2 without extracting record data.
    - Forward all older commands to the v0.21.0 wrapper.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schema_mapping import (
    SchemaMappingError,
    add_field_mapping,
    approve_target_contract,
    confirm_field_mapping,
    create_target_contract,
    docs_check_v0211,
    get_field_mapping,
    get_schema_snapshot,
    get_target_contract,
    list_field_mappings,
    mapping_readiness,
    register_schema_snapshot,
    reject_field_mapping,
    review_target_contract,
    suggest_field_mappings,
    sync_schema_mapping_schema,
)


def _load_json(path: str) -> object:
    """Load UTF-8 JSON from an operator-provided local file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(value: object) -> int:
    """Print structured JSON and derive CLI exit code."""
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build v0.21.1 CLI parser."""
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("db-schema-snapshot-register")
    snap.add_argument("--connection-id", type=int, required=True)
    snap.add_argument("--manifest-file", required=True)
    snap.add_argument("--captured-by", required=True)

    snap_show = sub.add_parser("db-schema-snapshot-show")
    snap_show.add_argument("--snapshot-id", type=int, required=True)

    contract = sub.add_parser("db-target-contract-create")
    contract.add_argument("--consolidation-id", type=int, required=True)
    contract.add_argument("--target-snapshot-id", type=int, required=True)
    contract.add_argument("--contract-file", required=True)
    contract.add_argument("--created-by", required=True)

    review = sub.add_parser("db-target-contract-review")
    review.add_argument("--contract-id", type=int, required=True)
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--human-confirmed", action="store_true", required=True)

    approve = sub.add_parser("db-target-contract-approve")
    approve.add_argument("--contract-id", type=int, required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--human-confirmed", action="store_true", required=True)

    contract_show = sub.add_parser("db-target-contract-show")
    contract_show.add_argument("--contract-id", type=int, required=True)

    mapping = sub.add_parser("db-field-mapping-add")
    mapping.add_argument("--consolidation-id", type=int, required=True)
    mapping.add_argument("--source-snapshot-id", type=int, required=True)
    mapping.add_argument("--target-contract-id", type=int, required=True)
    mapping.add_argument("--source-schema", required=True)
    mapping.add_argument("--source-table", required=True)
    mapping.add_argument("--source-column", required=True)
    mapping.add_argument("--target-schema", required=True)
    mapping.add_argument("--target-table", required=True)
    mapping.add_argument("--target-column", required=True)
    mapping.add_argument("--confidence", type=float, required=True)
    mapping.add_argument("--match-method", choices=["manual", "lexical", "dictionary", "semantic", "human"], required=True)
    mapping.add_argument("--evidence-file", required=True)
    mapping.add_argument("--created-by", required=True)
    mapping.add_argument("--transform-rule")
    mapping.add_argument("--transform-output-type")
    mapping.add_argument("--validation-rule-file")

    confirm = sub.add_parser("db-field-mapping-confirm")
    confirm.add_argument("--mapping-id", type=int, required=True)
    confirm.add_argument("--confirmed-by", required=True)
    confirm.add_argument("--human-confirmed", action="store_true", required=True)

    reject = sub.add_parser("db-field-mapping-reject")
    reject.add_argument("--mapping-id", type=int, required=True)
    reject.add_argument("--rejected-by", required=True)
    reject.add_argument("--human-confirmed", action="store_true", required=True)

    mapping_show = sub.add_parser("db-field-mapping-show")
    mapping_show.add_argument("--mapping-id", type=int, required=True)

    mapping_list = sub.add_parser("db-field-mapping-list")
    mapping_list.add_argument("--consolidation-id", type=int, required=True)
    mapping_list.add_argument("--status", choices=["proposed", "confirmed", "rejected", "stale"])

    suggest = sub.add_parser("db-field-mapping-suggest")
    suggest.add_argument("--consolidation-id", type=int, required=True)
    suggest.add_argument("--source-snapshot-id", type=int, required=True)
    suggest.add_argument("--target-contract-id", type=int, required=True)
    suggest.add_argument("--limit", type=int, default=50)

    readiness = sub.add_parser("db-mapping-readiness")
    readiness.add_argument("--consolidation-id", type=int, required=True)
    readiness.add_argument("--target-contract-id", type=int, required=True)

    sub.add_parser("db-schema-mapping-db-sync")
    sub.add_parser("docs-check-v0211")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run v0.21.1 operator CLI."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "db-schema-snapshot-register":
            manifest = _load_json(args.manifest_file)
            if not isinstance(manifest, dict):
                raise SchemaMappingError("schema manifest JSON root must be an object")
            return _emit(register_schema_snapshot(root, connection_id=args.connection_id, manifest=manifest, captured_by=args.captured_by))
        if args.command == "db-schema-snapshot-show":
            return _emit(get_schema_snapshot(root, args.snapshot_id))
        if args.command == "db-target-contract-create":
            contract = _load_json(args.contract_file)
            if not isinstance(contract, dict):
                raise SchemaMappingError("target contract JSON root must be an object")
            return _emit(create_target_contract(root, consolidation_id=args.consolidation_id, target_snapshot_id=args.target_snapshot_id, contract=contract, created_by=args.created_by))
        if args.command == "db-target-contract-review":
            return _emit(review_target_contract(root, args.contract_id, reviewed_by=args.reviewed_by, human_confirmed=args.human_confirmed))
        if args.command == "db-target-contract-approve":
            return _emit(approve_target_contract(root, args.contract_id, approved_by=args.approved_by, human_confirmed=args.human_confirmed))
        if args.command == "db-target-contract-show":
            return _emit(get_target_contract(root, args.contract_id))
        if args.command == "db-field-mapping-add":
            evidence = _load_json(args.evidence_file)
            if not isinstance(evidence, dict):
                raise SchemaMappingError("mapping evidence JSON root must be an object")
            validation = _load_json(args.validation_rule_file) if args.validation_rule_file else None
            if validation is not None and not isinstance(validation, dict):
                raise SchemaMappingError("validation rule JSON root must be an object")
            return _emit(add_field_mapping(
                root,
                consolidation_id=args.consolidation_id,
                source_snapshot_id=args.source_snapshot_id,
                target_contract_id=args.target_contract_id,
                source_schema=args.source_schema,
                source_table=args.source_table,
                source_column=args.source_column,
                target_schema=args.target_schema,
                target_table=args.target_table,
                target_column=args.target_column,
                confidence=args.confidence,
                match_method=args.match_method,
                evidence=evidence,
                created_by=args.created_by,
                transform_rule=args.transform_rule,
                transform_output_type=args.transform_output_type,
                validation_rule=validation,
            ))
        if args.command == "db-field-mapping-confirm":
            return _emit(confirm_field_mapping(root, args.mapping_id, confirmed_by=args.confirmed_by, human_confirmed=args.human_confirmed))
        if args.command == "db-field-mapping-reject":
            return _emit(reject_field_mapping(root, args.mapping_id, rejected_by=args.rejected_by, human_confirmed=args.human_confirmed))
        if args.command == "db-field-mapping-show":
            return _emit(get_field_mapping(root, args.mapping_id))
        if args.command == "db-field-mapping-list":
            return _emit(list_field_mappings(root, args.consolidation_id, status=args.status))
        if args.command == "db-field-mapping-suggest":
            return _emit(suggest_field_mappings(root, consolidation_id=args.consolidation_id, source_snapshot_id=args.source_snapshot_id, target_contract_id=args.target_contract_id, limit=args.limit))
        if args.command == "db-mapping-readiness":
            return _emit(mapping_readiness(root, args.consolidation_id, args.target_contract_id))
        if args.command == "db-schema-mapping-db-sync":
            return _emit(sync_schema_mapping_schema(root))
        if args.command == "docs-check-v0211":
            return _emit(docs_check_v0211(root))
        raise AssertionError(args.command)
    except (SchemaMappingError, DatabaseBoundaryError, json.JSONDecodeError, OSError, ValueError) as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    raise SystemExit(main())
