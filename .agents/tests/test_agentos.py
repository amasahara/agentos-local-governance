"""AgentOS v0.9.0 adversarial and regression tests."""
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


def test_schema_v8(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert db_status(root) == {"current": 8, "required": 8, "is_current": True}
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
    assert load_policy(ROOT)["version"] == "0.9.0"


def test_prepare_change_still_enforces_write_scope(tmp_path: Path) -> None:
    root = project(tmp_path); ready(root)
    (root / "src" / "a.py").write_text("def a():\n    return 1\n")
    result = prepare_change(root, "T1", "modify", "src/a.py", "Change a")
    assert result["ready"] is True
