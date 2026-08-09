#!/usr/bin/env python3
"""Validate an applied AgentOS v0.22.6 root without resolving credentials or loading key material."""
from __future__ import annotations
import json
import sys
from pathlib import Path

REQUIRED_MCP = {
    "agentos.secret_provider_catalog_get",
    "agentos.secret_provider_approvals_get",
    "agentos.lineage_keyring_get",
    "agentos.lineage_rotation_plan_get",
    "agentos.lineage_rekey_plan_get",
}
FORBIDDEN_MCP_WORDS = {
    "approve", "revoke", "execute", "rotate", "initialize", "credential", "secret_resolve",
}
REQUIRED_POLICY_CAPS = {
    "secret.resolver.approve",
    "secret.resolver.revoke",
    "identity.lineage.key.initialize",
    "identity.lineage.key.rotate.plan",
    "identity.lineage.key.rotate.review",
    "identity.lineage.key.rotate.approve",
    "identity.lineage.key.rotate.execute",
    "identity.lineage.key.revoke",
    "identity.lineage.rekey.plan",
    "identity.lineage.rekey.review",
    "identity.lineage.rekey.approve",
    "identity.lineage.rekey.authorize_source_reread",
}


def main(root_s: str) -> int:
    root = Path(root_s).resolve()
    sys.path.insert(0, str(root / ".agents"))
    from agentos.db import connect
    from agentos.cli_runtime import command_registry, PRIVILEGED_COMMANDS
    from agentos.mcp_runtime import ALL_TOOLS
    from agentos.secret_lineage import provider_catalog, keyring_status

    g = json.loads((root / ".agents/config/governance.json").read_text(encoding="utf-8"))
    with connect(root) as c:
        schema = int(c.execute("select max(version) from schema_migrations").fetchone()[0])
        fk = int(c.execute("pragma foreign_keys").fetchone()[0])
    cli = command_registry()
    mcp = [x["name"] for x in ALL_TOOLS]
    provider_schemes = {x["scheme"] for x in provider_catalog()}
    key_status = keyring_status(root)  # read-only by contract
    secret_lineage_mcp = [n for n in mcp if n.startswith("agentos.secret_") or n.startswith("agentos.lineage_")]
    forbidden = [n for n in secret_lineage_mcp if any(word in n.lower() for word in FORBIDDEN_MCP_WORDS)]
    caps = set(g.get("governance_enforcement_policy", {}).get("privileged_capabilities", []))
    sr = g.get("secret_resolver_policy", {})
    kp = g.get("lineage_key_lifecycle_policy", {})
    runtime = g.get("unified_runtime_policy", {})

    checks = {
        "version": (root / "VERSION").read_text(encoding="utf-8").strip() == "0.22.6",
        "schema": schema == 42,
        "foreign_keys": fk == 1,
        "cli_unique": len(cli) == len(set(cli)),
        "mcp_unique": len(mcp) == len(set(mcp)),
        "required_mcp": REQUIRED_MCP <= set(mcp),
        "forbidden_mcp": not forbidden,
        "providers": {"env", "keychain", "vault", "file-secret"} <= provider_schemes,
        "dynamic_import_forbidden": sr.get("dynamic_importlib_resolver_allowed") is False,
        "callback_injection_forbidden": sr.get("production_callback_injection_allowed") is False,
        "memory_only": sr.get("memory_only_resolution") is True and sr.get("secret_persist_allowed") is False,
        "keyring_inspection_read_only": kp.get("read_only_inspection_initializes_keyring") is False,
        "historical_rehmac_forbidden": kp.get("historical_rehmac_without_raw_identifier_forbidden") is True,
        "required_privileged_caps": REQUIRED_POLICY_CAPS <= caps,
        "initialize_cli_privileged": "lineage-keyring-initialize" in PRIVILEGED_COMMANDS,
        "unified_runtime": runtime.get("version_forwarding_runtime_allowed") is False and runtime.get("mcp_subprocess_forwarding_allowed") is False,
        "key_status_material_absent": key_status.get("material_included") is False,
    }
    result = {
        "ok": all(checks.values()),
        "version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "schema": schema,
        "foreign_keys": fk,
        "cli_count": len(cli),
        "mcp_count": len(mcp),
        "providers": sorted(provider_schemes),
        "forbidden_mcp": forbidden,
        "checks": checks,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_v0226.py ROOT")
    raise SystemExit(main(sys.argv[1]))
