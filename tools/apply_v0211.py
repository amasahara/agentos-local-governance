#!/usr/bin/env python3
"""Apply AgentOS v0.21.0 -> v0.21.1 upgrade fail-closed."""
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

BASELINE_VERSION = "0.21.0"
TARGET_VERSION = "0.21.1"

AGENTS_SECTION = """## AgentOS v0.21.1 — Target Schema Contract & Cross-DB Field Mapping

- Target schema is authoritative. AgentOS MUST NOT infer or create TARGET structure from SOURCE schemas.
- Every TARGET contract MUST be backed by an active TARGET schema snapshot and validated against that snapshot.
- v0.21.1 handles catalog/schema metadata only. Business record extraction remains disabled until v0.21.2 and TARGET writes remain disabled until v0.22.0.
- SOURCE schema snapshots require v0.21.0 read-only verification and MUST NOT contain record values.
- Mapping direction is always registered SOURCE → approved TARGET contract. SOURCE-to-SOURCE mapping is forbidden.
- Field mappings require evidence, canonical type compatibility, and explicit transformation metadata when types differ.
- Human confirmation is mandatory before a mapping becomes confirmed. LLM suggestions are advisory only.
- Every mapping is bound to source_snapshot_hash and target_contract_hash. Schema drift makes dependent mappings stale.
- MCP may expose read-only state/suggestions but MUST NOT expose mutation, extraction, raw SQL, or TARGET writes.
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
        root / "VERSION",
        root / "AGENTS.md",
        root / ".agents/agentos/__init__.py",
        root / ".agents/agentos/db.py",
        root / ".agents/agentos/database_boundary.py",
        root / ".agents/config/governance.json",
        root / ".agents/bin/agentos",
        root / ".agents/bin/agentos-mcp",
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
        raise RuntimeError("governance version does not match v0.21.0")
    if not isinstance(governance.get("database_boundary_policy"), dict):
        raise RuntimeError("v0.21.0 database boundary policy is missing")
    source = read(root / ".agents/agentos/db.py")
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if "_m35" not in names:
        raise RuntimeError("db.py does not contain v0.21.0 schema-35 migration")
    return {"version": version, "governance_version": BASELINE_VERSION}


def patch_db(source: str) -> str:
    import_line = "from .schema_mapping import migration_36 as _m36\n"
    if import_line not in source:
        source = import_line + source
    tree = ast.parse(source)
    target: ast.Assign | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MIGRATIONS" for t in node.targets):
            target = node
            break
    if target is None or not isinstance(target.value, (ast.List, ast.Tuple)):
        raise RuntimeError("unsupported db.py MIGRATIONS registry")
    existing = [e.id for e in target.value.elts if isinstance(e, ast.Name)]
    if "_m36" not in existing:
        target.value.elts.append(ast.Name(id="_m36", ctx=ast.Load()))
    ast.fix_missing_locations(tree)
    patched = ast.unparse(tree) + "\n"
    ast.parse(patched)
    return patched


def patch_init(source: str) -> str:
    if '__version__ = "0.21.0"' not in source and "__version__ = '0.21.0'" not in source:
        raise RuntimeError("could not safely locate __version__ 0.21.0")
    return source.replace('__version__ = "0.21.0"', '__version__ = "0.21.1"').replace("__version__ = '0.21.0'", "__version__ = '0.21.1'")


def merge_governance(source: str, fragment: dict[str, Any]) -> str:
    value = json.loads(source)
    incoming = fragment["schema_mapping_policy"]
    existing = value.get("schema_mapping_policy")
    if existing is not None and existing != incoming:
        raise RuntimeError("different schema_mapping_policy already exists")
    value["schema_mapping_policy"] = incoming
    if "version" in value:
        value["version"] = TARGET_VERSION
    else:
        value["governance_version"] = TARGET_VERSION
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def append_section(original: str) -> str:
    marker = "AGENTOS_V0211_SCHEMA_MAPPING"
    if marker in original:
        return original
    return original.rstrip() + f"\n\n<!-- {marker}_BEGIN -->\n" + AGENTS_SECTION.strip() + f"\n<!-- {marker}_END -->\n"


def backup(root: Path, files: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = root / ".agents/runtime/upgrade-backups" / f"v0210-to-v0211-{stamp}"
    manifest = []
    for p in files:
        if not p.exists() or not p.is_file():
            continue
        rel = p.relative_to(root)
        q = dest / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, q)
        manifest.append({"path": str(rel), "sha256": sha256(p)})
    dest.mkdir(parents=True, exist_ok=True)
    write(dest / "manifest.json", json.dumps({"from": BASELINE_VERSION, "to": TARGET_VERSION, "files": manifest}, indent=2) + "\n")
    return dest


def apply(root: Path, overlay: Path, dry_run: bool) -> dict[str, Any]:
    baseline = validate_baseline(root)
    fragment = json.loads(read(overlay / ".agents/config/schema_mapping_policy.v0211.json"))
    changed = [
        root / "VERSION", root / "AGENTS.md", root / "README.md", root / "README.vi.md", root / "README.en.md",
        root / "huong_dan.md", root / "huong_dan.vi.md", root / "huong_dan.en.md", root / "RELEASE_NOTES.md",
        root / ".agents/agentos/__init__.py", root / ".agents/agentos/db.py", root / ".agents/config/governance.json",
        root / ".agents/bin/agentos", root / ".agents/bin/agentos-mcp", root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ]
    if dry_run:
        return {"ok": True, "dry_run": True, "baseline": baseline, "target": TARGET_VERSION, "would_change": [str(p.relative_to(root)) for p in changed]}
    backup_root = backup(root, changed)

    # Preserve the v0.21.0 launchers as the compatibility backend.
    current_cli = root / ".agents/bin/agentos"
    old_cli = root / ".agents/bin/agentos.v0210"
    if not old_cli.exists():
        shutil.copy2(current_cli, old_cli); old_cli.chmod(0o755)
    current_mcp = root / ".agents/bin/agentos-mcp"
    old_mcp = root / ".agents/bin/agentos-mcp.v0210"
    if not old_mcp.exists():
        shutil.copy2(current_mcp, old_mcp); old_mcp.chmod(0o755)

    for rel in [
        ".agents/agentos/schema_mapping.py",
        ".agents/agentos/schema_mapping_cli.py",
        ".agents/agentos/mcp_schema_mapping_gateway.py",
        ".agents/config/schema_mapping_policy.v0211.json",
        ".agents/docs/TARGET_SCHEMA_CONTRACT_AND_FIELD_MAPPING.md",
        ".agents/docs/USAGE_V0211.md",
        ".agents/docs/RELEASE_NOTES_V0211.md",
        ".agents/tests/test_schema_mapping_v0211.py",
    ]:
        src, dst = overlay / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    write(root / ".agents/agentos/db.py", patch_db(read(root / ".agents/agentos/db.py")))
    write(root / ".agents/agentos/__init__.py", patch_init(read(root / ".agents/agentos/__init__.py")))
    write(root / ".agents/config/governance.json", merge_governance(read(root / ".agents/config/governance.json"), fragment))
    write(root / "AGENTS.md", append_section(read(root / "AGENTS.md")))

    for rel in ["README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md", "RELEASE_NOTES.md", "UPGRADE_FROM_0.21.0.md", "VERSION"]:
        shutil.copy2(overlay / rel, root / rel)
    shutil.copy2(overlay / "UPGRADE_FROM_0.21.0.md", root / ".agents/docs/UPGRADE_FROM_0.21.0.md")

    changelog = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    base = read(changelog) if changelog.exists() else "# Rules & Workflow Changelog\n"
    entry = """## v0.21.1 — Target Schema Contract & Cross-DB Field Mapping

- Schema 36 metadata-only snapshots, target contracts, field mappings, and evidence events.
- TARGET contract is authoritative and validated against TARGET snapshot.
- SOURCE→TARGET mappings require evidence/type checks/human confirmation.
- Snapshot/contract drift stales mappings fail-closed.
- No extraction until v0.21.2; no TARGET INSERT until v0.22.0.
"""
    if "## v0.21.1 — Target Schema Contract" not in base:
        write(changelog, base.rstrip() + "\n\n" + entry)

    shutil.copy2(overlay / ".agents/bin/agentos", current_cli); current_cli.chmod(0o755)
    shutil.copy2(overlay / ".agents/bin/agentos-mcp", current_mcp); current_mcp.chmod(0o755)

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(root / ".agents") + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    sync = subprocess.run([sys.executable, "-m", "agentos.schema_mapping_cli", "--root", str(root), "db-schema-mapping-db-sync"], env=env, capture_output=True, text=True)
    if sync.returncode != 0:
        raise RuntimeError("schema-36 sync failed after patch: " + sync.stderr + sync.stdout)
    return {"ok": True, "from": BASELINE_VERSION, "to": TARGET_VERSION, "backup": str(backup_root), "schema_sync": json.loads(sync.stdout)}


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
