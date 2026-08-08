from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.append(str(Path(__file__).parent))
from test_controlled_target_insert_v0220 import FakeTargetConnection, approved_run, setup_validated_batch  # noqa: E402

from agentos.controlled_target_insert import (
    ControlledTargetInsertError,
    execute_target_insert,
    get_target_insert_readiness,
    get_target_insert_receipt,
)
from agentos.mcp_reconciliation_recovery_gateway import ALL_TOOLS
from agentos.reconciliation_recovery import (
    ReconciliationRecoveryError,
    build_reconciliation_spec,
    create_reconciliation_run,
    get_reconciliation_run,
    get_reconciliation_summary,
    get_recovery_readiness,
    list_recovery_cases,
    list_recovery_checkpoints,
    recover_pending_lineage,
    resolve_commit_outcome,
    run_reconciliation,
    scan_recovery_cases,
    sync_reconciliation_recovery_schema,
)


def target_rows() -> list[dict]:
    return [
        {"birth_date": "2000-01-02", "patient_code": "BN001"},
        {"birth_date": None, "patient_code": "BN002"},
    ]


def provider(rows: list[dict]):
    def _provider(columns, business_fields, key_rows):
        assert set(columns) == {"birth_date", "patient_code"}
        assert business_fields == ["patient_code"]
        assert len(key_rows) == 2
        return rows
    return _provider


