"""
File: .agents/agentos/evaluation.py

Purpose:
    Provide aggregate execution and governance evaluation for AgentOS v0.17.1.

Responsibilities:
    - Calculate reproducible metrics across tasks and jobs.
    - Export versioned JSON and CSV evaluation reports.
    - Preserve benchmark dimensions for agent/model/policy comparison.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect

METRICS_SCHEMA_VERSION = 1


def aggregate_metrics(root: Path, since: str | None = None, agent: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Compute aggregate task, governance, and asynchronous-job metrics."""
    where = " WHERE created_at >= ?" if since else ""
    params = (since,) if since else ()
    with connect(root) as c:
        tasks = c.execute(f"SELECT COUNT(*) AS n, SUM(approved) AS approved FROM tasks{where}", params).fetchone()
        steps = c.execute("SELECT status,COUNT(*) AS n FROM workflow_steps GROUP BY status").fetchall()
        writes = c.execute("SELECT SUM(CASE WHEN allowed=0 THEN 1 ELSE 0 END) AS blocked,COUNT(*) AS n FROM write_audit").fetchone()
        jobs = c.execute("SELECT state,COUNT(*) AS n FROM async_jobs GROUP BY state").fetchall()
        claims = c.execute("SELECT COUNT(*) AS n FROM claims").fetchone()["n"]
        evidence = c.execute("SELECT COUNT(DISTINCT claim_id) AS n FROM claim_evidence").fetchone()["n"]
        conflicts = c.execute("SELECT COUNT(*) AS n FROM audit_events WHERE event_type LIKE '%conflict%' OR event_type LIKE '%stale%'").fetchone()["n"]
    step_counts = {r["status"]: r["n"] for r in steps}
    job_counts = {r["state"]: r["n"] for r in jobs}
    total_steps = sum(step_counts.values())
    completed_steps = sum(step_counts.get(x, 0) for x in ("done", "done_verified", "skipped", "skipped_verified"))
    report = {
        "metrics_schema_version": METRICS_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dimensions": {"agent": agent, "model": model, "policy_version": json.loads((root/".agents/config/governance.json").read_text())["version"], "repository_version": (root/"VERSION").read_text().strip()},
        "metrics": {
            "tasks_total": int(tasks["n"] or 0),
            "tasks_approved": int(tasks["approved"] or 0),
            "workflow_completion_rate": (completed_steps / total_steps) if total_steps else 0.0,
            "write_block_rate": (int(writes["blocked"] or 0) / int(writes["n"] or 1)) if writes["n"] else 0.0,
            "claims_total": int(claims),
            "evidence_completeness_rate": (int(evidence) / int(claims)) if claims else 0.0,
            "stale_or_conflict_events": int(conflicts),
            "job_states": job_counts,
        },
    }
    with connect(root) as c:
        c.execute("INSERT INTO evaluation_runs(metrics_schema_version,agent_name,model_name,policy_version,repository_version,filters_json,metrics_json) VALUES(?,?,?,?,?,?,?)", (METRICS_SCHEMA_VERSION, agent, model, report["dimensions"]["policy_version"], report["dimensions"]["repository_version"], json.dumps({"since": since}, sort_keys=True), json.dumps(report["metrics"], sort_keys=True)))
    return report


def export_metrics(root: Path, output: str, fmt: str = "json", **filters: Any) -> dict[str, Any]:
    """Export aggregate metrics to JSON or CSV."""
    report = aggregate_metrics(root, **filters)
    path = (root / output).resolve() if not Path(output).is_absolute() else Path(output).resolve()
    path.relative_to(root.resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "csv":
        flat = {k: v for k, v in report["metrics"].items() if not isinstance(v, dict)}
        flat.update({f"job_{k}": v for k, v in report["metrics"]["job_states"].items()})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(flat)); writer.writeheader(); writer.writerow(flat)
    else:
        raise RuntimeError("format must be json or csv")
    return {"ok": True, "path": str(path), "format": fmt, "report": report}
