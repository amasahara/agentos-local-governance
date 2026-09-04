"""Focused v0.31.1 governed memory promotion tests."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import agentos.memory_promotion as mp
from agentos.context_authority import evaluate_provenance, make_provenance_record
from agentos.db import _all_migrations, connect
from agentos.learning_signals import create_learning_signal
from agentos.memory_promotion import (
    MemoryPromotionError,
    create_memory_promotion_candidate,
    evaluate_memory_promotion,
    finalize_memory_promotion_candidate,
)
from agentos.retrieval import search_knowledge
from agentos.schema_version import CURRENT_SCHEMA_VERSION

POLICY = {
    "governed_learning_policy": {
        "enabled": True,
        "promotion": {
            "minimum_occurrences": 3,
            "minimum_distinct_tasks": 2,
            "window_days": 30,
            "promotion_cooldown_days": 7,
            "automatic_memory_candidate_flagging": True,
            "automatic_memory_activation": False,
            "automatic_memory_authority_promotion": False,
            "automatic_skill_graduation": False,
            "automatic_policy_activation": False,
            "automatic_architecture_mutation": False,
            "distinct_completed_tasks_required": True,
            "source_signal_revalidation_required": True,
            "architecture_baseline_revalidation_required": True,
            "human_decision_required_for_memory_activation": True,
            "candidate_memory_kind": "procedural",
            "candidate_status": "candidate",
            "active_status": "active",
            "rejected_status": "rejected",
        },
    }
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture(autouse=True)
def policy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mp, "load_policy", lambda _root: POLICY)


def add_task(root: Path, tid: str) -> None:
    with connect(root) as c:
        c.execute("INSERT INTO tasks(id,request,approved) VALUES(?,?,1)", (tid, "test " + tid))


def add_baseline(root: Path, name: str = "A") -> str:
    digest = sha("architecture-" + name)
    with connect(root) as c:
        c.execute(
            """INSERT INTO architecture_baselines(
                   baseline_uuid,baseline_version,status,baseline_hash,
                   section_count,created_by,activated_by,activated_at
               ) VALUES(?,?, 'active',?,27,'human','human',CURRENT_TIMESTAMP)""",
            ("BASELINE-" + name, 1 if name == "A" else 2, digest),
        )
    return digest


def add_finding(root: Path, occurrences: int = 3) -> int:
    with connect(root) as c:
        cur = c.execute(
            """INSERT INTO project_findings(
                   finding_key,kind,path,symbol,message,first_seen_task_id,
                   occurrences,status
               ) VALUES(?,?,?,?,?,?,?,'active')""",
            (
                sha("finding"), "regression", "src/example.py", "run",
                "Always validate the governed result before reuse", "T1", occurrences,
            ),
        )
        return int(cur.lastrowid)


def verify_task(root: Path, tid: str) -> None:
    request_id = "REQ-" + tid
    subject = sha("subject-" + tid)
    result = sha("result-" + tid)
    with connect(root) as c:
        c.execute(
            """INSERT INTO completion_verification_requests(
                   request_id,verification_version,subject_type,subject_id,
                   task_id,producer_task_id,producer_session_id,subject_hash,
                   required_checks_json,status
               ) VALUES(?,1,'task','subject',?,?,?,?,'[]','verified')""",
            (request_id, tid, tid, "producer-" + tid, subject),
        )
        c.execute(
            """INSERT INTO completion_verification_attempts(
                   request_id,verifier_task_id,verifier_session_id,
                   verifier_assignment_id,verifier_role,observed_subject_hash,
                   verdict,checks_json,evidence_json,result_hash
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (request_id, tid, "reviewer-" + tid, 1, "reviewer", subject,
             "pass", "{}", '{"verified":true}', result),
        )


def observe(root: Path, fid: int, tid: str) -> None:
    create_learning_signal(
        root,
        task_id=tid,
        session_id="S-" + tid,
        signal_kind="project_finding_observed",
        source_type="project_finding",
        source_id=str(fid),
    )


def make_candidate(root: Path) -> tuple[int, dict]:
    add_task(root, "T1")
    add_task(root, "T2")
    add_baseline(root)
    fid = add_finding(root, 3)
    observe(root, fid, "T1")
    observe(root, fid, "T2")
    verify_task(root, "T1")
    verify_task(root, "T2")
    return fid, create_memory_promotion_candidate(root, fid, open_human_decision=False)


