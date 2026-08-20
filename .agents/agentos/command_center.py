"""
Path: .agents/agentos/command_center.py
Purpose: Build a privacy-safe, read-only Architecture & Agent Command Center snapshot from existing AgentOS governance state.

The command center is a projection only. It never creates governance authority,
never mutates AgentOS state, never launches workers, and never approves architecture
or controlled integration.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .db import connect_read_only
from .policy import load_policy
from .schema_version import CURRENT_SCHEMA_VERSION

SNAPSHOT_VERSION = 1
_SECTIONS = {"architecture", "execution", "compliance", "human_actions", "authority"}
_PENDING_INTEGRATION = {"draft", "reviewed", "approved"}
_TERMINAL_TASK_STATES = {"completed", "cancelled", "failed"}
_DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "snapshot_version": SNAPSHOT_VERSION,
    "database_read_only": True,
    "mutation_authority": False,
    "mcp_mutation_allowed": False,
    "raw_source_content_exposed": False,
    "physical_workspace_paths_exposed": False,
    "web_control_plane_reserved_for_v0281": True,
}


def _now() -> str:
    """Return a UTC timestamp for one ephemeral snapshot."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _policy(root: Path) -> dict[str, Any]:
    """Load and validate the read-only command-center policy."""
    merged = dict(_DEFAULT_POLICY)
    configured = load_policy(root).get("command_center_policy", {})
    if isinstance(configured, dict):
        merged.update(configured)
    if not bool(merged.get("enabled", True)):
        raise PermissionError("command_center_disabled")
    required_false = (
        "mutation_authority",
        "mcp_mutation_allowed",
        "raw_source_content_exposed",
        "physical_workspace_paths_exposed",
    )
    for key in required_false:
        if bool(merged.get(key, False)):
            raise RuntimeError(f"invalid_command_center_policy:{key}_must_be_false")
    if not bool(merged.get("database_read_only", True)):
        raise RuntimeError("invalid_command_center_policy:database_read_only_must_be_true")
    return merged


def _rows_to_counts(rows: Iterable[Any], key: str = "status") -> dict[str, int]:
    """Convert grouped SQLite rows to a stable status-count mapping."""
    result: dict[str, int] = {}
    for row in rows:
        name = str(row[key] if key in row.keys() else row[0])
        count = int(row["n"] if "n" in row.keys() else row[1])
        result[name] = count
    return dict(sorted(result.items()))


def _status_counts(c: Any, table: str, column: str = "status") -> dict[str, int]:
    """Return grouped counts from one fixed internal AgentOS table."""
    rows = c.execute(
        f"SELECT {column} AS status, COUNT(*) AS n FROM {table} GROUP BY {column} ORDER BY {column}"
    ).fetchall()
    return _rows_to_counts(rows)


