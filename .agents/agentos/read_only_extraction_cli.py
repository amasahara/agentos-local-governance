"""
File: .agents/agentos/read_only_extraction_cli.py

Purpose:
    Human/operator CLI for AgentOS v0.21.2 read-only extraction and data validation.

Responsibilities:
    - Create immutable extraction batches from confirmed mappings.
    - Show generated SELECT-only specs without accepting arbitrary SQL.
    - Execute SOURCE reads and local validation under v0.21.0/v0.21.1 boundaries.
    - Inspect privacy-safe validation summaries/findings and staging integrity.
    - Keep TARGET INSERT unavailable until v0.22.0.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .database_boundary import DatabaseBoundaryError
from .schema_mapping import SchemaMappingError
from .read_only_extraction import (
    ReadOnlyExtractionError,
    build_select_spec,
    create_extraction_batch,
    docs_check_v0212,
    get_extraction_batch,
    get_extraction_summary,
    get_validation_findings,
    run_extraction_validation,
    sync_read_only_extraction_schema,
    verify_staging_artifact,
)


def _emit(value: object) -> int:
    """Print structured JSON and derive CLI exit code."""
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build v0.21.2 operator CLI parser."""
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("db-extraction-batch-create")
    create.add_argument("--consolidation-id", type=int, required=True)
    create.add_argument("--source-snapshot-id", type=int, required=True)
    create.add_argument("--target-contract-id", type=int, required=True)
    create.add_argument("--source-schema", required=True)
    create.add_argument("--source-table", required=True)
    create.add_argument("--target-schema", required=True)
    create.add_argument("--target-table", required=True)
    create.add_argument("--created-by", required=True)
    create.add_argument("--max-rows", type=int, default=100000)
    create.add_argument("--chunk-size", type=int, default=1000)

    show = sub.add_parser("db-extraction-batch-show")
    show.add_argument("--batch-id", type=int, required=True)

    spec = sub.add_parser("db-extraction-select-spec")
    spec.add_argument("--batch-id", type=int, required=True)

    run = sub.add_parser("db-extraction-run")
    run.add_argument("--batch-id", type=int, required=True)

    summary = sub.add_parser("db-extraction-summary")
    summary.add_argument("--batch-id", type=int, required=True)

    findings = sub.add_parser("db-validation-findings")
    findings.add_argument("--batch-id", type=int, required=True)
    findings.add_argument("--limit", type=int, default=1000)

    verify = sub.add_parser("db-staging-verify")
    verify.add_argument("--batch-id", type=int, required=True)

    sub.add_parser("db-readonly-extraction-db-sync")
    sub.add_parser("docs-check-v0212")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run v0.21.2 operator CLI."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "db-extraction-batch-create":
            return _emit(create_extraction_batch(
                root,
                consolidation_id=args.consolidation_id,
                source_snapshot_id=args.source_snapshot_id,
                target_contract_id=args.target_contract_id,
                source_schema=args.source_schema,
                source_table=args.source_table,
                target_schema=args.target_schema,
                target_table=args.target_table,
                created_by=args.created_by,
                max_rows=args.max_rows,
                chunk_size=args.chunk_size,
            ))
        if args.command == "db-extraction-batch-show":
            return _emit(get_extraction_batch(root, args.batch_id))
        if args.command == "db-extraction-select-spec":
            return _emit(build_select_spec(root, args.batch_id))
        if args.command == "db-extraction-run":
            return _emit(run_extraction_validation(root, args.batch_id))
        if args.command == "db-extraction-summary":
            return _emit(get_extraction_summary(root, args.batch_id))
        if args.command == "db-validation-findings":
            return _emit(get_validation_findings(root, args.batch_id, limit=args.limit))
        if args.command == "db-staging-verify":
            return _emit(verify_staging_artifact(root, args.batch_id))
        if args.command == "db-readonly-extraction-db-sync":
            return _emit(sync_read_only_extraction_schema(root))
        if args.command == "docs-check-v0212":
            return _emit(docs_check_v0212(root))
        raise AssertionError(args.command)
    except (ReadOnlyExtractionError, SchemaMappingError, DatabaseBoundaryError, OSError, ValueError) as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    raise SystemExit(main())