def add_decision(root: Path, *, memory_id: int, finding_id: int, evidence_hash: str,
                 task_id: str, option: str | None, resolved: bool) -> str:
    question = mp._decision_question(memory_id, finding_id, evidence_hash)
    uuid = "DECISION-" + str(memory_id)
    with connect(root) as c:
        arch = c.execute(
            "SELECT baseline_hash FROM architecture_baselines WHERE status='active'"
        ).fetchone()["baseline_hash"]
        cur = c.execute(
            """INSERT INTO human_decision_requests(
                   decision_uuid,task_id,phase,decision_type,severity,blocking,
                   question,question_hash,options_json,recommendation,
                   recommendation_rationale,requirement_ids_json,
                   architecture_section_ids_json,task_request_hash,plan_hash,
                   architecture_baseline_hash,raised_by_session,status,resolved_at
               ) VALUES(?,?,'post_execution','other','normal',0,?,?,?,
                        NULL,NULL,'[]','[]',?,NULL,?,'test',?,
                        CASE WHEN ?='resolved' THEN CURRENT_TIMESTAMP ELSE NULL END)""",
            (uuid, task_id, question, sha(question), '["approve","reject"]',
             sha("test " + task_id), arch,
             "resolved" if resolved else "open",
             "resolved" if resolved else "open"),
        )
        if resolved:
            c.execute(
                """INSERT INTO human_decision_resolutions(
                       decision_id,selected_option,answer_text,answer_hash,
                       resolved_by,human_confirmed,impact_classification
                   ) VALUES(?,?,?,?,?,1,'none')""",
                (int(cur.lastrowid), option, "human decision", sha("human decision"), "human"),
            )
    return uuid


def test_schema_remains_64_without_migration_65(tmp_path: Path) -> None:
    add_task(tmp_path, "T1")
    assert CURRENT_SCHEMA_VERSION == 64
    assert len(_all_migrations()) == 64
    with connect(tmp_path) as c:
        assert c.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"] == 64


def test_occurrences_alone_do_not_replace_distinct_verified_tasks(tmp_path: Path) -> None:
    add_task(tmp_path, "T1")
    add_baseline(tmp_path)
    fid = add_finding(tmp_path, 10)
    observe(tmp_path, fid, "T1")
    verify_task(tmp_path, "T1")
    report = evaluate_memory_promotion(tmp_path, fid)
    assert report["eligible"] is False
    assert report["distinct_verified_task_count"] == 1
    assert "distinct_verified_task_threshold_not_met" in report["reasons"]


def test_two_distinct_verified_tasks_are_eligible(tmp_path: Path) -> None:
    add_task(tmp_path, "T1")
    add_task(tmp_path, "T2")
    add_baseline(tmp_path)
    fid = add_finding(tmp_path, 3)
    observe(tmp_path, fid, "T1")
    observe(tmp_path, fid, "T2")
    verify_task(tmp_path, "T1")
    verify_task(tmp_path, "T2")
    report = evaluate_memory_promotion(tmp_path, fid)
    assert report["eligible"] is True
    assert report["distinct_verified_task_count"] == 2


def test_candidate_reuses_project_memory_and_is_idempotent(tmp_path: Path) -> None:
    fid, first = make_candidate(tmp_path)
    second = create_memory_promotion_candidate(tmp_path, fid, open_human_decision=False)
    assert first["created"] is True
    assert second["created"] is False
    assert second["memory_id"] == first["memory_id"]
    with connect(tmp_path) as c:
        rows = c.execute("SELECT id,status FROM project_memory").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "candidate"


def test_candidate_not_in_context_until_approved_and_finalized(tmp_path: Path) -> None:
    fid, candidate = make_candidate(tmp_path)
    assert search_knowledge(tmp_path, "governed result reuse", kinds=["memory"], limit=20)["result_count"] == 0
    decision = add_decision(
        tmp_path, memory_id=candidate["memory_id"], finding_id=fid,
        evidence_hash=candidate["evaluation"]["evidence_hash"], task_id="T2",
        option="approve", resolved=True,
    )
    result = finalize_memory_promotion_candidate(
        tmp_path, candidate["memory_id"], decision, expected_task_id="T2"
    )
    assert result["status"] == "active"
    after = search_knowledge(tmp_path, "governed result reuse", kinds=["memory"], limit=20)
    assert after["result_count"] == 1
    assert after["results"][0]["kind"] == "memory"


