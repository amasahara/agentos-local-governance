#!/usr/bin/env python3
"""Apply the fail-closed AgentOS v0.23.2 -> v0.23.3 upgrade overlay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

BASELINE = "0.23.2"
TARGET = "0.23.3"
OVERLAY_ROOT = Path(__file__).resolve().parents[1]
COPY_FILES = (
    ".agents/agentos/consolidation_cockpit.py",
    ".agents/agentos/performance_baseline.py",
    ".agents/agentos/consolidation_cockpit_cli.py",
    ".agents/agentos/mcp_consolidation_cockpit.py",
    ".agents/tests/test_consolidation_cockpit_v0233.py",
    ".agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md",
    "UPGRADE_FROM_0.23.2.md",
    "RELEASE_NOTES_V0233.md",
    "PERFORMANCE_BASELINE_V0233.json",
    "tools/apply_v0233.py",
    "tools/validate_v0233.py",
)
REQUIRED_BASELINE_FILES = (
    ".agents/agentos/cli_runtime.py",
    ".agents/agentos/mcp_runtime.py",
    ".agents/agentos/mcp_catalog.py",
    ".agents/agentos/release_integrity.py",
    ".agents/agentos/schema_version.py",
    ".agents/agentos/__init__.py",
    ".agents/config/governance.json",
    "README.md",
    "README.vi.md",
    "README.en.md",
    "huong_dan.md",
    "huong_dan.vi.md",
    "huong_dan.en.md",
    ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    "CHANGELOG.md",
    "RELEASE_NOTES.md",
)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one baseline pattern, got {count}")
    return text.replace(old, new, 1)


def _patch_text(path: Path, patches: list[tuple[str, str, str]], dry_run: bool) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text
    for old, new, label in patches:
        updated = _replace_once(updated, old, new, label)
    if not dry_run:
        path.write_text(updated, encoding="utf-8")


def _backup(root: Path, files: tuple[str, ...]) -> Path:
    backup = root / ".agents/runtime/upgrade-backups/v0.23.2-to-v0.23.3"
    backup.mkdir(parents=True, exist_ok=True)
    for rel in files:
        src = root / rel
        if not src.exists():
            continue
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return backup


def _patch_readmes(root: Path, dry_run: bool) -> None:
    _patch_text(root / "README.md", [
        (
            "**Current release: v0.23.2 — Context Expansion & Compression Evaluation**",
            "**Current release: v0.23.3 — Consolidation Cockpit & Performance Baseline**",
            "README release header",
        ),
        (
            "v0.23.2 extends the v0.23.0/0.23.1 requirement-preserving transport pipeline with **bounded, hash-pinned context expansion** and **deterministic compression evaluation**. The Control Plane remains 100% lossless. Expansion can reveal omitted evidence only through verified read-only handles, while evaluation checks candidate accountability, handle integrity, token-budget compliance, exact requirement preservation, compression stability, and shadow revision regressions.",
            "v0.23.3 adds a **read-only consolidation cockpit** spanning project selection through database reconciliation and a **non-destructive performance baseline** for fresh migrations, the current full-rebuild symbol index, and cockpit latency. It does not change consolidation authority, SOURCE/TARGET write boundaries, privacy rules, or the lossless Context Control Plane.",
            "README release summary",
        ),
        (
            "Database schema: **46**. Expanded source content is never persisted in expansion telemetry. MCP exposes inspection/expansion/evaluation reads only; evaluation persistence and transport mutation remain operator/CLI-only.",
            "Database schema: **46** (unchanged). MCP adds read-only cockpit/baseline inspection only; benchmark execution remains CLI/operator-only and all write-heavy measurements run in temporary fixtures.",
            "README schema summary",
        ),
        (
            "This repository is materialized so it can be uploaded/replaced as a complete v0.23.2 tree without running an upgrader first. GitHub Actions validates the pushed tree automatically. See [Full GitHub-Ready Materialization](.agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md).",
            "The public v0.23.2 tree remains the materialized baseline. Apply the v0.23.3 upgrader, capture `PERFORMANCE_BASELINE_V0233.json` on the materialized repository, then run release-integrity/docs/tests before publishing a v0.23.3 full tree.",
            "README materialization note",
        ),
        (
            "See [UPGRADE_FROM_0.23.1.md](UPGRADE_FROM_0.23.1.md).",
            "See [UPGRADE_FROM_0.23.2.md](UPGRADE_FROM_0.23.2.md).",
            "README upgrade link",
        ),
        (
            "## Node documentation\n- [Context Expansion & Compression Evaluation]",
            "## Node documentation\n- [Consolidation Cockpit & Performance Baseline](.agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md)\n- [Context Expansion & Compression Evaluation]",
            "README node doc",
        ),
    ], dry_run)

    _patch_text(root / "README.vi.md", [
        (
            "# AgentOS Local Governance v0.23.2 — Context Expansion & Compression Evaluation",
            "# AgentOS Local Governance v0.23.3 — Consolidation Cockpit & Performance Baseline",
            "README.vi header",
        ),
        (
            "[README landing](README.md) | [English](README.en.md)\n\n## Mục tiêu",
            "[README landing](README.md) | [English](README.en.md)\n\n## v0.23.3\n\nv0.23.3 bổ sung `consolidation-status` read-only cho toàn chuỗi project/database consolidation và baseline hiệu năng non-destructive cho migration 1→46, full symbol-index rebuild hiện tại và cockpit latency. Schema vẫn là **46**; MCP chỉ đọc status/baseline, không chạy benchmark và không có quyền mutation.\n\n## Nền v0.23.2",
            "README.vi v0233 section",
        ),
    ], dry_run)

    _patch_text(root / "README.en.md", [
        (
            "# AgentOS Local Governance v0.23.2 — Context Expansion & Compression Evaluation",
            "# AgentOS Local Governance v0.23.3 — Consolidation Cockpit & Performance Baseline",
            "README.en header",
        ),
        (
            "[README landing](README.md) | [Tiếng Việt](README.vi.md)\n\n",
            "[README landing](README.md) | [Tiếng Việt](README.vi.md)\n\nv0.23.3 adds a read-only end-to-end consolidation cockpit and non-destructive performance baselines for fresh schema migration, the current full-rebuild symbol index, and cockpit latency. Schema remains **46**. MCP can read status/baseline artifacts but cannot execute benchmarks or mutate consolidation state.\n\n## v0.23.2 foundation\n",
            "README.en v0233 section",
        ),
    ], dry_run)

    _patch_text(root / "huong_dan.md", [
        (
            "Current version: **0.23.2**. Database schema: **46**. Build a fresh canonical Context Pack, compile a requirement-preserving transport, expand omitted evidence only through bounded hash-pinned handles, then run deterministic Compression Evaluation v2. The lossless Control Plane remains authoritative and is never truncated to improve compression ratio.",
            "Current version: **0.23.3**. Database schema: **46**. Use `consolidation-status` for a read-only end-to-end pipeline view, capture `PERFORMANCE_BASELINE_V0233.json` with `performance-baseline-run`, and keep the v0.23.2 lossless Context Control Plane and all SOURCE/TARGET/privacy/approval boundaries unchanged.",
            "developer guide landing",
        ),
    ], dry_run)
    _patch_text(root / "huong_dan.vi.md", [
        ("# Hướng dẫn AgentOS v0.23.2", "# Hướng dẫn AgentOS v0.23.3", "guide.vi header"),
        (
            "1. Duyệt task/scope và xây canonical Context Pack không stale.",
            "1. Dùng `consolidation-status` để đọc snapshot toàn pipeline mà không mutate state.\n2. Chạy `performance-baseline-run --repeats 5` trên repository đã materialize và xác nhận `performance-baseline-check`.\n3. Duyệt task/scope và xây canonical Context Pack không stale.",
            "guide.vi cockpit steps",
        ),
        ("2. Compile transport", "4. Compile transport", "guide.vi renumber 2"),
        ("3. Dùng `context-expansion-explain`", "5. Dùng `context-expansion-explain`", "guide.vi renumber 3"),
        ("4. Dùng `context-expand`", "6. Dùng `context-expand`", "guide.vi renumber 4"),
        ("5. Chạy `context-compression-evaluate`", "7. Chạy `context-compression-evaluate`", "guide.vi renumber 5"),
        ("6. Dùng `context-compression-compare`", "8. Dùng `context-compression-compare`", "guide.vi renumber 6"),
    ], dry_run)
    _patch_text(root / "huong_dan.en.md", [
        ("# AgentOS v0.23.2 Developer Guide", "# AgentOS v0.23.3 Developer Guide", "guide.en header"),
        (
            "Build a fresh canonical Context Pack and v0.23.1-compatible transport first.",
            "Inspect the complete consolidation pipeline with `consolidation-status` and capture/validate `PERFORMANCE_BASELINE_V0233.json` first. Build a fresh canonical Context Pack and v0.23.1-compatible transport next.",
            "guide.en cockpit steps",
        ),
    ], dry_run)


def _prepend_once(path: Path, entry: str, label: str, dry_run: bool) -> None:
    text = path.read_text(encoding="utf-8")
    if entry in text:
        return
    updated = _replace_once(text, "# Changelog\n", "# Changelog\n" + entry, label)
    if not dry_run:
        path.write_text(updated, encoding="utf-8")


def _patch_changelog(root: Path, dry_run: bool) -> None:
    rules_entry = """## v0.23.3 — Consolidation Cockpit & Performance Baseline\n- **User requirement:** aggregate the complete consolidation pipeline status and establish a measurable performance baseline before concurrency/index optimizations.\n- **Decision:** add a SQLite read-only cockpit spanning candidate/primary selection, project consolidation, DB boundary, schema/mapping, extraction, identity, controlled insert, reconciliation and recovery.\n- **Performance baseline:** benchmark fresh schema migration, the current full-rebuild `index_build`, and cockpit latency only in temporary/non-mutating fixtures; absolute wall-clock thresholds remain disabled until the environment is pinned.\n- **MCP boundary:** add read-only `agentos.consolidation_status_get` and `agentos.performance_baseline_get`; benchmark execution remains CLI/operator-only.\n- **Compatibility:** schema remains 46; SOURCE read-only, Controlled Target Insert, human risk gates, signed audit, privacy/secret/key and lossless Context Control Plane remain unchanged.\n\n"""
    _prepend_once(
        root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
        rules_entry,
        "rules/workflow changelog header",
        dry_run,
    )
    release_entry = """## 0.23.3 — Consolidation Cockpit & Performance Baseline\n- Added a read-only end-to-end consolidation cockpit from project selection through reconciliation/recovery.\n- Added isolated fresh-migration and full-rebuild symbol-index timing plus read-only cockpit latency measurement.\n- Added a fail-closed measured-baseline release gate; environment-specific timing thresholds remain disabled until the runner is pinned.\n- Added two MCP read-only inspection tools; benchmark execution and all consolidation mutations remain outside MCP.\n- Preserved schema 46 and all SOURCE/TARGET, human approval, signed-audit, privacy/secret/key and lossless Context Control Plane invariants.\n\n"""
    _prepend_once(root / "CHANGELOG.md", release_entry, "root changelog header", dry_run)


