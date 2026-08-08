#!/usr/bin/env python3
"""Apply AgentOS v0.21.2 -> v0.22.0 Controlled Target Insert upgrade fail-closed."""
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

BASELINE_VERSION = "0.21.2"
TARGET_VERSION = "0.22.0"
MARKER = "AGENTOS_V0220_CONTROLLED_TARGET_INSERT"

AGENTS_SECTION = """## AgentOS v0.22.0 — Controlled Target Insert

- SOURCE databases remain immutable/read-only; recheck every SOURCE before TARGET execution.
- Generic/raw TARGET INSERT remains forbidden. Controlled write exists only through an immutable insert plan from a fully validated v0.21.2 staging batch.
- Partial batches with rejected rows are not eligible in v0.22.0.
- Bind every plan to staging/manifest/extraction/mapping/target-contract/target-snapshot hashes plus `insert_plan_hash`.
- Human review and human approval are mandatory after hash revalidation.
- INSERT only. UPDATE, UPSERT/MERGE, DELETE, DDL, raw SQL, and side-effect procedures are forbidden.
- Use generated parameterized/prepared INSERT statements; never interpolate business values into SQL text.
- Pre-commit failure rolls back. Commit uncertainty becomes `in_doubt` and must never auto-retry.
- SQLite/audit/MCP must not persist inserted row values or resolved credentials.
- MCP is read-only and must not create/review/approve/execute controlled writes.
"""


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def required_paths(root: Path) -> list[Path]:
    return [
        root / "VERSION", root / "AGENTS.md", root / ".agents/agentos/__init__.py", root / ".agents/agentos/db.py",
        root / ".agents/agentos/read_only_extraction.py", root / ".agents/config/governance.json",
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
        raise RuntimeError("governance version does not match v0.21.2")
    extraction = governance.get("read_only_extraction_policy")
    boundary = governance.get("database_boundary_policy")
    if not isinstance(extraction, dict) or extraction.get("source_select_only") is not True:
        raise RuntimeError("v0.21.2 read-only extraction policy is missing")
    if extraction.get("target_data_write_enabled") is not False:
        raise RuntimeError("baseline unexpectedly enables TARGET writes")
    if not isinstance(boundary, dict) or boundary.get("source_insert_allowed") is not False:
        raise RuntimeError("v0.21.2 SOURCE-write boundary is missing")
    tree = ast.parse(read(root / ".agents/agentos/db.py"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if "_m37" not in names:
        raise RuntimeError("db.py does not contain schema-37 migration")
    return {"version": version, "governance_version": BASELINE_VERSION, "source_write": False, "generic_target_insert": False}


def patch_db(source: str) -> str:
    import_line = "from .controlled_target_insert import migration_38 as _m38\n"
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
    if "_m38" not in existing:
        target.value.elts.append(ast.Name(id="_m38", ctx=ast.Load()))
    ast.fix_missing_locations(tree)
    patched = ast.unparse(tree) + "\n"
    ast.parse(patched)
    return patched


def patch_init(source: str) -> str:
    if '__version__ = "0.21.2"' not in source and "__version__ = '0.21.2'" not in source:
        raise RuntimeError("could not safely locate __version__ 0.21.2")
    return source.replace('__version__ = "0.21.2"', '__version__ = "0.22.0"').replace("__version__ = '0.21.2'", "__version__ = '0.22.0'")


def merge_governance(source: str, fragment: dict[str, Any]) -> str:
    value = json.loads(source)
    incoming = fragment["controlled_target_insert_policy"]
    existing = value.get("controlled_target_insert_policy")
    if existing is not None and existing != incoming:
        raise RuntimeError("different controlled_target_insert_policy already exists")
    value["controlled_target_insert_policy"] = incoming
    boundary = value.get("database_boundary_policy")
    mapping = value.get("schema_mapping_policy")
    extraction = value.get("read_only_extraction_policy")
    if not all(isinstance(x, dict) for x in (boundary, mapping, extraction)):
        raise RuntimeError("required v0.21.x database policies are missing")
    boundary["target_data_write_enabled"] = False
    boundary["controlled_target_insert_enabled"] = True
    boundary["target_write_mode"] = "controlled_insert_only"
    boundary["raw_target_insert_allowed"] = False
    boundary["target_insert_available_from_version"] = TARGET_VERSION
    mapping["target_data_write_enabled"] = False
    mapping["controlled_target_insert_enabled"] = True
    mapping["controlled_target_insert_version"] = TARGET_VERSION
    extraction["target_data_write_enabled"] = False
    extraction["controlled_target_insert_available"] = True
    extraction["controlled_target_insert_version"] = TARGET_VERSION
    value["version"] = TARGET_VERSION
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def append_agents(original: str) -> str:
    if f"<!-- {MARKER}_BEGIN -->" in original:
        return original
    return original.rstrip() + f"\n\n<!-- {MARKER}_BEGIN -->\n" + AGENTS_SECTION.strip() + f"\n<!-- {MARKER}_END -->\n"


def backup(root: Path, files: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = root / ".agents/runtime/upgrade-backups" / f"v0212-to-v0220-{stamp}"
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
    fragment = json.loads(read(overlay / ".agents/config/controlled_target_insert_policy.v0220.json"))
    changed = [
        root / "VERSION", root / "AGENTS.md", root / "README.md", root / "README.vi.md", root / "README.en.md",
        root / "huong_dan.md", root / "huong_dan.vi.md", root / "huong_dan.en.md", root / "RELEASE_NOTES.md",
        root / ".agents/agentos/__init__.py", root / ".agents/agentos/db.py", root / ".agents/config/governance.json",
        root / ".agents/bin/agentos", root / ".agents/bin/agentos-mcp", root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ]
    if dry_run:
        return {"ok": True, "dry_run": True, "baseline": baseline, "target": TARGET_VERSION, "would_change": [str(p.relative_to(root)) for p in changed]}
    backup_root = backup(root, changed)

    current_cli = root / ".agents/bin/agentos"
    old_cli = root / ".agents/bin/agentos.v0212"
    if not old_cli.exists():
        shutil.copy2(current_cli, old_cli); old_cli.chmod(0o755)
    current_mcp = root / ".agents/bin/agentos-mcp"
    old_mcp = root / ".agents/bin/agentos-mcp.v0212"
    if not old_mcp.exists():
        shutil.copy2(current_mcp, old_mcp); old_mcp.chmod(0o755)

    copy_paths = [
        ".agents/agentos/controlled_target_insert.py", ".agents/agentos/controlled_target_insert_cli.py",
        ".agents/agentos/mcp_controlled_target_insert_gateway.py", ".agents/config/controlled_target_insert_policy.v0220.json",
        ".agents/docs/CONTROLLED_TARGET_INSERT.md", ".agents/docs/USAGE_V0220.md", ".agents/docs/RELEASE_NOTES_V0220.md",
        ".agents/tests/test_controlled_target_insert_v0220.py",
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

    for rel in [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        "RELEASE_NOTES.md", "UPGRADE_FROM_0.21.2.md", "VERSION",
    ]:
        shutil.copy2(overlay / rel, root / rel)
    shutil.copy2(overlay / "UPGRADE_FROM_0.21.2.md", root / ".agents/docs/UPGRADE_FROM_0.21.2.md")

    changelog = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    base = read(changelog) if changelog.exists() else "# Rules & Workflow Changelog\n"
    entry = """## v0.22.0 — Controlled Target Insert

- Schema 38 controlled-target-insert plans/events.
- Fully validated staging only; generic/raw TARGET INSERT remains denied.
- Immutable plan + human review + human approval before INSERT-only transaction.
- Pre-commit failures roll back; commit uncertainty becomes `in_doubt` and cannot auto-retry.
- SOURCE write paths remain forbidden; row values/credentials remain out of SQLite/audit/MCP.
"""
    if "## v0.22.0 — Controlled Target Insert" not in base:
        write(changelog, base.rstrip() + "\n\n" + entry)

    shutil.copy2(overlay / ".agents/bin/agentos", current_cli); current_cli.chmod(0o755)
    shutil.copy2(overlay / ".agents/bin/agentos-mcp", current_mcp); current_mcp.chmod(0o755)

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(root / ".agents") + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    sync = subprocess.run([sys.executable, "-m", "agentos.controlled_target_insert_cli", "--root", str(root), "db-controlled-target-insert-db-sync"], env=env, capture_output=True, text=True)
    if sync.returncode != 0:
        raise RuntimeError("schema-38 sync failed after patch: " + sync.stderr + sync.stdout)
    return {"ok": True, "from": BASELINE_VERSION, "to": TARGET_VERSION, "backup": str(backup_root), "schema_sync": json.loads(sync.stdout), "generic_target_insert": False, "controlled_insert": True}


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
