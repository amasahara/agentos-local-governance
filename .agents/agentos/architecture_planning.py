"""Path: .agents/agentos/architecture_planning.py
Purpose: Bind task plans to the human-activated Architecture Contract for AgentOS v0.26.0.

Responsibilities:
    - Pin each architecture-aware plan to the exact ACTIVE baseline hash.
    - Canonicalize requirements, affected sections, expected modules/edges/files, and acceptance criteria.
    - Run deterministic pre-approval architecture impact checks without mutating architecture authority.
    - Mark affected plans stale when the architecture baseline changes.
    - Expose read-only planning context/status for CLI and MCP clients.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .architecture_contract import SECTION_BY_ID
from .architecture_compliance import architecture_target_check_from_sections
from .db import connect, connect_read_only

MIGRATION_VERSION = 54
PLANNING_CONTRACT_VERSION = 1
_STATES = {"not_evaluable", "bound", "stale"}


def migration_54(connection: Any) -> None:
    """Add architecture-aware task-plan binding and event state."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS task_plan_architecture_contexts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL UNIQUE,
            task_id TEXT NOT NULL,
            baseline_id INTEGER,
            baseline_hash TEXT,
            state TEXT NOT NULL CHECK(state IN ('not_evaluable','bound','stale')),
            requirements_json TEXT NOT NULL,
            affected_sections_json TEXT NOT NULL,
            expected_modules_json TEXT NOT NULL,
            expected_dependency_edges_json TEXT NOT NULL,
            expected_files_json TEXT NOT NULL,
            acceptance_criteria_json TEXT NOT NULL,
            impact_json TEXT NOT NULL,
            impact_hash TEXT NOT NULL,
            stale_reason TEXT,
            stale_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES task_plans(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            FOREIGN KEY(baseline_id) REFERENCES architecture_baselines(id)
        );
        CREATE INDEX IF NOT EXISTS idx_task_plan_arch_context_task
            ON task_plan_architecture_contexts(task_id,state,plan_id);
        CREATE INDEX IF NOT EXISTS idx_task_plan_arch_context_baseline
            ON task_plan_architecture_contexts(baseline_id,state,plan_id);
        CREATE TABLE IF NOT EXISTS task_plan_architecture_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES task_plans(id)
        );
        CREATE INDEX IF NOT EXISTS idx_task_plan_arch_events_plan
            ON task_plan_architecture_events(plan_id,id);
        """
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _strings(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{name}_must_be_list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"{name}_must_contain_nonempty_strings")
        normalized = item.strip().replace("\\", "/")
        if normalized not in out:
            out.append(normalized)
    return out


def _active_baseline(connection: Any) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM architecture_baselines WHERE status='active' ORDER BY baseline_version DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _baseline_sections(connection: Any, baseline_id: int) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """SELECT bs.section_id,sr.contract_json,sr.section_hash
           FROM architecture_baseline_sections bs
           JOIN architecture_section_revisions sr ON sr.id=bs.section_revision_id
           WHERE bs.baseline_id=? ORDER BY bs.section_id""",
        (baseline_id,),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        contract = json.loads(row["contract_json"])
        if not isinstance(contract, dict):
            contract = {}
        out[str(row["section_id"])] = {
            "payload": contract.get("payload") if isinstance(contract.get("payload"), dict) else {},
            "contract": contract,
            "section_hash": str(row["section_hash"]),
        }
    return out


def _edge_list(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError("expected_dependency_edges_must_be_list")
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeError("expected_dependency_edges_must_contain_objects")
        source = str(item.get("from") or item.get("source") or "").strip()
        target = str(item.get("import") or item.get("to") or item.get("target") or "").strip()
        if not source or not target:
            raise RuntimeError("expected_dependency_edge_requires_from_and_import")
        normalized = {"from": source, "import": target}
        if normalized not in out:
            out.append(normalized)
    return out


def _matches(value: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


def _contract_strings(payload: dict[str, Any], key: str) -> list[str]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _dependency_edge_blockers(sections: dict[str, dict[str, Any]], edges: list[dict[str, str]]) -> list[dict[str, Any]]:
    payload = sections.get("ARCH-12", {}).get("payload", {})
    forbidden_imports = _contract_strings(payload, "forbidden_imports")
    raw_edges = payload.get("forbidden_import_edges")
    forbidden_edges = raw_edges if isinstance(raw_edges, list) else []
    blockers: list[dict[str, Any]] = []
    for edge in edges:
        imported = edge["import"]
        if forbidden_imports and _matches(imported, forbidden_imports):
            blockers.append({"code": "architecture_plan_forbidden_import", "section_id": "ARCH-12", "edge": edge})
            continue
        for rule in forbidden_edges:
            if not isinstance(rule, dict):
                continue
            source_rule = str(rule.get("from") or "*")
            import_rule = str(rule.get("import") or rule.get("to") or "*")
            if fnmatch.fnmatch(edge["from"], source_rule) and fnmatch.fnmatch(imported, import_rule):
                blockers.append({"code": "architecture_plan_forbidden_dependency_edge", "section_id": "ARCH-12", "edge": edge, "rule": {"from": source_rule, "import": import_rule}})
                break
    return blockers


def _module_blockers(sections: dict[str, dict[str, Any]], modules: list[str]) -> list[dict[str, Any]]:
    payload = sections.get("ARCH-05", {}).get("payload", {})
    forbidden = _contract_strings(payload, "forbidden_module_paths")
    blockers: list[dict[str, Any]] = []
    for module in modules:
        candidate = module.replace(".", "/") if "/" not in module and not module.endswith(".py") else module
        if forbidden and _matches(candidate, forbidden):
            blockers.append({"code": "architecture_plan_forbidden_module", "section_id": "ARCH-05", "module": module})
    return blockers


def analyze_plan_on_connection(connection: Any, task_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic architecture impact envelope for one plan."""
    if not isinstance(plan, dict):
        raise RuntimeError("plan_must_be_object")
    files = _strings(plan.get("files"), "files")
    requirements = _strings(plan.get("requirements"), "requirements")
    acceptance = _strings(plan.get("acceptance_criteria", plan.get("acceptance")), "acceptance_criteria")
    architecture = plan.get("architecture") or {}
    if not isinstance(architecture, dict):
        raise RuntimeError("architecture_plan_envelope_must_be_object")
    affected_present = "affected_architecture_sections" in plan or "affected_sections" in architecture
    modules_present = "expected_modules" in plan or "expected_modules" in architecture
    edges_present = "expected_dependency_edges" in plan or "expected_dependency_edges" in architecture
    affected = _strings(plan.get("affected_architecture_sections", architecture.get("affected_sections")), "affected_architecture_sections")
    modules = _strings(plan.get("expected_modules", architecture.get("expected_modules")), "expected_modules")
    edges = _edge_list(plan.get("expected_dependency_edges", architecture.get("expected_dependency_edges")))
    expected_dependencies = _strings(plan.get("expected_dependencies", architecture.get("expected_dependencies")), "expected_dependencies")
    expected_languages = _strings(plan.get("expected_languages", architecture.get("expected_languages")), "expected_languages")
    declared_expected_files = architecture.get("expected_files", plan.get("expected_files"))
    expected_files = _strings(declared_expected_files, "expected_files") if declared_expected_files is not None else list(files)
    invalid_sections = [item for item in affected if item not in SECTION_BY_ID]
    if invalid_sections:
        raise RuntimeError(f"invalid_affected_architecture_sections:{invalid_sections}")

    baseline = _active_baseline(connection)
    base_envelope = {
        "contract_version": PLANNING_CONTRACT_VERSION,
        "task_id": task_id,
        "requirements": requirements,
        "affected_architecture_sections": affected,
        "expected_modules": modules,
        "expected_dependency_edges": edges,
        "expected_dependencies": expected_dependencies,
        "expected_languages": expected_languages,
        "expected_files": expected_files,
        "acceptance_criteria": acceptance,
    }
    if not baseline:
        impact = {**base_envelope, "state": "not_evaluable", "enforced": False, "baseline_id": None, "architecture_baseline_hash": None, "blockers": []}
        impact["impact_hash"] = _sha(impact)
        return {"ready": True, **impact}

    supplied_hash = plan.get("architecture_baseline_hash")
    if supplied_hash is not None and str(supplied_hash) != str(baseline["baseline_hash"]):
        raise RuntimeError("architecture_plan_supplied_baseline_hash_mismatch")
    blockers: list[dict[str, Any]] = []
    if not requirements:
        blockers.append({"code": "architecture_plan_requirements_required"})
    if not acceptance:
        blockers.append({"code": "architecture_plan_acceptance_criteria_required"})
    if not affected_present:
        blockers.append({"code": "architecture_plan_affected_sections_declaration_required"})
    if not modules_present:
        blockers.append({"code": "architecture_plan_expected_modules_declaration_required"})
    if not edges_present:
        blockers.append({"code": "architecture_plan_expected_dependency_edges_declaration_required"})
    if set(expected_files) != set(files):
        blockers.append({"code": "architecture_plan_expected_files_must_match_plan_files", "plan_files": files, "expected_files": expected_files})
    sections = _baseline_sections(connection, int(baseline["id"]))
    from .architecture_structural import analyze_plan_structure_on_connection
    structural = analyze_plan_structure_on_connection(connection, plan, sections, expected_files, modules, edges)
    blockers.extend(structural.get("blockers", []))
    base_envelope["expected_dependencies"] = list(structural.get("expected_dependencies", expected_dependencies))
    base_envelope["expected_languages"] = list(structural.get("expected_languages", expected_languages))
    base_envelope["inferred_languages"] = list(structural.get("inferred_languages", []))
    for path in expected_files:
        result = architecture_target_check_from_sections(sections, path)
        if not result.get("allowed", True):
            blockers.append({"code": str(result.get("reason") or "architecture_plan_target_blocked"), "section_id": result.get("section_id"), "target": path})
    blockers.extend(_module_blockers(sections, modules))
    blockers.extend(_dependency_edge_blockers(sections, edges))
    impact = {
        **base_envelope,
        "state": "bound",
        "enforced": True,
        "baseline_id": int(baseline["id"]),
        "architecture_baseline_hash": str(baseline["baseline_hash"]),
        "blockers": blockers,
    }
    impact["impact_hash"] = _sha(impact)
    return {"ready": not blockers, **impact}