def apply(root: Path, dry_run: bool = False) -> dict[str, object]:
    root = root.resolve()
    version_path = root / "VERSION"
    if not version_path.is_file():
        raise RuntimeError("VERSION missing")
    current = version_path.read_text(encoding="utf-8").strip()
    if current != BASELINE:
        raise RuntimeError(f"baseline must be {BASELINE}, got {current!r}")

    for rel in REQUIRED_BASELINE_FILES:
        if not (root / rel).is_file():
            raise RuntimeError(f"required baseline file missing: {rel}")

    schema_text = (root / ".agents/agentos/schema_version.py").read_text(encoding="utf-8")
    if "CURRENT_SCHEMA_VERSION = 46" not in schema_text:
        raise RuntimeError("v0.23.3 requires baseline schema 46")

    policy_path = root / ".agents/config/governance.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    governance_before = str(policy.get("version") or "")
    if governance_before != BASELINE:
        raise RuntimeError(
            f"governance baseline must be exactly {BASELINE}, got {governance_before!r}"
        )

    if not dry_run:
        _backup(root, (*REQUIRED_BASELINE_FILES, "VERSION"))

    for rel in COPY_FILES:
        src = OVERLAY_ROOT / rel
        dst = root / rel
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)

    _patch_text(root / ".agents/agentos/cli_runtime.py", [
        ('VERSION = "0.23.2"', 'VERSION = "0.23.3"', "cli runtime version"),
        ('    "context_evaluation_cli",\n)', '    "context_evaluation_cli",\n    "consolidation_cockpit_cli",\n)', "CLI feature registration"),
        ('AgentOS Local Governance v0.23.2 — unified CLI runtime', 'AgentOS Local Governance v0.23.3 — unified CLI runtime', "CLI help version"),
    ], dry_run)
    _patch_text(root / ".agents/agentos/mcp_runtime.py", [
        ('VERSION = "0.23.2"', 'VERSION = "0.23.3"', "MCP runtime version"),
    ], dry_run)
    _patch_text(root / ".agents/agentos/mcp_catalog.py", [
        ('from . import mcp_context_evaluation as context_evaluation\n', 'from . import mcp_context_evaluation as context_evaluation\nfrom . import mcp_consolidation_cockpit as consolidation_cockpit\n', "MCP cockpit import"),
        ('    (context_evaluation.TOOLS, context_evaluation._local_call),\n)', '    (context_evaluation.TOOLS, context_evaluation._local_call),\n    (consolidation_cockpit.TOOLS, consolidation_cockpit._local_call),\n)', "MCP cockpit registration"),
    ], dry_run)
    _patch_text(root / ".agents/agentos/release_integrity.py", [
        ('    ".agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md",\n    ".github/workflows/agentos-release-validation.yml",', '    ".agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md",\n    "tools/apply_v0233.py",\n    "tools/validate_v0233.py",\n    ".agents/tests/test_consolidation_cockpit_v0233.py",\n    ".agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md",\n    "UPGRADE_FROM_0.23.2.md",\n    "PERFORMANCE_BASELINE_V0233.json",\n    ".github/workflows/agentos-release-validation.yml",', "v0.23.3 release files"),
        ('    ".agents/agentos/mcp_context_evaluation.py",\n)', '    ".agents/agentos/mcp_context_evaluation.py",\n    ".agents/agentos/consolidation_cockpit.py",\n    ".agents/agentos/performance_baseline.py",\n    ".agents/agentos/consolidation_cockpit_cli.py",\n    ".agents/agentos/mcp_consolidation_cockpit.py",\n)', "v0.23.3 extension files"),
        ('    "context_expansion_evaluation_policy",\n)', '    "context_expansion_evaluation_policy",\n    "consolidation_cockpit_policy",\n)', "policy section registration"),
        ('    findings.extend(_db_contract_findings(root))\n', '    findings.extend(_db_contract_findings(root))\n    try:\n        from .performance_baseline import check_performance_baseline\n        baseline_result = check_performance_baseline(root)\n        for code in baseline_result.get("findings", []):\n            findings.append(_finding("performance_baseline_invalid", str(code), "PERFORMANCE_BASELINE_V0233.json"))\n    except Exception as exc:\n        findings.append(_finding("performance_baseline_unloadable", f"cannot validate performance baseline: {exc}", "PERFORMANCE_BASELINE_V0233.json"))\n', "performance baseline release gate"),
        ('version != "0.23.2"', 'version != "0.23.3"', "integrity VERSION comparison"),
        ('expected VERSION 0.23.2', 'expected VERSION 0.23.3', "integrity VERSION message"),
        ('policy.get("version") != "0.23.2"', 'policy.get("version") != "0.23.3"', "integrity governance comparison"),
        ('governance.json version must be 0.23.2', 'governance.json version must be 0.23.3', "integrity governance message"),
        ('    ".agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md",\n)', '    ".agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md",\n    ".agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md",\n    "UPGRADE_FROM_0.23.2.md",\n    "PERFORMANCE_BASELINE_V0233.json",\n)', "v0.23.3 docs registration"),
        ('numbers and therefore cannot be chained as the current-release gate. v0.23.2', 'numbers and therefore cannot be chained as the current-release gate. v0.23.3', "docs gate version text"),
    ], dry_run)
    _patch_text(root / ".agents/agentos/__init__.py", [
        ('0.23.2', '0.23.3', "package version"),
    ], dry_run)

    _patch_readmes(root, dry_run)
    _patch_changelog(root, dry_run)

    policy["version"] = TARGET
    policy["consolidation_cockpit_policy"] = {
        "status_surface": "read_only_aggregate",
        "database_open_mode": "read_only_query_only",
        "full_pipeline_scope": True,
        "raw_record_values": "forbidden",
        "credentials": "forbidden",
        "secret_material": "forbidden",
        "identity_tokens": "forbidden",
        "mcp_mutation": "forbidden",
        "performance_benchmark_execution": "cli_operator_only",
        "performance_write_target": "temporary_fixture_only",
        "wall_clock_thresholds": "disabled_until_environment_pinned",
        "symbol_index_baseline_mode": "full_rebuild_measure_only",
        "schema_change": "none",
    }
    if not dry_run:
        policy_path.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        version_path.write_text(TARGET + "\n", encoding="utf-8")
        # Keep the canonical release-notes path synchronized with the new node.
        shutil.copy2(root / "RELEASE_NOTES_V0233.md", root / "RELEASE_NOTES.md")

    return {
        "ok": True,
        "baseline": BASELINE,
        "target": TARGET,
        "dry_run": dry_run,
        "schema": 46,
        "governance_version_before": governance_before,
        "baseline_capture_required_before_release_gate_passes": True,
        "copied_files": list(COPY_FILES),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(apply(Path(args.root), args.dry_run), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
