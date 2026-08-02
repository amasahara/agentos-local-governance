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
import math
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


def record_outcome(root: Path, task_id: str, outcome: str, rated_by: str, test_pass_rate: float | None=None, rework_count: int=0, note: str | None=None, **cohort: Any) -> dict[str, Any]:
    """Record a lightweight task outcome without duplicating trajectories."""
    if outcome not in {"success","partial","failed"}: raise ValueError("invalid outcome")
    with connect(root) as c:
        if not c.execute("SELECT 1 FROM tasks WHERE id=?",(task_id,)).fetchone(): raise RuntimeError("task not found")
        cur=c.execute("INSERT INTO task_outcomes(task_id,outcome,rated_by,test_pass_rate,rework_count,note,benchmark_key,task_category,agent_id,model_id,policy_revision,context_revision,retrieval_backend,repository_revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(task_id,outcome,rated_by,test_pass_rate,rework_count,note,cohort.get("benchmark_key"),cohort.get("task_category"),cohort.get("agent_id"),cohort.get("model_id"),cohort.get("policy_revision"),cohort.get("context_revision"),cohort.get("retrieval_backend"),cohort.get("repository_revision")))
    return {"outcome_id":cur.lastrowid,"task_id":task_id,"outcome":outcome}

def _wilson(successes: int, n: int, z: float=1.95996398454) -> tuple[float,float]:
    if not n: return (0.0,0.0)
    p=successes/n; d=1+z*z/n; center=(p+z*z/(2*n))/d; margin=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/d
    return max(0.0,center-margin),min(1.0,center+margin)

def compare_outcomes(root: Path, filter_a: dict[str,Any], filter_b: dict[str,Any]) -> dict[str,Any]:
    """Compare outcome cohorts with Wilson intervals and a two-proportion z-test."""
    def load(f):
        clauses=["1=1"]; params=[]
        for k,v in f.items(): clauses.append(f"{k}=?"); params.append(v)
        with connect(root) as c: rows=c.execute("SELECT outcome FROM task_outcomes WHERE "+" AND ".join(clauses),params).fetchall()
        return len(rows),sum(1 for r in rows if r["outcome"]=="success")
    na,sa=load(filter_a); nb,sb=load(filter_b); pa=sa/na if na else 0; pb=sb/nb if nb else 0
    pooled=(sa+sb)/(na+nb) if na+nb else 0; se=math.sqrt(pooled*(1-pooled)*(1/na+1/nb)) if na and nb else 0
    z=(pb-pa)/se if se else 0; pval=math.erfc(abs(z)/math.sqrt(2)) if se else 1.0
    return {"sample_size_a":na,"sample_size_b":nb,"success_rate_a":pa,"success_rate_b":pb,"confidence_interval_a":_wilson(sa,na),"confidence_interval_b":_wilson(sb,nb),"effect_size":pb-pa,"p_value":pval,"significant":bool(pval<0.05 and na>=30 and nb>=30),"warning":"insufficient_sample_size" if min(na,nb)<30 else None}
