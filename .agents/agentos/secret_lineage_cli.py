"""
File: .agents/agentos/secret_lineage_cli.py

Purpose:
    Provide human/operator CLI for v0.22.6 secret resolver approvals and lineage-key lifecycle.

Responsibilities:
    - Keep resolver approval/revocation and key rotation outside MCP mutation authority.
    - Expose redacted provider/key metadata to operators.
    - Enforce explicit human confirmation for approval/review/revocation decisions.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

from .secret_lineage import (
    SecretLineageError, approve_provider, revoke_provider, provider_catalog, keyring_status,
    create_rotation_plan, review_rotation_plan, approve_rotation_plan, execute_rotation_plan,
    revoke_key, rotation_plan_get, create_rekey_plan, review_rekey_plan, approve_rekey_plan,
    authorize_rekey_source_reread, rekey_plan_get, sync_schema, ensure_keyring,
)


def _emit(value: Any) -> int:
    """Print JSON and return a conventional status code."""
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.22.6 operator CLI parser."""
    p = argparse.ArgumentParser(prog="agentos secret-lineage")
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("secret-provider-catalog")
    x = sub.add_parser("secret-provider-approve"); x.add_argument("--scheme", required=True); x.add_argument("--capability", action="append", required=True); x.add_argument("--approved-by", required=True); x.add_argument("--human-confirmed", action="store_true")
    x = sub.add_parser("secret-provider-revoke"); x.add_argument("--scheme", required=True); x.add_argument("--revoked-by", required=True); x.add_argument("--human-confirmed", action="store_true")
    sub.add_parser("lineage-keyring-status")
    sub.add_parser("lineage-keyring-initialize")
    x = sub.add_parser("lineage-key-rotation-plan-create"); x.add_argument("--reason", required=True); x.add_argument("--created-by", required=True)
    for name, actor in (("lineage-key-rotation-plan-review","reviewed-by"),("lineage-key-rotation-plan-approve","approved-by")):
        x=sub.add_parser(name); x.add_argument("--plan-id", type=int, required=True); x.add_argument(f"--{actor}", required=True); x.add_argument("--human-confirmed", action="store_true")
    x=sub.add_parser("lineage-key-rotation-execute"); x.add_argument("--plan-id", type=int, required=True); x.add_argument("--executed-by", required=True)
    x=sub.add_parser("lineage-key-rotation-plan-show"); x.add_argument("--plan-id", type=int, required=True)
    x=sub.add_parser("lineage-key-revoke"); x.add_argument("--key-id", required=True); x.add_argument("--revoked-by", required=True); x.add_argument("--human-confirmed", action="store_true")
    x=sub.add_parser("lineage-rekey-plan-create"); x.add_argument("--source-connection-id", type=int, required=True); x.add_argument("--from-key-id", required=True); x.add_argument("--created-by", required=True)
    x=sub.add_parser("lineage-rekey-plan-review"); x.add_argument("--plan-id", type=int, required=True); x.add_argument("--reviewed-by", required=True); x.add_argument("--human-confirmed", action="store_true")
    x=sub.add_parser("lineage-rekey-plan-approve"); x.add_argument("--plan-id", type=int, required=True); x.add_argument("--approved-by", required=True); x.add_argument("--human-confirmed", action="store_true")
    x=sub.add_parser("lineage-rekey-source-reread-authorize"); x.add_argument("--plan-id", type=int, required=True)
    x=sub.add_parser("lineage-rekey-plan-show"); x.add_argument("--plan-id", type=int, required=True)
    sub.add_parser("secret-lineage-db-sync")
    return p


def main(argv: list[str] | None = None) -> int:
    """Execute one v0.22.6 operator command."""
    args=build_parser().parse_args(argv); root=Path(args.root).resolve()
    try:
        c=args.command
        if c=="secret-provider-catalog": return _emit({"ok":True,"providers":provider_catalog(),"credential_values_included":False})
        if c=="secret-provider-approve": return _emit(approve_provider(root,args.scheme,capabilities=args.capability,approved_by=args.approved_by,human_confirmed=args.human_confirmed))
        if c=="secret-provider-revoke": return _emit(revoke_provider(root,args.scheme,revoked_by=args.revoked_by,human_confirmed=args.human_confirmed))
        if c=="lineage-keyring-status": return _emit(keyring_status(root))
        if c=="lineage-keyring-initialize": return _emit({"ok":True,"key":ensure_keyring(root),"material_included":False})
        if c=="lineage-key-rotation-plan-create": return _emit(create_rotation_plan(root,reason=args.reason,created_by=args.created_by))
        if c=="lineage-key-rotation-plan-review": return _emit(review_rotation_plan(root,args.plan_id,reviewed_by=args.reviewed_by,human_confirmed=args.human_confirmed))
        if c=="lineage-key-rotation-plan-approve": return _emit(approve_rotation_plan(root,args.plan_id,approved_by=args.approved_by,human_confirmed=args.human_confirmed))
        if c=="lineage-key-rotation-execute": return _emit(execute_rotation_plan(root,args.plan_id,executed_by=args.executed_by))
        if c=="lineage-key-rotation-plan-show": return _emit(rotation_plan_get(root,args.plan_id))
        if c=="lineage-key-revoke": return _emit(revoke_key(root,args.key_id,revoked_by=args.revoked_by,human_confirmed=args.human_confirmed))
        if c=="lineage-rekey-plan-create": return _emit(create_rekey_plan(root,source_connection_id=args.source_connection_id,from_key_id=args.from_key_id,created_by=args.created_by))
        if c=="lineage-rekey-plan-review": return _emit(review_rekey_plan(root,args.plan_id,reviewed_by=args.reviewed_by,human_confirmed=args.human_confirmed))
        if c=="lineage-rekey-plan-approve": return _emit(approve_rekey_plan(root,args.plan_id,approved_by=args.approved_by,human_confirmed=args.human_confirmed))
        if c=="lineage-rekey-source-reread-authorize": return _emit(authorize_rekey_source_reread(root,args.plan_id))
        if c=="lineage-rekey-plan-show": return _emit(rekey_plan_get(root,args.plan_id))
        if c=="secret-lineage-db-sync": return _emit(sync_schema(root))
    except SecretLineageError as exc:
        return _emit({"ok":False,"error":str(exc)})
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
