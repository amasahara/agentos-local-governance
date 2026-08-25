"""
File: .agents/agentos/database_boundary_cli.py

Purpose:
    Expose v0.21.0 Source/Target Database Boundary operator commands.

Responsibilities:
    - Register SOURCE/TARGET connection metadata without raw secrets.
    - Record human SOURCE read-only verification.
    - Create one-target database consolidation plans and attach verified sources.
    - Expose abstract authorization checks, not arbitrary SQL execution.
    - Forward all older commands to the v0.20.2 wrapper.
"""
from __future__ import annotations

from .cli_identity import cli_program

import argparse
import json
from pathlib import Path

from .database_boundary import (
    DatabaseBoundaryError,
    add_source,
    authorize_operation,
    create_consolidation,
    docs_check_v0210,
    get_connection,
    get_consolidation,
    register_connection,
    sync_database_boundary_schema,
    verify_source_readonly,
)


def _emit(value: object) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=cli_program())
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("db-connection-register")
    reg.add_argument("--alias", required=True)
    reg.add_argument("--role", choices=["SOURCE", "TARGET", "source", "target"], required=True)
    reg.add_argument("--engine", choices=["mysql", "mssql", "postgresql", "oracle"], required=True)
    reg.add_argument("--host", required=True)
    reg.add_argument("--port", type=int)
    reg.add_argument("--database", required=True)
    reg.add_argument("--domain", required=True)
    reg.add_argument("--credential-ref", required=True)
    reg.add_argument("--created-by", required=True)

    show = sub.add_parser("db-connection-show")
    show.add_argument("--connection-id", type=int, required=True)

    verify = sub.add_parser("db-source-verify-readonly")
    verify.add_argument("--connection-id", type=int, required=True)
    verify.add_argument("--verified-by", required=True)
    verify.add_argument("--method", choices=["grant_review", "account_policy", "session_readonly", "external_attestation"], required=True)
    verify.add_argument("--evidence", required=True)
    verify.add_argument("--human-confirmed", action="store_true", required=True)

    create = sub.add_parser("db-consolidation-create")
    create.add_argument("--target-connection-id", type=int, required=True)
    create.add_argument("--created-by", required=True)

    add = sub.add_parser("db-consolidation-add-source")
    add.add_argument("--consolidation-id", type=int, required=True)
    add.add_argument("--source-connection-id", type=int, required=True)
    add.add_argument("--registered-by", required=True)

    cshow = sub.add_parser("db-consolidation-show")
    cshow.add_argument("--consolidation-id", type=int, required=True)

    auth = sub.add_parser("db-boundary-authorize")
    auth.add_argument("--connection-id", type=int, required=True)
    auth.add_argument("--operation", required=True)

    sub.add_parser("db-boundary-db-sync")
    sub.add_parser("docs-check-v0210")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "db-connection-register":
            return _emit(register_connection(root, connection_alias=args.alias, role=args.role, engine=args.engine, host=args.host, port=args.port, database_name=args.database, domain_id=args.domain, credential_ref=args.credential_ref, created_by=args.created_by))
        if args.command == "db-connection-show":
            return _emit(get_connection(root, args.connection_id))
        if args.command == "db-source-verify-readonly":
            return _emit(verify_source_readonly(root, args.connection_id, verified_by=args.verified_by, method=args.method, evidence=args.evidence, human_confirmed=args.human_confirmed))
        if args.command == "db-consolidation-create":
            return _emit(create_consolidation(root, target_connection_id=args.target_connection_id, created_by=args.created_by))
        if args.command == "db-consolidation-add-source":
            return _emit(add_source(root, args.consolidation_id, args.source_connection_id, registered_by=args.registered_by))
        if args.command == "db-consolidation-show":
            return _emit(get_consolidation(root, args.consolidation_id))
        if args.command == "db-boundary-authorize":
            return _emit(authorize_operation(root, args.connection_id, args.operation))
        if args.command == "db-boundary-db-sync":
            return _emit(sync_database_boundary_schema(root))
        if args.command == "docs-check-v0210":
            return _emit(docs_check_v0210(root))
        raise AssertionError(args.command)
    except DatabaseBoundaryError as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    raise SystemExit(main())