def test_unresolved_human_decision_blocks_activation(tmp_path: Path) -> None:
    fid, candidate = make_candidate(tmp_path)
    decision = add_decision(
        tmp_path, memory_id=candidate["memory_id"], finding_id=fid,
        evidence_hash=candidate["evaluation"]["evidence_hash"], task_id="T2",
        option=None, resolved=False,
    )
    with pytest.raises(MemoryPromotionError, match="human_decision_unresolved"):
        finalize_memory_promotion_candidate(
            tmp_path, candidate["memory_id"], decision, expected_task_id="T2"
        )


def test_reject_marks_candidate_rejected_and_enters_cooldown(tmp_path: Path) -> None:
    fid, candidate = make_candidate(tmp_path)
    decision = add_decision(
        tmp_path, memory_id=candidate["memory_id"], finding_id=fid,
        evidence_hash=candidate["evaluation"]["evidence_hash"], task_id="T2",
        option="reject", resolved=True,
    )
    result = finalize_memory_promotion_candidate(
        tmp_path, candidate["memory_id"], decision, expected_task_id="T2"
    )
    assert result["status"] == "rejected"
    report = evaluate_memory_promotion(tmp_path, fid)
    assert report["cooldown_active"] is True
    assert report["eligible"] is False


def test_stale_source_hash_blocks_finalization(tmp_path: Path) -> None:
    fid, candidate = make_candidate(tmp_path)
    decision = add_decision(
        tmp_path, memory_id=candidate["memory_id"], finding_id=fid,
        evidence_hash=candidate["evaluation"]["evidence_hash"], task_id="T2",
        option="approve", resolved=True,
    )
    with connect(tmp_path) as c:
        c.execute("UPDATE project_findings SET message='changed finding content' WHERE id=?", (fid,))
    with pytest.raises(MemoryPromotionError, match="source_hash_stale"):
        finalize_memory_promotion_candidate(
            tmp_path, candidate["memory_id"], decision, expected_task_id="T2"
        )


def test_architecture_change_blocks_finalization(tmp_path: Path) -> None:
    fid, candidate = make_candidate(tmp_path)
    decision = add_decision(
        tmp_path, memory_id=candidate["memory_id"], finding_id=fid,
        evidence_hash=candidate["evaluation"]["evidence_hash"], task_id="T2",
        option="approve", resolved=True,
    )
    with connect(tmp_path) as c:
        c.execute("UPDATE architecture_baselines SET status='superseded' WHERE status='active'")
        c.execute(
            """INSERT INTO architecture_baselines(
                   baseline_uuid,baseline_version,status,baseline_hash,
                   section_count,created_by,activated_by,activated_at
               ) VALUES('BASELINE-B',2,'active',?,27,'human','human',CURRENT_TIMESTAMP)""",
            (sha("architecture-B"),),
        )
    with pytest.raises(MemoryPromotionError, match="decision_architecture_stale"):
        finalize_memory_promotion_candidate(
            tmp_path, candidate["memory_id"], decision, expected_task_id="T2"
        )


def test_promoted_memory_remains_project_evidence() -> None:
    authority = make_provenance_record(
        source_kind="human_request", content_hash=sha("request"),
        source_locator="request", producer="human",
    )
    memory = make_provenance_record(
        source_kind="knowledge_memory", content_hash=sha("promoted-memory"),
        source_locator="memory:1", producer="agentos",
    )
    before = evaluate_provenance([authority])
    after = evaluate_provenance([authority, memory])
    assert memory.trust_class == "project_evidence"
    assert memory.authority_class == "none"
    assert memory.instruction_authority is False
    assert before["context_authority_hash"] == after["context_authority_hash"]
    assert before["provenance_manifest_hash"] != after["provenance_manifest_hash"]


def test_no_v0311_mcp_mutation_and_finalize_is_privileged() -> None:
    from agentos import cli_runtime, mcp_runtime

    privileged = cli_runtime.privileged_command_registry()
    agent = cli_runtime.agent_command_registry()

    assert "memory-promotion-finalize" in cli_runtime.PRIVILEGED_COMMANDS
    assert "memory-promotion-finalize" in privileged
    assert "memory-promotion-finalize" not in agent
    # v0.31.0 validated 98 privileged commands. v0.31.1 intentionally adds
    # exactly one lifecycle-finalization command and no other privileged surface.
    assert len(privileged) == 99

    assert len(mcp_runtime.ALL_TOOLS) == 132
    assert not any(
        "memory_promotion" in str(tool.get("name", ""))
        for tool in mcp_runtime.ALL_TOOLS
    )
