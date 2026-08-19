"""
File: .agents/agentos/skill_selection.py

Purpose:
    Provide deterministic, architecture-aware advisory skill selection and
    observational skill evaluation for AgentOS v0.27.1.

Responsibilities:
    - Rank only graduated Governed Skill Contract v2 skills that remain current.
    - Bind selection evidence to the active task plan and Architecture Baseline.
    - Enforce least-authority compatibility for scopes, capabilities, tools,
      dependencies, external services, architecture sections, and test suites.
    - Persist hashes/counts/decision metadata without persisting the raw request.
    - Evaluate completed selected skills from existing task outcomes without
      changing skill lifecycle, future ranking weights, plans, or authority.
    - Expose read-only selection/evaluation inspection for MCP.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

from .db import connect, connect_read_only
from .policy import load_policy
from .planning import active_plan
from .architecture_planning import architecture_plan_status
from .skill_contract_v2 import validate_contract_shape

MIGRATION_VERSION = 59
SELECTION_VERSION = 1
EVALUATION_VERSION = 1
SELECTION_ALGORITHM = "architecture_aware_skill_selection_v1"
EVALUATION_ALGORITHM = "architecture_aware_skill_evaluation_v1"


def migration_59(c) -> None:
    """Add architecture-aware skill selection/evaluation observability state."""
    c.executescript("""
    CREATE TABLE IF NOT EXISTS skill_selection_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        plan_id INTEGER NOT NULL,
        plan_hash TEXT NOT NULL,
        architecture_baseline_id INTEGER,
        architecture_baseline_hash TEXT,
        selection_input_hash TEXT NOT NULL,
        query_hash TEXT NOT NULL,
        algorithm TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('recommended','no_eligible','not_ready')),
        recommended_skill_id INTEGER,
        candidate_count INTEGER NOT NULL DEFAULT 0,
        eligible_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(plan_id) REFERENCES task_plans(id),
        FOREIGN KEY(architecture_baseline_id) REFERENCES architecture_baselines(id),
        FOREIGN KEY(recommended_skill_id) REFERENCES promoted_skills(id)
    );
    CREATE INDEX IF NOT EXISTS idx_skill_selection_runs_task ON skill_selection_runs(task_id,id);
    CREATE INDEX IF NOT EXISTS idx_skill_selection_runs_plan ON skill_selection_runs(plan_id,id);

    CREATE TABLE IF NOT EXISTS skill_selection_candidates(
        selection_run_id INTEGER NOT NULL,
        skill_id INTEGER NOT NULL,
        rank INTEGER NOT NULL,
        eligible INTEGER NOT NULL CHECK(eligible IN (0,1)),
        recommendable INTEGER NOT NULL CHECK(recommendable IN (0,1)),
        score INTEGER NOT NULL,
        lexical_score INTEGER NOT NULL,
        architecture_overlap INTEGER NOT NULL,
        scope_match_count INTEGER NOT NULL,
        blockers_json TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        architecture_baseline_hash TEXT,
        PRIMARY KEY(selection_run_id,skill_id),
        FOREIGN KEY(selection_run_id) REFERENCES skill_selection_runs(id),
        FOREIGN KEY(skill_id) REFERENCES promoted_skills(id)
    );
    CREATE INDEX IF NOT EXISTS idx_skill_selection_candidates_rank ON skill_selection_candidates(selection_run_id,rank);

    CREATE TABLE IF NOT EXISTS skill_evaluation_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        selection_run_id INTEGER NOT NULL,
        task_id TEXT NOT NULL,
        skill_id INTEGER NOT NULL,
        outcome_id INTEGER NOT NULL,
        evaluation_version INTEGER NOT NULL DEFAULT 1,
        algorithm TEXT NOT NULL,
        evaluation_status TEXT NOT NULL CHECK(evaluation_status IN ('positive','mixed','negative','stale_context')),
        evaluation_json TEXT NOT NULL,
        evaluation_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(selection_run_id) REFERENCES skill_selection_runs(id),
        FOREIGN KEY(task_id) REFERENCES tasks(id),
        FOREIGN KEY(skill_id) REFERENCES promoted_skills(id),
        FOREIGN KEY(outcome_id) REFERENCES task_outcomes(id)
    );
    CREATE INDEX IF NOT EXISTS idx_skill_evaluation_runs_task ON skill_evaluation_runs(task_id,id);
    CREATE INDEX IF NOT EXISTS idx_skill_evaluation_runs_selection ON skill_evaluation_runs(selection_run_id,id);
    """)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    text = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tokens(text: str) -> set[str]:
    """Return deterministic Unicode lexical terms without external models."""
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    return {token for token in re.findall(r"[^\W\d_][\w.-]{1,}", normalized, flags=re.UNICODE) if len(token) >= 2}


def _json_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _norm_path(value: str) -> str:
    return PurePosixPath(str(value).replace("\\", "/")).as_posix().lstrip("./")


def _scope_allows(path: str, scope: str) -> bool:
    candidate = _norm_path(path)
    rule = _norm_path(scope)
    if not rule:
        return False
    if any(ch in rule for ch in "*?["):
        return fnmatch.fnmatchcase(candidate, rule)
    return candidate == rule or candidate.startswith(rule.rstrip("/") + "/")


def _selection_policy(root: Path) -> dict[str, Any]:
    policy = load_policy(root)
    cfg = policy.get("architecture_aware_skill_selection_policy")
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        raise RuntimeError("architecture_aware_skill_selection_policy_not_enabled")
    return cfg


def _effective_capabilities(root: Path, supplied: list[str] | None) -> list[str]:
    policy = load_policy(root)
    governed = set(_json_list((policy.get("proxy_policy") or {}).get("capabilities")))
    if supplied is None:
        return sorted(governed)
    # Caller inventory can narrow availability but can never manufacture policy authority.
    return sorted(governed.intersection(_json_list(supplied)))


def _plan_inputs(plan: dict[str, Any]) -> dict[str, list[str]]:
    payload = plan.get("plan") or {}
    architecture = plan.get("architecture") or {}
    impact = architecture.get("impact") if isinstance(architecture, dict) else None
    impact = impact if isinstance(impact, dict) else {}
    def values(key: str, fallback: str | None = None) -> list[str]:
        raw = payload.get(key)
        if raw is None and fallback:
            raw = payload.get(fallback)
        if raw is None:
            raw = impact.get(key)
        return _json_list(raw)
    files = values("expected_files") or values("files")
    return {
        "requirements": values("requirements"),
        "acceptance_criteria": values("acceptance_criteria", "acceptance"),
        "affected_architecture_sections": values("affected_architecture_sections"),
        "expected_files": files,
        "expected_dependencies": values("expected_dependencies"),
        "expected_external_services": values("expected_external_services"),
        "expected_test_suites": values("expected_test_suites"),
    }


def _candidate_rows(root: Path) -> list[dict[str, Any]]:
    with connect_read_only(root) as c:
        rows = c.execute(
            """SELECT p.*,s.contract_json,s.contract_hash AS stored_contract_hash,
                      s.validation_status,s.architecture_baseline_hash AS stored_architecture_baseline_hash
               FROM promoted_skills p
               JOIN skill_contracts s ON s.skill_id=p.id
               WHERE p.status='graduated' AND p.contract_version=2
               ORDER BY p.skill_key,p.version DESC,p.id"""
        ).fetchall()
    return [dict(row) for row in rows]


def _contract_currentness(row: dict[str, Any], active_baseline_hash: str | None) -> dict[str, Any]:
    """Inspect one graduated v2 contract without mutating contract lifecycle state.

    Selection/evaluation are advisory/observational features.  They must not call
    the mutating contract validator merely to decide whether an already graduated
    contract is current.  Instead this check verifies the stored human-reviewed
    state, canonical hash, closed contract shape, and any architecture pin.
    """
    try:
        contract = json.loads(str(row.get("contract_json") or "{}"))
    except json.JSONDecodeError:
        return {"ok": False, "status": "invalid", "contract": None, "reason": "skill_selection_contract_json_invalid"}
    if not isinstance(contract, dict):
        return {"ok": False, "status": "invalid", "contract": None, "reason": "skill_selection_contract_json_invalid"}

    findings = validate_contract_shape(
        contract,
        skill_key=str(row.get("skill_key") or ""),
        skill_version=int(row.get("version") or 0),
    )
    if findings:
        return {"ok": False, "status": "invalid", "contract": contract, "reason": "skill_selection_contract_shape_invalid", "findings": findings}

    canonical_hash = _sha(contract)
    stored_hash = str(row.get("stored_contract_hash") or "")
    promoted_hash = str(row.get("contract_hash") or "")
    if not stored_hash or canonical_hash != stored_hash or (promoted_hash and promoted_hash != stored_hash):
        return {"ok": False, "status": "invalid", "contract": contract, "reason": "skill_selection_contract_integrity_mismatch"}

    stored_status = str(row.get("validation_status") or "")
    promoted_status = str(row.get("contract_status") or "")
    if stored_status != "valid" or promoted_status != "valid":
        return {
            "ok": False,
            "status": stored_status or promoted_status or "invalid",
            "contract": contract,
            "reason": "skill_selection_contract_not_current",
        }

    architecture_bound = bool(
        contract.get("required_architecture_sections")
        or contract.get("allowed_dependencies")
        or contract.get("allowed_external_services")
        or contract.get("architecture_constraints")
    )
    pinned_hash = str(row.get("architecture_baseline_hash") or row.get("stored_architecture_baseline_hash") or "")
    if architecture_bound:
        if not active_baseline_hash:
            return {"ok": False, "status": "needs_architecture", "contract": contract, "reason": "skill_selection_active_architecture_required"}
        if not pinned_hash:
            return {"ok": False, "status": "needs_architecture", "contract": contract, "reason": "skill_selection_architecture_pin_required"}
        if pinned_hash != str(active_baseline_hash):
            return {"ok": False, "status": "stale_architecture", "contract": contract, "reason": "skill_selection_architecture_baseline_mismatch"}

    return {"ok": True, "status": "valid", "contract": contract, "architecture_baseline_hash": pinned_hash or None}


def _score_candidate(
    row: dict[str, Any],
    contract: dict[str, Any],
    plan_inputs: dict[str, list[str]],
    query_terms: set[str],
    available_capabilities: set[str],
    available_tools: set[str],
    active_baseline_hash: str | None,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    affected = set(plan_inputs["affected_architecture_sections"])
    required_sections = set(_json_list(contract.get("required_architecture_sections")))
    missing_sections = sorted(required_sections - affected)
    if missing_sections:
        blockers.append({"code": "skill_selection_plan_missing_required_architecture_sections", "count": len(missing_sections)})

    required_caps = set(_json_list(contract.get("required_capabilities")))
    missing_caps = sorted(required_caps - available_capabilities)
    if missing_caps:
        blockers.append({"code": "skill_selection_required_capabilities_unavailable", "count": len(missing_caps)})

    required_tools = set(_json_list(contract.get("required_tools")))
    missing_tools = sorted(required_tools - available_tools)
    if missing_tools:
        blockers.append({"code": "skill_selection_required_tools_unavailable", "count": len(missing_tools)})

    files = plan_inputs["expected_files"]
    write_scopes = _json_list(contract.get("allowed_write_scope"))
    scope_matches = [path for path in files if any(_scope_allows(path, scope) for scope in write_scopes)]
    if files and len(scope_matches) != len(files):
        blockers.append({"code": "skill_selection_write_scope_insufficient", "expected_file_count": len(files), "covered_file_count": len(scope_matches)})

    expected_dependencies = set(plan_inputs["expected_dependencies"])
    allowed_dependencies = set(_json_list(contract.get("allowed_dependencies")))
    missing_dependencies = sorted(expected_dependencies - allowed_dependencies)
    if missing_dependencies:
        blockers.append({"code": "skill_selection_dependency_contract_insufficient", "count": len(missing_dependencies)})

    expected_services = set(plan_inputs["expected_external_services"])
    allowed_services = set(_json_list(contract.get("allowed_external_services")))
    missing_services = sorted(expected_services - allowed_services)
    if missing_services:
        blockers.append({"code": "skill_selection_external_service_contract_insufficient", "count": len(missing_services)})

    test_contract = contract.get("test_contract") if isinstance(contract.get("test_contract"), dict) else {}
    required_suites = set(_json_list(test_contract.get("suites"))) if test_contract.get("required") is True else set()
    plan_suites = set(plan_inputs["expected_test_suites"])
    missing_suites = sorted(required_suites - plan_suites)
    if missing_suites:
        blockers.append({"code": "skill_selection_required_test_suites_missing", "count": len(missing_suites)})

    pinned_hash = row.get("architecture_baseline_hash") or row.get("stored_architecture_baseline_hash")
    if pinned_hash and str(pinned_hash) != str(active_baseline_hash or ""):
        blockers.append({"code": "skill_selection_architecture_baseline_mismatch"})

    skill_terms = _tokens(f"{row.get('skill_key','')} {row.get('title','')} {row.get('description','')}")
    lexical_overlap = query_terms.intersection(skill_terms)
    lexical_score = len(lexical_overlap)
    architecture_overlap = len(required_sections.intersection(affected))
    scope_match_count = len(scope_matches)
    test_overlap = len(required_suites.intersection(plan_suites))
    score = lexical_score * 100 + architecture_overlap * 10 + scope_match_count * 3 + test_overlap * 2
    eligible = not blockers
    recommendable = eligible and score > 0
    evidence = {
        "lexical_overlap_count": lexical_score,
        "lexical_overlap_hash": _sha(sorted(lexical_overlap)) if lexical_overlap else None,
        "architecture_required_count": len(required_sections),
        "architecture_overlap_count": architecture_overlap,
        "expected_file_count": len(files),
        "scope_match_count": scope_match_count,
        "required_capability_count": len(required_caps),
        "required_tool_count": len(required_tools),
        "expected_dependency_count": len(expected_dependencies),
        "expected_external_service_count": len(expected_services),
        "required_test_suite_count": len(required_suites),
        "test_suite_overlap_count": test_overlap,
    }
    return {
        "skill_id": int(row["id"]),
        "skill_key": row["skill_key"],
        "skill_version": int(row["version"]),
        "eligible": eligible,
        "recommendable": recommendable,
        "score": score,
        "lexical_score": lexical_score,
        "architecture_overlap": architecture_overlap,
        "scope_match_count": scope_match_count,
        "blockers": blockers,
        "evidence": evidence,
        "contract_hash": str(row.get("contract_hash") or row.get("stored_contract_hash") or ""),
        "architecture_baseline_hash": pinned_hash,
    }


def run_skill_selection(
    root: Path,
    task_id: str,
    *,
    available_tools: list[str] | None = None,
    available_capabilities: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Run one explicit deterministic advisory selection against the active plan."""
    root = Path(root).resolve()
    cfg = _selection_policy(root)
    if int(limit) < 1 or int(limit) > int(cfg.get("max_candidates", 100)):
        raise RuntimeError("skill_selection_limit_out_of_range")
    plan = active_plan(root, task_id)
    if not plan:
        raise RuntimeError("skill_selection_active_plan_required")
    plan_status = architecture_plan_status(root, task_id)
    if not plan_status.get("ready"):
        raise RuntimeError("skill_selection_architecture_plan_not_current:" + str(plan_status.get("reason")))

    with connect_read_only(root) as c:
        task = c.execute("SELECT request FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise RuntimeError("skill_selection_task_not_found")

    plan_inputs = _plan_inputs(plan)
    ephemeral_query = "\n".join([str(task["request"]), *plan_inputs["requirements"], *plan_inputs["acceptance_criteria"]])
    query_terms = _tokens(ephemeral_query)
    query_hash = _sha(ephemeral_query)
    caps = set(_effective_capabilities(root, available_capabilities))
    tools = set(_json_list(available_tools or []))
    architecture = plan_status.get("active_baseline") or {}
    active_baseline_hash = architecture.get("baseline_hash")
    active_baseline_id = architecture.get("id")

    candidates: list[dict[str, Any]] = []
    for row in _candidate_rows(root):
        current = _contract_currentness(row, active_baseline_hash)
        if current.get("ok") is not True:
            candidates.append({
                "skill_id": int(row["id"]), "skill_key": row["skill_key"], "skill_version": int(row["version"]),
                "eligible": False, "recommendable": False, "score": 0, "lexical_score": 0,
                "architecture_overlap": 0, "scope_match_count": 0,
                "blockers": [{
                    "code": "skill_selection_contract_not_current",
                    "status": current.get("status"),
                    "reason": current.get("reason"),
                }],
                "evidence": {"contract_validation_status": current.get("status")},
                "contract_hash": str(row.get("contract_hash") or row.get("stored_contract_hash") or ""),
                "architecture_baseline_hash": row.get("architecture_baseline_hash") or row.get("stored_architecture_baseline_hash"),
            })
            continue
        contract_state = current.get("contract") or {}
        candidates.append(_score_candidate(row, contract_state, plan_inputs, query_terms, caps, tools, active_baseline_hash))

    candidates.sort(key=lambda item: (
        0 if item["recommendable"] else 1,
        -int(item["score"]),
        -int(item["skill_version"]),
        str(item["skill_key"]),
        int(item["skill_id"]),
    ))
    for index, item in enumerate(candidates, start=1):
        item["rank"] = index
    eligible = [item for item in candidates if item["eligible"]]
    recommendable = [item for item in candidates if item["recommendable"]]
    recommended = recommendable[0] if recommendable else None
    status = "recommended" if recommended else "no_eligible"
    selection_input = {
        "selection_version": SELECTION_VERSION,
        "task_id": task_id,
        "plan_id": int(plan["id"]),
        "plan_hash": str(plan["plan_hash"]),
        "architecture_baseline_hash": active_baseline_hash,
        "query_hash": query_hash,
        "available_capabilities": sorted(caps),
        "available_tools": sorted(tools),
        "plan_inputs_hash": _sha(plan_inputs),
    }
    selection_input_hash = _sha(selection_input)

    with connect(root, immediate=True) as c:
        cur = c.execute(
            """INSERT INTO skill_selection_runs(
                task_id,plan_id,plan_hash,architecture_baseline_id,architecture_baseline_hash,
                selection_input_hash,query_hash,algorithm,status,recommended_skill_id,candidate_count,eligible_count
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, int(plan["id"]), str(plan["plan_hash"]), active_baseline_id, active_baseline_hash,
             selection_input_hash, query_hash, SELECTION_ALGORITHM, status,
             int(recommended["skill_id"]) if recommended else None, len(candidates), len(eligible)),
        )
        run_id = int(cur.lastrowid)
        for item in candidates:
            c.execute(
                """INSERT INTO skill_selection_candidates(
                    selection_run_id,skill_id,rank,eligible,recommendable,score,lexical_score,
                    architecture_overlap,scope_match_count,blockers_json,evidence_json,contract_hash,architecture_baseline_hash
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, int(item["skill_id"]), int(item["rank"]), int(item["eligible"]), int(item["recommendable"]),
                 int(item["score"]), int(item["lexical_score"]), int(item["architecture_overlap"]), int(item["scope_match_count"]),
                 _canonical(item["blockers"]), _canonical(item["evidence"]), item["contract_hash"], item.get("architecture_baseline_hash")),
            )

    return {
        "ok": True,
        "selection_run_id": run_id,
        "task_id": task_id,
        "plan_id": int(plan["id"]),
        "plan_hash": str(plan["plan_hash"]),
        "architecture_baseline_hash": active_baseline_hash,
        "status": status,
        "advisory_only": True,
        "automatic_execution": False,
        "recommended_skill": recommended,
        "candidate_count": len(candidates),
        "eligible_count": len(eligible),
        "candidates": candidates[: int(limit)],
        "query_persisted": False,
        "selection_input_hash": selection_input_hash,
    }


def _decode_candidate(row: Any) -> dict[str, Any]:
    value = dict(row)
    value["eligible"] = bool(value["eligible"])
    value["recommendable"] = bool(value["recommendable"])
    value["blockers"] = json.loads(value.pop("blockers_json"))
    value["evidence"] = json.loads(value.pop("evidence_json"))
    return value


def skill_selection_status(root: Path, *, task_id: str | None = None, run_id: int | None = None) -> dict[str, Any]:
    """Read selection status without running selection or changing authority."""
    root = Path(root).resolve()
    if run_id is None and not task_id:
        raise RuntimeError("skill_selection_run_id_or_task_id_required")
    with connect_read_only(root) as c:
        if run_id is not None:
            row = c.execute("SELECT * FROM skill_selection_runs WHERE id=?", (int(run_id),)).fetchone()
        else:
            row = c.execute("SELECT * FROM skill_selection_runs WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
        if not row:
            return {"ok": True, "status": "missing", "selection": None}
        value = dict(row)
        recommended = None
        if value.get("recommended_skill_id"):
            skill = c.execute("SELECT id,skill_key,version,title,status,contract_version,contract_hash,contract_status FROM promoted_skills WHERE id=?", (value["recommended_skill_id"],)).fetchone()
            recommended = dict(skill) if skill else None
    return {"ok": True, "status": value["status"], "selection": value, "recommended_skill": recommended, "advisory_only": True}


def skill_selection_candidates_get(root: Path, run_id: int, *, eligible_only: bool = False) -> dict[str, Any]:
    """Read persisted selection candidate metadata without raw request content."""
    root = Path(root).resolve()
    with connect_read_only(root) as c:
        run = c.execute("SELECT * FROM skill_selection_runs WHERE id=?", (int(run_id),)).fetchone()
        if not run:
            return {"ok": True, "status": "missing", "selection_run_id": int(run_id), "candidates": []}
        sql = """SELECT sc.*,p.skill_key,p.version AS skill_version,p.title
                 FROM skill_selection_candidates sc JOIN promoted_skills p ON p.id=sc.skill_id
                 WHERE sc.selection_run_id=?"""
        params: list[Any] = [int(run_id)]
        if eligible_only:
            sql += " AND sc.eligible=1"
        sql += " ORDER BY sc.rank,sc.skill_id"
        rows = c.execute(sql, params).fetchall()
    return {"ok": True, "status": "available", "selection_run_id": int(run_id), "candidates": [_decode_candidate(row) for row in rows]}


def run_skill_evaluation(root: Path, selection_run_id: int, *, skill_id: int | None = None) -> dict[str, Any]:
    """Evaluate one selected skill observationally from an existing task outcome."""
    root = Path(root).resolve()
    cfg = _selection_policy(root)
    with connect_read_only(root) as c:
        run = c.execute("SELECT * FROM skill_selection_runs WHERE id=?", (int(selection_run_id),)).fetchone()
        if not run:
            raise RuntimeError("skill_evaluation_selection_run_not_found")
        run = dict(run)
        selected_skill_id = int(skill_id or run.get("recommended_skill_id") or 0)
        if not selected_skill_id:
            raise RuntimeError("skill_evaluation_skill_required")
        candidate = c.execute("SELECT * FROM skill_selection_candidates WHERE selection_run_id=? AND skill_id=?", (int(selection_run_id), selected_skill_id)).fetchone()
        if not candidate:
            raise RuntimeError("skill_evaluation_skill_not_in_selection")
        outcome = c.execute("SELECT * FROM task_outcomes WHERE task_id=? ORDER BY id DESC LIMIT 1", (run["task_id"],)).fetchone()
        if not outcome:
            raise RuntimeError("skill_evaluation_task_outcome_required")
        outcome = dict(outcome)

    plan_status = architecture_plan_status(root, str(run["task_id"]))
    plan = active_plan(root, str(run["task_id"]))
    context_current = bool(
        plan
        and int(plan["id"]) == int(run["plan_id"])
        and str(plan["plan_hash"]) == str(run["plan_hash"])
        and plan_status.get("ready")
        and str((plan_status.get("active_baseline") or {}).get("baseline_hash") or "") == str(run.get("architecture_baseline_hash") or "")
    )
    with connect_read_only(root) as c:
        contract_row = c.execute(
            """SELECT p.*,s.contract_json,s.contract_hash AS stored_contract_hash,
                      s.validation_status,s.architecture_baseline_hash AS stored_architecture_baseline_hash
               FROM promoted_skills p JOIN skill_contracts s ON s.skill_id=p.id
               WHERE p.id=? AND p.status='graduated' AND p.contract_version=2""",
            (selected_skill_id,),
        ).fetchone()
    current_contract = _contract_currentness(
        dict(contract_row) if contract_row else {},
        str((plan_status.get("active_baseline") or {}).get("baseline_hash") or "") or None,
    ) if contract_row else {"ok": False}
    context_current = context_current and current_contract.get("ok") is True

    test_rate = outcome.get("test_pass_rate")
    test_rate_value = float(test_rate) if test_rate is not None else None
    rework = int(outcome.get("rework_count") or 0)
    outcome_name = str(outcome.get("outcome") or "").strip().lower()
    positive_min = float(cfg.get("positive_test_pass_rate_min", 0.95))
    negative_below = float(cfg.get("negative_test_pass_rate_below", 0.80))
    high_rework = int(cfg.get("high_rework_threshold", 3))

    if not context_current:
        classification = "stale_context"
    elif outcome_name in {"failed", "failure", "error"} or (test_rate_value is not None and test_rate_value < negative_below) or rework >= high_rework:
        classification = "negative"
    elif outcome_name in {"success", "succeeded", "passed", "complete", "completed"} and (test_rate_value is None or test_rate_value >= positive_min) and rework <= 1:
        classification = "positive"
    else:
        classification = "mixed"

    evaluation = {
        "evaluation_version": EVALUATION_VERSION,
        "algorithm": EVALUATION_ALGORITHM,
        "selection_run_id": int(selection_run_id),
        "task_id": str(run["task_id"]),
        "skill_id": selected_skill_id,
        "outcome_id": int(outcome["id"]),
        "outcome": outcome_name,
        "test_pass_rate": test_rate_value,
        "rework_count": rework,
        "context_current": context_current,
        "evaluation_status": classification,
        "automatic_lifecycle_change": False,
        "future_ranking_weight_change": False,
    }
    digest = _sha(evaluation)
    with connect(root, immediate=True) as c:
        existing = c.execute("SELECT id FROM skill_evaluation_runs WHERE evaluation_hash=?", (digest,)).fetchone()
        if existing:
            evaluation_id = int(existing["id"])
        else:
            cur = c.execute(
                """INSERT INTO skill_evaluation_runs(
                    selection_run_id,task_id,skill_id,outcome_id,evaluation_version,algorithm,evaluation_status,evaluation_json,evaluation_hash
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (int(selection_run_id), str(run["task_id"]), selected_skill_id, int(outcome["id"]), EVALUATION_VERSION,
                 EVALUATION_ALGORITHM, classification, _canonical(evaluation), digest),
            )
            evaluation_id = int(cur.lastrowid)
    return {"ok": True, "evaluation_id": evaluation_id, **evaluation}


def skill_evaluation_get(
    root: Path,
    *,
    evaluation_id: int | None = None,
    selection_run_id: int | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Read one/latest observational skill evaluation without mutation."""
    root = Path(root).resolve()
    if evaluation_id is None and selection_run_id is None and not task_id:
        raise RuntimeError("skill_evaluation_identifier_required")
    with connect_read_only(root) as c:
        if evaluation_id is not None:
            row = c.execute("SELECT * FROM skill_evaluation_runs WHERE id=?", (int(evaluation_id),)).fetchone()
        elif selection_run_id is not None:
            row = c.execute("SELECT * FROM skill_evaluation_runs WHERE selection_run_id=? ORDER BY id DESC LIMIT 1", (int(selection_run_id),)).fetchone()
        else:
            row = c.execute("SELECT * FROM skill_evaluation_runs WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
    if not row:
        return {"ok": True, "status": "missing", "evaluation": None}
    value = dict(row)
    value["evaluation"] = json.loads(value.pop("evaluation_json"))
    return {"ok": True, "status": "available", "evaluation": value}