def enrich_plan(plan: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """Return canonical persisted plan data with system-owned architecture pins."""
    out = json.loads(json.dumps(plan))
    out["requirements"] = list(analysis["requirements"])
    out["affected_architecture_sections"] = list(analysis["affected_architecture_sections"])
    out["expected_modules"] = list(analysis["expected_modules"])
    out["expected_dependency_edges"] = list(analysis["expected_dependency_edges"])
    out["expected_dependencies"] = list(analysis.get("expected_dependencies", []))
    out["expected_languages"] = list(analysis.get("expected_languages", []))
    out["expected_files"] = list(analysis["expected_files"])
    out["acceptance_criteria"] = list(analysis["acceptance_criteria"])
    out["architecture_baseline_hash"] = analysis.get("architecture_baseline_hash")
    out["architecture_impact_hash"] = analysis["impact_hash"]
    return out


def _event(connection: Any, plan_id: int, event_type: str, payload: dict[str, Any]) -> None:
    event = {"plan_id": plan_id, "event_type": event_type, **payload}
    connection.execute(
        "INSERT INTO task_plan_architecture_events(plan_id,event_type,event_json,event_hash) VALUES(?,?,?,?)",
        (plan_id, event_type, _canonical(event), _sha(event)),
    )


def bind_plan_on_connection(connection: Any, plan_id: int, task_id: str, analysis: dict[str, Any]) -> None:
    """Persist the immutable architecture context associated with one plan revision."""
    impact = {key: value for key, value in analysis.items() if key != "ready"}
    connection.execute(
        """INSERT INTO task_plan_architecture_contexts(
            plan_id,task_id,baseline_id,baseline_hash,state,requirements_json,affected_sections_json,
            expected_modules_json,expected_dependency_edges_json,expected_files_json,acceptance_criteria_json,
            impact_json,impact_hash
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            plan_id,
            task_id,
            analysis.get("baseline_id"),
            analysis.get("architecture_baseline_hash"),
            analysis["state"],
            _canonical(analysis["requirements"]),
            _canonical(analysis["affected_architecture_sections"]),
            _canonical(analysis["expected_modules"]),
            _canonical(analysis["expected_dependency_edges"]),
            _canonical(analysis["expected_files"]),
            _canonical(analysis["acceptance_criteria"]),
            _canonical(impact),
            analysis["impact_hash"],
        ),
    )
    _event(connection, plan_id, "architecture_plan.bound", {"state": analysis["state"], "baseline_hash": analysis.get("architecture_baseline_hash"), "impact_hash": analysis["impact_hash"]})


def _decode_context(row: Any) -> dict[str, Any]:
    value = dict(row)
    for column in ("requirements_json", "affected_sections_json", "expected_modules_json", "expected_dependency_edges_json", "expected_files_json", "acceptance_criteria_json", "impact_json"):
        value[column.removesuffix("_json")] = json.loads(value.pop(column))
    return value


def context_for_plan_on_connection(connection: Any, plan_id: int) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM task_plan_architecture_contexts WHERE plan_id=?", (plan_id,)).fetchone()
    return _decode_context(row) if row else None


def _mark_stale(connection: Any, plan_id: int, reason: str) -> bool:
    context = connection.execute("SELECT state FROM task_plan_architecture_contexts WHERE plan_id=?", (plan_id,)).fetchone()
    if not context or context["state"] == "stale":
        return False
    connection.execute(
        "UPDATE task_plan_architecture_contexts SET state='stale',stale_reason=?,stale_at=CURRENT_TIMESTAMP WHERE plan_id=?",
        (reason, plan_id),
    )
    connection.execute("UPDATE task_plans SET status='stale' WHERE id=? AND status IN ('submitted','active')", (plan_id,))
    _event(connection, plan_id, "architecture_plan.stale", {"reason": reason})
    return True


def approval_check_on_connection(connection: Any, plan_id: int) -> dict[str, Any]:
    """Fail closed when a submitted plan no longer matches architecture authority."""
    context = context_for_plan_on_connection(connection, plan_id)
    if not context:
        return {"ready": False, "reason": "architecture_plan_context_missing"}
    baseline = _active_baseline(connection)
    if context["state"] == "stale":
        return {"ready": False, "reason": context.get("stale_reason") or "architecture_plan_stale", "context": context}
    if context["state"] == "not_evaluable":
        if baseline:
            _mark_stale(connection, plan_id, "architecture_baseline_became_active")
            return {"ready": False, "reason": "architecture_baseline_became_active"}
        return {"ready": True, "reason": "architecture_not_evaluable_no_active_baseline", "context": context}
    if not baseline or str(baseline["baseline_hash"]) != str(context.get("baseline_hash")):
        _mark_stale(connection, plan_id, "architecture_baseline_changed")
        return {"ready": False, "reason": "architecture_baseline_changed"}
    return {"ready": True, "reason": "architecture_plan_current", "context": context}


def mark_plans_stale_for_baseline_change(connection: Any, old_baseline_id: int | None, new_baseline_id: int) -> dict[str, Any]:
    """Mark only affected bound plans stale; unknown/not-evaluable plans fail closed conservatively."""
    if old_baseline_id is None:
        rows = connection.execute(
            """SELECT c.plan_id FROM task_plan_architecture_contexts c
               JOIN task_plans p ON p.id=c.plan_id
               WHERE c.state='not_evaluable' AND p.status IN ('submitted','active')"""
        ).fetchall()
        stale = sum(1 for row in rows if _mark_stale(connection, int(row["plan_id"]), "architecture_baseline_became_active"))
        return {"stale_plan_count": stale, "changed_sections": list(SECTION_BY_ID)}
    old = {str(row["section_id"]): str(row["section_hash"]) for row in connection.execute("SELECT section_id,section_hash FROM architecture_baseline_sections WHERE baseline_id=?", (old_baseline_id,)).fetchall()}
    new = {str(row["section_id"]): str(row["section_hash"]) for row in connection.execute("SELECT section_id,section_hash FROM architecture_baseline_sections WHERE baseline_id=?", (new_baseline_id,)).fetchall()}
    changed = sorted(section_id for section_id in SECTION_BY_ID if old.get(section_id) != new.get(section_id))
    rows = connection.execute(
        """SELECT c.plan_id,c.affected_sections_json FROM task_plan_architecture_contexts c
           JOIN task_plans p ON p.id=c.plan_id
           WHERE c.baseline_id=? AND c.state='bound' AND p.status IN ('submitted','active')""",
        (old_baseline_id,),
    ).fetchall()
    stale = 0
    for row in rows:
        affected = set(json.loads(row["affected_sections_json"]))
        if not affected or affected.intersection(changed):
            stale += int(_mark_stale(connection, int(row["plan_id"]), "architecture_baseline_changed"))
    return {"stale_plan_count": stale, "changed_sections": changed}


def architecture_plan_get(root: Path | str, *, plan_id: int | None = None, task_id: str | None = None) -> dict[str, Any]:
    """Read one architecture-aware plan context without mutation."""
    if plan_id is None and not task_id:
        raise RuntimeError("plan_id_or_task_id_required")
    with connect_read_only(Path(root).resolve()) as connection:
        if plan_id is not None:
            row = connection.execute("SELECT * FROM task_plans WHERE id=?", (plan_id,)).fetchone()
        else:
            row = connection.execute("SELECT * FROM task_plans WHERE task_id=? ORDER BY revision DESC LIMIT 1", (task_id,)).fetchone()
        if not row:
            return {"ok": False, "status": "missing", "plan_id": plan_id, "task_id": task_id}
        plan = dict(row)
        plan["plan"] = json.loads(plan.pop("plan_json"))
        context = context_for_plan_on_connection(connection, int(plan["id"]))
        return {"ok": True, "plan": plan, "architecture": context}


def architecture_plan_status(root: Path | str, task_id: str) -> dict[str, Any]:
    """Return current plan/baseline relation without changing stale state."""
    with connect_read_only(Path(root).resolve()) as connection:
        baseline = _active_baseline(connection)
        row = connection.execute("SELECT * FROM task_plans WHERE task_id=? ORDER BY revision DESC LIMIT 1", (task_id,)).fetchone()
        if not row:
            return {"ok": True, "task_id": task_id, "plan": None, "active_baseline": baseline, "ready": False, "reason": "plan_missing"}
        context = context_for_plan_on_connection(connection, int(row["id"]))
        ready = False
        reason = "architecture_plan_context_missing"
        if context:
            if context["state"] == "stale":
                reason = context.get("stale_reason") or "architecture_plan_stale"
            elif context["state"] == "not_evaluable":
                ready = baseline is None
                reason = "architecture_not_evaluable_no_active_baseline" if ready else "architecture_baseline_became_active"
            elif baseline and str(baseline["baseline_hash"]) == str(context.get("baseline_hash")):
                ready = True
                reason = "architecture_plan_current"
            else:
                reason = "architecture_baseline_changed"
        return {"ok": True, "task_id": task_id, "plan_id": int(row["id"]), "plan_revision": int(row["revision"]), "plan_status": row["status"], "ready": ready, "reason": reason, "active_baseline": baseline, "architecture": context}


def architecture_plan_impact(root: Path | str, task_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Read-only deterministic impact analysis for a prospective plan."""
    with connect_read_only(Path(root).resolve()) as connection:
        return analyze_plan_on_connection(connection, task_id, plan)
