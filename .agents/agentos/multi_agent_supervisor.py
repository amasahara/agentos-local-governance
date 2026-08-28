"""Path: .agents/agentos/multi_agent_supervisor.py
Purpose: Govern multi-agent worker assignment, dependency scheduling, and readiness without creating a second execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .architecture_planning import architecture_plan_status
from .collaboration import ROLE_PERMISSIONS
from .db import connect, connect_read_only
from .external_audit import append_signed_event
from .policy import load_policy

MIGRATION_VERSION = 60
SUPERVISOR_VERSION = 1

_SUPERVISOR_STATES = {"draft", "active", "paused", "completed", "cancelled"}
_WORKER_STATES = {"registered", "ready", "running", "blocked", "completed", "failed", "removed"}
_TERMINAL_WORKER_STATES = {"completed", "failed", "removed"}
_MUTABLE_SUPERVISOR_STATES = {"draft", "paused"}

_DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "database_schema": MIGRATION_VERSION,
    "supervisor_version": SUPERVISOR_VERSION,
    "max_workers": 8,
    "require_existing_approved_worker_tasks": True,
    "require_current_worker_plans": True,
    "require_parent_active_plan": True,
    "require_parent_plan_file_envelope": True,
    "require_distinct_worker_sessions": True,
    "require_active_capability_sessions": True,
    "require_active_role_assignments": True,
    "require_acyclic_dependencies": True,
    "overlapping_executor_write_targets": "block",
    "auto_task_create": False,
    "auto_task_approve": False,
    "auto_plan_approve": False,
    "auto_capability_issue": False,
    "auto_skill_execute": False,
    "auto_model_provider_select": False,
    "auto_process_launch": False,
    "mcp_mutation_allowed": False,
    "isolated_workspace_reserved_for_v0273": True,
    "controlled_integration_reserved_for_v0273": True,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    data = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _human(identity: str) -> str:
    value = str(identity or "").strip()
    if not value or value.lower() in {"ai", "agent", "assistant", "model", "llm", "system"}:
        raise PermissionError("human_identity_required")
    return value


def _policy(root: Path) -> dict[str, Any]:
    policy = dict(_DEFAULT_POLICY)
    all_policy = load_policy(root)
    configured = all_policy.get("multi_agent_supervisor_policy", {})
    if isinstance(configured, dict):
        policy.update(configured)
    if not policy.get("enabled", True):
        raise PermissionError("multi_agent_supervisor_disabled")
    if bool(policy.get("auto_process_launch", False)):
        raise RuntimeError("invalid_supervisor_policy_auto_process_launch_must_be_false")
    if bool(policy.get("mcp_mutation_allowed", False)):
        raise RuntimeError("invalid_supervisor_policy_mcp_mutation_must_be_false")
    if not bool((all_policy.get("concurrency_policy") or {}).get("task_single_writer", True)):
        raise RuntimeError("multi_agent_supervisor_requires_task_single_writer")
    return policy


def migration_60(c) -> None:
    """Create additive schema 60 tables for governed multi-agent supervision.

    Input: SQLite connection/cursor-compatible object used by AgentOS migrations.
    Output: None. Creates supervisor, worker, dependency, and event tables/indexes.
    """
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS multi_agent_supervisor_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_task_id TEXT NOT NULL REFERENCES tasks(id),
            parent_plan_id INTEGER NOT NULL REFERENCES task_plans(id),
            parent_plan_hash TEXT NOT NULL,
            architecture_baseline_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','active','paused','completed','cancelled')),
            worker_limit INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            activated_by TEXT,
            supervisor_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            activated_at TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS multi_agent_workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supervisor_id INTEGER NOT NULL REFERENCES multi_agent_supervisor_runs(id) ON DELETE CASCADE,
            worker_key TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            plan_id INTEGER NOT NULL REFERENCES task_plans(id),
            plan_hash TEXT NOT NULL,
            architecture_baseline_hash TEXT NOT NULL,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            skill_id INTEGER REFERENCES promoted_skills(id),
            selection_run_id INTEGER REFERENCES skill_selection_runs(id),
            capability_set_hash TEXT NOT NULL,
            assignment_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('registered','ready','running','blocked','completed','failed','removed')),
            last_heartbeat_at TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(supervisor_id, worker_key),
            UNIQUE(supervisor_id, task_id),
            UNIQUE(supervisor_id, session_id)
        );

        CREATE TABLE IF NOT EXISTS multi_agent_worker_dependencies (
            supervisor_id INTEGER NOT NULL REFERENCES multi_agent_supervisor_runs(id) ON DELETE CASCADE,
            worker_id INTEGER NOT NULL REFERENCES multi_agent_workers(id) ON DELETE CASCADE,
            depends_on_worker_id INTEGER NOT NULL REFERENCES multi_agent_workers(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY(supervisor_id, worker_id, depends_on_worker_id),
            CHECK(worker_id <> depends_on_worker_id)
        );

        CREATE TABLE IF NOT EXISTS multi_agent_supervisor_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supervisor_id INTEGER NOT NULL REFERENCES multi_agent_supervisor_runs(id) ON DELETE CASCADE,
            worker_id INTEGER REFERENCES multi_agent_workers(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            external_event_hash TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_multi_agent_supervisors_parent
            ON multi_agent_supervisor_runs(parent_task_id, status);
        CREATE INDEX IF NOT EXISTS idx_multi_agent_workers_supervisor
            ON multi_agent_workers(supervisor_id, status);
        CREATE INDEX IF NOT EXISTS idx_multi_agent_workers_task_session
            ON multi_agent_workers(task_id, session_id);
        CREATE INDEX IF NOT EXISTS idx_multi_agent_dependencies_worker
            ON multi_agent_worker_dependencies(supervisor_id, worker_id);
        CREATE INDEX IF NOT EXISTS idx_multi_agent_events_supervisor
            ON multi_agent_supervisor_events(supervisor_id, id);
        """
    )


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _plan_files(plan_payload: dict[str, Any]) -> set[str]:
    raw = plan_payload.get("expected_files") or plan_payload.get("files") or []
    return {str(item).replace("\\", "/").strip() for item in raw if str(item).strip()}