def _latest_status(c: Any, table: str) -> dict[str, Any] | None:
    """Read the newest status-bearing row without exposing payload/source columns."""
    row = c.execute(
        f"SELECT id,status,created_at FROM {table} ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _overall_compliance(layers: dict[str, dict[str, Any]]) -> str:
    """Collapse architecture enforcement layers using block > warn > pass > not_evaluable."""
    statuses = [str(item.get("status") or "not_evaluable") for item in layers.values()]
    if any(value == "block" for value in statuses):
        return "block"
    if any(value == "warn" for value in statuses):
        return "warn"
    if any(value == "pass" for value in statuses):
        return "pass"
    return "not_evaluable"


def _layer(latest: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize one enforcement layer into a small dashboard-safe record."""
    if not latest:
        return {"status": "not_evaluable", "run_id": None, "created_at": None}
    return {
        "status": str(latest.get("status") or "not_evaluable"),
        "run_id": int(latest["id"]) if latest.get("id") is not None else None,
        "created_at": latest.get("created_at"),
    }


def _human_actions(c: Any) -> list[dict[str, Any]]:
    """Return privacy-safe pending human actions without raw requests/questions/source."""
    actions: list[dict[str, Any]] = []

    # Explicit clarification/decision requests.
    rows = c.execute(
        """SELECT id,decision_uuid,task_id,phase,decision_type,severity,blocking,status,created_at
           FROM human_decision_requests
           WHERE status='open'
           ORDER BY blocking DESC,id"""
    ).fetchall()
    for row in rows:
        actions.append({
            "kind": "human_decision",
            "id": int(row["id"]),
            "reference": str(row["decision_uuid"]),
            "task_id": str(row["task_id"]),
            "action": "resolve",
            "phase": str(row["phase"]),
            "decision_type": str(row["decision_type"]),
            "severity": str(row["severity"]),
            "blocking": bool(row["blocking"]),
            "created_at": row["created_at"],
        })

    # Architecture baseline lifecycle.
    row = c.execute(
        """SELECT id,baseline_version,status,created_at
           FROM architecture_baselines
           WHERE status IN ('draft','reviewed','approved')
           ORDER BY baseline_version DESC LIMIT 1"""
    ).fetchone()
    if row:
        action = {"draft": "review", "reviewed": "approve", "approved": "activate"}[str(row["status"])]
        actions.append({
            "kind": "architecture_baseline",
            "id": int(row["id"]),
            "reference": f"ARCH-{int(row['baseline_version'])}",
            "task_id": None,
            "action": action,
            "status": str(row["status"]),
            "blocking": False,
            "created_at": row["created_at"],
        })

    # Architecture change proposals and ADRs.
    for row in c.execute(
        """SELECT id,status,title,created_at
           FROM architecture_change_proposals
           WHERE status IN ('submitted','reviewed')
           ORDER BY id"""
    ).fetchall():
        actions.append({
            "kind": "architecture_change",
            "id": int(row["id"]),
            "reference": f"proposal:{int(row['id'])}",
            "task_id": None,
            "action": "review" if str(row["status"]) == "submitted" else "approve",
            "status": str(row["status"]),
            "blocking": False,
            "created_at": row["created_at"],
        })
    for row in c.execute(
        """SELECT id,proposal_id,status,created_at
           FROM architecture_adrs WHERE status='proposed' ORDER BY id"""
    ).fetchall():
        actions.append({
            "kind": "architecture_adr",
            "id": int(row["id"]),
            "reference": f"adr:{int(row['id'])}",
            "task_id": None,
            "action": "decide",
            "status": "proposed",
            "blocking": False,
            "created_at": row["created_at"],
        })

    # Multi-agent lifecycle that still requires human/operator authority.
    for row in c.execute(
        """SELECT id,parent_task_id,status,created_at
           FROM multi_agent_supervisor_runs
           WHERE status='draft' ORDER BY id"""
    ).fetchall():
        actions.append({
            "kind": "supervisor",
            "id": int(row["id"]),
            "reference": f"supervisor:{int(row['id'])}",
            "task_id": str(row["parent_task_id"]),
            "action": "activate",
            "status": "draft",
            "blocking": False,
            "created_at": row["created_at"],
        })
    for row in c.execute(
        """SELECT id,parent_task_id,status,conflict_status,architecture_status,security_status,test_status,created_at
           FROM multi_agent_integration_proposals
           WHERE status IN ('draft','reviewed','approved')
           ORDER BY id"""
    ).fetchall():
        status = str(row["status"])
        actions.append({
            "kind": "integration",
            "id": int(row["id"]),
            "reference": f"integration:{int(row['id'])}",
            "task_id": str(row["parent_task_id"]),
            "action": {"draft": "review", "reviewed": "approve", "approved": "apply"}[status],
            "status": status,
            "blocking": str(row["conflict_status"]) not in {"clear", "none", "pass"},
            "gates": {
                "conflict": str(row["conflict_status"]),
                "architecture": str(row["architecture_status"]),
                "security": str(row["security_status"]),
                "tests": str(row["test_status"]),
            },
            "created_at": row["created_at"],
        })

    actions.sort(key=lambda item: (not bool(item.get("blocking")), str(item.get("created_at") or ""), str(item["kind"]), int(item["id"])))
    return actions


def command_center_snapshot(root: Path | str) -> dict[str, Any]:
    """Build one privacy-safe command-center snapshot using strict read-only DB access."""
    root_path = Path(root).resolve()
    policy = _policy(root_path)
    with connect_read_only(root_path) as c:
        active = c.execute(
            """SELECT id,baseline_version,status,baseline_hash,section_count,activated_at
               FROM architecture_baselines WHERE status='active' LIMIT 1"""
        ).fetchone()
        latest_baseline = c.execute(
            """SELECT id,baseline_version,status,baseline_hash,section_count,created_at
               FROM architecture_baselines ORDER BY baseline_version DESC LIMIT 1"""
        ).fetchone()
        active_section_count = 0
        if active:
            active_section_count = int(c.execute(
                "SELECT COUNT(*) FROM architecture_baseline_sections WHERE baseline_id=?",
                (int(active["id"]),),
            ).fetchone()[0])

        proposal_counts = _status_counts(c, "architecture_change_proposals")
        adr_counts = _status_counts(c, "architecture_adrs")
        task_state_counts = _status_counts(c, "tasks", "task_state")
        supervisor_counts = _status_counts(c, "multi_agent_supervisor_runs")
        worker_counts = _status_counts(c, "multi_agent_workers")
        workspace_counts = _status_counts(c, "multi_agent_workspaces")
        integration_counts = _status_counts(c, "multi_agent_integration_proposals")

        total_tasks = int(c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
        approved_tasks = int(c.execute("SELECT COUNT(*) FROM tasks WHERE approved=1").fetchone()[0])
        active_leases = int(c.execute("SELECT COUNT(*) FROM resource_leases WHERE status='active'").fetchone()[0])
        conflict_count = int(c.execute(
            """SELECT COUNT(*) FROM multi_agent_integration_proposals
               WHERE status IN ('draft','reviewed','approved')
                 AND conflict_status NOT IN ('clear','none','pass')"""
        ).fetchone()[0])
        open_blocking_decisions = int(c.execute(
            "SELECT COUNT(*) FROM human_decision_requests WHERE status='open' AND blocking=1"
        ).fetchone()[0])

        layers = {
            "contract_compliance": _layer(_latest_status(c, "architecture_compliance_runs")),
            "structure": _layer(_latest_status(c, "architecture_structural_runs")),
            "runtime_boundaries": _layer(_latest_status(c, "architecture_runtime_runs")),
            "quality_operations": _layer(_latest_status(c, "architecture_quality_runs")),
        }
        actions = _human_actions(c)

    architecture = {
        "active_baseline": dict(active) if active else None,
        "latest_baseline": dict(latest_baseline) if latest_baseline else None,
        "active_sections": active_section_count,
        "expected_sections": 27,
        "proposal_status_counts": proposal_counts,
        "adr_status_counts": adr_counts,
        "pending_proposals": sum(proposal_counts.get(key, 0) for key in ("draft", "submitted", "reviewed")),
        "pending_adrs": int(adr_counts.get("proposed", 0)),
    }
    execution = {
        "tasks_total": total_tasks,
        "tasks_approved": approved_tasks,
        "task_state_counts": task_state_counts,
        "supervisor_status_counts": supervisor_counts,
        "worker_status_counts": worker_counts,
        "workers_total": sum(worker_counts.values()),
        "workers_running": int(worker_counts.get("running", 0)),
        "workers_blocked": int(worker_counts.get("blocked", 0)),
        "active_leases": active_leases,
        "workspace_status_counts": workspace_counts,
        "integration_status_counts": integration_counts,
        "integration_conflicts": conflict_count,
    }
    compliance = {
        "overall": _overall_compliance(layers),
        "layers": layers,
    }
    blocking_attention = (
        open_blocking_decisions
        + int(execution["workers_blocked"])
        + int(execution["integration_conflicts"])
        + (1 if compliance["overall"] == "block" else 0)
    )
    overall = "block" if blocking_attention else ("warn" if actions or compliance["overall"] == "warn" else "pass")
    return {
        "ok": True,
        "version": __version__,
        "schema": CURRENT_SCHEMA_VERSION,
        "snapshot_version": SNAPSHOT_VERSION,
        "generated_at": _now(),
        "overall_status": overall,
        "attention_count": len(actions),
        "blocking_attention_count": blocking_attention,
        "architecture": architecture,
        "execution": execution,
        "compliance": compliance,
        "human_actions": {
            "count": len(actions),
            "blocking_count": sum(1 for item in actions if item.get("blocking")),
            "items": actions,
        },
        "authority": {
            "projection_only": True,
            "database_read_only": True,
            "mutation_authority": False,
            "architecture_approval_authority": False,
            "integration_approval_authority": False,
            "worker_launch_authority": False,
            "model_provider_selection_authority": False,
            "mcp_mutation_allowed": False,
            "raw_source_content_exposed": False,
            "physical_workspace_paths_exposed": False,
            "web_control_plane_reserved_for_v0281": bool(policy.get("web_control_plane_reserved_for_v0281", True)),
        },
    }


def command_center_human_actions(root: Path | str) -> dict[str, Any]:
    """Return only pending human/operator actions from the shared snapshot read model."""
    snapshot = command_center_snapshot(root)
    return {
        "ok": True,
        "version": snapshot["version"],
        "schema": snapshot["schema"],
        "snapshot_version": snapshot["snapshot_version"],
        "generated_at": snapshot["generated_at"],
        **snapshot["human_actions"],
        "mutation_authority": False,
    }


def command_center_section(root: Path | str, section: str) -> dict[str, Any]:
    """Return one named command-center section without exposing mutation authority."""
    name = str(section or "").strip().lower()
    if name not in _SECTIONS:
        raise ValueError("invalid_command_center_section")
    snapshot = command_center_snapshot(root)
    return {
        "ok": True,
        "version": snapshot["version"],
        "schema": snapshot["schema"],
        "snapshot_version": snapshot["snapshot_version"],
        "generated_at": snapshot["generated_at"],
        "section": name,
        "data": snapshot[name],
        "mutation_authority": False,
    }


def _count_line(mapping: dict[str, int], *, limit: int = 6) -> str:
    """Render a compact status-count map for the terminal dashboard."""
    if not mapping:
        return "-"
    items = list(sorted(mapping.items()))
    shown = items[:limit]
    suffix = " ..." if len(items) > limit else ""
    return ", ".join(f"{key}={value}" for key, value in shown) + suffix


def render_command_center(snapshot: dict[str, Any]) -> str:
    """Render a deterministic cross-platform text TUI from a command-center snapshot."""
    arch = snapshot["architecture"]
    execution = snapshot["execution"]
    compliance = snapshot["compliance"]
    actions = snapshot["human_actions"]
    active = arch.get("active_baseline") or {}
    baseline_label = (
        f"ARCH-{active.get('baseline_version')} / {active.get('status')}"
        if active else "NONE"
    )
    lines = [
        f"AgentOS Architecture & Agent Command Center v{snapshot['version']}",
        "=" * 72,
        f"Overall        {str(snapshot['overall_status']).upper()}",
        f"Attention      {snapshot['attention_count']} ({snapshot['blocking_attention_count']} blocking)",
        "",
        "Architecture",
        "-" * 72,
        f"Baseline       {baseline_label}",
        f"Sections       {arch['active_sections']} / {arch['expected_sections']}",
        f"Proposals      {arch['pending_proposals']} pending",
        f"ADR Pending    {arch['pending_adrs']}",
        "",
        "Execution",
        "-" * 72,
        f"Tasks          {execution['tasks_total']} total / {execution['tasks_approved']} approved",
        f"Task States    {_count_line(execution['task_state_counts'])}",
        f"Workers        {execution['workers_total']} total / {execution['workers_running']} running / {execution['workers_blocked']} blocked",
        f"Supervisors    {_count_line(execution['supervisor_status_counts'])}",
        f"Workspaces     {_count_line(execution['workspace_status_counts'])}",
        f"Leases         {execution['active_leases']} active",
        f"Conflicts      {execution['integration_conflicts']}",
        "",
        "Compliance",
        "-" * 72,
        f"Overall        {str(compliance['overall']).upper()}",
    ]
    labels = {
        "contract_compliance": "Contract",
        "structure": "Structure",
        "runtime_boundaries": "Runtime",
        "quality_operations": "Quality",
    }
    for key in ("contract_compliance", "structure", "runtime_boundaries", "quality_operations"):
        layer = compliance["layers"][key]
        lines.append(f"{labels[key]:<14} {str(layer['status']).upper()}")
    lines += [
        "",
        "Human Actions",
        "-" * 72,
        f"Pending        {actions['count']} / {actions['blocking_count']} blocking",
    ]
    for item in actions["items"][:8]:
        marker = "BLOCK" if item.get("blocking") else "WAIT"
        task = f" task={item['task_id']}" if item.get("task_id") else ""
        lines.append(f"[{marker}] {item['kind']}:{item['id']} -> {item['action']}{task}")
    if actions["count"] > 8:
        lines.append(f"... {actions['count'] - 8} more")
    lines += [
        "",
        "Authority",
        "-" * 72,
        "READ-ONLY PROJECTION — no architecture approval, worker launch, integration approval, or mutation authority.",
    ]
    return "\n".join(lines) + "\n"
