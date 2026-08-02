"""
File: .agents/agentos/evolution.py

Purpose:
    Provide evaluation-driven, human-controlled governance evolution.

Responsibilities:
    - Require an evaluation baseline before creating policy proposals.
    - Simulate proposals without activating them.
    - Enforce reviewed shadow and canary stages before activation.
    - Preserve rollback metadata and signed audit provenance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .db import connect
from .evaluation import aggregate_metrics
from .external_audit import append_signed_event

_ALLOWED_TRANSITIONS = {
    "draft": {"simulated"},
    "simulated": {"reviewed"},
    "reviewed": {"shadow"},
    "shadow": {"canary"},
    "canary": {"active"},
    "active": {"rolled_back"},
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def create_proposal(root: Path, title: str, trigger_findings: list[int], policy_patch: dict[str, Any], expected_benefit: str, risks: list[str], rollback_plan: dict[str, Any], created_by: str) -> dict[str, Any]:
    """Create a draft proposal only when an evaluation baseline exists."""
    with connect(root) as c:
        baseline = c.execute("SELECT id,metrics_json FROM evaluation_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not baseline:
            raise RuntimeError("evaluation_baseline_required")
        proposal_hash = hashlib.sha256(_canonical({"title": title, "trigger_findings": trigger_findings, "policy_patch": policy_patch, "expected_benefit": expected_benefit, "risks": risks, "rollback_plan": rollback_plan}).encode()).hexdigest()
        cur = c.execute(
            "INSERT INTO evolution_proposals(title,status,trigger_findings_json,policy_patch_json,expected_benefit,risks_json,rollback_plan_json,baseline_evaluation_run_id,proposal_hash,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (title, "draft", _canonical(trigger_findings), _canonical(policy_patch), expected_benefit, _canonical(risks), _canonical(rollback_plan), baseline["id"], proposal_hash, created_by),
        )
        proposal_id = cur.lastrowid
    event = append_signed_event(root, "evolution.proposal_created", {"proposal_id": proposal_id, "proposal_hash": proposal_hash, "baseline_evaluation_run_id": baseline["id"]}, None, created_by)
    with connect(root) as c:
        c.execute("UPDATE evolution_proposals SET external_event_hash=? WHERE id=?", (event["event_hash"], proposal_id))
    return {"proposal_id": proposal_id, "status": "draft", "proposal_hash": proposal_hash, "baseline_evaluation_run_id": baseline["id"], "external_event_hash": event["event_hash"]}


def simulate_proposal(root: Path, proposal_id: int) -> dict[str, Any]:
    """Simulate a draft proposal against current evaluation metrics."""
    with connect(root) as c:
        row = c.execute("SELECT * FROM evolution_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise RuntimeError("proposal_not_found")
        if row["status"] != "draft":
            raise RuntimeError("proposal_must_be_draft")
    current = aggregate_metrics(root)
    patch = json.loads(row["policy_patch_json"])
    simulation = {
        "baseline_evaluation_run_id": row["baseline_evaluation_run_id"],
        "current_metrics": current["metrics"],
        "policy_keys_changed": sorted(patch.keys()),
        "newly_blocked_estimate": 0,
        "newly_permitted_estimate": 0,
        "mode": "deterministic_shadow_estimate",
    }
    with connect(root) as c:
        c.execute("UPDATE evolution_proposals SET status='simulated',simulation_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (_canonical(simulation), proposal_id))
    return {"proposal_id": proposal_id, "status": "simulated", "simulation": simulation}


def transition_proposal(root: Path, proposal_id: int, target_status: str, actor: str, note: str) -> dict[str, Any]:
    """Move a proposal through reviewed, shadow, canary, active, or rollback stages."""
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT status FROM evolution_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise RuntimeError("proposal_not_found")
        current = row["status"]
        if target_status not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise RuntimeError(f"invalid_evolution_transition:{current}->{target_status}")
        if target_status in {"reviewed", "active", "rolled_back"} and not actor.strip():
            raise RuntimeError("human_actor_required")
        c.execute("UPDATE evolution_proposals SET status=?,reviewed_by=CASE WHEN ?='reviewed' THEN ? ELSE reviewed_by END,review_note=CASE WHEN ?='reviewed' THEN ? ELSE review_note END,updated_at=CURRENT_TIMESTAMP WHERE id=?", (target_status, target_status, actor, target_status, note, proposal_id))
        c.execute("INSERT INTO evolution_stage_events(proposal_id,from_status,to_status,actor,note) VALUES(?,?,?,?,?)", (proposal_id, current, target_status, actor, note))
    event = append_signed_event(root, "evolution.stage_changed", {"proposal_id": proposal_id, "from": current, "to": target_status, "actor": actor, "note": note}, None, actor)
    with connect(root) as c:
        c.execute("UPDATE evolution_stage_events SET external_event_hash=? WHERE id=(SELECT MAX(id) FROM evolution_stage_events WHERE proposal_id=?)", (event["event_hash"], proposal_id))
    return {"proposal_id": proposal_id, "from_status": current, "status": target_status, "external_event_hash": event["event_hash"]}


def proposal_status(root: Path, proposal_id: int) -> dict[str, Any]:
    """Return one proposal and its stage history."""
    with connect(root) as c:
        row = c.execute("SELECT * FROM evolution_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise RuntimeError("proposal_not_found")
        events = [dict(x) for x in c.execute("SELECT * FROM evolution_stage_events WHERE proposal_id=? ORDER BY id", (proposal_id,)).fetchall()]
    result = dict(row)
    for key in ("trigger_findings_json", "policy_patch_json", "risks_json", "rollback_plan_json", "simulation_json"):
        result[key.removesuffix("_json")] = json.loads(result[key]) if result.get(key) else None
        result.pop(key, None)
    result["events"] = events
    return result
