"""
File: .agents/tests/test_schema_bootstrap_v0250.py

Purpose:
    Protect v0.25.0 Schema Bootstrap Baseline, schema equivalence, fresh identity
    semantics, and existing-database incremental compatibility.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from agentos import db
from agentos.schema_bootstrap import (
    BASELINE_SCHEMA_VERSION,
    bootstrap_artifact_status,
    schema_fingerprint,
)

ROOT = Path(__file__).resolve().parents[2]


def _memory() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _replay_to(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(
        "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)"
    )
    migrations = db._all_migrations()
    for number, migration in enumerate(migrations[:version], start=1):
        migration(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version) VALUES(?)",
            (number,),
        )
    connection.commit()


def _copy_identity_config(source_root: Path, target_root: Path) -> None:
    config = target_root / ".agents/config"
    config.mkdir(parents=True, exist_ok=True)
    for name in ("project.id", "project.purpose.json"):
        src = source_root / ".agents/config" / name
        if src.is_file():
            shutil.copy2(src, config / name)


def _file_connection(root: Path) -> sqlite3.Connection:
    state = root / ".agents/state"
    state.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(state / "agentos.db")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def test_bootstrap_artifact_is_self_consistent() -> None:
    status = bootstrap_artifact_status()
    assert status["ok"] is True
    assert status["baseline_schema"] == 46
    assert status["historical_migrations_invoked"] == 0


def test_migrate_public_api_remains_none() -> None:
    connection = _memory()
    try:
        assert db.migrate(connection) is None
    finally:
        connection.close()


def test_fresh_migrate_does_not_invoke_migrations_1_to_46(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrations = db._all_migrations()

    def forbidden(_connection: sqlite3.Connection) -> None:
        raise AssertionError(
            "historical migration 1..46 executed on fresh bootstrap path"
        )

    guarded = (
        [forbidden] * BASELINE_SCHEMA_VERSION
        + migrations[BASELINE_SCHEMA_VERSION:]
    )
    monkeypatch.setattr(db, "_all_migrations", lambda: guarded)

    connection = _memory()
    try:
        report = db.migrate_with_report(connection)
        versions = [
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    finally:
        connection.close()

    assert report["mode"] == "bootstrap"
    assert report["bootstrap_version"] == 46
    assert report["applied_migrations"] == [47, 48, 49, 50]
    assert report["bootstrap"]["historical_migrations_invoked"] == 0
    assert versions == list(range(1, 51))


def test_bootstrap_plus_47_49_matches_full_replay_schema() -> None:
    bootstrapped = _memory()
    replayed = _memory()
    try:
        report = db.migrate_with_report(bootstrapped)
        _replay_to(replayed, db.SCHEMA_VERSION)
        assert report["mode"] == "bootstrap"
        assert schema_fingerprint(bootstrapped) == schema_fingerprint(replayed)
        assert bootstrapped.execute("PRAGMA foreign_key_check").fetchall() == []
        assert replayed.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        bootstrapped.close()
        replayed.close()


def test_file_backed_bootstrap_preserves_project_identity_semantics(
    tmp_path: Path,
) -> None:
    legacy_root = tmp_path / "legacy"
    bootstrap_root = tmp_path / "bootstrap"
    _copy_identity_config(ROOT, legacy_root)
    _copy_identity_config(ROOT, bootstrap_root)

    legacy = _file_connection(legacy_root)
    bootstrapped = _file_connection(bootstrap_root)
    try:
        _replay_to(legacy, db.SCHEMA_VERSION)
        report = db.migrate_with_report(bootstrapped)

        legacy_identity = legacy.execute(
            """
            SELECT project_uuid,origin_project_uuid,audit_project_id,
                   identity_version,identity_hash,created_by
            FROM project_identity WHERE singleton=1
            """
        ).fetchone()
        bootstrap_identity = bootstrapped.execute(
            """
            SELECT project_uuid,origin_project_uuid,audit_project_id,
                   identity_version,identity_hash,created_by
            FROM project_identity WHERE singleton=1
            """
        ).fetchone()

        assert report["mode"] == "bootstrap"
        assert report["bootstrap"]["historical_migrations_invoked"] == 0
        assert legacy_identity is not None
        assert bootstrap_identity is not None
        assert tuple(bootstrap_identity) == tuple(legacy_identity)

        legacy_purpose = legacy.execute(
            "SELECT project_uuid,purpose_hash FROM project_purpose WHERE singleton=1"
        ).fetchone()
        bootstrap_purpose = bootstrapped.execute(
            "SELECT project_uuid,purpose_hash FROM project_purpose WHERE singleton=1"
        ).fetchone()
        assert (
            tuple(bootstrap_purpose) if bootstrap_purpose is not None else None
        ) == (
            tuple(legacy_purpose) if legacy_purpose is not None else None
        )
        assert bootstrapped.execute(
            "SELECT COUNT(*) FROM project_purpose_history"
        ).fetchone()[0] == legacy.execute(
            "SELECT COUNT(*) FROM project_purpose_history"
        ).fetchone()[0]
    finally:
        legacy.close()
        bootstrapped.close()


def test_existing_schema_45_remains_incremental() -> None:
    connection = _memory()
    try:
        _replay_to(connection, 45)
        report = db.migrate_with_report(connection)
        assert report["mode"] == "incremental"
        assert report["starting_version"] == 45
        assert report["bootstrap_version"] is None
        assert report["applied_migrations"] == [46, 47, 48, 49, 50]
    finally:
        connection.close()


def test_existing_schema_46_applies_only_post_baseline_migrations() -> None:
    connection = _memory()
    try:
        _replay_to(connection, 46)
        report = db.migrate_with_report(connection)
        assert report["mode"] == "incremental"
        assert report["starting_version"] == 46
        assert report["applied_migrations"] == [47, 48, 49, 50]
    finally:
        connection.close()


def test_unversioned_nonempty_database_fails_closed() -> None:
    connection = _memory()
    try:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)"
        )
        connection.execute("CREATE TABLE unknown_legacy_state(id INTEGER)")
        with pytest.raises(
            RuntimeError,
            match="unversioned_nonempty_state_database",
        ):
            db.migrate_with_report(connection)
        assert connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE name='unknown_legacy_state'
            """
        ).fetchone() is not None
    finally:
        connection.close()
