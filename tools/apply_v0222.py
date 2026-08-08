#!/usr/bin/env python3
"""Apply AgentOS v0.22.1 -> v0.22.2 Reconciliation & Recovery upgrade fail-closed."""
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

BASELINE_VERSION = "0.22.1"
TARGET_VERSION = "0.22.2"
MARKER = "AGENTOS_V0222_RECONCILIATION_RECOVERY"

AGENTS_SECTION = """## AgentOS v0.22.2 — Reconciliation & Recovery

- TARGET reconciliation is SELECT-only and scoped to approved identity business keys.
- Compare keyed whole-row fingerprints; counts alone are insufficient reconciliation evidence.
- Never persist raw TARGET rows, business-key query parameters, PHI/PII, credentials, or raw values in recovery state/audit.
- `committing`/`in_doubt` never auto-retry and never auto-resolve.
- Human `committed_verified` requires `matched`; human `not_committed_verified` requires `observed_none`.
- `observed_partial`/`mismatch` requires manual intervention; AgentOS must not auto UPDATE/DELETE/UPSERT/MERGE TARGET data.
- SOURCE writes remain forbidden throughout reconciliation/recovery.
- Known-commit pending lineage may be rebuilt locally/idempotently without repeating TARGET INSERT.
- MCP exposes read-only evidence only; reconciliation execution and recovery decisions remain human/operator actions.
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
        root / ".agents/agentos/controlled_target_insert.py", root / ".agents/agentos/identity_resolution.py",
        root / ".agents/config/governance.json", root / ".agents/bin/agentos", root / ".agents/bin/agentos-mcp",
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
        raise RuntimeError("governance version does not match v0.22.1")
    identity = governance.get("identity_resolution_policy")
    controlled = governance.get("controlled_target_insert_policy")
    if not isinstance(identity, dict) or identity.get("llm_may_decide_identity") is not False:
        raise RuntimeError("v0.22.1 identity-resolution boundary is missing")
    if not isinstance(controlled, dict) or controlled.get("raw_target_insert_allowed") is not False or controlled.get("source_write_allowed") is not False:
        raise RuntimeError("v0.22.1 controlled-write boundary is not fail-closed")
    tree = ast.parse(read(root / ".agents/agentos/db.py"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if "_m39" not in names:
        raise RuntimeError("db.py does not contain schema-39 migration")
    return {"version": version, "governance_version": BASELINE_VERSION, "source_write": False, "raw_target_insert": False}


def patch_db(source: str) -> str:
    import_line = "from .reconciliation_recovery import migration_40 as _m40\n"
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
    if "_m40" not in existing:
        target.value.elts.append(ast.Name(id="_m40", ctx=ast.Load()))
    ast.fix_missing_locations(tree)
    patched = ast.unparse(tree) + "\n"
    ast.parse(patched)
    return patched


def patch_init(source: str) -> str:
    if '__version__ = "0.22.1"' not in source and "__version__ = '0.22.1'" not in source:
        raise RuntimeError("could not safely locate __version__ 0.22.1")
    return source.replace('__version__ = "0.22.1"', '__version__ = "0.22.2"').replace("__version__ = '0.22.1'", "__version__ = '0.22.2'")


def merge_governance(source: str, fragment: dict[str, Any]) -> str:
    value = json.loads(source)
    incoming = fragment["reconciliation_recovery_policy"]
    existing = value.get("reconciliation_recovery_policy")
    if existing is not None and existing != incoming:
        raise RuntimeError("different reconciliation_recovery_policy already exists")
    value["reconciliation_recovery_policy"] = incoming
    controlled = value.get("controlled_target_insert_policy")
    if not isinstance(controlled, dict):
        raise RuntimeError("controlled_target_insert_policy is missing")
    controlled["reconciled_not_committed_manual_retry_allowed"] = True
    controlled["reconciled_not_committed_automatic_retry_allowed"] = False
    controlled["in_doubt_reconciliation_version"] = TARGET_VERSION
    value["version"] = TARGET_VERSION
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def append_agents(original: str) -> str:
    if f"<!-- {MARKER}_BEGIN -->" in original:
        return original
    return original.rstrip() + f"\n\n<!-- {MARKER}_BEGIN -->\n" + AGENTS_SECTION.strip() + f"\n<!-- {MARKER}_END -->\n"


def backup(root: Path, files: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = root / ".agents/runtime/upgrade-backups" / f"v0221-to-v0222-{stamp}"
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
    fragment = json.loads(read(overlay / ".agents/config/reconciliation_recovery_policy.v0222.json"))
    changed = [
        root / "VERSION", root / "AGENTS.md", root / "README.md", root / "README.vi.md", root / "README.en.md",
        root / "huong_dan.md", root / "huong_dan.vi.md", root / "huong_dan.en.md", root / "RELEASE_NOTES.md",
        root / ".agents/agentos/__init__.py", root / ".agents/agentos/db.py", root / ".agents/agentos/controlled_target_insert.py",
        root / ".agents/config/governance.json", root / ".agents/bin/agentos", root / ".agents/bin/agentos-mcp",
        root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    ]
    if dry_run:
        return {"ok": True, "dry_run": True, "baseline": baseline, "target": TARGET_VERSION, "would_change": [str(p.relative_to(root)) for p in changed]}
    backup_root = backup(root, changed)

    current_cli = root / ".agents/bin/agentos"
    old_cli = root / ".agents/bin/agentos.v0221"
    if not old_cli.exists():
        shutil.copy2(current_cli, old_cli)
        old_cli.chmod(0o755)
    current_mcp = root / ".agents/bin/agentos-mcp"
    old_mcp = root / ".agents/bin/agentos-mcp.v0221"
    if not old_mcp.exists():
        shutil.copy2(current_mcp, old_mcp)
        old_mcp.chmod(0o755)

    copy_paths = [
        ".agents/agentos/reconciliation_recovery.py", ".agents/agentos/reconciliation_recovery_cli.py",
        ".agents/agentos/mcp_reconciliation_recovery_gateway.py", ".agents/agentos/controlled_target_insert.py",
        ".agents/config/reconciliation_recovery_policy.v0222.json",
        ".agents/docs/RECONCILIATION_AND_RECOVERY.md", ".agents/docs/USAGE_V0222.md", ".agents/docs/RELEASE_NOTES_V0222.md",
        ".agents/tests/test_reconciliation_recovery_v0222.py",
        "tools/apply_v0222.py", "tools/validate_release.py",
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
        "RELEASE_NOTES.md", "UPGRADE_FROM_0.22.1.md", "VERSION",
    ]:
        shutil.copy2(overlay / rel, root / rel)
    shutil.copy2(overlay / "UPGRADE_FROM_0.22.1.md", root / ".agents/docs/UPGRADE_FROM_0.22.1.md")

    changelog = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    base = read(changelog) if changelog.exists() else "# Rules & Workflow Changelog\n"
    entry = read(overlay / ".agents/docs/RELEASE_NOTES_V0222.md")
    if "## v0.22.2 — Reconciliation & Recovery" not in base:
        write(changelog, base.rstrip() + "\n\n## v0.22.2 — Reconciliation & Recovery\n\n" + "\n".join(entry.splitlines()[2:]).strip() + "\n")

    shutil.copy2(overlay / ".agents/bin/agentos", current_cli)
    current_cli.chmod(0o755)
    shutil.copy2(overlay / ".agents/bin/agentos-mcp", current_mcp)
    current_mcp.chmod(0o755)

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(root / ".agents") + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    sync = subprocess.run([sys.executable, "-m", "agentos.reconciliation_recovery_cli", "--root", str(root), "db-reconciliation-recovery-db-sync"], env=env, capture_output=True, text=True)
    if sync.returncode != 0:
        raise RuntimeError("schema-40 sync failed after patch: " + sync.stderr + sync.stdout)
    return {"ok": True, "from": BASELINE_VERSION, "to": TARGET_VERSION, "backup": str(backup_root), "schema_sync": json.loads(sync.stdout),
            "in_doubt_auto_retry": False, "partial_target_auto_repair": False}


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
