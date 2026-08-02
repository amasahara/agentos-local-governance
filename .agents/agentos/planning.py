"""
File: .agents/agentos/planning.py

Purpose:
    Manage versioned task plans and Git-aware change gates for AgentOS v0.16.1.

Responsibilities:
    - Store immutable plan revisions and approval state.
    - Compare Git changes with approved task scope and plan paths.
    - Produce a pre-commit decision with auditable reasons.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .db import connect
from .external_audit import append_signed_event
from .workflow import workflow_status


def submit_plan(root: Path, task_id: str, session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Persist a new immutable task-plan revision."""
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    with connect(root, immediate=True) as c:
        rev = c.execute("SELECT COALESCE(MAX(revision),0)+1 AS r FROM task_plans WHERE task_id=?", (task_id,)).fetchone()["r"]
        c.execute("UPDATE task_plans SET status='superseded' WHERE task_id=? AND status IN ('draft','submitted')", (task_id,))
        c.execute("INSERT INTO task_plans(task_id,revision,status,plan_json,plan_hash,submitted_by) VALUES(?,?,'submitted',?,?,?)", (task_id, rev, canonical, digest, session_id))
        plan_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    event = append_signed_event(root, "plan.submitted", {"plan_id": plan_id, "revision": rev, "plan_hash": digest}, task_id, session_id)
    return {"ok": True, "plan_id": plan_id, "task_id": task_id, "revision": rev, "status": "submitted", "plan_hash": digest, "event_hash": event["event_hash"]}


def approve_plan(root: Path, plan_id: int, approved_by: str, note: str) -> dict[str, Any]:
    """Approve one submitted plan revision and supersede older active plans."""
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM task_plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            raise RuntimeError("plan not found")
        if row["status"] != "submitted":
            raise RuntimeError("only submitted plans can be approved")
        c.execute("UPDATE task_plans SET status='superseded' WHERE task_id=? AND status='active'", (row["task_id"],))
        c.execute("UPDATE task_plans SET status='active',approved_by=?,approval_note=?,approved_at=CURRENT_TIMESTAMP WHERE id=?", (approved_by, note, plan_id))
    event = append_signed_event(root, "plan.approved", {"plan_id": plan_id, "revision": row["revision"], "approved_by": approved_by, "note": note}, row["task_id"], None)
    return {"ok": True, "plan_id": plan_id, "task_id": row["task_id"], "status": "active", "event_hash": event["event_hash"]}


def active_plan(root: Path, task_id: str) -> dict[str, Any] | None:
    """Return the active plan for a task, if any."""
    with connect(root) as c:
        row = c.execute("SELECT * FROM task_plans WHERE task_id=? AND status='active' ORDER BY revision DESC LIMIT 1", (task_id,)).fetchone()
    if not row: return None
    result = dict(row); result["plan"] = json.loads(result.pop("plan_json")); return result


def _git_changes(root: Path) -> list[str]:
    proc = subprocess.run(["git", "diff", "--name-only", "--cached"], cwd=root, text=True, capture_output=True)
    if proc.returncode != 0:
        proc = subprocess.run(["git", "diff", "--name-only"], cwd=root, text=True, capture_output=True)
    return sorted({line.strip() for line in proc.stdout.splitlines() if line.strip()})


def precommit_check(root: Path, task_id: str, changed_files: list[str] | None = None) -> dict[str, Any]:
    """Validate Git changes against task scope, active plan, and workflow state."""
    with connect(root) as c:
        task = c.execute("SELECT approved,approved_scope FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task: raise RuntimeError("task not found")
    files = sorted(set(changed_files if changed_files is not None else _git_changes(root)))
    scope = json.loads(task["approved_scope"])
    plan = active_plan(root, task_id)
    planned = set((plan or {}).get("plan", {}).get("files", []))
    outside_scope = [p for p in files if not any(p == s or p.startswith(s.rstrip("/") + "/") for s in scope)]
    unplanned = [p for p in files if planned and p not in planned]
    wf = workflow_status(root, task_id)
    blockers = {
        "task_not_approved": not bool(task["approved"]),
        "missing_active_plan": plan is None,
        "outside_scope": outside_scope,
        "unplanned_files": unplanned,
        "invalid_provenance": wf["invalid_provenance"],
    }
    ok = bool(task["approved"]) and plan is not None and not outside_scope and not unplanned and not wf["invalid_provenance"]
    return {"ok": ok, "task_id": task_id, "changed_files": files, "active_plan_revision": plan["revision"] if plan else None, "blockers": blockers}
