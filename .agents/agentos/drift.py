"""
File: .agents/agentos/drift.py

Purpose:
    Detect unacknowledged changes to AgentOS governance files.

Responsibilities:
    - Snapshot governance file hashes.
    - Compare current content to the latest human baseline.
    - Record and expose unacknowledged drift.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .db import connect


def tracked_files(root: Path) -> list[str]:
    """Return all governance files monitored for drift.

    Args:
        root: Project root.

    Returns:
        Sorted project-relative file paths.
    """
    fixed = ["AGENTS.md", ".agents/config/governance.json", "VERSION"]
    modules = [p.relative_to(root).as_posix() for p in (root / ".agents" / "agentos").glob("*.py")]
    local = [".agents/config/governance.local.json"] if (root / ".agents/config/governance.local.json").exists() else []
    return sorted(set(fixed + modules + local))


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def ack_baseline(root: Path, acknowledged_by: str = "human") -> dict[str, Any]:
    """Acknowledge current governance content as the reviewed baseline.

    Args:
        root: Project root.
        acknowledged_by: Human identity label.

    Returns:
        Baseline summary.
    """
    commit = _git_commit(root)
    files = tracked_files(root)
    with connect(root) as c:
        for rel in files:
            path = root / rel
            if path.exists():
                c.execute(
                    "INSERT INTO governance_baseline(file_path,content_hash,acknowledged_by,git_commit) VALUES(?,?,?,?)",
                    (rel, _hash(path), acknowledged_by, commit),
                )
        c.execute("UPDATE governance_change_log SET acknowledged=1 WHERE acknowledged=0")
    return {"ok": True, "acknowledged_files": files, "acknowledged_by": acknowledged_by, "git_commit": commit}


def drift_check(root: Path, detected_by: str = "agentos_cli", task_id: str | None = None) -> dict[str, Any]:
    """Compare governance files to their latest acknowledged hashes.

    Args:
        root: Project root.
        detected_by: Detection source.
        task_id: Optional active task.

    Returns:
        Drift report.
    """
    changes: list[dict[str, Any]] = []
    with connect(root) as c:
        for rel in tracked_files(root):
            path = root / rel
            current = _hash(path) if path.exists() else "<missing>"
            row = c.execute(
                "SELECT content_hash,acknowledged_at,git_commit FROM governance_baseline WHERE file_path=? ORDER BY id DESC LIMIT 1",
                (rel,),
            ).fetchone()
            baseline = row["content_hash"] if row else None
            if baseline != current:
                existing = c.execute(
                    "SELECT id FROM governance_change_log WHERE file_path=? AND old_hash IS ? AND new_hash=? AND acknowledged=0",
                    (rel, baseline, current),
                ).fetchone()
                if not existing:
                    c.execute(
                        "INSERT INTO governance_change_log(file_path,old_hash,new_hash,detected_by,task_id) VALUES(?,?,?,?,?)",
                        (rel, baseline, current, detected_by, task_id),
                    )
                changes.append({"file_path": rel, "baseline_hash": baseline, "current_hash": current, "acknowledged": False, "since": row["acknowledged_at"] if row else None})
    return {"ok": not changes, "drift_detected": bool(changes), "changes": changes, "message": f"{len(changes)} governance file(s) changed since the last acknowledged baseline."}


def drift_diff(root: Path, file_path: str) -> dict[str, Any]:
    """Show a git diff or current content for a drifted governance file.

    Args:
        root: Project root.
        file_path: Tracked project-relative path.

    Returns:
        Diff report.
    """
    if file_path not in tracked_files(root):
        raise RuntimeError("file is not tracked by governance drift policy")
    path = root / file_path
    try:
        result = subprocess.run(["git", "diff", "--", file_path], cwd=root, text=True, capture_output=True, check=True)
        if result.stdout:
            return {"file_path": file_path, "mode": "git_diff", "content": result.stdout}
    except (OSError, subprocess.CalledProcessError):
        pass
    return {"file_path": file_path, "mode": "current_content", "warning": "No git diff is available; showing current content.", "content": path.read_text(encoding="utf-8") if path.exists() else "<missing>"}