def _plan_sections(plan_payload: dict[str, Any]) -> set[str]:
    raw = plan_payload.get("affected_architecture_sections") or plan_payload.get("architecture_sections") or []
    return {str(item).strip() for item in raw if str(item).strip()}


def _active_plan_row(c, task_id: str):
    return c.execute(
        """
        SELECT p.id, p.task_id, p.plan_hash, p.plan_json, p.status,
               a.baseline_hash, a.state AS architecture_state
        FROM task_plans p
        LEFT JOIN task_plan_architecture_contexts a ON a.plan_id = p.id
        WHERE p.task_id=? AND p.status='active'
        ORDER BY p.revision DESC, p.id DESC
        LIMIT 1
        """,
        (str(task_id),),
    ).fetchone()


def _approved_task(c, task_id: str):
    row = c.execute("SELECT id, approved, owner_session_id, task_state FROM tasks WHERE id=?", (str(task_id),)).fetchone()
    if not row:
        raise ValueError("task_not_found")
    if int(row["approved"] or 0) != 1:
        raise PermissionError("task_not_approved")
    return row


def _supervisor_row(c, supervisor_id: int):
    row = c.execute("SELECT * FROM multi_agent_supervisor_runs WHERE id=?", (int(supervisor_id),)).fetchone()
    if not row:
        raise ValueError("supervisor_not_found")
    return row


def _worker_row(c, supervisor_id: int, worker_key: str):
    row = c.execute(
        "SELECT * FROM multi_agent_workers WHERE supervisor_id=? AND worker_key=?",
        (int(supervisor_id), str(worker_key)),
    ).fetchone()
    if not row:
        raise ValueError("worker_not_found")
    return row


