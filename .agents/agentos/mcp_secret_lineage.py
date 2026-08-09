"""
File: .agents/agentos/mcp_secret_lineage.py

Purpose:
    Expose v0.22.6 secret/key lifecycle inspection through read-only MCP tools.

Responsibilities:
    - Return provider identities, approvals, key metadata, and immutable plan metadata.
    - Never expose credential values, key material, approvals, rotations, revocations, or rekey mutations.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .db import connect
from .secret_lineage import provider_catalog, keyring_status, rotation_plan_get, rekey_plan_get, SecretLineageError

TOOLS = [
    {"name":"agentos.secret_provider_catalog_get","description":"Read trusted secret provider identities/hash pins; never credential values.","inputSchema":{"type":"object","properties":{}}},
    {"name":"agentos.secret_provider_approvals_get","description":"Read redacted provider approval metadata.","inputSchema":{"type":"object","properties":{}}},
    {"name":"agentos.lineage_keyring_get","description":"Read active/retired/revoked lineage key metadata without material.","inputSchema":{"type":"object","properties":{}}},
    {"name":"agentos.lineage_rotation_plan_get","description":"Read one immutable lineage-key rotation plan.","inputSchema":{"type":"object","properties":{"plan_id":{"type":"integer"}},"required":["plan_id"]}},
    {"name":"agentos.lineage_rekey_plan_get","description":"Read one SOURCE-reread rekey plan without raw identifiers.","inputSchema":{"type":"object","properties":{"plan_id":{"type":"integer"}},"required":["plan_id"]}},
]


def _local_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    """Dispatch a read-only v0.22.6 MCP operation."""
    try:
        if name=="agentos.secret_provider_catalog_get": return {"ok":True,"providers":provider_catalog(),"credentials_included":False}
        if name=="agentos.secret_provider_approvals_get":
            with connect(root) as conn:
                rows=conn.execute("SELECT provider_id,scheme,provider_version,provider_hash,capabilities_json,status,approved_at,revoked_at FROM secret_resolver_approvals ORDER BY id").fetchall()
            return {"ok":True,"approvals":[dict(r) for r in rows],"credentials_included":False}
        if name=="agentos.lineage_keyring_get": return keyring_status(root)
        if name=="agentos.lineage_rotation_plan_get": return rotation_plan_get(root,int(arguments["plan_id"]))
        if name=="agentos.lineage_rekey_plan_get": return rekey_plan_get(root,int(arguments["plan_id"]))
    except (SecretLineageError, KeyError, ValueError) as exc:
        return {"ok":False,"error":str(exc)}
    return {"ok":False,"error":"unknown v0.22.6 read-only MCP tool"}
