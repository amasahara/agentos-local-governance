#!/usr/bin/env python3
"""Apply AgentOS v0.20.2 -> v0.21.0 upgrade fail-closed."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any

BASELINE_VERSION = "0.20.2"
TARGET_VERSION = "0.21.0"


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
        root / ".agents/agentos/project_consolidation.py",
        root / ".agents/config/governance.json",
        root / ".agents/bin/agentos",
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
        raise RuntimeError("governance version does not match v0.20.2")
    if not isinstance(governance.get("primary_project_consolidation_policy"), dict):
        raise RuntimeError("v0.20.2 primary consolidation policy is missing")
    db_source = read(root / ".agents/agentos/db.py")
    tree = ast.parse(db_source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if "_m34" not in names:
        raise RuntimeError("db.py does not contain v0.20.2 schema-34 migration")
    return {"version": version, "governance_version": BASELINE_VERSION}


def patch_db(source: str) -> str:
    import_line = "from .database_boundary import migration_35 as _m35\n"
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
    if "_m35" not in existing:
        target.value.elts.append(ast.Name(id="_m35", ctx=ast.Load()))
    ast.fix_missing_locations(tree)
    patched = ast.unparse(tree) + "\n"
    ast.parse(patched)
    return patched


def patch_init(source: str) -> str:
    if '__version__ = "0.20.2"' not in source and "__version__ = '0.20.2'" not in source:
        raise RuntimeError("could not safely locate __version__ 0.20.2")
    return source.replace('__version__ = "0.20.2"', '__version__ = "0.21.0"').replace("__version__ = '0.20.2'", "__version__ = '0.21.0'")


def merge_governance(source: str, fragment: dict[str, Any]) -> str:
    value = json.loads(source)
    incoming = fragment["database_boundary_policy"]
    existing = value.get("database_boundary_policy")
    if existing is not None and existing != incoming:
        raise RuntimeError("different database_boundary_policy already exists")
    value["database_boundary_policy"] = incoming
    if "version" in value:
        value["version"] = TARGET_VERSION
    else:
        value["governance_version"] = TARGET_VERSION
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def append_once(original: str, fragment: str, marker: str) -> str:
    if marker in original:
        return original
    return original.rstrip() + f"\n\n<!-- {marker}_BEGIN -->\n" + fragment.strip() + f"\n<!-- {marker}_END -->\n"


def posix_cli_wrapper() -> str:
    return '''#!/usr/bin/env sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
CMD="${1:-}"
case "$CMD" in
  db-connection-register|db-connection-show|db-source-verify-readonly|db-consolidation-create|db-consolidation-add-source|db-consolidation-show|db-boundary-authorize|db-boundary-db-sync)
    PYTHONPATH="$ROOT/.agents${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m agentos.database_boundary_cli --root "$ROOT" "$@"
    ;;
  docs-check)
    PYTHONPATH="$ROOT/.agents${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m agentos.database_boundary_cli --root "$ROOT" docs-check-v0210
    ;;
esac
exec "$HERE/agentos.v0202" "$@"
'''


def posix_mcp_wrapper() -> str:
    return '''#!/usr/bin/env sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
export AGENTOS_PROJECT_ROOT="$ROOT"
export AGENTOS_V0202_MCP="$HERE/agentos-mcp.v0202"
PYTHONPATH="$ROOT/.agents${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m agentos.mcp_database_boundary_gateway "$@"
'''


def backup(root: Path, files: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = root / ".agents/runtime/upgrade-backups" / f"v0202-to-v0210-{stamp}"
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
    policy = json.loads(read(overlay / ".agents/config/database_boundary_policy.v0210.json"))
    changed = [
        root / "VERSION", root / "AGENTS.md", root / "README.md", root / "README.vi.md", root / "README.en.md",
        root / "huong_dan.md", root / "huong_dan.vi.md", root / "huong_dan.en.md", root / "RELEASE_NOTES.md",
        root / ".agents/agentos/__init__.py", root / ".agents/agentos/db.py", root / ".agents/config/governance.json",
        root / ".agents/bin/agentos", root / ".agents/bin/agentos-mcp",
    ]
    if dry_run:
        return {"ok": True, "dry_run": True, "baseline": baseline, "target": TARGET_VERSION, "would_change": [str(p.relative_to(root)) for p in changed]}
    backup_root = backup(root, changed)

    # Preserve previous wrappers as chain backends before replacing them.
    current_cli = root / ".agents/bin/agentos"
    old_cli = root / ".agents/bin/agentos.v0202"
    if not old_cli.exists():
        shutil.copy2(current_cli, old_cli)
        old_cli.chmod(0o755)
    current_mcp = root / ".agents/bin/agentos-mcp"
    old_mcp = root / ".agents/bin/agentos-mcp.v0202"
    if current_mcp.exists() and not old_mcp.exists():
        shutil.copy2(current_mcp, old_mcp)
        old_mcp.chmod(0o755)

    # Runtime and tests/docs.
    for rel in [
        ".agents/agentos/database_boundary.py",
        ".agents/agentos/database_boundary_cli.py",
        ".agents/agentos/mcp_database_boundary_gateway.py",
        ".agents/config/database_boundary_policy.v0210.json",
        ".agents/docs/SOURCE_TARGET_DATABASE_BOUNDARY.md",
        ".agents/docs/USAGE_V0210.md",
        ".agents/tests/test_database_boundary_v0210.py",
    ]:
        src, dst = overlay / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    write(root / ".agents/agentos/db.py", patch_db(read(root / ".agents/agentos/db.py")))
    write(root / ".agents/agentos/__init__.py", patch_init(read(root / ".agents/agentos/__init__.py")))
    write(root / ".agents/config/governance.json", merge_governance(read(root / ".agents/config/governance.json"), policy))
    write(root / "AGENTS.md", append_once(read(root / "AGENTS.md"), read(overlay / "AGENTS.v0210.section.md"), "AGENTOS_V0210_DATABASE_BOUNDARY"))

    for rel in ["README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md", "RELEASE_NOTES.md", "UPGRADE_FROM_0.20.2.md", "VERSION"]:
        shutil.copy2(overlay / rel, root / rel)
    shutil.copy2(overlay / "UPGRADE_FROM_0.20.2.md", root / ".agents/docs/UPGRADE_FROM_0.20.2.md")
    shutil.copy2(overlay / "RELEASE_NOTES.md", root / ".agents/docs/RELEASE_NOTES_V0210.md")
    changelog = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    base = read(changelog) if changelog.exists() else "# Rules & Workflow Changelog\n"
    write(changelog, append_once(base, read(overlay / "RULES_WORKFLOW_CHANGELOG.v0210.md"), "AGENTOS_V0210_CHANGELOG"))

    write(current_cli, posix_cli_wrapper()); current_cli.chmod(0o755)
    if current_mcp.exists():
        write(current_mcp, posix_mcp_wrapper()); current_mcp.chmod(0o755)

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(root / ".agents") + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    sync = subprocess.run([sys.executable, "-m", "agentos.database_boundary_cli", "--root", str(root), "db-boundary-db-sync"], env=env, capture_output=True, text=True)
    if sync.returncode != 0:
        raise RuntimeError("schema-35 sync failed after patch: " + sync.stderr + sync.stdout)
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
