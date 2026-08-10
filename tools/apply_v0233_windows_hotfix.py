#!/usr/bin/env python3
"""
File: tools/apply_v0233_windows_hotfix.py

Purpose:
    Apply the AgentOS v0.23.3 Windows Portability Hotfix as one idempotent,
    fail-closed update and optionally run the focused seven-suite regression.

Responsibilities:
    - Require an AgentOS v0.23.3 target root.
    - Back up every file before the first modification.
    - Patch binary/hash handling, Windows CLI invocation, symlink-test capability
      handling, POSIX-only mode-bit assertions, and long atomic temporary names.
    - Refuse to patch when expected source contracts are not present.
    - Compile patched Python files before reporting success.
    - Optionally run the seven focused regression suites with PYTHONPATH set.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
from typing import Iterable

HOTFIX_ID = "v0.23.3-windows-portability-hotfix-1"
REQUIRED_VERSION = "0.23.3"

TARGETED_TESTS = [
    ".agents/tests/test_secret_lineage_v0226.py",
    ".agents/tests/test_identity_resolution_v0221.py",
    ".agents/tests/test_controlled_target_insert_v0220.py",
    ".agents/tests/test_reconciliation_recovery_v0222.py",
    ".agents/tests/test_core_reintegration_v0223.py",
    ".agents/tests/test_governance_enforcement_v0224.py",
    ".agents/tests/test_project_consolidation_v0202.py",
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_root(root: Path) -> None:
    version_file = root / "VERSION"
    if not version_file.is_file():
        raise RuntimeError("VERSION missing")
    version = version_file.read_text(encoding="utf-8").strip()
    if version != REQUIRED_VERSION:
        raise RuntimeError(f"hotfix requires VERSION={REQUIRED_VERSION}; found {version!r}")
    required = [
        ".agents/agentos/identity_resolution.py",
        ".agents/agentos/secret_lineage.py",
        ".agents/agentos/project_consolidation.py",
        ".agents/agentos/skills.py",
        ".agents/tests/test_core_reintegration_v0223.py",
        ".agents/tests/test_governance_enforcement_v0224.py",
        ".agents/tests/test_project_consolidation_v0202.py",
        ".agents/tests/test_secret_lineage_v0226.py",
        ".agents/tests/test_identity_resolution_v0221.py",
        ".agents/tests/test_read_only_extraction_v0212.py",
        ".agents/tests/test_agentos.py",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    if missing:
        raise RuntimeError("required hotfix files missing: " + ", ".join(missing))


def _replace_contract(text: str, old: str, new: str, *, label: str) -> tuple[str, str]:
    if new in text:
        return text, "already_applied"
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected source contract exactly once; found {count}")
    return text.replace(old, new, 1), "patched"


def _patch_file(root: Path, rel: str, replacements: Iterable[tuple[str, str, str]], backup_root: Path, dry_run: bool) -> dict:
    path = root / rel
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    original = raw.decode("utf-8").replace("\r\n", "\n")
    text = original
    statuses: list[dict[str, str]] = []
    for label, old, new in replacements:
        text, status = _replace_contract(text, old, new, label=f"{rel}:{label}")
        statuses.append({"patch": label, "status": status})
    changed = text != original
    result = {
        "path": rel,
        "changed": changed,
        "before_sha256": _sha256(path),
        "patches": statuses,
    }
    if changed and not dry_run:
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        serialized = text.replace("\n", newline).encode("utf-8")
        path.write_bytes(serialized)
        result["after_sha256"] = _sha256(path)
        result["backup"] = str(backup.relative_to(root)).replace("\\", "/")
    elif not changed:
        result["after_sha256"] = result["before_sha256"]
    return result


def _patches() -> dict[str, list[tuple[str, str, str]]]:
    identity_old = '''def _write_atomic(path: Path, data: bytes) -> str:\n    """Atomically write an owner-only local identity artifact and return SHA-256."""\n    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)\n    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n    try:\n        os.write(fd, data)\n        os.fsync(fd)\n    finally:\n        os.close(fd)\n    os.replace(tmp, path)\n    try:\n        path.chmod(0o600)\n    except OSError:\n        pass\n    return hashlib.sha256(data).hexdigest()\n'''
    identity_new = '''def _write_atomic(path: Path, data: bytes) -> str:\n    """Atomically write exact binary bytes and verify the persisted SHA-256."""\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_name(f".aos-{uuid.uuid4().hex[:12]}.tmp")\n    expected_hash = hashlib.sha256(data).hexdigest()\n    try:\n        with tmp.open("xb") as handle:\n            handle.write(data)\n            handle.flush()\n            os.fsync(handle.fileno())\n        os.replace(tmp, path)\n    finally:\n        if tmp.exists():\n            tmp.unlink()\n    try:\n        path.chmod(0o600)\n    except OSError:\n        pass\n    persisted_hash = _sha256_file(path)\n    if persisted_hash != expected_hash:\n        raise IdentityResolutionError("identity artifact bytes changed during persistence")\n    return persisted_hash\n'''

    key_old = '''def _write_key(path: Path, material: bytes) -> None:\n    """Atomically create a key file with owner-only permissions."""\n    path.parent.mkdir(parents=True, exist_ok=True)\n    try:\n        path.parent.chmod(0o700)\n    except OSError:\n        pass\n    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n    try:\n        os.write(fd, material)\n        os.fsync(fd)\n    finally:\n        os.close(fd)\n'''
    key_new = '''def _write_key(path: Path, material: bytes) -> None:\n    """Create exact binary key material and verify the persisted bytes."""\n    path.parent.mkdir(parents=True, exist_ok=True)\n    try:\n        path.parent.chmod(0o700)\n    except OSError:\n        pass\n    with path.open("xb") as handle:\n        handle.write(material)\n        handle.flush()\n        os.fsync(handle.fileno())\n    try:\n        path.chmod(0o600)\n    except OSError:\n        pass\n    persisted = path.read_bytes()\n    if persisted != material or hashlib.sha256(persisted).digest() != hashlib.sha256(material).digest():\n        try:\n            path.unlink()\n        except OSError:\n            pass\n        raise SecretLineageError("lineage key bytes changed during persistence")\n'''

    skill_old = '''        digest=hashlib.sha256(body.encode()).hexdigest()\n        rel=Path('.agents/runtime/skills/candidates')/f"{key}-v{version}.md"\n        target=root/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(body,encoding='utf-8')\n'''
    skill_new = '''        payload=body.encode("utf-8")\n        digest=hashlib.sha256(payload).hexdigest()\n        rel=Path('.agents/runtime/skills/candidates')/f"{key}-v{version}.md"\n        target=root/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(payload)\n'''

    core_helper_old = '''from agentos.policy import load_policy\n\n\n'''
    core_helper_new = '''from agentos.policy import load_policy\n\n\ndef _agentos_args(root: Path, *args: str) -> list[str]:\n    """Return the native AgentOS launcher command for the current platform."""\n    if os.name == "nt":\n        return [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", str(root / ".agents/bin/agentos.cmd"), *args]\n    return [str(root / ".agents/bin/agentos"), *args]\n\n\n'''

    gov_helper_old = '''from agentos.workflow import complete_automated_step, seed_workflow\n\n'''
    gov_helper_new = '''from agentos.workflow import complete_automated_step, seed_workflow\n\n\ndef _agentos_args(root: Path, *args: str) -> list[str]:\n    """Return the native AgentOS launcher command for the current platform."""\n    if os.name == "nt":\n        return [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", str(root / ".agents/bin/agentos.cmd"), *args]\n    return [str(root / ".agents/bin/agentos"), *args]\n\n'''

    project_helper_old = '''def _digest(path: Path) -> str:\n'''
    project_helper_new = '''def _symlink_or_skip(link: Path, target: Path) -> None:\n    """Create a symlink or skip when Windows has no symlink privilege."""\n    try:\n        link.symlink_to(target)\n    except OSError as exc:\n        if getattr(exc, "winerror", None) == 1314:\n            pytest.skip("Windows symlink privilege is unavailable for this test")\n        raise\n\n\ndef _digest(path: Path) -> str:\n'''

    return {
        ".agents/agentos/identity_resolution.py": [
            ("binary_identity_artifact", identity_old, identity_new),
        ],
        ".agents/agentos/secret_lineage.py": [
            ("binary_lineage_key", key_old, key_new),
        ],
        ".agents/agentos/project_consolidation.py": [
            (
                "short_atomic_temp_name",
                '    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")\n',
                '    tmp = path.with_name(f".aos-{uuid.uuid4().hex[:12]}.tmp")\n',
            ),
        ],
        ".agents/agentos/skills.py": [
            ("canonical_skill_bytes", skill_old, skill_new),
        ],
        ".agents/tests/test_core_reintegration_v0223.py": [
            ("native_cli_helper", core_helper_old, core_helper_new),
            (
                "unknown_command_native_launcher",
                '    cp=subprocess.run([str(ROOT/".agents/bin/agentos"),"definitely-not-an-agentos-command"],cwd=ROOT,capture_output=True,text=True)\n',
                '    cp=subprocess.run(_agentos_args(ROOT,"definitely-not-an-agentos-command"),cwd=ROOT,capture_output=True,text=True)\n',
            ),
            (
                "docs_check_native_launcher",
                '    cp=subprocess.run([str(ROOT/".agents/bin/agentos"),"docs-check"],cwd=ROOT,capture_output=True,text=True)\n',
                '    cp=subprocess.run(_agentos_args(ROOT,"docs-check"),cwd=ROOT,capture_output=True,text=True)\n',
            ),
        ],
        ".agents/tests/test_governance_enforcement_v0224.py": [
            ("native_cli_helper", gov_helper_old, gov_helper_new),
            (
                "privileged_cli_native_launcher",
                '''    cp = subprocess.run([\n        str(root / ".agents/bin/agentos"), "--task-id", "T-GOV", "--session-id", "S-GOV",\n        "db-connection-register", "--alias", "cli-source", "--role", "SOURCE", "--engine", "mssql",\n        "--host", "source.internal", "--database", "HIS", "--domain", "healthcare",\n        "--credential-ref", "env://TEST_SOURCE_DB", "--created-by", "operator",\n    ], cwd=root, text=True, capture_output=True, env=os.environ.copy())\n''',
                '''    cp = subprocess.run(_agentos_args(\n        root, "--task-id", "T-GOV", "--session-id", "S-GOV",\n        "db-connection-register", "--alias", "cli-source", "--role", "SOURCE", "--engine", "mssql",\n        "--host", "source.internal", "--database", "HIS", "--domain", "healthcare",\n        "--credential-ref", "env://TEST_SOURCE_DB", "--created-by", "operator",\n    ), cwd=root, text=True, capture_output=True, env=os.environ.copy())\n''',
            ),
            (
                "missing_context_native_launcher",
                '    cp = subprocess.run([str(root / ".agents/bin/agentos"), "db-connection-register", "--help"], cwd=root, text=True, capture_output=True, env=os.environ.copy())\n',
                '    cp = subprocess.run(_agentos_args(root, "db-connection-register", "--help"), cwd=root, text=True, capture_output=True, env=os.environ.copy())\n',
            ),
        ],
        ".agents/tests/test_project_consolidation_v0202.py": [
            ("symlink_capability_helper", project_helper_old, project_helper_new),
            (
                "source_symlink_capability",
                '    (source / "src/link.py").symlink_to(outside)\n',
                '    _symlink_or_skip(source / "src/link.py", outside)\n',
            ),
            (
                "prepared_symlink_capability",
                '    link.symlink_to(real)\n',
                '    _symlink_or_skip(link, real)\n',
            ),
        ],
        ".agents/tests/test_secret_lineage_v0226.py": [
            (
                "import_os",
                'import json\nfrom pathlib import Path\n',
                'import json\nimport os\nfrom pathlib import Path\n',
            ),
            (
                "posix_mode_only",
                '''    assert resolve_secret(tmp_path,"file-secret://db.json",capability="db.source.select")["user"] == "u"\n    path.chmod(0o644)\n    with pytest.raises(SecretLineageError):\n        resolve_secret(tmp_path,"file-secret://db.json",capability="db.source.select")\n''',
                '''    assert resolve_secret(tmp_path,"file-secret://db.json",capability="db.source.select")["user"] == "u"\n    if os.name == "nt":\n        pytest.skip("POSIX chmod mode-bit enforcement is not a Windows security primitive")\n    path.chmod(0o644)\n    with pytest.raises(SecretLineageError):\n        resolve_secret(tmp_path,"file-secret://db.json",capability="db.source.select")\n''',
            ),
        ],
        ".agents/tests/test_identity_resolution_v0221.py": [
            (
                "posix_lineage_mode_only",
                '    if hasattr(key.stat(), "st_mode"):\n        assert key.stat().st_mode & 0o077 == 0\n',
                '    if os.name != "nt" and hasattr(key.stat(), "st_mode"):\n        assert key.stat().st_mode & 0o077 == 0\n',
            ),
            (
                "import_os",
                'from datetime import datetime\n',
                'from datetime import datetime\nimport os\n',
            ),
        ],
        ".agents/tests/test_read_only_extraction_v0212.py": [
            (
                "posix_artifact_mode_only",
                '''    for key in ["staging_path", "quarantine_path", "manifest_path"]:\n        mode = os.stat(root / summary[key]).st_mode & 0o777\n        assert mode & 0o077 == 0\n    assert verify_staging_artifact(root, batch["id"])["ok"] is True\n''',
                '''    if os.name != "nt":\n        for key in ["staging_path", "quarantine_path", "manifest_path"]:\n            mode = os.stat(root / summary[key]).st_mode & 0o777\n            assert mode & 0o077 == 0\n    assert verify_staging_artifact(root, batch["id"])["ok"] is True\n''',
            ),
        ],
        ".agents/tests/test_agentos.py": [
            (
                "platform_drift_launcher",
                '''def test_drift_detects_runtime_and_hook_changes(tmp_path: Path) -> None:\n    root = project(tmp_path); ack_baseline(root, "ci", force_noninteractive=True)\n    (root / ".agents" / "bin" / "agentos").write_text("changed\\n")\n    result = drift_check(root)\n    assert result["drift_detected"] is True\n    assert any(x["file_path"] == ".agents/bin/agentos" for x in result["changes"])\n''',
                '''def test_drift_detects_runtime_and_hook_changes(tmp_path: Path) -> None:\n    root = project(tmp_path); ack_baseline(root, "ci", force_noninteractive=True)\n    launcher = ".agents/bin/agentos.cmd" if os.name == "nt" else ".agents/bin/agentos"\n    (root / launcher).write_bytes(b"changed\\n")\n    result = drift_check(root)\n    assert result["drift_detected"] is True\n    assert any(x["file_path"] == launcher for x in result["changes"])\n''',
            ),
            (
                "atomic_fixture_hash_disk_bytes",
                '    path = root / "src" / "a.py"; path.write_text("one\\n", encoding="utf-8")\n    old_hash = __import__("hashlib").sha256(b"one\\n").hexdigest()\n',
                '    path = root / "src" / "a.py"; path.write_bytes(b"one\\n")\n    old_hash = __import__("hashlib").sha256(path.read_bytes()).hexdigest()\n',
            ),
        ],
    }


def _compile(root: Path, files: Iterable[str]) -> list[str]:
    compiled: list[str] = []
    for rel in files:
        path = root / rel
        py_compile.compile(str(path), doraise=True)
        compiled.append(rel)
    return compiled


def _run_targeted_tests(root: Path) -> dict:
    env = os.environ.copy()
    agents_path = str((root / ".agents").resolve())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = agents_path + (os.pathsep + existing if existing else "")
    cmd = [sys.executable, "-m", "pytest", "-q", *TARGETED_TESTS]
    completed = subprocess.run(cmd, cwd=root, env=env)
    return {"command": cmd, "returncode": completed.returncode, "ok": completed.returncode == 0}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply AgentOS v0.23.3 Windows Portability Hotfix")
    parser.add_argument("root", nargs="?", default=".", help="AgentOS repository root")
    parser.add_argument("--dry-run", action="store_true", help="Validate patch contracts without modifying files")
    parser.add_argument("--run-tests", action="store_true", help="Run the seven focused regression suites after patching")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report: dict = {"ok": False, "hotfix": HOTFIX_ID, "root": str(root), "dry_run": bool(args.dry_run)}
    try:
        _require_root(root)
        backup_root = root / ".agents/runtime/hotfix-backups" / f"{HOTFIX_ID}-{_utc_stamp()}"
        file_reports = []
        patch_map = _patches()
        for rel, replacements in patch_map.items():
            file_reports.append(_patch_file(root, rel, replacements, backup_root, args.dry_run))
        report["files"] = file_reports
        report["changed_files"] = [item["path"] for item in file_reports if item["changed"]]
        if not args.dry_run:
            report["compiled"] = _compile(root, patch_map.keys())
            marker = root / ".agents/runtime/hotfixes" / f"{HOTFIX_ID}.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({
                "hotfix": HOTFIX_ID,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "changed_files": report["changed_files"],
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["marker"] = str(marker.relative_to(root)).replace("\\", "/")
            if args.run_tests:
                report["targeted_tests"] = _run_targeted_tests(root)
                if not report["targeted_tests"]["ok"]:
                    report["error"] = "targeted_tests_failed"
                    print(json.dumps(report, ensure_ascii=False, indent=2))
                    return int(report["targeted_tests"]["returncode"] or 1)
        report["ok"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        report["error"] = type(exc).__name__
        report["message"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