def _event_payload(event_type: str, supervisor_id: int, worker_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    safe = {
        "event_type": event_type,
        "supervisor_id": int(supervisor_id),
        "worker_id": int(worker_id) if worker_id is not None else None,
        "payload": payload,
        "created_at": _now(),
    }
    return safe


def _record_event(root: Path, supervisor_id: int, event_type: str, payload: dict[str, Any], worker_id: int | None = None) -> None:
    event = _event_payload(event_type, supervisor_id, worker_id, payload)
    event_json = _canonical(event)
    event_hash = _sha(event_json)
    with connect(root, immediate=True) as c:
        supervisor = _supervisor_row(c, supervisor_id)
        cur = c.execute(
            """
            INSERT INTO multi_agent_supervisor_events(
                supervisor_id, worker_id, event_type, event_json, event_hash, created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (int(supervisor_id), worker_id, event_type, event_json, event_hash, event["created_at"]),
        )
        local_event_id = int(cur.lastrowid)
        parent_task_id = str(supervisor["parent_task_id"])
    signed = append_signed_event(
        root,
        f"multi_agent_supervisor.{event_type}",
        event,
        str(payload.get("task_id") or parent_task_id),
        None,
    )
    external_hash = str(signed.get("event_hash") or "")
    if external_hash:
        with connect(root, immediate=True) as c:
            c.execute(
                "UPDATE multi_agent_supervisor_events SET external_event_hash=? WHERE id=?",
                (external_hash, local_event_id),
            )


def _require_plan_current(root: Path, task_id: str, plan_id: int, plan_hash: str) -> dict[str, Any]:
    status = architecture_plan_status(root, str(task_id))
    if not status.get("ready"):
        raise PermissionError("architecture_plan_not_ready:" + str(status.get("reason") or "unknown"))
    if int(status.get("plan_id") or 0) != int(plan_id) or str(status.get("plan_status") or "") != "active":
        raise PermissionError("architecture_plan_stale")
    with connect_read_only(root) as c:
        row = c.execute("SELECT plan_hash FROM task_plans WHERE id=? AND task_id=? AND status='active'", (int(plan_id), str(task_id))).fetchone()
    if not row or str(row["plan_hash"]) != str(plan_hash):
        raise PermissionError("architecture_plan_hash_mismatch")
    return status


def _session_binding(c, task_id: str, session_id: str) -> tuple[str, int]:
    row = c.execute(
        """
        SELECT capability_set_json
        FROM session_tokens
        WHERE task_id=? AND session_id=? AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP
        ORDER BY issued_at DESC LIMIT 1
        """,
        (str(task_id), str(session_id)),
    ).fetchone()
    if not row:
        raise PermissionError("active_capability_session_required")
    capabilities = sorted({str(x) for x in _json_list(row["capability_set_json"])})
    return _sha(capabilities), len(capabilities)


def _role_binding(c, task_id: str, session_id: str, role: str) -> None:
    if role not in ROLE_PERMISSIONS:
        raise ValueError("unsupported_worker_role")
    row = c.execute(
        """
        SELECT id FROM task_role_assignments
        WHERE task_id=? AND session_id=? AND role=? AND status='active'
        ORDER BY id DESC LIMIT 1
        """,
        (str(task_id), str(session_id), str(role)),
    ).fetchone()
    if not row:
        raise PermissionError("active_role_assignment_required")


def _selection_binding(
    c,
    task_id: str,
    plan_id: int,
    plan_hash: str,
    architecture_baseline_hash: str,
    selection_run_id: int | None,
    skill_id: int | None,
) -> None:
    if selection_run_id is None and skill_id is None:
        return
    if selection_run_id is None or skill_id is None:
        raise ValueError("selection_run_id_and_skill_id_required_together")
    row = c.execute(
        """
        SELECT r.id AS run_id, r.task_id, r.plan_id, r.plan_hash, r.architecture_baseline_hash,
               r.status AS selection_status, r.recommended_skill_id,
               cand.eligible, cand.recommendable, cand.contract_hash AS candidate_contract_hash,
               p.id AS skill_id, p.status AS skill_status, p.contract_version, p.contract_hash,
               p.contract_status, sc.validation_status, sc.architecture_baseline_hash AS contract_baseline_hash
        FROM skill_selection_runs r
        JOIN skill_selection_candidates cand ON cand.selection_run_id=r.id AND cand.skill_id=?
        JOIN promoted_skills p ON p.id=cand.skill_id
        JOIN skill_contracts sc ON sc.skill_id=p.id
        WHERE r.id=?
        """,
        (int(skill_id), int(selection_run_id)),
    ).fetchone()
    if not row:
        raise PermissionError("skill_selection_binding_not_found")
    if str(row["task_id"]) != str(task_id) or int(row["plan_id"]) != int(plan_id):
        raise PermissionError("skill_selection_task_plan_mismatch")
    if str(row["plan_hash"]) != str(plan_hash):
        raise PermissionError("skill_selection_plan_hash_mismatch")
    if str(row["architecture_baseline_hash"] or "") != str(architecture_baseline_hash or ""):
        raise PermissionError("skill_selection_architecture_baseline_mismatch")
    if int(row["eligible"] or 0) != 1 or int(row["recommendable"] or 0) != 1:
        raise PermissionError("skill_not_eligible_or_recommendable")
    if str(row["skill_status"]) != "graduated" or int(row["contract_version"] or 0) != 2:
        raise PermissionError("skill_contract_v2_graduated_required")
    if str(row["contract_status"]) != "valid" or str(row["validation_status"]) != "valid":
        raise PermissionError("skill_contract_v2_current_validation_required")
    if str(row["candidate_contract_hash"] or "") != str(row["contract_hash"] or ""):
        raise PermissionError("skill_selection_contract_hash_stale")
    contract_baseline = str(row["contract_baseline_hash"] or "")
    if contract_baseline and contract_baseline != str(architecture_baseline_hash or ""):
        raise PermissionError("skill_contract_architecture_baseline_stale")

def create_supervisor(root: Path, parent_task_id: str, created_by: str, worker_limit: int | None = None) -> dict[str, Any]:
    """Create a draft supervisor around an already approved parent task and active architecture-aware plan."""
    policy = _policy(root)
    human = _human(created_by)
    with connect_read_only(root) as c:
        _approved_task(c, parent_task_id)
        plan = _active_plan_row(c, parent_task_id)
        if not plan:
            raise PermissionError("parent_active_plan_required")
        plan_payload = _json_obj(plan["plan_json"])
        plan_id = int(plan["id"])
        plan_hash = str(plan["plan_hash"])
        baseline_hash = str(plan["baseline_hash"] or "")
    if policy.get("require_parent_active_plan", True):
        _require_plan_current(root, parent_task_id, plan_id, plan_hash)
    limit = int(worker_limit or policy.get("max_workers", 8))
    maximum = int(policy.get("max_workers", 8))
    if limit < 1 or limit > maximum:
        raise ValueError("worker_limit_out_of_policy")
    envelope = {
        "supervisor_version": SUPERVISOR_VERSION,
        "parent_task_id": str(parent_task_id),
        "parent_plan_id": plan_id,
        "parent_plan_hash": plan_hash,
        "architecture_baseline_hash": baseline_hash,
        "expected_files": sorted(_plan_files(plan_payload)),
        "affected_architecture_sections": sorted(_plan_sections(plan_payload)),
        "worker_limit": limit,
    }
    supervisor_hash = _sha(envelope)
    created_at = _now()
    with connect(root) as c:
        cur = c.execute(
            """
            INSERT INTO multi_agent_supervisor_runs(
                parent_task_id, parent_plan_id, parent_plan_hash, architecture_baseline_hash,
                status, worker_limit, created_by, supervisor_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (str(parent_task_id), plan_id, plan_hash, baseline_hash, "draft", limit, human, supervisor_hash, created_at),
        )
        supervisor_id = int(cur.lastrowid)
    _record_event(root, supervisor_id, "supervisor_created", {"created_by": human, "supervisor_hash": supervisor_hash})
    return {"supervisor_id": supervisor_id, "status": "draft", "supervisor_hash": supervisor_hash, "worker_limit": limit}


def add_worker(
    root: Path,
    supervisor_id: int,
    worker_key: str,
    task_id: str,
    session_id: str,
    role: str,
    *,
    selection_run_id: int | None = None,
    skill_id: int | None = None,
) -> dict[str, Any]:
    """Bind an existing approved worker task/session/role/plan into a draft or paused supervisor."""
    policy = _policy(root)
    key = str(worker_key or "").strip()
    session = str(session_id or "").strip()
    if not key or not session:
        raise ValueError("worker_key_and_session_id_required")
    with connect_read_only(root) as c:
        supervisor = _supervisor_row(c, supervisor_id)
        if str(supervisor["status"]) not in _MUTABLE_SUPERVISOR_STATES:
            raise PermissionError("supervisor_not_mutable")
        count = int(c.execute("SELECT COUNT(*) AS n FROM multi_agent_workers WHERE supervisor_id=? AND status<>'removed'", (int(supervisor_id),)).fetchone()["n"])
        if count >= int(supervisor["worker_limit"]):
            raise PermissionError("supervisor_worker_limit_reached")
        if str(task_id) == str(supervisor["parent_task_id"]):
            raise PermissionError("worker_task_must_be_distinct_from_parent_task")
        task_row = _approved_task(c, task_id)
        owner = str(task_row["owner_session_id"] or "")
        if owner and owner != session:
            raise PermissionError("worker_task_owned_by_other_session")
        worker_plan = _active_plan_row(c, task_id)
        parent_plan = c.execute("SELECT plan_json FROM task_plans WHERE id=?", (int(supervisor["parent_plan_id"]),)).fetchone()
        if not worker_plan or not parent_plan:
            raise PermissionError("worker_active_plan_required")
        worker_plan_id = int(worker_plan["id"])
        worker_plan_hash = str(worker_plan["plan_hash"])
        worker_baseline_hash = str(worker_plan["baseline_hash"] or "")
        if worker_baseline_hash != str(supervisor["architecture_baseline_hash"]):
            raise PermissionError("worker_architecture_baseline_mismatch")
        worker_payload = _json_obj(worker_plan["plan_json"])
        parent_payload = _json_obj(parent_plan["plan_json"])
        if policy.get("require_parent_plan_file_envelope", True):
            outside = sorted(_plan_files(worker_payload) - _plan_files(parent_payload))
            if outside:
                raise PermissionError("worker_plan_outside_parent_file_envelope:" + ",".join(outside))
            section_outside = sorted(_plan_sections(worker_payload) - _plan_sections(parent_payload))
            if section_outside:
                raise PermissionError("worker_plan_outside_parent_architecture_envelope:" + ",".join(section_outside))
        capability_hash, capability_count = _session_binding(c, task_id, session)
        _role_binding(c, task_id, session, role)
        _selection_binding(c, task_id, worker_plan_id, worker_plan_hash, worker_baseline_hash, selection_run_id, skill_id)
    if policy.get("require_current_worker_plans", True):
        _require_plan_current(root, task_id, worker_plan_id, worker_plan_hash)
    assignment = {
        "supervisor_id": int(supervisor_id),
        "worker_key": key,
        "task_id": str(task_id),
        "plan_id": worker_plan_id,
        "plan_hash": worker_plan_hash,
        "architecture_baseline_hash": worker_baseline_hash,
        "session_id_hash": _sha(session),
        "role": role,
        "selection_run_id": int(selection_run_id) if selection_run_id is not None else None,
        "skill_id": int(skill_id) if skill_id is not None else None,
        "capability_set_hash": capability_hash,
    }
    assignment_hash = _sha(assignment)
    with connect(root) as c:
        cur = c.execute(
            """
            INSERT INTO multi_agent_workers(
                supervisor_id, worker_key, task_id, plan_id, plan_hash, architecture_baseline_hash,
                session_id, role, skill_id, selection_run_id, capability_set_hash,
                assignment_hash, status, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                int(supervisor_id), key, str(task_id), worker_plan_id, worker_plan_hash, worker_baseline_hash,
                session, role, skill_id, selection_run_id, capability_hash, assignment_hash, "registered", _now(),
            ),
        )
        worker_id = int(cur.lastrowid)
    _record_event(
        root,
        supervisor_id,
        "worker_added",
        {"worker_key": key, "task_id": str(task_id), "role": role, "capability_count": capability_count, "assignment_hash": assignment_hash},
        worker_id=worker_id,
    )
    return {"worker_id": worker_id, "worker_key": key, "status": "registered", "assignment_hash": assignment_hash}


def _graph(c, supervisor_id: int) -> dict[int, set[int]]:
    workers = [int(r["id"]) for r in c.execute("SELECT id FROM multi_agent_workers WHERE supervisor_id=? AND status<>'removed'", (int(supervisor_id),)).fetchall()]
    graph = {wid: set() for wid in workers}
    for row in c.execute("SELECT worker_id, depends_on_worker_id FROM multi_agent_worker_dependencies WHERE supervisor_id=?", (int(supervisor_id),)).fetchall():
        graph.setdefault(int(row["worker_id"]), set()).add(int(row["depends_on_worker_id"]))
    return graph


def _cycle(graph: dict[int, set[int]]) -> bool:
    visiting: set[int] = set()
    done: set[int] = set()

    def visit(node: int) -> bool:
        if node in done:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        for dep in graph.get(node, set()):
            if visit(dep):
                return True
        visiting.remove(node)
        done.add(node)
        return False

    return any(visit(node) for node in graph)


def add_dependency(root: Path, supervisor_id: int, worker_key: str, depends_on_worker_key: str) -> dict[str, Any]:
    """Add a DAG dependency between two workers. Cycles fail closed."""
    _policy(root)
    with connect(root) as c:
        supervisor = _supervisor_row(c, supervisor_id)
        if str(supervisor["status"]) not in _MUTABLE_SUPERVISOR_STATES:
            raise PermissionError("supervisor_not_mutable")
        worker = _worker_row(c, supervisor_id, worker_key)
        dependency = _worker_row(c, supervisor_id, depends_on_worker_key)
        if int(worker["id"]) == int(dependency["id"]):
            raise ValueError("worker_dependency_self_cycle")
        c.execute(
            "INSERT OR IGNORE INTO multi_agent_worker_dependencies(supervisor_id,worker_id,depends_on_worker_id,created_at) VALUES(?,?,?,?)",
            (int(supervisor_id), int(worker["id"]), int(dependency["id"]), _now()),
        )
        if _cycle(_graph(c, supervisor_id)):
            c.execute(
                "DELETE FROM multi_agent_worker_dependencies WHERE supervisor_id=? AND worker_id=? AND depends_on_worker_id=?",
                (int(supervisor_id), int(worker["id"]), int(dependency["id"])),
            )
            raise PermissionError("worker_dependency_cycle")
    _record_event(root, supervisor_id, "worker_dependency_added", {"worker_key": worker_key, "depends_on_worker_key": depends_on_worker_key})
    return {"ok": True, "worker_key": worker_key, "depends_on": depends_on_worker_key}


def _worker_freshness(root: Path, worker: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    try:
        _require_plan_current(root, str(worker["task_id"]), int(worker["plan_id"]), str(worker["plan_hash"]))
    except Exception as exc:  # fail-closed aggregation for readiness surface
        reasons.append(str(exc))
    try:
        with connect_read_only(root) as c:
            current_capability_hash, _ = _session_binding(c, str(worker["task_id"]), str(worker["session_id"]))
            if current_capability_hash != str(worker["capability_set_hash"]):
                reasons.append("worker_capability_set_changed")
            _role_binding(c, str(worker["task_id"]), str(worker["session_id"]), str(worker["role"]))
            _selection_binding(c, str(worker["task_id"]), int(worker["plan_id"]), str(worker["plan_hash"]), str(worker["architecture_baseline_hash"] or ""), worker.get("selection_run_id"), worker.get("skill_id"))
    except Exception as exc:
        reasons.append(str(exc))
    return sorted(set(reasons))


def supervisor_readiness(root: Path, supervisor_id: int) -> dict[str, Any]:
    """Return read-only readiness, freshness, overlap findings, and runnable workers."""
    policy = _policy(root)
    with connect_read_only(root) as c:
        supervisor_row = _supervisor_row(c, supervisor_id)
        supervisor = dict(supervisor_row)
        parent_plan = c.execute("SELECT plan_json FROM task_plans WHERE id=?", (int(supervisor["parent_plan_id"]),)).fetchone()
        workers = [dict(r) for r in c.execute("SELECT * FROM multi_agent_workers WHERE supervisor_id=? AND status<>'removed' ORDER BY id", (int(supervisor_id),)).fetchall()]
        dependency_rows = [dict(r) for r in c.execute("SELECT * FROM multi_agent_worker_dependencies WHERE supervisor_id=?", (int(supervisor_id),)).fetchall()]
        graph = _graph(c, supervisor_id)
        worker_plan_payloads = {
            int(w["id"]): _json_obj(c.execute("SELECT plan_json FROM task_plans WHERE id=?", (int(w["plan_id"]),)).fetchone()["plan_json"])
            for w in workers
        }
    reasons: list[str] = []
    try:
        _require_plan_current(root, str(supervisor["parent_task_id"]), int(supervisor["parent_plan_id"]), str(supervisor["parent_plan_hash"]))
    except Exception as exc:
        reasons.append(str(exc))
    if _cycle(graph):
        reasons.append("worker_dependency_cycle")
    if len(workers) == 0:
        reasons.append("no_workers_registered")
    if len(workers) > int(supervisor["worker_limit"]):
        reasons.append("worker_limit_exceeded")

    worker_freshness: dict[str, list[str]] = {}
    for worker in workers:
        wr = _worker_freshness(root, worker)
        worker_freshness[str(worker["worker_key"])] = wr
        reasons.extend(f"{worker['worker_key']}:{reason}" for reason in wr)

    for worker in workers:
        if str(worker["status"]) == "failed":
            reasons.append(f"{worker['worker_key']}:worker_failed")
        elif str(worker["status"]) == "blocked":
            reasons.append(f"{worker['worker_key']}:worker_blocked")

    overlap_findings: list[dict[str, Any]] = []
    if str(policy.get("overlapping_executor_write_targets", "block")) == "block":
        executors = [w for w in workers if str(w["role"]) == "executor" and str(w["status"]) not in _TERMINAL_WORKER_STATES]
        for i, left in enumerate(executors):
            left_files = _plan_files(worker_plan_payloads[int(left["id"])])
            for right in executors[i + 1 :]:
                overlap = sorted(left_files & _plan_files(worker_plan_payloads[int(right["id"])]))
                if overlap:
                    overlap_findings.append({"left": left["worker_key"], "right": right["worker_key"], "files": overlap})
        if overlap_findings:
            reasons.append("overlapping_executor_write_targets")

    dependency_map: dict[int, set[int]] = {int(w["id"]): set() for w in workers}
    for row in dependency_rows:
        dependency_map.setdefault(int(row["worker_id"]), set()).add(int(row["depends_on_worker_id"]))
    statuses = {int(w["id"]): str(w["status"]) for w in workers}
    runnable: list[str] = []
    blocked_by_dependency: dict[str, list[str]] = {}
    key_by_id = {int(w["id"]): str(w["worker_key"]) for w in workers}
    for worker in workers:
        if str(worker["status"]) not in {"registered", "ready"}:
            continue
        if worker_freshness.get(str(worker["worker_key"])):
            continue
        deps = dependency_map.get(int(worker["id"]), set())
        incomplete = [dep for dep in deps if statuses.get(dep) != "completed"]
        failed = [dep for dep in deps if statuses.get(dep) in {"failed", "blocked", "removed"}]
        if failed:
            blocked_by_dependency[str(worker["worker_key"])] = [key_by_id.get(dep, str(dep)) for dep in failed]
        elif not incomplete:
            runnable.append(str(worker["worker_key"]))

    effective_status = str(supervisor["status"])
    if any(str(w["status"]) in {"failed", "blocked"} for w in workers) and effective_status in {"active", "paused"}:
        effective_status = "blocked"
    elif reasons and effective_status in {"active", "paused"}:
        effective_status = "stale"
    elif workers and all(str(w["status"]) == "completed" for w in workers):
        effective_status = "completed"

    workspace_cfg = load_policy(root).get("isolated_workspace_integration_policy", {})
    workspace_enabled = bool(isinstance(workspace_cfg, dict) and workspace_cfg.get("enabled", False))
    return {
        "supervisor_id": int(supervisor_id),
        "stored_status": str(supervisor["status"]),
        "effective_status": effective_status,
        "ready": not reasons,
        "reasons": sorted(set(reasons)),
        "worker_count": len(workers),
        "worker_limit": int(supervisor["worker_limit"]),
        "runnable_workers": sorted(runnable),
        "blocked_by_dependency": blocked_by_dependency,
        "worker_freshness": worker_freshness,
        "overlap_findings": overlap_findings,
        "parent_plan_hash": str(supervisor["parent_plan_hash"]),
        "architecture_baseline_hash": str(supervisor["architecture_baseline_hash"]),
        "automatic_process_launch": False,
        "isolated_workspace": workspace_enabled,
        "controlled_integration": workspace_enabled,
    }


def activate_supervisor(root: Path, supervisor_id: int, approved_by: str) -> dict[str, Any]:
    """Human-activate a valid supervisor; marks registered workers ready but launches no process."""
    human = _human(approved_by)
    readiness = supervisor_readiness(root, supervisor_id)
    if not readiness["ready"]:
        raise PermissionError("supervisor_not_ready:" + ";".join(readiness["reasons"]))
    with connect(root) as c:
        supervisor = _supervisor_row(c, supervisor_id)
        if str(supervisor["status"]) not in _MUTABLE_SUPERVISOR_STATES:
            raise PermissionError("supervisor_not_activatable")
        now = _now()
        c.execute(
            "UPDATE multi_agent_supervisor_runs SET status='active', activated_by=?, activated_at=? WHERE id=?",
            (human, now, int(supervisor_id)),
        )
        c.execute(
            "UPDATE multi_agent_workers SET status='ready' WHERE supervisor_id=? AND status='registered'",
            (int(supervisor_id),),
        )
    _record_event(root, supervisor_id, "supervisor_activated", {"approved_by": human})
    result = supervisor_readiness(root, supervisor_id)
    result["approved_by"] = human
    return result


def pause_supervisor(root: Path, supervisor_id: int, approved_by: str) -> dict[str, Any]:
    human = _human(approved_by)
    with connect(root) as c:
        supervisor = _supervisor_row(c, supervisor_id)
        if str(supervisor["status"]) != "active":
            raise PermissionError("supervisor_not_active")
        running = int(c.execute("SELECT COUNT(*) AS n FROM multi_agent_workers WHERE supervisor_id=? AND status='running'", (int(supervisor_id),)).fetchone()["n"])
        if running:
            raise PermissionError("running_workers_must_finish_or_block_before_pause")
        c.execute("UPDATE multi_agent_supervisor_runs SET status='paused' WHERE id=?", (int(supervisor_id),))
    _record_event(root, supervisor_id, "supervisor_paused", {"approved_by": human})
    return supervisor_readiness(root, supervisor_id)


def cancel_supervisor(root: Path, supervisor_id: int, approved_by: str) -> dict[str, Any]:
    human = _human(approved_by)
    with connect(root) as c:
        supervisor = _supervisor_row(c, supervisor_id)
        if str(supervisor["status"]) in {"completed", "cancelled"}:
            raise PermissionError("supervisor_already_terminal")
        running = int(c.execute("SELECT COUNT(*) AS n FROM multi_agent_workers WHERE supervisor_id=? AND status='running'", (int(supervisor_id),)).fetchone()["n"])
        if running:
            raise PermissionError("running_workers_must_finish_or_block_before_cancel")
        c.execute("UPDATE multi_agent_supervisor_runs SET status='cancelled', completed_at=? WHERE id=?", (_now(), int(supervisor_id)))
    _record_event(root, supervisor_id, "supervisor_cancelled", {"approved_by": human})
    return {"supervisor_id": int(supervisor_id), "status": "cancelled", "approved_by": human}


def worker_start(root: Path, supervisor_id: int, worker_key: str, caller_task_id: str, caller_session_id: str) -> dict[str, Any]:
    """Mark an assigned worker running after rechecking dependency/freshness. Does not launch a process."""
    workspace_cfg = load_policy(root).get("isolated_workspace_integration_policy", {})
    if isinstance(workspace_cfg, dict) and workspace_cfg.get("enabled", False) and workspace_cfg.get("require_workspace_before_executor_start", True):
        from .multi_agent_workspace import require_executor_workspace
        require_executor_workspace(root, supervisor_id, worker_key, sealed=False)
    readiness = supervisor_readiness(root, supervisor_id)
    if readiness["effective_status"] != "active":
        raise PermissionError("supervisor_not_effectively_active")
    if str(worker_key) not in set(readiness["runnable_workers"]):
        raise PermissionError("worker_not_runnable")
    with connect(root) as c:
        worker = _worker_row(c, supervisor_id, worker_key)
        if str(worker["task_id"]) != str(caller_task_id) or str(worker["session_id"]) != str(caller_session_id):
            raise PermissionError("worker_assignment_owner_mismatch")
        if str(worker["status"]) != "ready":
            raise PermissionError("worker_not_ready")
        now = _now()
        c.execute(
            "UPDATE multi_agent_workers SET status='running', started_at=COALESCE(started_at,?), last_heartbeat_at=? WHERE id=?",
            (now, now, int(worker["id"])),
        )
        worker_id = int(worker["id"])
    _record_event(root, supervisor_id, "worker_started", {"worker_key": worker_key, "task_id": str(caller_task_id)}, worker_id=worker_id)
    return {"supervisor_id": int(supervisor_id), "worker_key": worker_key, "status": "running", "process_launched": False}


def worker_completion_subject(root: Path, supervisor_id: int, worker_key: str) -> dict[str, Any]:
    """Return deterministic hashable state for one worker completion candidate."""
    with connect_read_only(root) as c:
        worker = dict(_worker_row(c, supervisor_id, worker_key))
        supervisor = dict(_supervisor_row(c, supervisor_id))
        workspace = None
        has_workspace = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='multi_agent_workspaces'"
        ).fetchone()
        if has_workspace:
            row = c.execute(
                "SELECT id,status,base_commit,diff_manifest_hash,collected_at,sealed_at FROM multi_agent_workspaces WHERE worker_id=?",
                (int(worker["id"]),),
            ).fetchone()
            if row:
                workspace = {
                    "workspace_id": int(row["id"]),
                    "status": str(row["status"]),
                    "base_commit": str(row["base_commit"]),
                    "diff_manifest_hash": row["diff_manifest_hash"],
                    "collected_at": row["collected_at"],
                    "sealed_at": row["sealed_at"],
                }
    return {
        "supervisor_id": int(supervisor_id),
        "supervisor_hash": str(supervisor["supervisor_hash"]),
        "parent_task_id": str(supervisor["parent_task_id"]),
        "parent_plan_id": int(supervisor["parent_plan_id"]),
        "parent_plan_hash": str(supervisor["parent_plan_hash"]),
        "worker_id": int(worker["id"]),
        "worker_key": str(worker["worker_key"]),
        "task_id": str(worker["task_id"]),
        "session_id": str(worker["session_id"]),
        "role": str(worker["role"]),
        "plan_id": int(worker["plan_id"]),
        "plan_hash": str(worker["plan_hash"]),
        "architecture_baseline_hash": str(worker["architecture_baseline_hash"]),
        "assignment_hash": str(worker["assignment_hash"]),
        "capability_set_hash": str(worker["capability_set_hash"]),
        "workspace": workspace,
    }


def worker_completion_request(root: Path, supervisor_id: int, worker_key: str, caller_task_id: str, caller_session_id: str) -> dict[str, Any]:
    """Create a completion candidate; producer cannot terminalize itself."""
    with connect_read_only(root) as c:
        worker = dict(_worker_row(c, supervisor_id, worker_key))
    if str(worker["task_id"]) != str(caller_task_id) or str(worker["session_id"]) != str(caller_session_id):
        raise PermissionError("worker_assignment_owner_mismatch")
    if str(worker["status"]) != "running":
        raise PermissionError("worker_not_running")
    workspace_cfg = load_policy(root).get("isolated_workspace_integration_policy", {})
    if (
        str(worker["role"]) == "executor"
        and isinstance(workspace_cfg, dict)
        and workspace_cfg.get("enabled", False)
        and workspace_cfg.get("require_sealed_workspace_before_executor_complete", True)
    ):
        from .multi_agent_workspace import require_executor_workspace
        require_executor_workspace(root, supervisor_id, worker_key, sealed=True)
    from .completion_verification import request_completion
    subject = worker_completion_subject(root, supervisor_id, worker_key)
    return request_completion(
        root,
        subject_type="multi_agent_worker",
        subject_id=f"{int(supervisor_id)}:{worker_key}",
        task_id=str(worker["task_id"]),
        producer_task_id=str(caller_task_id),
        producer_session_id=str(caller_session_id),
        subject_payload=subject,
        required_checks=["evidence", "tests"],
    )


def worker_completion_verify(
    root: Path,
    request_id: str,
    verifier_task_id: str,
    verifier_session_id: str,
    *,
    verdict: str,
    checks: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Verify current worker state and terminalize only on independent pass."""
    from .completion_verification import require_current_verification, verify_completion
    with connect_read_only(root) as c:
        request = c.execute(
            "SELECT subject_type,subject_id FROM completion_verification_requests WHERE request_id=?",
            (str(request_id),),
        ).fetchone()
        if not request:
            raise ValueError("completion_verification_request_not_found")
        if str(request["subject_type"]) != "multi_agent_worker":
            raise PermissionError("worker_completion_request_type_required")
        try:
            supervisor_text, worker_key = str(request["subject_id"]).split(":", 1)
            supervisor_id = int(supervisor_text)
        except Exception as exc:
            raise RuntimeError("invalid_worker_completion_subject_id") from exc
    subject = worker_completion_subject(root, supervisor_id, worker_key)
    result = verify_completion(
        root,
        request_id=str(request_id),
        verifier_task_id=str(verifier_task_id),
        verifier_session_id=str(verifier_session_id),
        observed_subject_payload=subject,
        verdict=str(verdict),
        checks=checks,
        evidence=evidence,
    )
    if str(result["verdict"]) != "pass":
        return {**result, "worker_status": "running", "supervisor_completed": False}
    current_subject = worker_completion_subject(root, supervisor_id, worker_key)
    require_current_verification(
        root,
        subject_type="multi_agent_worker",
        subject_id=f"{int(supervisor_id)}:{worker_key}",
        current_subject_payload=current_subject,
    )
    with connect(root, immediate=True) as c:
        worker = _worker_row(c, supervisor_id, worker_key)
        if str(worker["status"]) != "running":
            raise PermissionError("worker_not_running")
        now = _now()
        c.execute(
            "UPDATE multi_agent_workers SET status='completed',last_heartbeat_at=?,completed_at=? WHERE id=?",
            (now, now, int(worker["id"])),
        )
        worker_id = int(worker["id"])
        pending = int(c.execute(
            "SELECT COUNT(*) AS n FROM multi_agent_workers WHERE supervisor_id=? AND status NOT IN ('completed','removed')",
            (int(supervisor_id),),
        ).fetchone()["n"])
        completed_supervisor = False
        if pending == 0:
            c.execute(
                "UPDATE multi_agent_supervisor_runs SET status='completed',completed_at=? WHERE id=? AND status='active'",
                (now, int(supervisor_id)),
            )
            completed_supervisor = True
    _record_event(
        root,
        supervisor_id,
        "worker_completion_verified",
        {
            "worker_key": worker_key,
            "request_id": str(request_id),
            "verification_result_hash": str(result["result_hash"]),
            "verifier_task_id": str(verifier_task_id),
            "verifier_session_id": str(verifier_session_id),
        },
        worker_id=worker_id,
    )
    if completed_supervisor:
        _record_event(
            root,
            supervisor_id,
            "supervisor_completed",
            {"trigger_worker_key": worker_key, "completion_request_id": str(request_id)},
            worker_id=worker_id,
        )
    return {**result, "worker_status": "completed", "supervisor_completed": completed_supervisor}


def worker_update(root: Path, supervisor_id: int, worker_key: str, caller_task_id: str, caller_session_id: str, status: str) -> dict[str, Any]:
    """Update a running worker to failed/blocked; completion requires independent verification."""
    target = str(status)
    if target == "completed":
        raise PermissionError("independent_completion_verification_required")
    if target not in {"failed", "blocked"}:
        raise ValueError("unsupported_worker_update_status")
    with connect(root) as c:
        worker = _worker_row(c, supervisor_id, worker_key)
        if str(worker["task_id"]) != str(caller_task_id) or str(worker["session_id"]) != str(caller_session_id):
            raise PermissionError("worker_assignment_owner_mismatch")
        if str(worker["status"]) != "running":
            raise PermissionError("worker_not_running")
        now = _now()
        c.execute(
            "UPDATE multi_agent_workers SET status=?, last_heartbeat_at=?, completed_at=? WHERE id=?",
            (target, now, now if target in {"completed", "failed"} else None, int(worker["id"])),
        )
        worker_id = int(worker["id"])
    _record_event(root, supervisor_id, "worker_status_updated", {"worker_key": worker_key, "status": target}, worker_id=worker_id)
    return {"supervisor_id": int(supervisor_id), "worker_key": worker_key, "status": target, "supervisor_completed": False}


def supervisor_status(root: Path, supervisor_id: int) -> dict[str, Any]:
    """Read-only supervisor status with hashes and computed readiness, never session token material."""
    readiness = supervisor_readiness(root, supervisor_id)
    with connect_read_only(root) as c:
        row = dict(_supervisor_row(c, supervisor_id))
    return {
        **readiness,
        "parent_task_id": str(row["parent_task_id"]),
        "parent_plan_id": int(row["parent_plan_id"]),
        "supervisor_hash": str(row["supervisor_hash"]),
        "created_by": str(row["created_by"]),
        "activated_by": row["activated_by"],
        "created_at": str(row["created_at"]),
        "activated_at": row["activated_at"],
    }


def supervisor_workers(root: Path, supervisor_id: int) -> dict[str, Any]:
    """Return redacted worker assignments and dependency keys for read-only diagnostics."""
    _policy(root)
    with connect_read_only(root) as c:
        _supervisor_row(c, supervisor_id)
        workers = [dict(r) for r in c.execute("SELECT * FROM multi_agent_workers WHERE supervisor_id=? ORDER BY id", (int(supervisor_id),)).fetchall()]
        dependencies = [dict(r) for r in c.execute("SELECT worker_id, depends_on_worker_id FROM multi_agent_worker_dependencies WHERE supervisor_id=?", (int(supervisor_id),)).fetchall()]
    key_by_id = {int(w["id"]): str(w["worker_key"]) for w in workers}
    deps_by_id: dict[int, list[str]] = {int(w["id"]): [] for w in workers}
    for dep in dependencies:
        deps_by_id.setdefault(int(dep["worker_id"]), []).append(key_by_id.get(int(dep["depends_on_worker_id"]), str(dep["depends_on_worker_id"])))
    payload = []
    for worker in workers:
        payload.append(
            {
                "worker_key": str(worker["worker_key"]),
                "task_id": str(worker["task_id"]),
                "plan_id": int(worker["plan_id"]),
                "plan_hash": str(worker["plan_hash"]),
                "architecture_baseline_hash": str(worker["architecture_baseline_hash"]),
                "session_id_hash": _sha(str(worker["session_id"])),
                "role": str(worker["role"]),
                "skill_id": worker["skill_id"],
                "selection_run_id": worker["selection_run_id"],
                "capability_set_hash": str(worker["capability_set_hash"]),
                "assignment_hash": str(worker["assignment_hash"]),
                "status": str(worker["status"]),
                "depends_on": sorted(deps_by_id.get(int(worker["id"]), [])),
                "last_heartbeat_at": worker["last_heartbeat_at"],
            }
        )
    return {"supervisor_id": int(supervisor_id), "workers": payload}