def committed_run(tmp_path: Path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    execute_target_insert(
        root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"},
        target_connection_factory=lambda *_: FakeTargetConnection(),
    )
    return root, state, run


def in_doubt_run(tmp_path: Path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    with pytest.raises(ControlledTargetInsertError, match="uncertain"):
        execute_target_insert(
            root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"},
            target_connection_factory=lambda *_: FakeTargetConnection(fail_commit=True),
        )
    assert get_target_insert_receipt(root, run["id"])["status"] == "in_doubt"
    return root, state, run


def test_schema_40_created(tmp_path):
    root, _ = setup_validated_batch(tmp_path)
    assert sync_reconciliation_recovery_schema(root)["schema"] == 40


def test_committed_insert_reconciles_whole_target_rows(tmp_path):
    root, _, run = committed_run(tmp_path)
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    result = run_reconciliation(root, recon["id"], target_row_provider=provider(target_rows()))["reconciliation"]
    assert result["status"] == "completed"
    assert result["outcome"] == "matched"
    assert result["matching_rows"] == 2 and result["missing_rows"] == 0 and result["unexpected_rows"] == 0


def test_reconciliation_detects_missing_and_changed_target_rows(tmp_path):
    root, _, run = committed_run(tmp_path)
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    changed = [{"birth_date": "1999-12-31", "patient_code": "BN001"}]
    result = run_reconciliation(root, recon["id"], target_row_provider=provider(changed))["reconciliation"]
    assert result["outcome"] in {"observed_partial", "mismatch"}
    assert result["missing_rows"] >= 1
    summary = get_reconciliation_summary(root, recon["id"])
    assert summary["reconciliation_findings"] >= 1
    assert summary["insert_status"] == "committed"


def test_select_spec_is_generated_read_only_without_values(tmp_path):
    root, _, run = committed_run(tmp_path)
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    spec = build_reconciliation_spec(root, recon["id"])
    assert spec["statement_class"] == "SELECT_ONLY"
    assert spec["sql_shape"].startswith("SELECT ")
    assert "INSERT" not in spec["sql_shape"].upper()
    assert "UPDATE" not in spec["sql_shape"].upper()
    assert spec["query_parameters_included"] is False
    blob = json.dumps(spec)
    assert "BN001" not in blob and "2000-01-02" not in blob


def test_in_doubt_never_auto_resolves_even_after_matched_reconciliation(tmp_path):
    root, _, run = in_doubt_run(tmp_path)
    scan_recovery_cases(root)
    case = [c for c in list_recovery_cases(root)["cases"] if c["case_type"] == "COMMIT_OUTCOME"][0]
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    result = run_reconciliation(root, recon["id"], target_row_provider=provider(target_rows()))["reconciliation"]
    assert result["outcome"] == "matched"
    assert get_target_insert_receipt(root, run["id"])["status"] == "in_doubt"
    with pytest.raises(ReconciliationRecoveryError):
        resolve_commit_outcome(root, case["id"], decision="committed_verified", decided_by="owner", human_confirmed=False)
    resolved = resolve_commit_outcome(root, case["id"], decision="committed_verified", decided_by="owner", human_confirmed=True)
    assert resolved["insert_status"] == "committed"
    receipt = get_target_insert_receipt(root, run["id"])
    assert receipt["status"] == "committed" and receipt["lineage_status"] == "complete"


def test_observed_none_human_resolution_enables_manual_retry_only(tmp_path):
    root, _, run = in_doubt_run(tmp_path)
    scan_recovery_cases(root)
    case = [c for c in list_recovery_cases(root)["cases"] if c["case_type"] == "COMMIT_OUTCOME"][0]
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    result = run_reconciliation(root, recon["id"], target_row_provider=provider([]))["reconciliation"]
    assert result["outcome"] == "observed_none"
    resolve_commit_outcome(root, case["id"], decision="not_committed_verified", decided_by="owner", human_confirmed=True)
    readiness = get_target_insert_readiness(root, run["id"])
    assert readiness["manual_retry_allowed"] is True and readiness["eligible_to_execute"] is True
    assert readiness["automatic_retry_after_committing_or_in_doubt"] is False
    success = FakeTargetConnection()
    receipt = execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: success)
    assert receipt["status"] == "committed" and success.committed is True


def test_partial_in_doubt_requires_manual_target_intervention(tmp_path):
    root, _, run = in_doubt_run(tmp_path)
    scan_recovery_cases(root)
    case = [c for c in list_recovery_cases(root)["cases"] if c["case_type"] == "COMMIT_OUTCOME"][0]
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    result = run_reconciliation(root, recon["id"], target_row_provider=provider(target_rows()[:1]))["reconciliation"]
    assert result["outcome"] == "observed_partial"
    with pytest.raises(ReconciliationRecoveryError):
        resolve_commit_outcome(root, case["id"], decision="committed_verified", decided_by="owner", human_confirmed=True)
    with pytest.raises(ReconciliationRecoveryError):
        resolve_commit_outcome(root, case["id"], decision="not_committed_verified", decided_by="owner", human_confirmed=True)
    manual = resolve_commit_outcome(root, case["id"], decision="manual_intervention", decided_by="owner", human_confirmed=True)
    assert manual["status"] == "manual_intervention" and manual["automatic_target_repair"] is False
    readiness = get_recovery_readiness(root, run["id"])
    assert readiness["manual_target_intervention_required"] is True and readiness["automatic_target_repair_allowed"] is False


def test_lineage_pending_can_be_recovered_without_target_write(tmp_path):
    root, _, run = committed_run(tmp_path)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        conn.execute("DELETE FROM target_record_lineage WHERE insert_run_id=?", (run["id"],))
        conn.execute("UPDATE db_target_insert_runs SET lineage_status='pending',lineage_finalized_at=NULL WHERE id=?", (run["id"],))
    scan_recovery_cases(root)
    case = [c for c in list_recovery_cases(root)["cases"] if c["case_type"] == "LINEAGE_FINALIZATION"][0]
    result = recover_pending_lineage(root, case["id"], recovered_by="owner", human_confirmed=True)
    assert result["lineage_status"] == "complete" and result["target_write_attempted"] is False
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM target_record_lineage WHERE insert_run_id=?", (run["id"],)).fetchone()[0] == 2


def test_reconciliation_state_never_persists_raw_business_values(tmp_path):
    root, _, run = committed_run(tmp_path)
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    run_reconciliation(root, recon["id"], target_row_provider=provider(target_rows()))
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        chunks = []
        for table, columns in [
            ("db_reconciliation_runs", ["plan_json", "evidence_hash"]),
            ("db_reconciliation_findings", ["evidence_json"]),
            ("db_recovery_checkpoints", ["checkpoint_json"]),
            ("db_recovery_events", ["event_json"]),
        ]:
            rows = conn.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall()
            chunks.extend(str(value) for row in rows for value in row if value is not None)
    blob = "\n".join(chunks)
    assert "BN001" not in blob and "BN002" not in blob and "2000-01-02" not in blob


def test_recovery_checkpoints_are_hash_only_read_api(tmp_path):
    root, _, run = committed_run(tmp_path)
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    run_reconciliation(root, recon["id"], target_row_provider=provider(target_rows()))
    checkpoints = list_recovery_checkpoints(root, run["id"])["checkpoints"]
    assert len(checkpoints) >= 3
    assert all(len(item["checkpoint_hash"]) == 64 and item["raw_values_included"] is False for item in checkpoints)


def test_mcp_catalog_remains_read_only_for_recovery(tmp_path):
    names = {item["name"] for item in ALL_TOOLS}
    assert len(names) == 37
    assert {
        "agentos.db_reconciliation_get", "agentos.db_reconciliation_summary_get", "agentos.db_reconciliation_spec_get",
        "agentos.db_recovery_cases_get", "agentos.db_recovery_readiness_get", "agentos.db_recovery_checkpoints_get",
    } <= names
    forbidden = ("execute", "approve", "decide", "finalize", "run_reconciliation", "credential")
    assert not any(any(word in name for word in forbidden) for name in names)


def test_recovery_summary_preserves_pipeline_accounting(tmp_path):
    root, _, run = committed_run(tmp_path)
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    run_reconciliation(root, recon["id"], target_row_provider=provider(target_rows()))
    summary = get_reconciliation_summary(root, recon["id"])
    assert summary["source_selected_rows"] == 2
    assert summary["validated_rows"] == 2 and summary["rejected_rows"] == 0
    assert summary["identity_output_rows"] == 2
    assert summary["insert_committed_rows"] == 2
    assert summary["lineage_rows_for_batch"] == 2
    assert summary["reconciliation_outcome"] == "matched"

@pytest.mark.parametrize("engine,marker", [
    ("postgresql", "%s"), ("mysql", "%s"), ("mssql", "?"), ("oracle", ":1"),
])
def test_reconciliation_select_spec_supports_all_target_engines(tmp_path, engine, marker):
    root, state = setup_validated_batch(tmp_path, target_engine=engine)
    run = approved_run(root, state)
    execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user":"u","password":"p"}, target_connection_factory=lambda *_: FakeTargetConnection())
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    spec = build_reconciliation_spec(root, recon["id"])
    assert spec["statement_class"] == "SELECT_ONLY" and marker in spec["sql_shape"]
    assert "WHERE" in spec["sql_shape"].upper() and "INSERT" not in spec["sql_shape"].upper()


class FakeReadCursor:
    def __init__(self):
        self.description = [("birth_date",), ("patient_code",)]
        self.calls = []
        self._rows = [(date(2000, 1, 2), "BN001"), (None, "BN002")]
        self._returned = False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchmany(self, size):
        if self._returned:
            return []
        self._returned = True
        return self._rows

    def close(self):
        pass


class FakeReadConnection:
    def __init__(self):
        self.cursor_obj = FakeReadCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_production_dbapi_reconciliation_path_is_select_only(tmp_path):
    root, _, run = committed_run(tmp_path)
    recon = create_reconciliation_run(root, insert_run_id=run["id"], created_by="operator")["reconciliation"]
    fake = FakeReadConnection()
    result = run_reconciliation(
        root, recon["id"], secret_resolver=lambda _: {"user":"u","password":"p"},
        target_connection_factory=lambda *_: fake,
    )["reconciliation"]
    assert result["outcome"] == "matched" and fake.closed is True
    assert fake.cursor_obj.calls and all(sql.upper().startswith("SELECT ") for sql, _ in fake.cursor_obj.calls)
    assert all("INSERT" not in sql.upper() and "UPDATE" not in sql.upper() and "DELETE" not in sql.upper() for sql, _ in fake.cursor_obj.calls)


def test_recovery_scan_is_idempotent(tmp_path):
    root, _, _ = in_doubt_run(tmp_path)
    first = scan_recovery_cases(root)
    second = scan_recovery_cases(root)
    assert first["created_cases"] == 1 and second["created_cases"] == 0
    assert len([c for c in second["cases"] if c["case_type"] == "COMMIT_OUTCOME" and c["status"] == "open"]) == 1
