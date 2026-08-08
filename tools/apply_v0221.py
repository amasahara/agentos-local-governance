#!/usr/bin/env python3
"""Apply AgentOS v0.22.0 -> v0.22.1 identity resolution/dedup/lineage upgrade fail-closed."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

BASELINE_VERSION = "0.22.0"
TARGET_VERSION = "0.22.1"
MARKER = "AGENTOS_V0221_IDENTITY_RESOLUTION"

AGENTS_SECTION = """## AgentOS v0.22.1 — Identity Resolution, Deduplication & Lineage

- New TARGET INSERT plans require a resolved v0.22.1 identity-resolution run.
- Identity policy must use a TARGET-contract business key and requires explicit human review + approval.
- Exact business-key matching may auto-bind only under that approved deterministic policy.
- Strong multi-field matches are candidates only and require explicit human confirm/reject; LLM/MCP must never decide identity.
- Fuzzy/embedding similarity may not auto-merge canonical entities.
- Persist only pseudonymous HMAC tokens/hashes in AgentOS state/audit; raw identity/PHI/PII remains local staging data.
- Deduplicate intra-batch and cross-batch before TARGET INSERT while preserving lineage from every SOURCE binding.
- Never reinsert an entity that already has committed TARGET lineage.
- If TARGET commit succeeds but lineage finalization is pending, never retry the INSERT.
"""


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def required_paths(root: Path) -> list[Path]:
    return [
        root / "VERSION", root / "AGENTS.md", root / ".agents/agentos/__init__.py", root / ".agents/agentos/db.py",
        root / ".agents/agentos/controlled_target_insert.py", root / ".agents/config/governance.json",
        root / ".agents/bin/agentos", root / ".agents/bin/agentos-mcp",
    ]


def validate_baseline(root: Path) -> dict[str, Any]:
    missing = [str(p.relative_to(root)) for p in required_paths(root) if not p.exists()]
    if missing:
        raise RuntimeError("baseline structure mismatch; missing: " + ", ".join(missing))
    version = read(root / "VERSION").strip()
    if version != BASELINE_VERSION:
        raise RuntimeError(f"refusing upgrade: VERSION={version!r}; expected {BASELINE_VERSION!r}")
    governance = json.loads(read(root / ".agents/config/governance.json"))
    if governance.get("version", governance.get("governance_version")) != BASELINE_VERSION:
        raise RuntimeError("governance version does not match v0.22.0")
    controlled = governance.get("controlled_target_insert_policy")
    if not isinstance(controlled, dict) or controlled.get("controlled_insert_enabled") is not True:
        raise RuntimeError("v0.22.0 controlled-target-insert policy is missing")
    if controlled.get("raw_target_insert_allowed") is not False or controlled.get("source_write_allowed") is not False:
        raise RuntimeError("v0.22.0 write boundary is not fail-closed")
    tree = ast.parse(read(root / ".agents/agentos/db.py"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if "_m38" not in names:
        raise RuntimeError("db.py does not contain schema-38 migration")
    return {"version": version, "governance_version": BASELINE_VERSION, "source_write": False, "raw_target_insert": False}


def patch_db(source: str) -> str:
    import_line = "from .identity_resolution import migration_39 as _m39\n"
    if import_line not in source:
        source = import_line + source
    tree = ast.parse(source)
    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MIGRATIONS" for t in node.targets):
            target = node
            break
    if target is None or not isinstance(target.value, (ast.List, ast.Tuple)):
        raise RuntimeError("unsupported db.py MIGRATIONS registry")
    existing = [e.id for e in target.value.elts if isinstance(e, ast.Name)]
    if "_m39" not in existing:
        target.value.elts.append(ast.Name(id="_m39", ctx=ast.Load()))
    ast.fix_missing_locations(tree)
    patched = ast.unparse(tree) + "\n"
    ast.parse(patched)
    return patched


def patch_init(source: str) -> str:
    if '__version__ = "0.22.0"' not in source and "__version__ = '0.22.0'" not in source:
        raise RuntimeError("could not safely locate __version__ 0.22.0")
    return source.replace('__version__ = "0.22.0"', '__version__ = "0.22.1"').replace("__version__ = '0.22.0'", "__version__ = '0.22.1'")


def merge_governance(source: str, fragment: dict[str, Any]) -> str:
    value = json.loads(source)
    incoming = fragment["identity_resolution_policy"]
    existing = value.get("identity_resolution_policy")
    if existing is not None and existing != incoming:
        raise RuntimeError("different identity_resolution_policy already exists")
    value["identity_resolution_policy"] = incoming
    controlled = value.get("controlled_target_insert_policy")
    if not isinstance(controlled, dict):
        raise RuntimeError("controlled_target_insert_policy is missing")
    controlled["identity_resolution_required"] = True
    controlled["identity_resolution_version"] = TARGET_VERSION
    controlled["lineage_finalization_required"] = True
    value["version"] = TARGET_VERSION
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def append_agents(original: str) -> str:
    if f"<!-- {MARKER}_BEGIN -->" in original:
        return original
    return original.rstrip() + f"\n\n<!-- {MARKER}_BEGIN -->\n" + AGENTS_SECTION.strip() + f"\n<!-- {MARKER}_END -->\n"


def backup(root: Path, files: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = root / ".agents/runtime/upgrade-backups" / f"v0220-to-v0221-{stamp}"
    manifest = []
    for path in files:
        if not path.exists() or not path.is_file():
            continue
        rel = path.relative_to(root)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        manifest.append({"path": str(rel), "sha256": sha256(path)})
    dest.mkdir(parents=True, exist_ok=True)
    write(dest / "manifest.json", json.dumps({"from": BASELINE_VERSION, "to": TARGET_VERSION, "files": manifest}, indent=2) + "\n")
    return dest


def apply(root: Path, overlay: Path, dry_run: bool) -> dict[str, Any]:
    baseline = validate_baseline(root)
    fragment = json.loads(read(overlay / ".agents/config/identity_resolution_policy.v0221.json"))
    changed = [
        root / "VERSION", root / "AGENTS.md", root / "README.md", root / "README.vi.md", root / "README.en.md",
        root / "huong_dan.md", root / "huong_dan.vi.md", root / "huong_dan.en.md", root / "RELEASE_NOTES.md",
        root / ".agents/agentos/__init__.py", root / ".agents/agentos/db.py", root / ".agents/agentos/controlled_target_insert.py",
        root / ".agents/config/governance.json", root / ".agents/bin/agentos", root / ".agents/bin/agentos-mcp",
        root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md", root / ".gitignore",
    ]
    if dry_run:
        return {"ok": True, "dry_run": True, "baseline": baseline, "target": TARGET_VERSION, "would_change": [str(p.relative_to(root)) for p in changed]}
    backup_root = backup(root, changed)

    current_cli = root / ".agents/bin/agentos"
    old_cli = root / ".agents/bin/agentos.v0220"
    if not old_cli.exists():
        shutil.copy2(current_cli, old_cli); old_cli.chmod(0o755)
    current_mcp = root / ".agents/bin/agentos-mcp"
    old_mcp = root / ".agents/bin/agentos-mcp.v0220"
    if not old_mcp.exists():
        shutil.copy2(current_mcp, old_mcp); old_mcp.chmod(0o755)

    copy_paths = [
        ".agents/agentos/identity_resolution.py", ".agents/agentos/identity_resolution_cli.py",
        ".agents/agentos/mcp_identity_resolution_gateway.py", ".agents/agentos/controlled_target_insert.py",
        ".agents/config/identity_resolution_policy.v0221.json",
        ".agents/docs/IDENTITY_RESOLUTION_DEDUPLICATION_LINEAGE.md", ".agents/docs/USAGE_V0221.md", ".agents/docs/RELEASE_NOTES_V0221.md",
        ".agents/tests/test_identity_resolution_v0221.py", ".agents/tests/test_controlled_target_insert_v0220.py",
        "tools/apply_v0221.py", "tools/validate_release.py",
    ]
    for rel in copy_paths:
        src, dst = overlay / rel, root / rel
        if not src.exists():
            raise RuntimeError(f"overlay missing required file: {rel}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    write(root / ".agents/agentos/db.py", patch_db(read(root / ".agents/agentos/db.py")))
    write(root / ".agents/agentos/__init__.py", patch_init(read(root / ".agents/agentos/__init__.py")))
    write(root / ".agents/config/governance.json", merge_governance(read(root / ".agents/config/governance.json"), fragment))
    write(root / "AGENTS.md", append_agents(read(root / "AGENTS.md")))

    gitignore = read(root / ".gitignore") if (root / ".gitignore").exists() else ""
    if ".agents/state/identity_lineage.key" not in gitignore:
        write(root / ".gitignore", gitignore.rstrip() + "\n# v0.22.1 local-only identity pseudonymization key\n.agents/state/identity_lineage.key\n")

    for rel in [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        "RELEASE_NOTES.md", "UPGRADE_FROM_0.22.0.md", "VERSION",
    ]:
        shutil.copy2(overlay / rel, root / rel)
    shutil.copy2(overlay / "UPGRADE_FROM_0.22.0.md", root / ".agents/docs/UPGRADE_FROM_0.22.0.md")

    changelog = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    base = read(changelog) if changelog.exists() else "# Rules & Workflow Changelog\n"
    entry = """## v0.22.1 — Identity Resolution, Deduplication & Lineage

