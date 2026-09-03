"""Focused v0.31.0 governed-learning tests."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import pytest
from agentos.context_authority import classify_source, evaluate_provenance, make_provenance_record
from agentos.db import connect
from agentos.learning_signals import LearningSignalError, create_learning_signal, learning_status, link_learning_signal
from agentos.mcp_v0310 import TOOL_NAMES

def sha(v: str) -> str: return hashlib.sha256(v.encode()).hexdigest()
def task(root: Path, tid="T1"):
    with connect(root) as c: c.execute("INSERT INTO tasks(id,request,approved) VALUES(?,?,1)",(tid,"test"))
def outcome(root: Path, tid="T1") -> int:
    with connect(root) as c:
        cur=c.execute("INSERT INTO task_outcomes(task_id,outcome,rated_by,test_pass_rate,rework_count) VALUES(?,?,?,?,?)",(tid,"failed","test",0.0,1)); return int(cur.lastrowid)
def verify(root: Path, tid="T1"):
    rid="REQ-"+tid; subject=sha("subject-"+tid); result=sha("result-"+tid)
    with connect(root) as c:
        c.execute("INSERT INTO completion_verification_requests(request_id,verification_version,subject_type,subject_id,task_id,producer_task_id,producer_session_id,subject_hash,required_checks_json,status) VALUES(?,1,'task','subject',?,?,?,?,'[]','verified')",(rid,tid,tid,"producer",subject))
        c.execute("INSERT INTO completion_verification_attempts(request_id,verifier_task_id,verifier_session_id,verifier_assignment_id,verifier_role,observed_subject_hash,verdict,checks_json,evidence_json,result_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",(rid,tid,"reviewer",1,"reviewer",subject,"pass","{}",'{"evidence":true}',result))
    return rid

def test_schema64(tmp_path):
    task(tmp_path)
    with connect(tmp_path) as c:
        assert c.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]==64
        tables={r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"learning_signals","learning_signal_links","knowledge_usage"}<=tables

def test_idempotent_monotonic(tmp_path):
    task(tmp_path); a=outcome(tmp_path); b=outcome(tmp_path)
    x=create_learning_signal(tmp_path,task_id="T1",session_id="S1",signal_kind="outcome_failed",source_type="task_outcome",source_id=str(a))
    y=create_learning_signal(tmp_path,task_id="T1",session_id="S1",signal_kind="outcome_failed",source_type="task_outcome",source_id=str(a))
    z=create_learning_signal(tmp_path,task_id="T1",session_id="S1",signal_kind="outcome_failed",source_type="task_outcome",source_id=str(b))
    assert x["signal_sequence_number"]==1 and y["signal_id"]==x["signal_id"] and not y["created"] and z["signal_sequence_number"]==2

def test_hash_mismatch_blocks(tmp_path):
    task(tmp_path); oid=outcome(tmp_path)
    with pytest.raises(LearningSignalError,match="learning_source_hash_mismatch"):
        create_learning_signal(tmp_path,task_id="T1",session_id="S1",signal_kind="outcome_failed",source_type="task_outcome",source_id=str(oid),expected_source_hash="0"*64)

def test_unverified_promotion_link_blocks_then_verified_allows(tmp_path):
    task(tmp_path); oid=outcome(tmp_path)
    s=create_learning_signal(tmp_path,task_id="T1",session_id="S1",signal_kind="outcome_failed",source_type="task_outcome",source_id=str(oid))
    with pytest.raises(LearningSignalError,match="not_cross_task_eligible"):
        link_learning_signal(tmp_path,signal_id=s["signal_id"],relation_type="memory_candidate",target_type="project_memory",target_id="M1",target_hash=sha("M1"))
    verify(tmp_path)
    linked=link_learning_signal(tmp_path,signal_id=s["signal_id"],relation_type="memory_candidate",target_type="project_memory",target_id="M1",target_hash=sha("M1"))
    assert linked["target_id"]=="M1"

def test_evidence_does_not_raise_authority():
    a=make_provenance_record(source_kind="human_request",content_hash=sha("r"),source_locator="r",producer="human")
    e=make_provenance_record(source_kind="knowledge_memory",content_hash=sha("m"),source_locator="m",producer="agentos")
    one=evaluate_provenance([a]); two=evaluate_provenance([a,e])
    assert one["context_authority_hash"]==two["context_authority_hash"]
    assert one["provenance_manifest_hash"]!=two["provenance_manifest_hash"]

def test_raw_learning_signal_is_not_registered_as_context_source():
    classified=classify_source("learning_signal")
    assert classified["known_source"] is False
    assert classified["trust_class"]=="unknown_untrusted"
    assert classified["authority_class"]=="none"
    assert classified["instruction_authority"] is False

def test_mcp_read_only():
    assert TOOL_NAMES=={"agentos.learning_signals_get","agentos.learning_signal_links_get","agentos.knowledge_usage_get","agentos.learning_status_get"}
    assert not any(any(w in n for w in ("create","record","approve","graduate","activate","delete","deactivate")) for n in TOOL_NAMES)

def test_status_nonclaims(tmp_path):
    task(tmp_path); s=learning_status(tmp_path)
    assert s["learning_signals_directly_injected"] is False and s["instruction_authority"] is False and s["mcp_mutation_allowed"] is False
