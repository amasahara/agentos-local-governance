#!/usr/bin/env python3
"""
File: tools/repository_release_cleanup.py

Purpose:
    Normalize AgentOS v0.24.2 into a clean GitHub `main` release tree while
    preserving historical release artifacts outside the repository.

Responsibilities:
    - Keep current runtime source, all regression tests, current architecture docs,
      current release notes, manifest/checksums and runtime-required benchmarks.
    - Archive versioned updater/validator/release-history packaging files outside repo.
    - Keep local runtime/state/cache data but remove them from Git tracking.
    - Replace historical version-pinned release validation with current-release validation.
    - Reframe release-integrity around the clean-main package instead of old updater files.
    - Rebuild manifest/checksums and require targeted + full regression before completion.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable

VERSION = "0.24.2"
SCHEMA = 49
CLEANUP_ID = "v0.24.2-repository-release-cleanup-1"

LATEST_UPGRADE_GUIDE = "UPGRADE_FROM_0.24.1.md"

GENERIC_TOOLS = {
    "build_manifest.py",
    "verify_manifest.py",
    "validate_release.py",
    "repository_release_cleanup.py",
}

ROOT_ARCHIVE_GLOBS = (
    "apply_v*.py",
    "apply_v*.py.sha256",
    "RELEASE_NOTES_V*.md",
    "CHECKSUMS_V*.sha256",
    "VALIDATION_REPORT*.json",
    "HOTFIX_INFO.txt",
    "*.zip",
    "*.zip.sha256",
)

DOC_ARCHIVE_GLOBS = (
    ".agents/docs/RELEASE_NOTES_V*.md",
    ".agents/docs/USAGE_V*.md",
    ".agents/docs/GITHUB_READY_FULL_RELEASE_V*.md",
)

MANIFEST_LOCAL_ONLY_GLOBS = (
    "apply_v*.py",
    "apply_v*.py.sha256",
    "tools/apply_v*.py",
    "tools/validate_v*.py",
    "CHECKSUMS_V*.sha256",
    "VALIDATION_REPORT*.json",
    "*.zip",
    "*.zip.sha256",
    ".agents/bin/agentos.v*",
    ".agents/bin/agentos-mcp.v*",
    ".agents/docs/RELEASE_NOTES_V*.md",
    ".agents/docs/USAGE_V*.md",
    ".agents/docs/GITHUB_READY_FULL_RELEASE_V*.md",
    ".agents/docs/archive/*",
    ".agents/docs/archive/**",
)

RELEASE_CLUTTER_GLOBS = MANIFEST_LOCAL_ONLY_GLOBS + (
    "HOTFIX_INFO.txt",
    "UPGRADE_FROM_0.22*.md",
    "UPGRADE_FROM_0.23*.md",
    "UPGRADE_FROM_0.24.0.md",
)

GITIGNORE_APPEND = r"""
# Generated release / hotfix artifacts — GitHub Release assets, not main.
/apply_v*.py
/apply_v*.py.sha256
/tools/apply_v*.py
/tools/validate_v*.py
/CHECKSUMS_V*.sha256
/VALIDATION_REPORT*.json
/HOTFIX_INFO.txt
/*.zip
/*.zip.sha256

# Historical release packaging/docs are retained by git tags/releases, not main.
.agents/bin/agentos.v*
.agents/bin/agentos-mcp.v*
.agents/docs/RELEASE_NOTES_V*.md
.agents/docs/USAGE_V*.md
.agents/docs/GITHUB_READY_FULL_RELEASE_V*.md
.agents/docs/archive/

# Local environments and generated reports.
.env
.env.*
!.env.example
.coverage
coverage.xml
htmlcov/
*.tmp
*.bak
*.log
"""


class CleanupError(RuntimeError):
    """Raised when clean-main release normalization cannot proceed safely."""


def _read(path: Path) -> str:
    if not path.is_file():
        raise CleanupError(f"required file missing: {path}")
    return path.read_text(encoding="utf-8")


def _newline(path: Path) -> str:
    if not path.exists():
        return "\n"
    return "\r\n" if b"\r\n" in path.read_bytes() else "\n"


def _write(path: Path, text: str) -> None:
    newline = _newline(path)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized.replace("\n", newline).encode("utf-8"))


def _run(
    root: Path,
    cmd: list[str],
    env: dict[str, str] | None = None,
    *,
    check: bool = False,
) -> dict[str, Any]:
    cp = subprocess.run(
        cmd,
        cwd=root,
        text=True,
        capture_output=True,
        env=env,
    )
    result = {
        "command": cmd,
        "returncode": cp.returncode,
        "ok": cp.returncode == 0,
        "stdout": cp.stdout[-24000:],
        "stderr": cp.stderr[-12000:],
    }
    if check and cp.returncode != 0:
        raise CleanupError(
            f"command failed ({cp.returncode}): {' '.join(cmd)}\n{cp.stderr or cp.stdout}"
        )
    return result


def _git(root: Path, *args: str, check: bool = True) -> dict[str, Any]:
    return _run(root, ["git", *args], check=check)


def _preflight(root: Path) -> dict[str, Any]:
    version = _read(root / "VERSION").strip()
    if version != VERSION:
        raise CleanupError(f"cleanup requires VERSION={VERSION}; found {version!r}")
    if "CURRENT_SCHEMA_VERSION = 49" not in _read(
        root / ".agents/agentos/schema_version.py"
    ):
        raise CleanupError("cleanup requires schema marker 49")
    policy = json.loads(_read(root / ".agents/config/governance.json"))
    if policy.get("version") != VERSION:
        raise CleanupError("governance version must be 0.24.2")
    if int((policy.get("documentation_policy") or {}).get("current_schema", -1)) != SCHEMA:
        raise CleanupError("governance documentation schema must be 49")
    if not (root / ".git").exists():
        raise CleanupError("cleanup requires the local Git working tree")
    git_root = _git(root, "rev-parse", "--show-toplevel")["stdout"].strip()
    if Path(git_root).resolve() != root:
        raise CleanupError(f"run cleanup at git root; detected {git_root}")
    for rel in (
        ".agents/agentos/release_integrity.py",
        ".agents/agentos/release_manifest.py",
        ".agents/tests/test_agentos.py",
        ".agents/tests/test_db_aware_context_projection_v0242.py",
        "tools/build_manifest.py",
    ):
        if not (root / rel).is_file():
            raise CleanupError(f"required v0.24.2 file missing: {rel}")
    return {
        "version": version,
        "schema": SCHEMA,
        "branch": _git(root, "branch", "--show-current", check=False)["stdout"].strip(),
        "git_status_before": _git(root, "status", "--short", check=False)["stdout"],
    }


def _archive_home(root: Path) -> Path:
    override = os.environ.get("AGENTOS_RELEASE_ARCHIVE_HOME", "").strip()
    base = (
        Path(override).expanduser().resolve()
        if override
        else (root.parent / ".agentos-release-archive").resolve()
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base / root.name / f"v0.24.2-{stamp}"


def _all_candidates(root: Path) -> list[Path]:
    candidates: set[Path] = set()

    for glob in ROOT_ARCHIVE_GLOBS:
        candidates.update(p for p in root.glob(glob) if p.is_file())

    tools = root / "tools"
    if tools.is_dir():
        for p in tools.glob("apply_v*.py"):
            candidates.add(p)
        for p in tools.glob("validate_v*.py"):
            candidates.add(p)
        for p in tools.glob("*hotfix*.py"):
            candidates.add(p)
        for p in tools.glob("*finaliz*.py"):
            candidates.add(p)
        for p in tools.glob("*recover*.py"):
            candidates.add(p)

    # Current upgrade/validator are Release assets too; main keeps generic tools only.
    for p in list(candidates):
        if p.parent == tools and p.name in GENERIC_TOOLS:
            candidates.discard(p)

    for glob in DOC_ARCHIVE_GLOBS:
        candidates.update(p for p in root.glob(glob) if p.is_file())

    docs_archive = root / ".agents/docs/archive"
    if docs_archive.exists():
        candidates.update(p for p in docs_archive.rglob("*") if p.is_file())

    bindir = root / ".agents/bin"
    if bindir.is_dir():
        candidates.update(p for p in bindir.glob("agentos.v*") if p.is_file())
        candidates.update(p for p in bindir.glob("agentos-mcp.v*") if p.is_file())

    # Keep only the direct upgrade guide to current release.
    for p in root.glob("UPGRADE_FROM_*.md"):
        if p.name != LATEST_UPGRADE_GUIDE:
            candidates.add(p)

    # Never archive current source metadata.
    protected = {
        root / "RELEASE_NOTES.md",
        root / "CHANGELOG.md",
        root / "MANIFEST.json",
        root / "CHECKSUMS.sha256",
        root / LATEST_UPGRADE_GUIDE,
    }
    candidates.difference_update(protected)
    return sorted(candidates)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _archive_candidates(
    root: Path,
    archive: Path,
    candidates: Iterable[Path],
    dry_run: bool,
) -> list[dict[str, Any]]:
    reports = []
    history = archive / "repository-history"
    current_assets = archive / "release-assets" / VERSION

    for src in candidates:
        rel = _relative(root, src)
        # Current v0.24.2 updater/validator are staged as release assets.
        if rel in {"tools/apply_v0242.py", "tools/validate_v0242.py"}:
            dst = current_assets / src.name
        else:
            dst = history / rel
        reports.append({"path": rel, "archive_to": str(dst)})
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    return reports


def _tuple_assignment(
    path: Path, name: str
) -> tuple[list[str], ast.Assign]:
    text = _read(path)
    tree = ast.parse(text)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, tuple):
            raise CleanupError(f"{name} must be a tuple in {path}")
        return [str(x) for x in value], node
    raise CleanupError(f"{name} assignment not found in {path}")


def _rewrite_tuple(path: Path, name: str, values: list[str]) -> None:
    text = _read(path)
    tree = ast.parse(text)
    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            target = node
            break
    if target is None or target.end_lineno is None:
        raise CleanupError(f"cannot locate tuple assignment {name} in {path}")
    lines = text.splitlines(keepends=True)
    replacement = [f"{name} = (\n"]
    replacement.extend(f'    "{value}",\n' for value in values)
    replacement.append(")\n")
    lines[target.lineno - 1 : target.end_lineno] = replacement
    _write(path, "".join(lines))


def _clean_release_files(existing: list[str], root: Path) -> list[str]:
    kept: list[str] = []
    for rel in existing:
        if rel.startswith("tools/apply_v") or rel.startswith("tools/validate_v"):
            continue
        if rel.startswith("UPGRADE_FROM_"):
            continue
        if rel.startswith(".agents/docs/USAGE_V"):
            continue
        if "RELEASE_NOTES_V" in rel or "GITHUB_READY_FULL_RELEASE_V" in rel:
            continue
        if rel.startswith(".agents/bin/agentos.v") or rel.startswith(
            ".agents/bin/agentos-mcp.v"
        ):
            continue
        # Keep historical regression tests, generic tools, workflow and runtime-required artifacts.
        if rel.startswith(".agents/tests/"):
            kept.append(rel)
        elif rel.startswith(".github/workflows/"):
            kept.append(rel)
        elif rel in {
            "tools/build_manifest.py",
            "tools/verify_manifest.py",
            "tools/validate_release.py",
        }:
            kept.append(rel)
        elif rel.endswith("_BENCHMARK.json") or rel in {
            "PERFORMANCE_BASELINE_V0233.json",
            "INDEX_INCREMENTAL_BENCHMARK_V0234.json",
            "ADAPTIVE_TOKEN_BUDGET_BENCHMARK.json",
        }:
            kept.append(rel)

    additions = [
        ".agents/bin/hooks/pre-commit",
        "tools/build_manifest.py",
        "tools/verify_manifest.py",
        "tools/validate_release.py",
        "tools/repository_release_cleanup.py",
        ".agents/tests/test_agentos.py",
        ".agents/tests/test_db_aware_context_projection_v0242.py",
        ".github/workflows/agentos-release-validation.yml",
        "RELEASE_NOTES.md",
        LATEST_UPGRADE_GUIDE,
    ]
    for rel in additions:
        if (root / rel).is_file() and rel not in kept:
            kept.append(rel)
    return sorted(dict.fromkeys(kept))


def _clean_doc_files(existing: list[str], root: Path) -> list[str]:
    kept: list[str] = []
    for rel in existing:
        if rel.startswith("tools/") or rel.startswith(".agents/tests/"):
            continue
        if rel.startswith("UPGRADE_FROM_"):
            continue
        if "RELEASE_NOTES_V" in rel or "GITHUB_READY_FULL_RELEASE_V" in rel:
            continue
        if rel.startswith(".agents/docs/USAGE_V"):
            continue
        if rel.startswith(".agents/docs/archive/"):
            continue
        if (root / rel).is_file():
            kept.append(rel)

    additions = [
        "README.md",
        "README.vi.md",
        "README.en.md",
        "huong_dan.md",
        "huong_dan.vi.md",
        "huong_dan.en.md",
        "CHANGELOG.md",
        "RELEASE_NOTES.md",
        LATEST_UPGRADE_GUIDE,
        ".agents/docs/PROJECT_STRUCTURE.md",
        ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
        ".agents/docs/REPOSITORY_RELEASE_POLICY.md",
        ".agents/docs/RISK_TIERED_BATCH_REVIEW_V0241.md",
        ".agents/docs/DB_AWARE_CONTEXT_PROJECTION_V0242.md",
    ]
    for rel in additions:
        if (root / rel).is_file() and rel not in kept:
            kept.append(rel)
    return sorted(dict.fromkeys(kept))


def _patch_release_integrity(root: Path) -> dict[str, Any]:
    path = root / ".agents/agentos/release_integrity.py"
    release_files, _ = _tuple_assignment(path, "RELEASE_FILES")
    doc_files, _ = _tuple_assignment(path, "DOC_FILES")
    new_release = _clean_release_files(release_files, root)
    new_docs = _clean_doc_files(doc_files, root)

    _rewrite_tuple(path, "RELEASE_FILES", new_release)
    _rewrite_tuple(path, "DOC_FILES", new_docs)

    text = _read(path)

    # Current release assertions stay current after historical packaging files are removed.
    text = re.sub(
        r'if version != "[0-9.]+"',
        f'if version != "{VERSION}"',
        text,
        count=1,
    )
    text = re.sub(
        r'expected VERSION [0-9.]+',
        f'expected VERSION {VERSION}',
        text,
        count=1,
    )
    text = re.sub(
        r'policy\.get\("version"\) != "[0-9.]+"',
        f'policy.get("version") != "{VERSION}"',
        text,
        count=1,
    )
    text = re.sub(
        r'governance\.json version must be [0-9.]+',
        f'governance.json version must be {VERSION}',
        text,
        count=1,
    )

    # Versioned compatibility launchers are release history, not current main requirements.
    start_marker = '    for rel, forbidden in ((".agents/bin/agentos.v0195"'
    start = text.find(start_marker)
    end = text.find("    runtime_wrappers = {", start if start >= 0 else 0)
    if start >= 0 and end > start:
        replacement = (
            '    legacy_launchers = sorted(\n'
            '        p.relative_to(root).as_posix()\n'
            '        for pattern in (".agents/bin/agentos.v*", ".agents/bin/agentos-mcp.v*")\n'
            '        for p in root.glob(pattern)\n'
            '        if p.is_file()\n'
            '    )\n'
            '    if legacy_launchers:\n'
            '        findings.append(_finding(\n'
            '            "legacy_versioned_launcher_present",\n'
            '            f"versioned compatibility launchers belong in Git tags/releases: {legacy_launchers}",\n'
            '        ))\n'
        )
        text = text[:start] + replacement + text[end:]

    # Add a clean-main clutter gate immediately before MANIFEST inspection.
    clutter_marker = "    # Clean-main release packaging gate."
    if clutter_marker not in text:
        anchor = '    manifest_path = root / "MANIFEST.json"\n'
        if anchor not in text:
            raise CleanupError("release_integrity manifest anchor missing")
        glob_literal = repr(RELEASE_CLUTTER_GLOBS)
        block = (
            f"{clutter_marker}\n"
            f"    release_clutter_globs = {glob_literal}\n"
            "    release_clutter = sorted({\n"
            "        p.relative_to(root).as_posix()\n"
            "        for pattern in release_clutter_globs\n"
            "        for p in root.glob(pattern)\n"
            "        if p.is_file()\n"
            "    })\n"
            "    if release_clutter:\n"
            "        findings.append(_finding(\n"
            '            "release_clutter_present",\n'
            '            f"historical release packaging files must not be present on main: {release_clutter[:50]}",\n'
            "        ))\n"
        )
        text = text.replace(anchor, block + anchor, 1)

    text = re.sub(
        r"Older node-specific docs checks intentionally validate their historical release\n"
        r"\s*numbers and therefore cannot be chained as the current-release gate\. v[0-9.]+\n"
        r"\s*validates their authoritative documents are present, while the core docs checker\n"
        r"\s*validates the current VERSION/governance/package synchronization\.",
        "Historical regression tests keep their version-specific assertions, while this\\n"
        "    current-release gate validates only authoritative current docs plus clean-main\\n"
        "    release integrity.",
        text,
        count=1,
    )

    _write(path, text)
    return {
        "release_files_before": len(release_files),
        "release_files_after": len(new_release),
        "doc_files_before": len(doc_files),
        "doc_files_after": len(new_docs),
    }


def _patch_release_manifest(root: Path) -> dict[str, Any]:
    path = root / ".agents/agentos/release_manifest.py"
    text = _read(path)

    if "import fnmatch" not in text:
        text = text.replace("import hashlib\n", "import hashlib\nimport fnmatch\n", 1)

    old_prefix = (
        'EXCLUDE_PREFIXES = (".git/", ".agents/runtime/", ".agents/state/", '
        '".agents/cache/", ".pytest_cache/")'
    )
    new_prefix = (
        'EXCLUDE_PREFIXES = (".git/", ".agents/runtime/", ".agents/state/", '
        '".agents/cache/", ".pytest_cache/", ".vscode/", ".idea/")'
    )
    if old_prefix in text:
        text = text.replace(old_prefix, new_prefix, 1)

    marker = "EXCLUDE_GLOBS = ("
    if marker not in text:
        anchor = 'EXCLUDE_PARTS = {"__pycache__"}\n'
        if anchor not in text:
            raise CleanupError("release_manifest exclusion anchor missing")
        glob_lines = "".join(f'    "{g}",\n' for g in MANIFEST_LOCAL_ONLY_GLOBS)
        extra = (
            anchor
            + "EXCLUDE_GLOBS = (\n"
            + glob_lines
            + ")\n\n"
            + "def _excluded_local_release_artifact(rel: str) -> bool:\n"
            + "    return any(fnmatch.fnmatch(rel, pattern) for pattern in EXCLUDE_GLOBS)\n"
        )
        text = text.replace(anchor, extra, 1)

    old = (
        "        if any(part in EXCLUDE_PARTS for part in path.relative_to(root).parts) "
        'or rel.endswith(".pyc"):\n'
        "            continue\n"
        "        out.add(rel)"
    )
    new = (
        "        if any(part in EXCLUDE_PARTS for part in path.relative_to(root).parts) "
        'or rel.endswith(".pyc"):\n'
        "            continue\n"
        "        if _excluded_local_release_artifact(rel):\n"
        "            continue\n"
        "        out.add(rel)"
    )
    if "_excluded_local_release_artifact(rel)" not in text:
        if old not in text:
            raise CleanupError("release_manifest candidate filter anchor missing")
        text = text.replace(old, new, 1)

    _write(path, text)
    return {"path": ".agents/agentos/release_manifest.py", "status": "patched"}


def _patch_gitignore(root: Path) -> dict[str, Any]:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "# Generated release / hotfix artifacts" not in text:
        text = text.rstrip() + "\n\n" + GITIGNORE_APPEND.strip() + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        return {"status": "patched"}
    return {"status": "already_applied"}


def _write_policy_doc(root: Path) -> None:
    path = root / ".agents/docs/REPOSITORY_RELEASE_POLICY.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('# v0.24.2 — Repository Release Cleanup Policy\n\n## Mục tiêu\n\n`main` chỉ đại diện cho trạng thái AgentOS mới nhất có thể clone, test và phát hành trực tiếp.\n\nLịch sử phát hành không bị mất: Git commit/tag giữ snapshot source; GitHub Release giữ release notes, updater và checksum theo phiên bản.\n\n## Main phải giữ\n\n- Source runtime hiện tại trong `.agents/agentos/`.\n- Toàn bộ regression tests trong `.agents/tests/`.\n- Launcher hiện tại: `agentos`, `agentos.cmd`, `agentos-mcp`, `agentos-mcp.cmd` và hooks.\n- Governance/config và tài liệu kiến trúc còn hiệu lực.\n- `README*`, `huong_dan*`, `CHANGELOG.md`, `RELEASE_NOTES.md`.\n- `UPGRADE_FROM_0.24.1.md` cho bước nâng cấp hiện tại.\n- `MANIFEST.json`, `CHECKSUMS.sha256`.\n- Benchmark/evaluation artifacts vẫn được runtime checker hoặc regression test tham chiếu.\n- Tool generic: `build_manifest.py`, `verify_manifest.py`, `validate_release.py`,\n  `repository_release_cleanup.py`.\n\n## Main không giữ\n\n- `tools/apply_v*.py`, `tools/validate_v*.py`.\n- Recovery/finalizer/hotfix updater theo phiên bản.\n- `RELEASE_NOTES_V*.md`, `USAGE_V*.md`, `GITHUB_READY_FULL_RELEASE_V*.md`.\n- Upgrade guide cũ hơn bước trực tiếp đến current release.\n- Versioned compatibility launchers `.agents/bin/agentos.v*`,\n  `.agents/bin/agentos-mcp.v*`.\n- `VALIDATION_REPORT*.json`, `CHECKSUMS_V*.sha256`, `HOTFIX_INFO.txt`.\n- ZIP/release asset trong repository.\n- `.agents/runtime`, `.agents/state`, `.agents/cache`, test/editor caches.\n\n## GitHub Release\n\nMỗi tag/release nên chứa:\n\n- release notes;\n- updater của chính release (nếu cần);\n- updater checksum;\n- optional validation report;\n- GitHub tự cung cấp source zip/tar.gz.\n\nKhông commit release ZIP vào `main`.\n\n## Regression policy\n\nHistorical regression tests được giữ trên `main` vì chúng là contract bảo vệ backward compatibility.\nHistorical release packaging scripts không phải runtime contract và được archive ngoài repository.\n\n## Local archive\n\nCleanup mặc định lưu file được loại khỏi `main` tại sibling directory:\n\n`.agentos-release-archive/<project-name>/v0.24.2-<timestamp>/`\n\nCó thể override bằng `AGENTOS_RELEASE_ARCHIVE_HOME`.\n\nKhông có file nào thuộc nhóm cleanup bị xóa vĩnh viễn trong quá trình này.\n', encoding="utf-8", newline="\n")


def _write_generic_validator(root: Path) -> None:
    path = root / "tools/validate_release.py"
    path.write_text('#!/usr/bin/env python3\n"""\nFile: tools/validate_release.py\n\nPurpose:\n    Validate the currently materialized AgentOS release without pinning the\n    validator to a historical version number.\n"""\nfrom __future__ import annotations\n\nimport argparse\nimport json\nimport sys\nimport tempfile\nfrom pathlib import Path\n\n\ndef validate(root: Path, *, skip_manifest: bool = False) -> dict[str, object]:\n    root = root.resolve()\n    sys.path.insert(0, str(root / ".agents"))\n\n    from agentos.cli_runtime import command_registry\n    from agentos.core import instruction_check\n    from agentos.db import SCHEMA_VERSION, connect\n    from agentos.mcp_runtime import ALL_TOOLS, VERSION as MCP_VERSION\n    from agentos.policy import load_policy\n    from agentos.release_integrity import check_release_integrity, docs_check_current\n    from agentos.release_manifest import verify_manifest\n\n    version = (root / "VERSION").read_text(encoding="utf-8").strip()\n    policy = load_policy(root)\n    commands = command_registry()\n    tools = [str(item.get("name")) for item in ALL_TOOLS]\n\n    checks: dict[str, bool] = {}\n    checks["version_nonempty"] = bool(version)\n    checks["mcp_version"] = MCP_VERSION == version\n    checks["policy_version"] = policy.get("version") == version\n    checks["policy_schema"] = int(\n        (policy.get("documentation_policy") or {}).get("current_schema", -1)\n    ) == int(SCHEMA_VERSION)\n    checks["cli_unique"] = len(commands) == len(set(commands))\n    checks["mcp_unique"] = len(tools) == len(set(tools))\n    checks["mcp_health"] = "agentos.mcp_health" in tools\n\n    with tempfile.TemporaryDirectory() as td:\n        fresh = Path(td) / "project"\n        (fresh / ".agents").mkdir(parents=True)\n        with connect(fresh) as conn:\n            versions = [\n                int(row[0])\n                for row in conn.execute(\n                    "SELECT version FROM schema_migrations ORDER BY version"\n                )\n            ]\n            foreign_keys = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])\n        checks["migration_chain"] = versions == list(range(1, int(SCHEMA_VERSION) + 1))\n        checks["foreign_keys_on"] = foreign_keys == 1\n\n    integrity = check_release_integrity(root)\n    docs = docs_check_current(root)\n    instructions = instruction_check(root)\n    checks["release_integrity"] = integrity.get("ok") is True\n    checks["docs_check"] = docs.get("ok") is True\n    checks["instruction_check"] = instructions.get("ok") is True\n\n    manifest = None\n    if not skip_manifest:\n        manifest = verify_manifest(root)\n        checks["manifest"] = (\n            manifest.get("ok") is True and manifest.get("release") == version\n        )\n\n    return {\n        "ok": all(checks.values()),\n        "version": version,\n        "schema": int(SCHEMA_VERSION),\n        "mcp_version": MCP_VERSION,\n        "cli_count": len(commands),\n        "mcp_count": len(tools),\n        "checks": checks,\n        "release_integrity": integrity,\n        "docs_check": docs,\n        "instruction_check": instructions,\n        "manifest": manifest,\n    }\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser()\n    parser.add_argument("root", nargs="?", default=".")\n    parser.add_argument("--skip-manifest", action="store_true")\n    args = parser.parse_args()\n    result = validate(Path(args.root), skip_manifest=args.skip_manifest)\n    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))\n    return 0 if result["ok"] else 2\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n', encoding="utf-8", newline="\n")


def _install_self(root: Path) -> None:
    src = Path(__file__).resolve()
    dst = root / "tools/repository_release_cleanup.py"
    if src != dst:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _patch_release_docs(root: Path) -> list[dict[str, Any]]:
    reports = []

    readme = root / "README.md"
    if readme.is_file():
        text = _read(readme)
        marker = "Repository release policy"
        if marker not in text:
            text = text.rstrip() + (
                "\n\n## Repository release policy\n\n"
                "`main` contains the latest runnable source, regression tests and current docs. "
                "Versioned updater/recovery artifacts belong to Git tags/GitHub Releases. "
                "See `.agents/docs/REPOSITORY_RELEASE_POLICY.md`.\n"
            )
            _write(readme, text)
            reports.append({"path": "README.md", "status": "patched"})

    notes = root / "RELEASE_NOTES.md"
    if notes.is_file():
        text = _read(notes)
        marker = "Repository Release Cleanup"
        if marker not in text:
            text = text.rstrip() + (
                "\n\n## Repository Release Cleanup\n\n"
                "- `main` now represents only the latest runnable AgentOS package.\n"
                "- Historical versioned updater/validator/release packaging files are staged outside "
                "the repository for GitHub Release assets.\n"
                "- Historical regression tests remain on `main` as compatibility contracts.\n"
                "- Runtime/state/cache and editor/test caches remain local-only.\n"
            )
            _write(notes, text)
            reports.append({"path": "RELEASE_NOTES.md", "status": "patched"})

    changelog = root / "CHANGELOG.md"
    if changelog.is_file():
        text = _read(changelog)
        marker = "Repository release cleanup"
        if marker not in text:
            line = (
                "- Repository release cleanup: clean-main packaging, external release archive, "
                "generic current-release validator, and runtime/state/cache Git isolation.\n"
            )
            # Put under current v0.24.2 entry if possible, otherwise top.
            match = re.search(r"(?m)^##\s+0\.24\.2[^\n]*\n", text)
            if match:
                text = text[: match.end()] + line + text[match.end() :]
            else:
                text = line + text
            _write(changelog, text)
            reports.append({"path": "CHANGELOG.md", "status": "patched"})
    return reports


def _git_untrack_local_state(root: Path, dry_run: bool) -> list[dict[str, Any]]:
    targets = [
        ".agents/state",
        ".agents/runtime",
        ".agents/cache",
        ".pytest_cache",
        ".vscode",
        ".idea",
    ]
    reports = []
    for rel in targets:
        tracked = _git(
            root, "ls-files", "--", rel, check=False
        )["stdout"].splitlines()
        if tracked:
            reports.append({"path": rel, "tracked_entries": len(tracked)})
            if not dry_run:
                _git(root, "rm", "-r", "--cached", "--ignore-unmatch", "--", rel)
    if not dry_run:
        for rel in (".agents/state", ".agents/runtime", ".agents/cache"):
            directory = root / rel
            directory.mkdir(parents=True, exist_ok=True)
            keep = directory / ".gitkeep"
            if not keep.exists():
                keep.write_text("", encoding="utf-8")
            _git(root, "add", "-f", "--", keep.relative_to(root).as_posix())
    return reports


def _assert_no_clutter(root: Path) -> list[str]:
    clutter = set()
    for pattern in RELEASE_CLUTTER_GLOBS:
        for p in root.glob(pattern):
            if p.is_file():
                clutter.add(_relative(root, p))
    return sorted(clutter)


def _stage_release_assets(root: Path, archive: Path) -> dict[str, Any]:
    assets = archive / "release-assets" / VERSION
    assets.mkdir(parents=True, exist_ok=True)

    for rel in ("RELEASE_NOTES.md", LATEST_UPGRADE_GUIDE, "VERSION", "CHECKSUMS.sha256"):
        src = root / rel
        if src.is_file():
            shutil.copy2(src, assets / src.name)

    checksums = []
    for p in sorted(assets.iterdir()):
        if not p.is_file() or p.name == "SHA256SUMS.txt":
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {p.name}\n")
    (assets / "SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")
    return {
        "path": str(assets),
        "files": sorted(p.name for p in assets.iterdir() if p.is_file()),
    }


def _compile_changed(root: Path) -> list[str]:
    files = [
        ".agents/agentos/release_integrity.py",
        ".agents/agentos/release_manifest.py",
        "tools/validate_release.py",
        "tools/repository_release_cleanup.py",
    ]
    for rel in files:
        py_compile.compile(str(root / rel), doraise=True)
    return files


def _env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / ".agents") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return env


def cleanup(
    root: Path,
    *,
    dry_run: bool = False,
    run_full_tests: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    preflight = _preflight(root)
    archive = _archive_home(root)
    candidates = _all_candidates(root)

    plan = {
        "archive_root": str(archive),
        "candidate_count": len(candidates),
        "candidates": [_relative(root, p) for p in candidates],
    }
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "cleanup": CLEANUP_ID,
            "preflight": preflight,
            "plan": plan,
        }

    # Snapshot every file that will be edited, in the same external archive.
    source_backup = archive / "pre-cleanup-source"
    for rel in (
        ".gitignore",
        ".agents/agentos/release_integrity.py",
        ".agents/agentos/release_manifest.py",
        "tools/validate_release.py",
        "README.md",
        "RELEASE_NOTES.md",
        "CHANGELOG.md",
        "MANIFEST.json",
        "CHECKSUMS.sha256",
    ):
        src = root / rel
        if src.is_file():
            dst = source_backup / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Install clean-main source policy first.
    _install_self(root)
    _write_policy_doc(root)
    _write_generic_validator(root)
    gitignore = _patch_gitignore(root)
    manifest_patch = _patch_release_manifest(root)
    docs = _patch_release_docs(root)

    # Archive release-history packaging before release-integrity is rewritten.
    archived = _archive_candidates(root, archive, candidates, False)

    integrity_patch = _patch_release_integrity(root)
    untracked = _git_untrack_local_state(root, False)

    clutter = _assert_no_clutter(root)
    if clutter:
        raise CleanupError(f"release clutter remains after cleanup: {clutter[:50]}")

    compiled = _compile_changed(root)
    env = _env(root)

    # Build authoritative package after cleanup before any docs/integrity tests.
    build = _run(root, [sys.executable, "tools/build_manifest.py", str(root)], env)
    if not build["ok"]:
        raise CleanupError(f"manifest build failed: {build['stderr'] or build['stdout']}")

    verify = _run(root, [sys.executable, "tools/verify_manifest.py", str(root)], env)
    if not verify["ok"]:
        raise CleanupError(f"manifest verify failed: {verify['stderr'] or verify['stdout']}")

    targeted = _run(
        root,
        [
            sys.executable, "-m", "pytest", "-q",
            ".agents/tests/test_agentos.py",
            ".agents/tests/test_core_reintegration_v0223.py",
            ".agents/tests/test_governance_enforcement_v0224.py",
            ".agents/tests/test_db_aware_context_projection_v0242.py",
            "-rs",
        ],
        env,
    )
    if not targeted["ok"]:
        return {
            "ok": False,
            "error": "targeted_cleanup_regression_failed",
            "archive_root": str(archive),
            "targeted_tests": targeted,
            "git_status": _git(root, "status", "--short", check=False)["stdout"],
        }

    full = None
    if run_full_tests:
        full = _run(
            root,
            [sys.executable, "-m", "pytest", "-q", ".agents/tests", "-rs"],
            env,
        )
        if not full["ok"]:
            return {
                "ok": False,
                "error": "full_cleanup_regression_failed",
                "archive_root": str(archive),
                "targeted_tests": targeted,
                "full_tests": full,
                "git_status": _git(root, "status", "--short", check=False)["stdout"],
            }

    # Tests may generate ignored runtime state; manifest remains source-only.
    build_final = _run(
        root, [sys.executable, "tools/build_manifest.py", str(root)], env
    )
    if not build_final["ok"]:
        raise CleanupError("final manifest build failed")

    validate = _run(
        root, [sys.executable, "tools/validate_release.py", str(root)], env
    )
    if not validate["ok"]:
        return {
            "ok": False,
            "error": "generic_release_validation_failed",
            "validation": validate,
            "archive_root": str(archive),
        }

    integrity = _run(
        root,
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from agentos.release_integrity import check_release_integrity, docs_check_current; "
                "import json; "
                "i=check_release_integrity(Path.cwd()); d=docs_check_current(Path.cwd()); "
                "print(json.dumps({'integrity':i,'docs':d},ensure_ascii=False,indent=2)); "
                "raise SystemExit(0 if i.get('ok') and d.get('ok') else 2)"
            ),
        ],
        env,
    )
    if not integrity["ok"]:
        return {
            "ok": False,
            "error": "release_integrity_or_docs_failed",
            "integrity": integrity,
            "archive_root": str(archive),
        }

    assets = _stage_release_assets(root, archive)
    report = {
        "ok": True,
        "cleanup": CLEANUP_ID,
        "version": VERSION,
        "schema": SCHEMA,
        "archive_root": str(archive),
        "release_assets": assets,
        "candidate_count": len(candidates),
        "archived": archived,
        "release_integrity_patch": integrity_patch,
        "release_manifest_patch": manifest_patch,
        "gitignore": gitignore,
        "docs": docs,
        "untracked_local_state": untracked,
        "compiled": compiled,
        "targeted_tests": targeted,
        "full_tests": full,
        "manifest_verify": verify,
        "validation": validate,
        "integrity": integrity,
        "git_status_after": _git(root, "status", "--short", check=False)["stdout"],
    }
    (archive / "REPOSITORY_CLEANUP_REPORT_V0242.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-full-tests", action="store_true")
    args = parser.parse_args()
    try:
        result = cleanup(
            Path(args.root),
            dry_run=args.dry_run,
            run_full_tests=not args.no_full_tests,
        )
    except Exception as exc:
        result = {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "root": str(Path(args.root).resolve()),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