def test_verified_legacy_module_local_state_is_reconciled_and_rows_survive() -> None:
    from agentos.project_selection import migration_33
    from agentos.project_consolidation import migration_34

    connection = _memory()
    try:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)"
        )
        migration_33(connection)
        migration_34(connection)
        connection.execute(
            """
            INSERT INTO project_candidate_sets(
                coordinator_project_uuid,status,created_by,created_at,updated_at
            ) VALUES('legacy-project','draft','legacy','2026-01-01','2026-01-01')
            """
        )
        legacy_id = int(connection.execute(
            "SELECT id FROM project_candidate_sets"
        ).fetchone()[0])

        report = db.migrate_with_report(connection)

        assert report["mode"] == "legacy_reconcile"
        assert report["legacy_reconcile"]["recognized"] is True
        assert report["applied_migrations"] == list(range(1, 51))
        assert connection.execute(
            "SELECT coordinator_project_uuid FROM project_candidate_sets WHERE id=?",
            (legacy_id,),
        ).fetchone()[0] == "legacy-project"
        assert [
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ] == list(range(1, 51))
    finally:
        connection.close()


def test_legacy_reconcile_rejects_unknown_schema_even_with_known_signature() -> None:
    from agentos.project_selection import migration_33

    connection = _memory()
    try:
        connection.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY)"
        )
        migration_33(connection)
        connection.execute("CREATE TABLE unexpected_vendor_state(id INTEGER)")
        with pytest.raises(
            RuntimeError,
            match="unversioned_nonempty_state_database",
        ):
            db.migrate_with_report(connection)
    finally:
        connection.close()


def test_project_selection_and_consolidation_use_central_connect(tmp_path: Path) -> None:
    from agentos import project_selection, project_consolidation

    root = tmp_path / "central-connect"
    with project_selection._connect(root) as connection:
        assert connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0] == db.SCHEMA_VERSION

    with project_consolidation._connect(root) as connection:
        assert connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0] == db.SCHEMA_VERSION
