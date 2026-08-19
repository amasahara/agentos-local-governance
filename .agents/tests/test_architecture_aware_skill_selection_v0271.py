"""Path: .agents/tests/test_architecture_aware_skill_selection_v0271.py
Purpose: Regression tests for v0.27.1 Architecture-Aware Skill Selection & Evaluation.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from agentos.db import SCHEMA_VERSION, connect
from agentos.mcp_v0271 import TOOLS as V0271_TOOLS
from agentos.policy import load_policy
from agentos.skill_contract_v2 import default_contract
from agentos.skill_selection import (
    run_skill_evaluation,
    run_skill_selection,
    skill_evaluation_get,
    skill_selection_candidates_get,
    skill_selection_status,
)


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    config = root / ".agents" / "config"
    config.mkdir(parents=True)
    source_config = Path(__file__).resolve().parents[1] / "config"
    shutil.copy2(source_config / "governance.json", config / "governance.json")
    shutil.copy2(source_config / "release_policy.json", config / "release_policy.json")
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    return root


def _active_plan(root: Path, *, request: str = "Add deterministic user API validation", files: list[str] | None = None, sections: list[str] | None = None, tests: list[str] | None = None) -> tuple[str, int]:
    task_id = "T-v0271"
    files = files or ["src/api/users.py"]
    sections = sections or ["ARCH-10", "ARCH-17", "ARCH-21"]
    tests = tests or ["tests/test_users.py"]
    plan = {
        "files": files,
        "requirements": [request],
        "acceptance_criteria": ["tests pass"],
        "affected_architecture_sections": sections,
        "expected_modules": ["src.api.users"],
        "expected_dependency_edges": [],
        "expected_dependencies": [],
        "expected_external_services": [],
        "expected_test_suites": tests,
        "expected_files": files,
        "architecture_baseline_hash": "a" * 64,
    }
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    with connect(root, immediate=True) as c:
        c.execute("INSERT INTO tasks(id,request,approved,approved_scope) VALUES(?,?,1,?)", (task_id, request, json.dumps(["src", "tests"])))
        c.execute("INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by) VALUES('a',1,'active',?,27,'human')", ("a" * 64,))
        baseline_id = int(c.execute("SELECT id FROM architecture_baselines WHERE baseline_uuid='a'").fetchone()["id"])
        cur = c.execute("INSERT INTO task_plans(task_id,revision,status,plan_json,plan_hash,submitted_by,approved_by,approval_note,approved_at) VALUES(?,1,'active',?,?, 'human:planner','human:approver','approved',CURRENT_TIMESTAMP)", (task_id, canonical, digest))
        plan_id = int(cur.lastrowid)
        impact = dict(plan)
        impact.update({"state": "bound", "baseline_id": baseline_id, "architecture_baseline_hash": "a" * 64})
        impact_hash = hashlib.sha256(json.dumps(impact, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        c.execute(
            """INSERT INTO task_plan_architecture_contexts(
                plan_id,task_id,baseline_id,baseline_hash,state,requirements_json,affected_sections_json,
                expected_modules_json,expected_dependency_edges_json,expected_files_json,acceptance_criteria_json,
                impact_json,impact_hash
            ) VALUES(?,?,?,?, 'bound',?,?,?,?,?,?,?,?)""",
            (plan_id, task_id, baseline_id, "a" * 64, json.dumps([request]), json.dumps(sections),
             json.dumps(["src.api.users"]), "[]", json.dumps(files), json.dumps(["tests pass"]), json.dumps(impact), impact_hash),
        )
    return task_id, plan_id


def _skill(root: Path, *, key: str = "user-api-validation", description: str = "Add deterministic user API validation", write_scope: list[str] | None = None, capabilities: list[str] | None = None, tools: list[str] | None = None, tests: list[str] | None = None) -> int:
    with connect(root, immediate=True) as c:
        mem = c.execute("INSERT INTO project_memory(kind,statement,confidence,evidence_hash,status) VALUES('procedural',?,0.95,?,'active')", (description, "e" * 64))
        memory_id = int(mem.lastrowid)
        cur = c.execute(
            """INSERT INTO promoted_skills(skill_key,version,memory_id,title,description,candidate_path,graduated_path,status,content_hash,promoted_by,approved_by,contract_version,contract_status)
               VALUES(?,1,?,?,?,? ,?,'graduated',?,'human:author','human:reviewer',2,'valid')""",
            (key, memory_id, key, description, f".agents/runtime/skills/candidates/{key}-v1.md", f".agents/skills/{key}-v1.md", "c" * 64),
        )
        skill_id = int(cur.lastrowid)
        contract = default_contract(key, 1)
        contract["allowed_write_scope"] = write_scope if write_scope is not None else ["src/**"]
        contract["required_capabilities"] = capabilities or []
        contract["required_tools"] = tools or []
        contract["test_contract"] = {"required": bool(tests), "suites": tests or []}
        text = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(text.encode()).hexdigest()
        c.execute("INSERT INTO skill_contracts(skill_id,contract_version,contract_json,contract_hash,validation_status,drafted_by,validated_at) VALUES(?,2,?,?,'valid','human:architect',CURRENT_TIMESTAMP)", (skill_id, text, digest))
        c.execute("UPDATE promoted_skills SET contract_hash=? WHERE id=?", (digest, skill_id))
    return skill_id


def test_schema_59_selection_and_evaluation_tables_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    with connect(root) as c:
        version = c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION == 59
    assert {"skill_selection_runs", "skill_selection_candidates", "skill_evaluation_runs"} <= tables


def test_policy_enables_explicit_advisory_selection_without_automatic_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy = load_policy(_root(tmp_path, monkeypatch))
    cfg = policy["architecture_aware_skill_selection_policy"]
    assert cfg["enabled"] is True
    assert cfg["selection_is_advisory"] is True
    assert cfg["automatic_execution_allowed"] is False
    assert cfg["model_provider_selection_authority"] is False
    assert cfg["evaluation_changes_future_selection_weights"] is False


def test_selection_recommends_current_graduated_v2_skill_deterministically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root)
    skill_id = _skill(root)
    first = run_skill_selection(root, task_id)
    second = run_skill_selection(root, task_id)
    assert first["recommended_skill"]["skill_id"] == skill_id
    assert second["recommended_skill"]["skill_id"] == skill_id
    assert first["recommended_skill"]["score"] == second["recommended_skill"]["score"]
    assert first["advisory_only"] is True and first["automatic_execution"] is False


def test_selection_does_not_persist_raw_request_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    marker = "PRIVATE-SELECTION-REQUEST-MUST-NOT-BE-PERSISTED"
    task_id, _ = _active_plan(root, request=marker + " user API validation")
    _skill(root, description="user API validation")
    result = run_skill_selection(root, task_id)
    with connect(root) as c:
        run = c.execute("SELECT selection_input_hash,query_hash FROM skill_selection_runs WHERE id=?", (result["selection_run_id"],)).fetchone()
        candidate_payloads = c.execute("SELECT blockers_json,evidence_json FROM skill_selection_candidates WHERE selection_run_id=?", (result["selection_run_id"],)).fetchall()
    assert marker not in str(dict(run))
    assert all(marker not in str(dict(row)) for row in candidate_payloads)
    assert result["query_persisted"] is False


def test_write_scope_must_cover_every_planned_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root, files=["src/api/users.py", "tests/test_users.py"])
    skill_id = _skill(root, write_scope=["src/**"])
    result = run_skill_selection(root, task_id)
    item = next(x for x in result["candidates"] if x["skill_id"] == skill_id)
    assert item["eligible"] is False
    assert any(x["code"] == "skill_selection_write_scope_insufficient" for x in item["blockers"])


def test_required_capability_is_intersection_with_governed_proxy_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root)
    skill_id = _skill(root, capabilities=["forbidden.superpower"])
    result = run_skill_selection(root, task_id, available_capabilities=["forbidden.superpower", "filesystem.write"])
    item = next(x for x in result["candidates"] if x["skill_id"] == skill_id)
    assert item["eligible"] is False
    assert any(x["code"] == "skill_selection_required_capabilities_unavailable" for x in item["blockers"])


def test_required_tools_fail_closed_when_inventory_is_not_supplied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root)
    skill_id = _skill(root, tools=["pytest"])
    result = run_skill_selection(root, task_id)
    item = next(x for x in result["candidates"] if x["skill_id"] == skill_id)
    assert item["eligible"] is False
    assert any(x["code"] == "skill_selection_required_tools_unavailable" for x in item["blockers"])
    allowed = run_skill_selection(root, task_id, available_tools=["pytest"])
    assert allowed["recommended_skill"]["skill_id"] == skill_id


def test_required_test_contract_must_be_declared_by_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root, tests=["tests/test_users.py"])
    skill_id = _skill(root, tests=["tests/test_security.py"])
    result = run_skill_selection(root, task_id)
    item = next(x for x in result["candidates"] if x["skill_id"] == skill_id)
    assert item["eligible"] is False
    assert any(x["code"] == "skill_selection_required_test_suites_missing" for x in item["blockers"])


def test_legacy_v1_skill_is_not_selection_eligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root)
    with connect(root, immediate=True) as c:
        mem = c.execute("INSERT INTO project_memory(kind,statement,confidence,evidence_hash,status) VALUES('procedural','legacy',0.95,?,'active')", ("e" * 64,))
        c.execute("INSERT INTO promoted_skills(skill_key,version,memory_id,title,description,candidate_path,status,content_hash,promoted_by) VALUES('legacy',1,?,'legacy','user API validation','.agents/skills/legacy.md','graduated',?,'human')", (int(mem.lastrowid), "d" * 64))
    result = run_skill_selection(root, task_id)
    assert result["candidate_count"] == 0


def test_stale_contract_is_excluded_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root)
    skill_id = _skill(root)
    with connect(root, immediate=True) as c:
        c.execute("UPDATE skill_contracts SET validation_status='stale_architecture' WHERE skill_id=?", (skill_id,))
        c.execute("UPDATE promoted_skills SET contract_status='stale_architecture' WHERE id=?", (skill_id,))
    result = run_skill_selection(root, task_id)
    item = next(x for x in result["candidates"] if x["skill_id"] == skill_id)
    assert item["eligible"] is False
    assert item["blockers"][0]["code"] == "skill_selection_contract_not_current"
    assert item["blockers"][0]["status"] == "stale_architecture"


def test_status_and_candidate_reads_are_non_mutating(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root)
    _skill(root)
    result = run_skill_selection(root, task_id)
    status = skill_selection_status(root, run_id=result["selection_run_id"])
    candidates = skill_selection_candidates_get(root, result["selection_run_id"])
    assert status["advisory_only"] is True
    assert candidates["candidates"][0]["rank"] == 1


def test_evaluation_is_observational_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, _ = _active_plan(root)
    skill_id = _skill(root)
    selection = run_skill_selection(root, task_id)
    with connect(root, immediate=True) as c:
        c.execute("INSERT INTO task_outcomes(task_id,outcome,rated_by,test_pass_rate,rework_count) VALUES(?, 'success','human',1.0,0)", (task_id,))
    first = run_skill_evaluation(root, selection["selection_run_id"], skill_id=skill_id)
    second = run_skill_evaluation(root, selection["selection_run_id"], skill_id=skill_id)
    assert first["evaluation_status"] == "positive"
    assert first["evaluation_id"] == second["evaluation_id"]
    assert first["automatic_lifecycle_change"] is False
    assert first["future_ranking_weight_change"] is False
    assert skill_evaluation_get(root, evaluation_id=first["evaluation_id"])["status"] == "available"


def test_evaluation_fails_closed_to_stale_context_after_plan_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    task_id, plan_id = _active_plan(root)
    skill_id = _skill(root)
    selection = run_skill_selection(root, task_id)
    with connect(root, immediate=True) as c:
        c.execute("UPDATE task_plans SET status='stale' WHERE id=?", (plan_id,))
        c.execute("UPDATE task_plan_architecture_contexts SET state='stale',stale_reason='test' WHERE plan_id=?", (plan_id,))
        c.execute("INSERT INTO task_outcomes(task_id,outcome,rated_by,test_pass_rate,rework_count) VALUES(?, 'success','human',1.0,0)", (task_id,))
    result = run_skill_evaluation(root, selection["selection_run_id"], skill_id=skill_id)
    assert result["evaluation_status"] == "stale_context"


def test_mcp_v0271_is_exactly_three_read_only_inspection_tools() -> None:
    names = {item["name"] for item in V0271_TOOLS}
    assert names == {
        "agentos.skill_selection_status_get",
        "agentos.skill_selection_candidates_get",
        "agentos.skill_evaluation_get",
    }
    assert not any(any(word in name for word in ("run", "execute", "approve", "graduate", "revoke", "mutate", "set")) for name in names)
