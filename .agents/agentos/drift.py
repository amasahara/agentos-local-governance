"""
File: .agents/agentos/drift.py

Purpose:
    Detect and gate unacknowledged governance changes.

Responsibilities:
    - Track governance files recursively.
    - Distinguish uninitialized baselines from real drift.
    - Require interactive acknowledgement by default.
    - Expose drift state to the final report gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .db import connect
from .policy import load_policy


def tracked_files(root: Path) -> list[str]:
    """Return governance files selected by structured drift policy."""
    policy = load_policy(root).get("drift_policy", {})
    patterns = policy.get("tracked_paths") or ["AGENTS.md", "README.md", "huong_dan.md", "VERSION", ".agents/config/**/*.json", ".agents/agentos/**/*.py", ".agents/bin/**", ".agents/docs/**/*.md"]
    excluded = policy.get("excluded_paths", [])
    required = {"AGENTS.md", "VERSION", ".agents/config/governance.json", ".agents/agentos/policy.py", ".agents/agentos/drift.py", ".agents/agentos/proxy.py"}
    found: set[str] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                if not any(path.match(item) or Path(rel).match(item) for item in excluded):
                    found.add(rel)
    for rel in required:
        if (root / rel).exists():
            found.add(rel)
    return sorted(found)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def ack_baseline(root: Path, identity: str | None = None, method: str = "interactive_human", force_noninteractive: bool = False, session_id: str | None = None) -> dict[str, Any]:
    """Acknowledge governance content after explicit review.

    Args:
        root: Project root.
        identity: Human identity; defaults to AGENTOS_HUMAN_ID or OS user.
        method: Acknowledgement method.
        force_noninteractive: Permit non-TTY acknowledgement with machine label.
        session_id: Optional session identifier.

    Returns:
        Baseline summary.
    """
    if method == "interactive_human" and not sys.stdin.isatty() and not force_noninteractive:
        raise RuntimeError("ack-baseline requires an interactive TTY; use --force-noninteractive only for explicitly configured machine acknowledgement")
    if force_noninteractive and method == "interactive_human":
        method = "ci_machine"
    actor = identity or os.environ.get("AGENTOS_HUMAN_ID") or os.environ.get("USER") or "unknown"
    commit = _git_commit(root)
    files = tracked_files(root)
    with connect(root) as c:
        for rel in files:
            path = root / rel
            if path.exists():
                c.execute("INSERT INTO governance_baseline(file_path,content_hash,acknowledged_by,git_commit,acknowledgement_method,session_id) VALUES(?,?,?,?,?,?)", (rel, _hash(path), actor, commit, method, session_id))
        c.execute("UPDATE governance_change_log SET acknowledged=1 WHERE acknowledged=0")
    return {"ok": True, "acknowledged_files": files, "acknowledged_by": actor, "acknowledgement_method": method, "git_commit": commit}


def drift_check(root: Path, detected_by: str = "agentos_cli", task_id: str | None = None) -> dict[str, Any]:
    """Compare governance files with the latest acknowledged baseline."""
    changes: list[dict[str, Any]] = []
    files = tracked_files(root)
    with connect(root) as c:
        baseline_count = c.execute("SELECT COUNT(*) AS n FROM governance_baseline").fetchone()["n"]
        if baseline_count == 0:
            return {"ok": False, "baseline_state": "not_initialized", "review_required": True, "drift_detected": False, "changes": [], "message": "Governance baseline has not been acknowledged."}
        for rel in files:
            path = root / rel
            if not path.exists():
                continue
            current = _hash(path)
            row = c.execute("SELECT content_hash FROM governance_baseline WHERE file_path=? ORDER BY id DESC LIMIT 1", (rel,)).fetchone()
            baseline = row["content_hash"] if row else None
            if baseline != current:
                existing = c.execute("SELECT id FROM governance_change_log WHERE file_path=? AND new_hash=? AND acknowledged=0", (rel, current)).fetchone()
                if not existing:
                    c.execute("INSERT INTO governance_change_log(file_path,old_hash,new_hash,detected_by,task_id) VALUES(?,?,?,?,?)", (rel, baseline, current, detected_by, task_id))
                changes.append({"file_path": rel, "baseline_hash": baseline, "current_hash": current, "acknowledged": False})
    return {"ok": not changes, "baseline_state": "initialized", "review_required": bool(changes), "drift_detected": bool(changes), "changes": changes, "message": "Governance drift detected." if changes else "No unacknowledged governance drift."}


def drift_diff(root: Path, file_path: str) -> dict[str, Any]:
    """Return a bounded diff or current content for one tracked file."""
    if file_path not in tracked_files(root):
        raise RuntimeError("file is not tracked by drift policy")
    path = root / file_path
    try:
        proc = subprocess.run(["git", "diff", "--", file_path], cwd=root, text=True, capture_output=True, check=True)
        return {"file_path": file_path, "mode": "git_diff", "content": proc.stdout[:20000]}
    except (OSError, subprocess.CalledProcessError):
        return {"file_path": file_path, "mode": "full_current_content", "content": path.read_text(encoding="utf-8")[:20000]}
