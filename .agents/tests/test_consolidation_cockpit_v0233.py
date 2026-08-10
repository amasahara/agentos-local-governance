"""
File: .agents/tests/test_consolidation_cockpit_v0233.py

Purpose:
    Verify the v0.23.3 cockpit remains read-only, privacy-safe, correctly scoped,
    and exposes a non-destructive performance baseline contract.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / ".agents"))

from agentos.consolidation_cockpit import consolidation_status
from agentos.performance_baseline import run_performance_baseline


def _db(root: Path) -> sqlite3.Connection:
    state = root / ".agents" / "state"
    state.mkdir(parents=True)
    conn = sqlite3.connect(state / "agentos.db")
    conn.executescript(
        """
        CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY);
        INSERT INTO schema_migrations VALUES(46);

        CREATE TABLE project_candidate_sets(id INTEGER PRIMARY KEY, status TEXT);
        CREATE TABLE project_candidates(id INTEGER PRIMARY KEY, candidate_set_id INTEGER);
        CREATE TABLE project_compatibility(
            id INTEGER PRIMARY KEY, candidate_set_id INTEGER,
            compatibility_status TEXT, human_confirmed INTEGER
        );
        CREATE TABLE primary_project_selections(
            id INTEGER PRIMARY KEY, candidate_set_id INTEGER, status TEXT
        );
        CREATE TABLE project_consolidations(id INTEGER PRIMARY KEY, candidate_set_id INTEGER, status TEXT);
        CREATE TABLE project_consolidation_sources(id INTEGER PRIMARY KEY, consolidation_id INTEGER);
        CREATE TABLE project_component_mappings(id INTEGER PRIMARY KEY, consolidation_id INTEGER, status TEXT);
        CREATE TABLE project_consolidation_reviews(id INTEGER PRIMARY KEY, consolidation_id INTEGER, status TEXT);
        CREATE TABLE project_consolidation_approvals(id INTEGER PRIMARY KEY, consolidation_id INTEGER, status TEXT);
        CREATE TABLE project_component_provenance(id INTEGER PRIMARY KEY, consolidation_id INTEGER);

        CREATE TABLE db_consolidations(id INTEGER PRIMARY KEY, status TEXT);
        CREATE TABLE db_consolidation_sources(
            id INTEGER PRIMARY KEY, consolidation_id INTEGER,
            readonly_verified_at_registration INTEGER
        );
        CREATE TABLE db_connections(id INTEGER PRIMARY KEY, role TEXT, status TEXT);
        CREATE TABLE db_schema_snapshots(id INTEGER PRIMARY KEY, status TEXT);
        CREATE TABLE target_schema_contracts(
            id INTEGER PRIMARY KEY, consolidation_id INTEGER,
            target_snapshot_id INTEGER, status TEXT
        );
        CREATE TABLE db_field_mappings(
            id INTEGER PRIMARY KEY, consolidation_id INTEGER,
            source_snapshot_id INTEGER, status TEXT
        );
        CREATE TABLE db_extraction_batches(id INTEGER PRIMARY KEY, consolidation_id INTEGER, status TEXT);
        CREATE TABLE db_validation_findings(id INTEGER PRIMARY KEY, batch_id INTEGER);
        CREATE TABLE identity_resolution_policies(id INTEGER PRIMARY KEY, consolidation_id INTEGER, status TEXT);
        CREATE TABLE identity_resolution_runs(id INTEGER PRIMARY KEY, extraction_batch_id INTEGER, status TEXT);
        CREATE TABLE identity_candidates(id INTEGER PRIMARY KEY, resolution_run_id INTEGER, status TEXT);
        CREATE TABLE db_target_insert_runs(id INTEGER PRIMARY KEY, consolidation_id INTEGER, status TEXT);
        CREATE TABLE db_reconciliation_runs(id INTEGER PRIMARY KEY, insert_run_id INTEGER, status TEXT);
        CREATE TABLE db_recovery_cases(id INTEGER PRIMARY KEY, insert_run_id INTEGER, status TEXT);
        """
    )
    conn.executescript(
        """
        INSERT INTO project_candidate_sets VALUES(3,'active');
        INSERT INTO project_candidates VALUES(1,3);
        INSERT INTO project_candidates VALUES(2,3);
        INSERT INTO project_compatibility VALUES(1,3,'conditionally_compatible',0);
        INSERT INTO primary_project_selections VALUES(1,3,'selected');
        INSERT INTO project_consolidations VALUES(4,3,'approved');
        INSERT INTO project_consolidation_sources VALUES(1,4);
        INSERT INTO project_component_mappings VALUES(1,4,'planned');
        INSERT INTO project_consolidation_reviews VALUES(1,4,'reviewed');
        INSERT INTO project_consolidation_approvals VALUES(1,4,'active');

        INSERT INTO db_consolidations VALUES(7,'active');
        INSERT INTO db_consolidations VALUES(8,'active');
        INSERT INTO db_consolidation_sources VALUES(1,7,1);
        INSERT INTO db_connections VALUES(1,'TARGET','active');
        INSERT INTO target_schema_contracts VALUES(1,7,10,'approved');
        INSERT INTO db_field_mappings VALUES(1,7,11,'proposed');
        INSERT INTO db_extraction_batches VALUES(1,7,'completed');
        INSERT INTO db_extraction_batches VALUES(2,8,'completed');
        INSERT INTO db_validation_findings VALUES(1,1);
        INSERT INTO identity_resolution_policies VALUES(1,7,'approved');
        INSERT INTO identity_resolution_runs VALUES(1,1,'resolved');
        INSERT INTO identity_resolution_runs VALUES(2,2,'resolved');
        INSERT INTO identity_candidates VALUES(1,1,'awaiting_human');
        INSERT INTO identity_candidates VALUES(2,2,'pending');
        INSERT INTO db_target_insert_runs VALUES(1,7,'in_doubt');
        INSERT INTO db_target_insert_runs VALUES(2,8,'committed');
        INSERT INTO db_reconciliation_runs VALUES(1,1,'matched');
        INSERT INTO db_reconciliation_runs VALUES(2,2,'matched');
        INSERT INTO db_recovery_cases VALUES(1,1,'manual_intervention');
        INSERT INTO db_recovery_cases VALUES(2,2,'resolved');
        """
    )
    conn.commit()
    return conn


def test_cockpit_aggregates_complete_pipeline_and_is_read_only(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    db_path = tmp_path / ".agents/state/agentos.db"
    before_mtime = db_path.stat().st_mtime_ns
    before_changes = conn.total_changes

    result = consolidation_status(
        tmp_path,
        7,
        candidate_set_id=3,
        project_consolidation_id=4,
    )

    after_mtime = db_path.stat().st_mtime_ns
    after_changes = conn.total_changes
    conn.close()

    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["schema_observed"] == 46
    assert result["scope"] == {
        "candidate_set_id": 3,
        "project_consolidation_id": 4,
        "db_consolidation_id": 7,
    }
    assert result["stages"]["project"]["candidate_set"]["candidate_count"] == 2
    assert result["stages"]["database"]["identity"]["runs"] == {"resolved": 1}
    assert result["stages"]["database"]["identity"]["candidates"] == {"awaiting_human": 1}
    assert result["stages"]["database"]["reconciliation"]["runs"] == {"matched": 1}
    assert result["stages"]["database"]["reconciliation"]["recovery_cases"] == {"manual_intervention": 1}
    assert "project_compatibility_requires_human_confirmation" in result["blockers"]
    assert "field_mappings_require_attention" in result["blockers"]
    assert "identity_candidates_require_human_decision" in result["blockers"]
    assert "target_commit_requires_reconciliation" in result["blockers"]
    assert "recovery_manual_intervention_required" in result["blockers"]
    assert before_mtime == after_mtime
    assert before_changes == after_changes
    assert result["privacy"]["raw_record_values_returned"] is False
    assert result["privacy"]["identity_tokens_returned"] is False


def test_cockpit_handles_uninitialized_database(tmp_path: Path) -> None:
    result = consolidation_status(tmp_path)
    assert result["ok"] is True
    assert result["database_present"] is False
    assert result["overall_state"] == "not_initialized"


def test_performance_baseline_does_not_write_governed_database(tmp_path: Path) -> None:
    package = tmp_path / ".agents/agentos"
    tests = tmp_path / ".agents/tests"
    package.mkdir(parents=True)
    tests.mkdir(parents=True)
    (package / "sample.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    (tests / "test_sample.py").write_text("def test_f():\n    assert True\n", encoding="utf-8")
    result = run_performance_baseline(tmp_path, repeats=1)
    assert result["version"] == "0.23.3"
    assert result["regression_contract"]["project_state_mutation_allowed"] is False
    assert result["repository"]["python_file_count"] == 2
    assert result["symbol_index_current_design"]["mode"] == "full_rebuild"
    assert not (tmp_path / ".agents/state/agentos.db").exists()