- Schema 39 identity policies/runs/canonical entities/bindings/candidates/lineage/events.
- Exact business-key resolution only under a human-approved deterministic policy.
- Strong multi-field matches require explicit human decisions; LLM/MCP cannot decide identity.
- Deduplicated staging is mandatory before new controlled insert plans.
- Raw identity values remain out of SQLite/audit; cross-batch duplicates retain pseudonymous lineage.
"""
    if "## v0.22.1 — Identity Resolution, Deduplication & Lineage" not in base:
        write(changelog, base.rstrip() + "\n\n" + entry)

    shutil.copy2(overlay / ".agents/bin/agentos", current_cli); current_cli.chmod(0o755)
    shutil.copy2(overlay / ".agents/bin/agentos-mcp", current_mcp); current_mcp.chmod(0o755)

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(root / ".agents") + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    sync = subprocess.run([sys.executable, "-m", "agentos.identity_resolution_cli", "--root", str(root), "db-identity-resolution-db-sync"], env=env, capture_output=True, text=True)
    if sync.returncode != 0:
        raise RuntimeError("schema-39 sync failed after patch: " + sync.stderr + sync.stdout)
    return {"ok": True, "from": BASELINE_VERSION, "to": TARGET_VERSION, "backup": str(backup_root), "schema_sync": json.loads(sync.stdout), "llm_identity_decision": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    overlay = Path(__file__).resolve().parents[1]
    try:
        result = apply(root, overlay, args.dry_run)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
