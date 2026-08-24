"""AgentOS v0.16.2 security, knowledge, execution-platform, and regression tests."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".agents") not in sys.path:
    sys.path.insert(0, str(ROOT / ".agents"))

from agentos.concurrency import acquire_resource, atomic_write, claim_task, handoff_task, heartbeat_resource, list_resources, release_resource
from agentos.core import approve_task as _core_approve_task, check_write, db_status, docs_check, instruction_check, prepare_change, record_claim, record_tool_execution, start_task
from agentos.db import SCHEMA_VERSION, connect
from agentos.drift import ack_baseline, drift_check, tracked_files
from agentos.human_decision import record_clarity_assessment
from agentos.policy import approve_local_override, load_policy, local_override_status
from agentos.tooling import classify_tool, complete_tool, guard_tool, redact_text
from agentos.workflow import complete_automated_step, current_task_id, mark_step, seed_workflow, set_current_task, workflow_status


def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "runtime", "agentos.db", "__pycache__", ".pytest_cache"))
    (root / "src").mkdir(exist_ok=True)
    return root


def approve_task(root: Path, task_id: str, scope: list[str]):
    """Approve a historical-test task through the v0.25.2 clarity gate."""
    record_clarity_assessment(
        root, task_id, "pytest-fixture",
        objective_understood=True,
        scope_understood=True,
        constraints_understood=True,
        acceptance_understood=True,
    )
    return _core_approve_task(root, task_id, scope)


def ready(root: Path, task_id: str = "T1") -> None:
    start_task(root, task_id, "Test request")
    seed_workflow(root, task_id)
    approve_task(root, task_id, ["src", "tests", ".agents"])
    complete_automated_step(root, task_id, "approve_task", "approve-task", {"approved": True})


def guarded_local_call(root: Path, task_id: str = "T1", session: str = "S1", summary: str = "read ok") -> int:
    args = {"path": "src/a.py"}
    guard = guard_tool(root, task_id, session, "bounded_file_read", args)
    assert guard["allowed"]
    result = complete_tool(root, guard["execution_token"], args, True, summary, session)
    return result["tool_call_id"]


def test_schema_v11_legacy_and_hardening_tables(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert db_status(root) == {"current": SCHEMA_VERSION, "required": SCHEMA_VERSION, "is_current": True}
    with connect(root) as c:
        tables = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"guarded_executions", "policy_override_approvals", "audit_events"} <= tables


def test_absolute_path_inside_root_is_allowed(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    target = root / "src" / "a.py"
    assert check_write(root, "T1", str(target))["allowed"] is True


def test_outside_path_is_denied(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    assert check_write(root, "T1", str(tmp_path / "outside.py"))["allowed"] is False


def test_classification_is_derived() -> None:
    assert classify_tool("web")["classification"] == "network"
    assert classify_tool("bounded_file_read")["classification"] == "local"
    assert classify_tool("made-up")["classification"] == "unknown"


def test_direct_record_tool_is_disabled(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    with pytest.raises(RuntimeError, match="guard-tool"):
        record_tool_execution(root, "T1", "web", {}, True, "x", "local")


def test_unknown_tool_fails_closed(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    result = guard_tool(root, "T1", "S1", "invented_tool", {})
    assert result["allowed"] is False
    assert result["execution_token"] is None


def test_network_tool_cannot_be_forged_local(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    denied = guard_tool(root, "T1", "S1", "web", {"q": "x"}, "research", "Need current data", "example.org")
    assert denied["allowed"] is False
    guarded_local_call(root)
    allowed = guard_tool(root, "T1", "S1", "web", {"q": "x"}, "research", "Need current data", "example.org")
    assert allowed["allowed"] is True
    result = complete_tool(root, allowed["execution_token"], {"q": "x"}, True, "network result", "S1")
    assert result["classification"] == "network"


def test_execution_token_is_single_use_and_argument_bound(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    guard = guard_tool(root, "T1", "S1", "bounded_file_read", {"path": "src/a.py"})
    with pytest.raises(RuntimeError, match="arguments"):
        complete_tool(root, guard["execution_token"], {"path": "src/b.py"}, True, "x", "S1")
    complete_tool(root, guard["execution_token"], {"path": "src/a.py"}, True, "x", "S1")
    with pytest.raises(RuntimeError, match="already been used"):
        complete_tool(root, guard["execution_token"], {"path": "src/a.py"}, True, "x", "S1")


def test_execution_token_is_session_bound(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    guard = guard_tool(root, "T1", "S1", "bounded_file_read", {})
    with pytest.raises(RuntimeError, match="another session"):
        complete_tool(root, guard["execution_token"], {}, True, "x", "S2")


def test_secret_redaction() -> None:
    text = redact_text("authorization: abc password=hunter2 Bearer abc.def")
    assert "hunter2" not in text and "abc.def" not in text
    assert "[REDACTED]" in text


def test_claim_uses_canonical_tool_call(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    call_id = guarded_local_call(root)
    claim = record_claim(root, "T1", "Local source confirms behavior", "business_logic", "high", [call_id])
    assert claim["evidence_count"] == 1


def test_network_evidence_rejected_by_default(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    guarded_local_call(root)
    g = guard_tool(root, "T1", "S1", "web", {"q": "x"}, "research", "Need current data", "example.org")
    call = complete_tool(root, g["execution_token"], {"q": "x"}, True, "x", "S1")
    with pytest.raises(RuntimeError, match="not local evidence"):
        record_claim(root, "T1", "Claim", "security", "high", [call["tool_call_id"]])


def test_manual_done_for_automated_step_is_blocked(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    for step in ["tests", "documentation_check", "synchronize", "execute_guarded"]:
        with pytest.raises(RuntimeError, match="canonical"):
            mark_step(root, "T1", step, "done", "Trust me")


def test_automated_step_records_provenance(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    complete_automated_step(root, "T1", "tests", "run-tests", {"ok": True}, 0)
    row = next(x for x in workflow_status(root, "T1")["steps"] if x["step_name"] == "tests")
    assert row["completion_source"] == "auto"
    assert row["result_hash"]


def test_session_current_tasks_are_isolated(tmp_path: Path) -> None:
    root = project(tmp_path)
    start_task(root, "T1", "one"); start_task(root, "T2", "two")
    set_current_task(root, "T1", "test", "S1"); set_current_task(root, "T2", "test", "S2")
    assert current_task_id(root, "S1") == "T1"
    assert current_task_id(root, "S2") == "T2"


def test_drift_distinguishes_uninitialized_baseline(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = drift_check(root)
    assert result["baseline_state"] == "not_initialized"
    assert result["drift_detected"] is False
    assert result["review_required"] is True


def test_noninteractive_ack_is_labeled_machine(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = ack_baseline(root, "ci", force_noninteractive=True)
    assert result["acknowledgement_method"] == "ci_machine"


def test_recursive_tracking_includes_nested_runtime_module(tmp_path: Path) -> None:
    root = project(tmp_path)
    nested = root / ".agents" / "agentos" / "adapters" / "jira.py"
    nested.parent.mkdir(); nested.write_text("x=1\n")
    assert ".agents/agentos/adapters/jira.py" in tracked_files(root)


def test_drift_detects_runtime_and_hook_changes(tmp_path: Path) -> None:
    root = project(tmp_path); ack_baseline(root, "ci", force_noninteractive=True)
    launcher = ".agents/bin/agentos.cmd" if os.name == "nt" else ".agents/bin/agentos"
    (root / launcher).write_bytes(b"changed\n")
    result = drift_check(root)
    assert result["drift_detected"] is True
    assert any(x["file_path"] == launcher for x in result["changes"])


def test_sensitive_override_is_staged_not_applied(tmp_path: Path) -> None:
    root = project(tmp_path)
    local = root / ".agents" / "config" / "governance.local.json"
    local.write_text(json.dumps({"claim_policy": {"allow_network_evidence": True}}))
    status = local_override_status(root)
    assert status["status"] == "pending"
    assert load_policy(root)["claim_policy"]["allow_network_evidence"] is False
    approve_local_override(root, "reviewer", "Approved for this project")
    assert load_policy(root)["claim_policy"]["allow_network_evidence"] is True


def test_safe_override_applies_without_sensitive_approval(tmp_path: Path) -> None:
    root = project(tmp_path)
    local = root / ".agents" / "config" / "governance.local.json"
    local.write_text(json.dumps({"source_root": "app"}))
    assert load_policy(root)["source_root"] == "app"


def test_report_prerequisites_expose_invalid_provenance(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    with connect(root) as c:
        c.execute("UPDATE workflow_steps SET status='done',completion_source='manual',result_hash=NULL WHERE task_id='T1' AND step_name='tests'")
    assert "tests" in workflow_status(root, "T1")["invalid_provenance"]


def test_instruction_check_detects_modern_rule_files(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / ".clinerules").write_text("rules")
    result = instruction_check(root)
    assert result["ok"] is False and ".clinerules" in result["duplicate_instruction_sources"]


def test_release_docs_and_version_are_synchronized() -> None:
    assert docs_check(ROOT)["ok"] is True
    assert instruction_check(ROOT)["ok"] is True
    assert load_policy(ROOT)["version"] == (ROOT / "VERSION").read_text().strip()


def test_prepare_change_still_enforces_write_scope(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    (root / "src" / "a.py").write_text("def a():\n    return 1\n")
    result = prepare_change(root, "T1", "modify", "src/a.py", "Change a")
    assert result["ready"] is True


def test_schema_v11_proxy_and_concurrency_tables(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert db_status(root) == {"current": SCHEMA_VERSION, "required": SCHEMA_VERSION, "is_current": True}
    with connect(root) as c:
        tables = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"proxy_executions", "external_audit_checkpoints", "resource_leases", "file_versions", "task_handoffs"} <= tables


def test_proxy_read_creates_signed_external_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.external_audit import verify_external_log
    from agentos.proxy import proxy_execute
    root = project(tmp_path); ready(root)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit-home"))
    ack_baseline(root, "ci", force_noninteractive=True)
    (root / "src" / "a.py").write_text("value = 1\n", encoding="utf-8")
    result = proxy_execute(root, "T1", "S1", "agentos.read_file", {"path": "src/a.py"})
    assert result["success"] is True
    assert result["tool_call_id"]
    assert result["external_audit"]["signature"]
    assert verify_external_log(root)["ok"] is True
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) n FROM proxy_executions").fetchone()["n"] == 1


def test_proxy_blocks_when_baseline_not_initialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.proxy import proxy_execute
    root = project(tmp_path); ready(root)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit-home"))
    (root / "src" / "a.py").write_text("x=1\n")
    with pytest.raises(RuntimeError, match="baseline"):
        proxy_execute(root, "T1", "S1", "agentos.read_file", {"path": "src/a.py"})


def test_external_audit_detects_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.external_audit import append_signed_event, log_path, verify_external_log
    root = project(tmp_path)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit-home"))
    append_signed_event(root, "test", {"value": 1}, None, "S1")
    path = log_path(root)
    text = path.read_text(encoding="utf-8").replace('"value": 1', '"value": 2')
    path.write_text(text, encoding="utf-8")
    assert verify_external_log(root)["ok"] is False


def test_proxy_rejects_unexposed_backend_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.proxy import proxy_execute
    root = project(tmp_path); ready(root)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit-home"))
    ack_baseline(root, "ci", force_noninteractive=True)
    with pytest.raises(RuntimeError, match="not exposed"):
        proxy_execute(root, "T1", "S1", "raw_shell", {"command": ["echo", "x"]})


def test_mcp_server_advertises_only_proxy_tools() -> None:
    from agentos.mcp_server import TOOLS
    names = {item["name"] for item in TOOLS}
    assert {"agentos.read_file", "agentos.write_file", "agentos.run_command", "agentos.http_request", "agentos.acquire_resource", "agentos.handoff_task"} <= names


def test_external_audit_is_outside_repository_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.external_audit import log_path
    root = project(tmp_path)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "external-audit"))
    assert root.resolve() not in log_path(root).parents


def test_process_exec_rejects_network_client() -> None:
    from agentos.proxy import _command_profile
    policy = load_policy(ROOT)
    with pytest.raises(RuntimeError, match="denied"):
        _command_profile(["curl", "https://example.com"], policy)


def test_process_exec_rejects_python_inline_code() -> None:
    from agentos.proxy import _command_profile
    policy = load_policy(ROOT)
    with pytest.raises(RuntimeError, match="inline Python"):
        _command_profile(["python3", "-c", "print('x')"], policy)


def test_process_exec_accepts_pytest_profile() -> None:
    from agentos.proxy import _command_profile
    policy = load_policy(ROOT)
    assert _command_profile(["python3", "-m", "pytest", "-q"], policy) == "test"


def test_file_symlink_escape_is_denied(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    outside = tmp_path / "outside.py"; outside.write_text("x=1\n")
    link = root / "src" / "outside-link.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert check_write(root, "T1", str(link))["allowed"] is False


def test_directory_symlink_escape_is_denied(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    outside = tmp_path / "outside-dir"; outside.mkdir()
    link = root / "src" / "outside-dir-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert check_write(root, "T1", str(link / "x.py"))["allowed"] is False


def test_internal_symlink_is_allowed(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    real = root / "src" / "real.py"; real.write_text("x=1\n")
    link = root / "src" / "alias.py"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert check_write(root, "T1", str(link))["allowed"] is True


def test_audit_key_rotation_preserves_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.external_audit import append_signed_event, rotate_signing_key, verify_external_log
    root = project(tmp_path)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    append_signed_event(root, "before", {"x": 1}, None, "S1")
    rotation = rotate_signing_key(root, "reviewer", "scheduled")
    append_signed_event(root, "after", {"x": 2}, None, "S1")
    assert rotation["old_key_id"] != rotation["new_key_id"]
    assert verify_external_log(root)["ok"] is True


def test_audit_verify_accepts_empty_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.external_audit import verify_external_log
    root = project(tmp_path); monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "empty-audit"))
    assert verify_external_log(root)["state"] == "empty"


def test_docs_check_current_release_is_consistent() -> None:
    report = docs_check(ROOT)
    assert report["content_consistency"]["ok"] is True
    assert report["version"]["VERSION"] == (ROOT / "VERSION").read_text().strip()



def test_exclusive_file_lease_blocks_other_session(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root, "T1"); start_task(root, "T2", "Other task"); seed_workflow(root, "T2"); approve_task(root, "T2", ["src"])
    assert claim_task(root, "T1", "S1")["claimed"] is True
    first = acquire_resource(root, "T1", "S1", "file", "src/a.py", "exclusive_write")
    assert first["acquired"] is True
    second = acquire_resource(root, "T2", "S2", "file", "src/a.py", "exclusive_write")
    assert second["acquired"] is False
    assert second["reason"] == "resource_lease_conflict"


def test_shared_read_leases_are_compatible(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root, "T1"); start_task(root, "T2", "Other task"); seed_workflow(root, "T2"); approve_task(root, "T2", ["src"])
    assert acquire_resource(root, "T1", "S1", "file", "src/a.py", "shared_read")["acquired"] is True
    assert acquire_resource(root, "T2", "S2", "file", "src/a.py", "shared_read")["acquired"] is True


def test_atomic_write_rejects_stale_expected_hash(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root); claim_task(root, "T1", "S1")
    path = root / "src" / "a.py"; path.write_bytes(b"one\n")
    old_hash = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    first = atomic_write(root, "T1", "S1", "src/a.py", "two\n", old_hash)
    assert first["allowed"] is True and first["atomic"] is True
    stale = atomic_write(root, "T1", "S1", "src/a.py", "three\n", old_hash)
    assert stale["allowed"] is False
    assert stale["reason"] == "stale_write_conflict"
    assert path.read_text(encoding="utf-8") == "two\n"


def test_existing_file_write_requires_expected_hash(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root); claim_task(root, "T1", "S1")
    (root / "src" / "a.py").write_text("one\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="expected_hash"):
        atomic_write(root, "T1", "S1", "src/a.py", "two\n", None)


def test_task_single_writer_and_handoff(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    assert claim_task(root, "T1", "S1")["claimed"] is True
    blocked = claim_task(root, "T1", "S2")
    assert blocked["claimed"] is False
    moved = handoff_task(root, "T1", "S1", "S2", "Reviewed handoff")
    assert moved["handed_off"] is True
    assert claim_task(root, "T1", "S2")["claimed"] is True


def test_lease_heartbeat_and_release(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root); claim_task(root, "T1", "S1")
    lease = acquire_resource(root, "T1", "S1", "file", "src/a.py")
    assert heartbeat_resource(root, lease["lease_id"], "T1", "S1")["renewed"] is True
    assert release_resource(root, lease["lease_id"], "T1", "S1")["released"] is True
    assert list_resources(root, "T1") == []


def test_mcp_lists_coordination_tools() -> None:
    from agentos.mcp_server import TOOLS
    names={x['name'] for x in TOOLS}
    assert {'agentos.acquire_resource','agentos.handoff_task','agentos.force_reclaim_task'} <= names

def test_coordination_proxy_creates_signed_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.proxy import proxy_execute
    root=project(tmp_path); ready(root); monkeypatch.setenv('AGENTOS_AUDIT_HOME',str(tmp_path/'audit')); ack_baseline(root,'ci',force_noninteractive=True)
    result=proxy_execute(root,'T1','S1','agentos.acquire_resource',{'resource_type':'file','resource':'src/a.py','lease_mode':'exclusive_write'})
    assert result['external_audit']['signature']
    with connect(root) as c: assert c.execute('SELECT COUNT(*) n FROM coordination_events').fetchone()['n']==1

def test_handoff_rejects_non_owner_caller(tmp_path: Path) -> None:
    from agentos.concurrency import claim_task, handoff_task
    root=project(tmp_path); ready(root); claim_task(root,'T1','S1')
    with pytest.raises(RuntimeError,match='current task owner'): handoff_task(root,'T1','S2','S3','steal')

def test_symbol_lease_rejected_when_disabled(tmp_path: Path) -> None:
    from agentos.concurrency import acquire_resource
    root=project(tmp_path); ready(root)
    with pytest.raises(RuntimeError,match='disabled'): acquire_resource(root,'T1','S1','symbol','src/a.py::a')

def test_expired_lease_not_listed_active(tmp_path: Path) -> None:
    from agentos.concurrency import acquire_resource, list_resources
    root=project(tmp_path); ready(root); r=acquire_resource(root,'T1','S1','file','src/a.py',ttl_seconds=10)
    with connect(root) as c: c.execute("UPDATE resource_leases SET expires_at='2000-01-01T00:00:00Z' WHERE id=?",(r['lease_id'],))
    assert list_resources(root,'T1',True)==[]

def test_write_lease_rejects_out_of_scope(tmp_path: Path) -> None:
    from agentos.concurrency import acquire_resource
    root=project(tmp_path); ready(root)
    result=acquire_resource(root,'T1','S1','file','README.md')
    assert result['acquired'] is False



def test_security_schema_tables(tmp_path: Path) -> None:
    root = project(tmp_path)
    with connect(root) as c:
        tables = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"session_tokens", "signed_state_index", "authenticated_requests", "execution_manifests", "state_reconciliation_runs"} <= tables


def test_capability_session_replay_and_revoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path); ready(root)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit-home"))
    from agentos.security import authenticate_request, issue_session_token, revoke_session
    issued = issue_session_token(root, "T1", "S1", ["filesystem.read"], 300)
    auth = authenticate_request(root, issued["session_token"], "T1", "filesystem.read", {"path": "src/a.py"}, "R1", 1)
    assert auth["session_id"] == "S1"
    with pytest.raises(RuntimeError, match="replayed_request"):
        authenticate_request(root, issued["session_token"], "T1", "filesystem.read", {"path": "src/a.py"}, "R1", 1)
    revoke_session(root, issued["token_id"], "operator", "test")
    with pytest.raises(RuntimeError, match="revoked_session_token"):
        authenticate_request(root, issued["session_token"], "T1", "filesystem.read", {"path": "src/a.py"}, "R2", 2)


def test_static_agentos_import_is_denied(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    from agentos.proxy import _scan_agentos_imports
    path = root / "src" / "bad_test.py"; path.write_text("import agentos.workflow\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="agentos_internal_import_denied"):
        _scan_agentos_imports(root, ["pytest", "src/bad_test.py"], root)


def test_workflow_state_is_signed_and_reconcilable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path); monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit-home")); ready(root)
    from agentos.security import reconcile_state
    status = workflow_status(root, "T1")
    approved = next(x for x in status["steps"] if x["step_name"] == "approve_task")
    assert approved["external_event_hash"]
    result = reconcile_state(root)
    assert result["ok"] is True


def test_audit_daemon_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTOS_AUDIT_DAEMON_TOKEN", raising=False)
    from agentos.audit_daemon import main
    with pytest.raises(SystemExit, match="AGENTOS_AUDIT_DAEMON_TOKEN is required"):
        main()


def test_context_pack_is_bounded_and_stale_aware(tmp_path: Path) -> None:
    root=project(tmp_path); ready(root)
    from agentos.context_runtime import build_context_pack, context_status
    result=build_context_pack(root,'T1',max_lines=80)
    assert result['revision']==1
    assert sum(len(x['excerpt'].splitlines()) for x in result['sources']) <= 80
    assert context_status(root,'T1')['stale'] is False
    (root/'AGENTS.md').write_text((root/'AGENTS.md').read_text(encoding='utf-8')+'\nchanged\n',encoding='utf-8')
    assert 'AGENTS.md' in context_status(root,'T1')['stale_sources']


def test_context_pack_revisions_supersede_previous(tmp_path: Path) -> None:
    root=project(tmp_path); ready(root)
    from agentos.context_runtime import build_context_pack
    assert build_context_pack(root,'T1')['revision']==1
    assert build_context_pack(root,'T1')['revision']==2
    with connect(root) as c:
        rows=c.execute("SELECT revision,status FROM context_packs WHERE task_id='T1' ORDER BY revision").fetchall()
    assert [(r['revision'],r['status']) for r in rows]==[(1,'superseded'),(2,'active')]


def test_project_finding_is_deduplicated(tmp_path: Path) -> None:
    root=project(tmp_path); ready(root)
    from agentos.memory import record_finding
    first=record_finding(root,'duplicate','Repeated date converter','src/a.py','convert','T1')
    second=record_finding(root,'duplicate','Repeated date converter','src/a.py','convert','T1')
    assert first['finding_id']==second['finding_id']
    assert second['occurrences']==2


def test_project_memory_provenance_becomes_stale(tmp_path: Path) -> None:
    root=project(tmp_path); ready(root)
    from agentos.memory import query_memory, remember, validate_memory
    source=root/'src'/'a.py'; source.parent.mkdir(parents=True,exist_ok=True); source.write_text('def a():\n    return 1\n',encoding='utf-8')
    result=remember(root,'semantic','Function a is the canonical implementation','src/a.py','T1',0.9)
    assert query_memory(root,'canonical')[0]['id']==result['memory_id']
    source.write_text('def a():\n    return 2\n',encoding='utf-8')
    validation=validate_memory(root)
    assert result['memory_id'] in validation['stale_memory_ids']
    assert query_memory(root,'canonical')==[]


def test_knowledge_runtime_schema(tmp_path: Path) -> None:
    root=project(tmp_path)
    with connect(root) as c:
        tables={r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'context_packs','project_findings','project_memory'} <= tables


def test_async_job_manifest_and_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=project(tmp_path); monkeypatch.setenv("AGENTOS_AUDIT_HOME",str(tmp_path/"audit")); ready(root)
    complete_automated_step(root,"T1","prepare_change","prepare-change",{"ready":True})
    from agentos.jobs import discover_tools, submit_job
    result=submit_job(root,"T1","S1",["python3","-m","pytest","--version"],auto_start=False)
    assert result["state"]=="queued"
    assert result["spec"]["network_policy"]=="none"
    assert "agentos.run_command_async" in discover_tools(root,"T1")["available_now"]


def test_task_plan_revision_and_precommit_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=project(tmp_path); monkeypatch.setenv("AGENTOS_AUDIT_HOME",str(tmp_path/"audit")); ready(root)
    from agentos.planning import approve_plan, precommit_check, submit_plan
    submitted=submit_plan(root,"T1","S1",{"goal":"change a","files":["src/a.py"],"tests":["tests/test_a.py"]})
    approved=approve_plan(root,submitted["plan_id"],"human","reviewed")
    assert approved["status"]=="active"
    assert precommit_check(root,"T1",["src/a.py"])["ok"] is True
    denied=precommit_check(root,"T1",["README.md"])
    assert denied["ok"] is False
    assert denied["blockers"]["outside_scope"]==["README.md"]


def test_evaluation_harness_and_export(tmp_path: Path) -> None:
    root=project(tmp_path); ready(root)
    from agentos.evaluation import aggregate_metrics, export_metrics
    report=aggregate_metrics(root,agent="agent-a",model="model-x")
    assert report["metrics_schema_version"]==1
    assert report["dimensions"]["repository_version"]==(ROOT / "VERSION").read_text().strip()
    exported=export_metrics(root,".agents/runtime/evaluation/report.json","json",agent="agent-a",model="model-x")
    assert exported["ok"] is True
    assert Path(exported["path"]).exists()


def test_execution_platform_schema(tmp_path: Path) -> None:
    root=project(tmp_path)
    with connect(root) as c:
        tables={r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"async_jobs","job_events","task_plans","precommit_checks","evaluation_runs"} <= tables



def test_controlled_evolution_requires_evaluation_and_staged_activation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=project(tmp_path); monkeypatch.setenv("AGENTOS_AUDIT_HOME",str(tmp_path/"audit")); ready(root)
    from agentos.evolution import create_proposal, simulate_proposal, transition_proposal
    with pytest.raises(RuntimeError,match="evaluation_baseline_required"):
        create_proposal(root,"Tighten writes",[],{"filesystem_policy":{"strict":True}},"Reduce unsafe writes",["false blocks"],{"action":"restore previous policy"},"operator")
    from agentos.evaluation import aggregate_metrics
    aggregate_metrics(root,agent="agent-a",model="model-x")
    proposal=create_proposal(root,"Tighten writes",[],{"filesystem_policy":{"strict":True}},"Reduce unsafe writes",["false blocks"],{"action":"restore previous policy"},"operator")
    assert proposal["status"]=="draft"
    assert simulate_proposal(root,proposal["proposal_id"])["status"]=="simulated"
    with pytest.raises(RuntimeError,match="invalid_evolution_transition"):
        transition_proposal(root,proposal["proposal_id"],"active","operator","skip gates")
    for status in ("reviewed","shadow","canary","active","rolled_back"):
        result=transition_proposal(root,proposal["proposal_id"],status,"operator",f"move to {status}")
        assert result["status"]==status


def test_multi_agent_requires_capability_role_and_fresh_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=project(tmp_path); monkeypatch.setenv("AGENTOS_AUDIT_HOME",str(tmp_path/"audit")); ready(root)
    from agentos.collaboration import assign_role, collaboration_readiness, send_message
    from agentos.context_runtime import build_context_pack
    from agentos.security import issue_session_token
    assert collaboration_readiness(root,"T1")["ok"] is False
    issue_session_token(root,"T1","EXEC")
    issue_session_token(root,"T1","REVIEW")
    assign_role(root,"T1","EXEC","executor","operator")
    assign_role(root,"T1","REVIEW","reviewer","operator")
    assert collaboration_readiness(root,"T1")["ok"] is False
    build_context_pack(root,"T1")
    assert collaboration_readiness(root,"T1")["ok"] is True
    message=send_message(root,"T1","REVIEW","EXEC","review_request",{"path":"src/a.py"},"selected-artifacts",["src/a.py"])
    assert message["status"]=="sent"
    with pytest.raises(RuntimeError,match="role_message_permission_denied"):
        send_message(root,"T1","EXEC","REVIEW","scope_request",{},"metadata-only")
    (root/"AGENTS.md").write_text((root/"AGENTS.md").read_text(encoding="utf-8")+"\nstale\n",encoding="utf-8")
    with pytest.raises(RuntimeError,match="collaboration_prerequisites_not_stable"):
        send_message(root,"T1","REVIEW","EXEC","review_request",{},"metadata-only")


def test_adaptive_multi_agent_schema(tmp_path: Path) -> None:
    root=project(tmp_path)
    with connect(root) as c:
        tables={r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"evolution_proposals","evolution_stage_events","task_role_assignments","task_messages"} <= tables


def test_context_symbol_window_reports_omissions(tmp_path: Path) -> None:
    root=project(tmp_path); ready(root)
    from agentos.context_runtime import build_context_pack, context_explain
    for i in range(8):
        (root/'src'/f'mod_{i}.py').write_text(f'def important_{i}():\n    return {i}\n')
    from agentos.indexing import index_build
    index_build(root,'src')
    result=build_context_pack(root,'T1',max_lines=20,mode='symbol_window')
    assert result['compaction_mode']=='symbol_window'
    assert result['total_candidate_files'] >= result['included_files']
    assert 'omitted_files' in context_explain(root,'T1')

def test_collaboration_disclosure_filters_payload(tmp_path: Path) -> None:
    from agentos.collaboration import _filter_payload
    payload={'title':'x','summary':'safe','secret':'hidden'}
    assert 'secret' not in _filter_payload('metadata-only',payload,[])
    assert _filter_payload('summary',payload,[])=={'summary':'safe'}
    assert _filter_payload('full-task-context',payload,[])==payload


def test_skill_promotion_and_retrieval(tmp_path, monkeypatch):
    root=project(tmp_path)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME",str(tmp_path/"audit"))
    from agentos.memory import remember
    from agentos.skills import promote_skill_candidate, graduate_skill, match_skills, revoke_skill
    from agentos.retrieval import search_knowledge
    item=remember(root,"procedural","Convert Excel serial dates by validating epoch and timezone.",task_id="T1",confidence=0.9,evidence_hash="abc123")
    candidate=promote_skill_candidate(root,item["memory_id"],"AGENT-A")
    assert candidate["status"]=="candidate"
    assert match_skills(root,"excel date")==[]
    graduated=graduate_skill(root,candidate["skill_id"],"human_reviewer","Reviewed procedure")
    assert graduated["status"]=="graduated"
    assert match_skills(root,"excel date")[0]["id"]==candidate["skill_id"]
    result=search_knowledge(root,"excel date",["memory","skill"],10)
    assert result["ok"] and not result["network_used"] and not result["llm_used"]
    assert {x["kind"] for x in result["results"]} >= {"memory","skill"}
    revoke_skill(root,candidate["skill_id"],"obsolete","human_reviewer")
    assert match_skills(root,"excel date")==[]


def test_skill_graduation_rejects_agent_identity(tmp_path, monkeypatch):
    root=project(tmp_path)
    monkeypatch.setenv("AGENTOS_AUDIT_HOME",str(tmp_path/"audit"))
    from agentos.memory import remember
    from agentos.skills import promote_skill_candidate, graduate_skill
    item=remember(root,"procedural","Run deterministic validation before release.",task_id="T1",confidence=0.9,evidence_hash="evidence")
    candidate=promote_skill_candidate(root,item["memory_id"],"AGENT-A")
    import pytest
    with pytest.raises(RuntimeError): graduate_skill(root,candidate["skill_id"],"agent","self approved")


def test_db_schema_legacy_25_updated(tmp_path):
    root=project(tmp_path)
    from agentos.core import db_status
    assert db_status(root)["required"]==SCHEMA_VERSION


def test_optional_local_embeddings_and_rag(tmp_path):
    root=project(tmp_path)
    from agentos.memory import remember
    from agentos.embeddings import build_embedding_index, rag_query
    from agentos.retrieval import search_knowledge
    remember(root,"semantic","Spreadsheet serial dates require explicit epoch validation.",task_id="T1",confidence=0.9,evidence_hash="e1")
    indexed=build_embedding_index(root,["memory"])
    assert indexed["indexed"] >= 1 and not indexed["network_used"] and not indexed["llm_used"]
    result=search_knowledge(root,"validate spreadsheet date epoch",["memory"],10,"local_feature_hash_v1")
    assert result["backend"]=="local_feature_hash_v1" and result["result_count"]>=1
    rag=rag_query(root,"validate spreadsheet date epoch",["memory"],top_k=3)
    assert rag["result_count"]>=1 and rag["context_hash"] and not rag["network_used"]


def test_use_case_driven_knowledge_graph(tmp_path, monkeypatch):
    root=project(tmp_path); monkeypatch.setenv("AGENTOS_AUDIT_HOME",str(tmp_path/"audit"))
    from agentos.memory import remember
    from agentos.skills import promote_skill_candidate, graduate_skill
    from agentos.knowledge_graph import build_graph, graph_neighbors, graph_path
    item=remember(root,"procedural","Validate deterministic release evidence.",task_id="T1",confidence=0.9,evidence_hash="evidence")
    skill=promote_skill_candidate(root,item["memory_id"],"AGENT-A")
    graduate_skill(root,skill["skill_id"],"human_reviewer","reviewed")
    built=build_graph(root)
    assert built["nodes"]>=2 and "skill_provenance" in built["use_cases"]
    neighbors=graph_neighbors(root,f"skill:{skill['skill_id']}")
    assert any(x["relation"]=="derived_from" for x in neighbors["neighbors"])
    path=graph_path(root,f"skill:{skill['skill_id']}",f"memory:{item['memory_id']}")
    assert path["ok"] is True


def test_db_schema_27(tmp_path):
    root=project(tmp_path)
    from agentos.core import db_status
    assert db_status(root)["required"]==SCHEMA_VERSION
    with connect(root) as c:
        tables={r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"knowledge_embeddings","rag_retrieval_events","knowledge_nodes","knowledge_edges"} <= tables


def test_v0192_v0195_capabilities(tmp_path):
    root=project(tmp_path)
    from agentos.core import start_task
    start_task(root,"T-NEW","use approved workflow skill and memory"); approve_task(root,"T-NEW",["src"])
    from agentos.memory import remember, query_memory, forget_identity
    remember(root,"semantic","private preference",task_id="T-NEW",owner_scope="user:alice",consent_source="explicit-test")
    assert query_memory(root,"private",identity="alice")
    assert not query_memory(root,"private")
    assert forget_identity(root,"alice")["revoked_count"]==1
    from agentos.evaluation import record_outcome, compare_outcomes
    record_outcome(root,"T-NEW","success","human",task_category="unit")
    cmp=compare_outcomes(root,{"task_category":"unit"},{"task_category":"unit"})
    assert cmp["warning"]=="insufficient_sample_size"
    from agentos.storage import backup_create, backup_verify
    b=backup_create(root,".agents/runtime/test-backup.zip")
    assert backup_verify(root,b["path"])["ok"]
