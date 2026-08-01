"""AgentOS v0.12.0 adversarial, concurrency, and regression tests."""
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
from agentos.core import approve_task, check_write, db_status, docs_check, instruction_check, prepare_change, record_claim, record_tool_execution, start_task
from agentos.db import connect
from agentos.drift import ack_baseline, drift_check, tracked_files
from agentos.policy import approve_local_override, load_policy, local_override_status
from agentos.tooling import classify_tool, complete_tool, guard_tool, redact_text
from agentos.workflow import complete_automated_step, current_task_id, mark_step, seed_workflow, set_current_task, workflow_status


def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("agentos.db", "__pycache__", ".pytest_cache"))
    (root / "src").mkdir(exist_ok=True)
    return root


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
    assert db_status(root) == {"current": 11, "required": 11, "is_current": True}
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
    (root / ".agents" / "bin" / "agentos").write_text("changed\n")
    result = drift_check(root)
    assert result["drift_detected"] is True
    assert any(x["file_path"] == ".agents/bin/agentos" for x in result["changes"])


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
    assert load_policy(ROOT)["version"] == "0.12.0"


def test_prepare_change_still_enforces_write_scope(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    (root / "src" / "a.py").write_text("def a():\n    return 1\n")
    result = prepare_change(root, "T1", "modify", "src/a.py", "Change a")
    assert result["ready"] is True


def test_schema_v11_proxy_and_concurrency_tables(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert db_status(root) == {"current": 11, "required": 11, "is_current": True}
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
    assert names == {"agentos.read_file", "agentos.write_file", "agentos.run_command", "agentos.http_request"}


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
    assert report["version"]["VERSION"] == "0.12.0"



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
    path = root / "src" / "a.py"; path.write_text("one\n", encoding="utf-8")
    old_hash = __import__("hashlib").sha256(b"one\n").hexdigest()
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
