from __future__ import annotations
import hashlib, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".agents") not in sys.path: sys.path.insert(0, str(ROOT / ".agents"))
from agentos import completion_verification as cv
from agentos import workflow as wf
from agentos.core import start_task
from agentos.db import connect
from agentos.policy import load_policy

def project(tmp_path):
    root=tmp_path/"project"; shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(
            ".git",
            "runtime",
            "agentos.db",
            "__pycache__",
            ".pytest_cache",
        ),
    ); return root

def h(x): return hashlib.sha256(x.encode()).hexdigest()
def schema62(root):
    with connect(root) as c: cv.migration_62(c)
def session(root,task,sid,token,role):
    with connect(root) as c:
        c.execute("INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES(?,?,?,?,?,?)",(h(token),token,sid,task,"[]","2999-01-01T00:00:00+00:00"))
        c.execute("INSERT INTO task_role_assignments(task_id,session_id,token_id,role,permissions_json,assigned_by,status) VALUES(?,?,?,?,?,'test','active')",(task,sid,token,role,"[]"))
def ready(root):
    start_task(root,"T1","Implement change"); wf.seed_workflow(root,"T1")
    with connect(root) as c:
        c.execute("UPDATE tasks SET approved=1,approved_scope='[\"src\",\"tests\"]',owner_session_id='producer-session' WHERE id='T1'")
        for step in load_policy(root)["workflows"]["default"]:
            if step in {"receive_request","report"}: continue
            source="auto" if step in wf.AUTOMATED_ONLY_STEPS else "manual"
            c.execute("UPDATE workflow_steps SET status='done',completion_source=?,result_hash=?,command_name='fixture',exit_code=0,verification_status=?,note='fixture' WHERE task_id='T1' AND workflow_name='default' AND step_name=?",(source,h(step),"verified" if source=="auto" else "unverified",step))
    start_task(root,"R1","Review T1"); session(root,"T1","producer-session","producer-token","executor"); session(root,"R1","reviewer-session","reviewer-token","reviewer")
def pass_verify(root):
    req=wf.workflow_completion_request(root,"T1","producer-session")
    return wf.workflow_completion_verify(root,req["request_id"],"R1","reviewer-session",verdict="pass",checks={"evidence":True,"requirements":True,"tests":True},evidence={"review":"independent"})

def test_schema62_requires_independent_completion(tmp_path):
    root = project(tmp_path)
    start_task(root, "T1", "released")
    wf.seed_workflow(root, "T1")

    with connect(root) as c:
        for step in load_policy(root)["workflows"]["default"]:
            source = (
                "auto"
                if step in wf.AUTOMATED_ONLY_STEPS
                else "manual"
            )
            c.execute(
                "UPDATE workflow_steps "
                "SET status='done', completion_source=?, result_hash='x' "
                "WHERE task_id='T1' AND step_name=?",
                (source, step),
            )

    status = wf.workflow_status(root, "T1")

    assert status["independent_completion_enforced"] is True
    assert status["complete"] is False

def test_candidate_requires_verification_before_report(tmp_path):
    root=project(tmp_path); schema62(root); ready(root); status=wf.workflow_status(root,"T1")
    assert status["completion_candidate_ready"] is True; assert status["required_pending"]==["report"]; assert status["completion_verification"]["accepted"] is False; assert wf.next_step(root,"T1")["next_step"]=="completion_verification"

def test_pass_and_report_binding_complete(tmp_path):
    root=project(tmp_path); schema62(root); ready(root); passed=pass_verify(root); assert wf.workflow_status(root,"T1")["complete"] is False
    wf.mark_step(root,"T1","report","done","final report"); bound=wf.bind_workflow_report_verification(root,"T1"); assert bound["completion_verification_result_hash"]==passed["result_hash"]; assert wf.workflow_status(root,"T1")["complete"] is True

def test_claim_mutation_stales_receipt(tmp_path):
    root=project(tmp_path); schema62(root); ready(root); pass_verify(root); wf.mark_step(root,"T1","report","done","final report"); wf.bind_workflow_report_verification(root,"T1")
    with connect(root) as c: c.execute("INSERT INTO claims(task_id,claim_text,claim_type,risk) VALUES('T1','new claim','other','low')")
    status=wf.workflow_status(root,"T1"); assert status["completion_verification"]["accepted"] is False; assert status["completion_verification"]["reason"]=="completion_verification_stale"; assert status["complete"] is False

def test_reverification_requires_report_rebinding(tmp_path):
    root=project(tmp_path); schema62(root); ready(root); first=pass_verify(root); wf.mark_step(root,"T1","report","done","first"); wf.bind_workflow_report_verification(root,"T1")
    with connect(root) as c: c.execute("INSERT INTO claims(task_id,claim_text,claim_type,risk) VALUES('T1','new claim','other','low')")
    second=pass_verify(root); status=wf.workflow_status(root,"T1"); assert status["completion_verification"]["accepted"] is True; assert status["report_completion_verification"]["current"] is False; assert status["complete"] is False; assert second["result_hash"] != first["result_hash"]
    wf.mark_step(root,"T1","report","done","second"); wf.bind_workflow_report_verification(root,"T1"); assert wf.workflow_status(root,"T1")["complete"] is True

def test_no_new_process_primitive():
    source=Path(wf.__file__).read_text(encoding="utf-8"); assert "subprocess.run(" not in source; assert "subprocess.Popen(" not in source
