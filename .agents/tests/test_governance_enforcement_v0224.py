"""AgentOS v0.22.4 unified governance enforcement and signed-audit tests."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".agents") not in sys.path:
    sys.path.insert(0, str(ROOT / ".agents"))

from agentos.concurrency import claim_task
from agentos.controlled_target_insert import execute_target_insert
from agentos.core import approve_task, start_task
from agentos.database_boundary import register_connection
from agentos.db import SCHEMA_VERSION, connect
from agentos.drift import ack_baseline
from agentos.external_audit import verify_external_log
from agentos.human_decision import record_clarity_assessment
from agentos.governance_enforcement import GovernanceEnforcementError
from agentos.policy import load_policy
from agentos.workflow import complete_automated_step, seed_workflow


def _agentos_args(root: Path, *args: str) -> list[str]:
    """Return the native AgentOS launcher command for the current platform."""
    if os.name == "nt":
        return [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", str(root / ".agents/bin/agentos.cmd"), *args]
    return [str(root / ".agents/bin/agentos"), *args]


def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "runtime", "agentos.db", "__pycache__", ".pytest_cache", "MANIFEST.json", "CHECKSUMS.sha256"))
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    monkeypatch.setenv("AGENTOS_AUDIT_SINK", "jsonl")
    return root


def prepare(root: Path, *, task_id: str = "T-GOV", session_id: str = "S-GOV", approved: bool = True) -> None:
    start_task(root, task_id, "Governed database-domain mutation")
    seed_workflow(root, task_id)
    record_clarity_assessment(
        root, task_id, "pytest-fixture",
        objective_understood=True,
        scope_understood=True,
        constraints_understood=True,
        acceptance_understood=True,
    )
    if approved:
        approve_task(root, task_id, [".agents", "src", "tests"])
        complete_automated_step(root, task_id, "approve_task", "approve-task", {"approved": True})
    claim_task(root, task_id, session_id)
    ack_baseline(root, "test-human", force_noninteractive=True, session_id=session_id)


def register_source(root: Path, **context):
    return register_connection(
        root,
        connection_alias="source1",
        role="SOURCE",
        engine="mssql",
        host="source.internal",
        database_name="HIS",
        domain_id="healthcare",
        credential_ref="env://TEST_SOURCE_DB",
        created_by="operator",
        **context,
    )


def test_schema_41_adds_governed_operation_and_event_correlation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    assert SCHEMA_VERSION >= 41
    with connect(root) as c:
        versions = [int(r["version"]) for r in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
        assert versions == list(range(1, SCHEMA_VERSION + 1))
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        for table in ("db_boundary_events", "db_schema_mapping_events", "db_extraction_events", "db_target_insert_events", "identity_resolution_events", "db_recovery_events"):
            cols = {str(r["name"]) for r in c.execute(f"PRAGMA table_info({table})")}
            assert {"governed_operation_id", "external_event_hash"} <= cols


def test_valid_project_mutation_requires_task_and_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    with pytest.raises(GovernanceEnforcementError, match="task_id_and_session_id_required"):
        register_source(root)
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM db_connections").fetchone()[0] == 0


def test_unapproved_task_is_denied_and_signed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    prepare(root, approved=False)
    with pytest.raises(GovernanceEnforcementError, match="task_not_approved"):
        register_source(root, task_id="T-GOV", session_id="S-GOV")
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM db_connections").fetchone()[0] == 0
    assert verify_external_log(root)["ok"] is True
    log = Path(verify_external_log(root)["log_path"]).read_text(encoding="utf-8")
    assert "governed_operation.denied" in log


def test_wrong_session_owner_is_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    prepare(root)
    with pytest.raises(GovernanceEnforcementError, match="task_not_owned_by_session"):
        register_source(root, task_id="T-GOV", session_id="S-OTHER")


def test_valid_mutation_consumes_guard_token_and_links_signed_domain_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    prepare(root)
    result = register_source(root, task_id="T-GOV", session_id="S-GOV")
    assert result["ok"] is True
    with connect(root) as c:
        op = c.execute("SELECT * FROM governed_operations WHERE capability='db.connection.register'").fetchone()
        assert op and op["status"] == "completed" and op["success"] == 1
        guarded = c.execute("SELECT completed_at,success,tool_name FROM guarded_executions WHERE task_id='T-GOV' ORDER BY id DESC LIMIT 1").fetchone()
        assert guarded and guarded["completed_at"] and guarded["success"] == 1 and guarded["tool_name"] == "governed_operation"
        event = c.execute("SELECT governed_operation_id,external_event_hash FROM db_boundary_events WHERE event_type='connection_registered'").fetchone()
        assert event["governed_operation_id"] == op["operation_id"]
        assert event["external_event_hash"]
    verification = verify_external_log(root)
    assert verification["ok"] is True and verification["events"] >= 4


def test_unacknowledged_drift_blocks_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    prepare(root)
    with (root / "AGENTS.md").open("a", encoding="utf-8") as handle:
        handle.write("\n<!-- drift-test -->\n")
    with pytest.raises(GovernanceEnforcementError, match="unacknowledged_governance_drift"):
        register_source(root, task_id="T-GOV", session_id="S-GOV")
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM db_connections").fetchone()[0] == 0


def test_policy_poisoning_is_non_overridable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    path = root / ".agents/config/governance.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    policy["controlled_target_insert_policy"]["raw_target_insert_allowed"] = True
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(RuntimeError, match="non-overridable safety invariant"):
        load_policy(root)


def test_signed_audit_failure_blocks_before_domain_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    prepare(root)
    monkeypatch.setenv("AGENTOS_AUDIT_SINK", "unsupported-test-sink")
    with pytest.raises(RuntimeError, match="unsupported external audit sink"):
        register_source(root, task_id="T-GOV", session_id="S-GOV")
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM db_connections").fetchone()[0] == 0


def test_high_risk_target_insert_is_inside_same_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    with pytest.raises(GovernanceEnforcementError, match="task_id_and_session_id_required"):
        execute_target_insert(root, 999)


def test_governance_policy_registers_privileged_capabilities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    cfg = load_policy(root)["governance_enforcement_policy"]
    caps = set(cfg["privileged_capabilities"])
    assert {"db.target_insert.execute", "db.identity.candidate.decide", "db.recovery.commit.decide", "db.connection.register"} <= caps
    assert cfg["mcp_privileged_mutation_exposed"] is False


def test_cli_prefix_context_routes_privileged_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    prepare(root)
    cp = subprocess.run(_agentos_args(
        root, "--task-id", "T-GOV", "--session-id", "S-GOV",
        "db-connection-register", "--alias", "cli-source", "--role", "SOURCE", "--engine", "mssql",
        "--host", "source.internal", "--database", "HIS", "--domain", "healthcare",
        "--credential-ref", "env://TEST_SOURCE_DB", "--created-by", "operator",
    ), cwd=root, text=True, capture_output=True, env=os.environ.copy())
    assert cp.returncode == 0, cp.stderr + cp.stdout
    payload = json.loads(cp.stdout)
    assert payload["ok"] is True


def test_cli_rejects_privileged_command_without_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = project(tmp_path, monkeypatch)
    cp = subprocess.run(_agentos_args(root, "db-connection-register", "--help"), cwd=root, text=True, capture_output=True, env=os.environ.copy())
    assert cp.returncode == 2
    assert "requires --task-id and --session-id" in cp.stderr
