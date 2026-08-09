"""
File: .agents/agentos/controlled_target_insert.py

Purpose:
    Implement AgentOS v0.22.0 controlled INSERT-only writes from validated
    v0.21.2 local staging artifacts into the single configured TARGET database.

Responsibilities:
    - Build immutable target-insert plans from validated extraction batches.
    - Bind every plan to staging, extraction, mapping, contract, and target hashes.
    - Require explicit human review and approval before any external write.
    - Generate INSERT-only prepared statements for MySQL, SQL Server, PostgreSQL, and Oracle.
    - Revalidate staging integrity and all upstream contracts immediately before write.
    - Execute one external TARGET transaction and roll back on pre-commit failure.
    - Mark commit-time uncertainty as in_doubt and forbid automatic retry.
    - Record privacy-safe batch receipts without persisting row values or credentials.
    - Keep SOURCE write operations and arbitrary/raw SQL permanently forbidden.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Iterable, Iterator
import uuid
from contextlib import contextmanager

from .db import connect as central_connect
from .governance_enforcement import governed_mutation, mirror_domain_event


from .database_boundary import DatabaseBoundaryError, authorize_operation
from .read_only_extraction import (
    ReadOnlyExtractionError,
    _resolve_env_secret,
    migration_37,
    verify_staging_artifact,
)

MIGRATION_VERSION = 38
INSERT_PLAN_VERSION = 1
RUN_STATUSES = {
    "draft", "reviewed", "approved", "running", "committing", "committed",
    "failed", "in_doubt", "stale", "cancelled",
}
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#@.-]{0,127}$")
MAX_INSERT_CHUNK_SIZE = 5000
DEFAULT_INSERT_CHUNK_SIZE = 500
SUPPORTED_ENGINES = {"mysql", "mssql", "postgresql", "oracle"}


class ControlledTargetInsertError(RuntimeError):
    """Raised when a v0.22.0 controlled-target-insert invariant is violated."""


def utc_now() -> str:
    """Return current UTC time as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for hashes and privacy-safe evidence."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _sha256_json(value: Any) -> str:
    """Return SHA-256 of canonical JSON."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return SHA-256 of a local file without loading it fully in memory."""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_default(value: Any) -> Any:
    """Convert common database-compatible Python values to deterministic JSON."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"$binary_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _db_path(root: Path | str) -> Path:
    """Return active AgentOS local state database path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


@contextmanager
def _connect(root: Path | str):
    """Open the shared AgentOS governance database connection."""
    with central_connect(Path(root)) as conn:
        yield conn


def migration_38(conn: sqlite3.Connection) -> None:
    """Apply additive schema 38 for controlled TARGET INSERT plans and receipts."""
    migration_37(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS db_target_insert_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_uuid TEXT NOT NULL UNIQUE,
            extraction_batch_id INTEGER NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            target_connection_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            insert_plan_version INTEGER NOT NULL,
            insert_plan_json TEXT NOT NULL,
            insert_plan_hash TEXT NOT NULL,
            staging_path TEXT NOT NULL,
            staging_hash TEXT NOT NULL,
            staging_manifest_hash TEXT NOT NULL,
            extraction_plan_hash TEXT NOT NULL,
            mapping_set_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            target_snapshot_hash TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            column_order_json TEXT NOT NULL,
            chunk_size INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            started_at TEXT,
            committing_at TEXT,
            committed_at TEXT,
            failed_at TEXT,
            failure_stage TEXT,
            failure_reason TEXT,
            attempted_rows INTEGER NOT NULL DEFAULT 0,
            committed_rows INTEGER NOT NULL DEFAULT 0,
            commit_receipt_hash TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(extraction_batch_id) REFERENCES db_extraction_batches(id),
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(target_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id)
        );
        CREATE TABLE IF NOT EXISTS db_target_insert_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_run_id INTEGER,
            extraction_batch_id INTEGER,
            consolidation_id INTEGER,
            target_connection_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id)
        );
        CREATE INDEX IF NOT EXISTS idx_db_target_insert_runs_status
            ON db_target_insert_runs(consolidation_id,target_connection_id,status);
        CREATE INDEX IF NOT EXISTS idx_db_target_insert_events_run
            ON db_target_insert_events(insert_run_id,created_at);
        """
    )


def sync_controlled_target_insert_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema 38 and report required v0.22.0 tables."""
    required = {"db_target_insert_runs", "db_target_insert_events"}
    with _connect(root) as conn:
        migration_38(conn)
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"ok": required <= tables, "schema": MIGRATION_VERSION, "tables": sorted(required)}


def _assert_privacy_safe_event(payload: Any) -> None:
    """Reject event structures that could persist record values or credentials."""
    forbidden = {
        "row", "rows", "record", "records", "value", "values", "raw_value",
        "password", "credential", "credential_ref", "dsn", "connection_string",
    }

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in forbidden:
                    raise ControlledTargetInsertError(f"record/secret-bearing event key is forbidden: {key}")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)


def _event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    payload: Any,
    insert_run_id: int | None = None,
    extraction_batch_id: int | None = None,
    consolidation_id: int | None = None,
    target_connection_id: int | None = None,
) -> None:
    """Append privacy-safe controlled-write evidence to local AgentOS state."""
    _assert_privacy_safe_event(payload)
    mirror = mirror_domain_event(event_type, payload)
    conn.execute(
        """INSERT INTO db_target_insert_events(
            insert_run_id,extraction_batch_id,consolidation_id,target_connection_id,event_type,event_json,created_at,governed_operation_id,external_event_hash
        ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            insert_run_id, extraction_batch_id, consolidation_id, target_connection_id,
            event_type, _canonical_json(payload), utc_now(), mirror["governed_operation_id"], mirror["external_event_hash"],
        ),
    )


def _require_identifier(value: str, label: str) -> str:
    """Validate one SQL catalog identifier before quoting it."""
    text = str(value).strip()
    if not SAFE_IDENTIFIER.fullmatch(text):
        raise ControlledTargetInsertError(f"invalid {label}: {value!r}")
    return text


def _quote_identifier(engine: str, identifier: str) -> str:
    """Quote a previously validated identifier for one supported engine."""
    value = _require_identifier(identifier, "identifier")
    if engine == "mssql":
        return "[" + value.replace("]", "]]" ) + "]"
    if engine == "mysql":
        return "`" + value.replace("`", "``") + "`"
    if engine in {"postgresql", "oracle"}:
        return '"' + value.replace('"', '""') + '"'
    raise ControlledTargetInsertError(f"unsupported engine: {engine}")


def _contract_table(contract: dict[str, Any], schema: str, table: str) -> dict[str, Any]:
    """Return one target table contract by case-insensitive schema/name."""
    for item in contract.get("tables", []):
        if str(item.get("schema", "")).lower() == schema.lower() and str(item.get("name", "")).lower() == table.lower():
            return item
    raise ControlledTargetInsertError(f"target table is absent from approved contract: {schema}.{table}")


def _column_index(table_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index target contract columns by lowercase name."""
    return {str(c["name"]).lower(): c for c in table_contract.get("columns", [])}


def _load_staging_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield validated staging records from local JSONL without buffering the file."""
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ControlledTargetInsertError(f"staging JSONL is invalid at line {line_no}") from exc
            if not isinstance(row, dict) or not isinstance(row.get("target"), dict) or not isinstance(row.get("values"), dict):
                raise ControlledTargetInsertError(f"staging record shape is invalid at line {line_no}")
            yield row


def _build_plan_from_batch(conn: sqlite3.Connection, batch: sqlite3.Row, chunk_size: int) -> tuple[dict[str, Any], sqlite3.Row, sqlite3.Row, sqlite3.Row]:
    """Build immutable INSERT plan metadata after all upstream checks succeed."""
    if batch["status"] != "validated":
        raise ControlledTargetInsertError("only fully validated extraction batches with zero rejections are eligible for v0.22.0 INSERT")
    if int(batch["valid_rows"]) <= 0:
        raise ControlledTargetInsertError("validated batch contains no rows to insert")
    consolidation = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(batch["consolidation_id"]),)).fetchone()
    if consolidation is None:
        raise ControlledTargetInsertError("database consolidation not found")
    target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(consolidation["target_connection_id"]),)).fetchone()
    if target is None or target["role"] != "TARGET" or target["status"] != "active":
        raise ControlledTargetInsertError("active TARGET connection required")
    if str(target["engine"]) not in SUPPORTED_ENGINES:
        raise ControlledTargetInsertError("unsupported TARGET engine")
    contract = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(batch["target_contract_id"]),)).fetchone()
    if contract is None or contract["status"] != "approved":
        raise ControlledTargetInsertError("approved TARGET schema contract required")
    if int(contract["target_connection_id"]) != int(target["id"]):
        raise ControlledTargetInsertError("TARGET contract does not belong to consolidation TARGET")
    target_snapshot = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(contract["target_snapshot_id"]),)).fetchone()
    if target_snapshot is None or target_snapshot["status"] != "active":
        raise ControlledTargetInsertError("active TARGET schema snapshot required")
    if str(target_snapshot["snapshot_hash"]) != str(contract["target_snapshot_hash"]):
        raise ControlledTargetInsertError("TARGET schema snapshot drifted from approved contract")
    if str(contract["contract_hash"]) != str(batch["target_contract_hash"]):
        raise ControlledTargetInsertError("extraction batch TARGET contract hash is stale")

    extraction_plan = json.loads(batch["extraction_plan_json"])
    if _sha256_json(extraction_plan) != str(batch["extraction_plan_hash"]):
        raise ControlledTargetInsertError("extraction plan hash mismatch")
    mappings = conn.execute(
        """SELECT m.*,bm.mapping_hash AS pinned_mapping_hash FROM db_extraction_batch_mappings bm
           JOIN db_field_mappings m ON m.id=bm.mapping_id WHERE bm.batch_id=? ORDER BY m.id""",
        (int(batch["id"]),),
    ).fetchall()
    mapping_set = []
    for mapping in mappings:
        if mapping["status"] != "confirmed" or str(mapping["mapping_hash"]) != str(mapping["pinned_mapping_hash"]):
            raise ControlledTargetInsertError(f"mapping {mapping['id']} is no longer confirmed/current")
        if str(mapping["source_snapshot_hash"]) != str(batch["source_snapshot_hash"]):
            raise ControlledTargetInsertError(f"mapping {mapping['id']} SOURCE snapshot hash drifted")
        if str(mapping["target_contract_hash"]) != str(batch["target_contract_hash"]):
            raise ControlledTargetInsertError(f"mapping {mapping['id']} TARGET contract hash drifted")
        mapping_set.append({"id": int(mapping["id"]), "hash": str(mapping["mapping_hash"])})
    if _sha256_json(mapping_set) != str(batch["mapping_set_hash"]):
        raise ControlledTargetInsertError("mapping-set hash mismatch")

    contract_json = json.loads(contract["contract_json"])
    table_contract = _contract_table(contract_json, str(batch["target_schema"]), str(batch["target_table"]))
    target_columns = {str(m["target_column"]): str(m["target_canonical_type"]) for m in mappings}
    if not target_columns:
        raise ControlledTargetInsertError("no target columns are available for INSERT")
    contract_columns = _column_index(table_contract)
    for column, canonical_type in target_columns.items():
        meta = contract_columns.get(column.lower())
        if meta is None:
            raise ControlledTargetInsertError(f"mapped target column is absent from approved contract: {column}")
        if str(meta["canonical_type"]) != canonical_type:
            raise ControlledTargetInsertError(f"mapped target column type drifted: {column}")

    column_order = sorted(target_columns, key=str.lower)
    plan = {
        "insert_plan_version": INSERT_PLAN_VERSION,
        "extraction_batch_id": int(batch["id"]),
        "extraction_batch_uuid": str(batch["batch_uuid"]),
        "consolidation_id": int(batch["consolidation_id"]),
        "target_connection_id": int(target["id"]),
        "target_engine": str(target["engine"]),
        "target_contract_id": int(contract["id"]),
        "target_contract_hash": str(contract["contract_hash"]),
        "target_snapshot_hash": str(target_snapshot["snapshot_hash"]),
        "target_schema": str(batch["target_schema"]),
        "target_table": str(batch["target_table"]),
        "column_order": column_order,
        "column_types": {k: target_columns[k] for k in column_order},
        "row_count": int(batch["valid_rows"]),
        "staging_path": str(batch["staging_path"]),
        "staging_hash": str(batch["staging_hash"]),
        "staging_manifest_hash": str(batch["manifest_hash"]),
        "extraction_plan_hash": str(batch["extraction_plan_hash"]),
        "mapping_set_hash": str(batch["mapping_set_hash"]),
        "write_mode": "INSERT_ONLY",
        "upsert": False,
        "update": False,
        "delete": False,
        "ddl": False,
        "raw_sql": False,
        "chunk_size": int(chunk_size),
    }
    return plan, target, contract, target_snapshot


@governed_mutation("db.target_insert.plan.create")
def create_target_insert_plan(
    root: Path | str,
    *,
    extraction_batch_id: int,
    created_by: str,
    chunk_size: int = DEFAULT_INSERT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Create one immutable draft INSERT plan from a fully validated staging batch.

    Args:
        root: Active AgentOS project root.
        extraction_batch_id: v0.21.2 extraction batch with status ``validated``.
        created_by: Human/operator identity creating the plan.
        chunk_size: Prepared-executemany chunk size, 1..5000.

    Returns:
        Privacy-safe insert-plan metadata. No staged row values are returned.

    Raises:
        ControlledTargetInsertError: If any staging, mapping, contract, target, or hash invariant fails.
    """
    if not str(created_by).strip():
        raise ControlledTargetInsertError("created_by is required")
    chunk_size = int(chunk_size)
    if chunk_size < 1 or chunk_size > MAX_INSERT_CHUNK_SIZE:
        raise ControlledTargetInsertError(f"chunk_size must be between 1 and {MAX_INSERT_CHUNK_SIZE}")
    integrity = verify_staging_artifact(root, int(extraction_batch_id))
    if not integrity.get("ok"):
        raise ControlledTargetInsertError("staging integrity verification failed")
    try:
        from .identity_resolution import get_identity_insert_artifact
        identity_artifact = get_identity_insert_artifact(root, int(extraction_batch_id))
    except Exception as exc:
        raise ControlledTargetInsertError(f"v0.22.1 identity resolution is required before TARGET INSERT: {exc}") from exc
    if int(identity_artifact["row_count"]) <= 0:
        raise ControlledTargetInsertError("identity resolution produced no new canonical rows to insert")
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_38(conn)
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(extraction_batch_id),)).fetchone()
        if batch is None:
            raise ControlledTargetInsertError("extraction batch not found")
        if conn.execute("SELECT 1 FROM db_target_insert_runs WHERE extraction_batch_id=?", (int(extraction_batch_id),)).fetchone():
            raise ControlledTargetInsertError("an insert plan already exists for this extraction batch")
        plan, target, contract, target_snapshot = _build_plan_from_batch(conn, batch, chunk_size)
        plan["source_validated_staging_path"] = str(batch["staging_path"])
        plan["source_validated_staging_hash"] = str(batch["staging_hash"])
        plan["identity_resolution_run_id"] = int(identity_artifact["resolution_run_id"])
        plan["identity_policy_id"] = int(identity_artifact["policy_id"])
        plan["identity_manifest_hash"] = str(identity_artifact["identity_manifest_hash"])
        plan["identity_duplicate_rows"] = int(identity_artifact["duplicate_rows"])
        plan["staging_path"] = str(identity_artifact["staging_path"])
        plan["staging_hash"] = str(identity_artifact["staging_hash"])
        plan["row_count"] = int(identity_artifact["row_count"])
        staging_path = (root_path / str(identity_artifact["staging_path"])).resolve()
        runtime_root = (root_path / ".agents/runtime/data-staging").resolve()
        try:
            staging_path.relative_to(runtime_root)
        except ValueError as exc:
            raise ControlledTargetInsertError("staging path escaped the local data-staging runtime") from exc
        if not staging_path.is_file() or _sha256_file(staging_path) != str(identity_artifact["staging_hash"]):
            raise ControlledTargetInsertError("deduplicated identity staging file changed after resolution")

        # Validate every staged record shape without persisting any row value.
        expected = {str(x) for x in plan["column_order"]}
        count = 0
        for record in _load_staging_records(staging_path):
            count += 1
            target_meta = record["target"]
            if str(target_meta.get("schema")) != str(batch["target_schema"]) or str(target_meta.get("table")) != str(batch["target_table"]):
                raise ControlledTargetInsertError(f"staging target mismatch at row {count}")
            keys = {str(k) for k in record["values"].keys()}
            if keys != expected:
                raise ControlledTargetInsertError(f"staging column set mismatch at row {count}")
            provenance = record.get("provenance") or {}
            if str(provenance.get("mapping_set_hash")) != str(batch["mapping_set_hash"]):
                raise ControlledTargetInsertError(f"staging mapping-set provenance mismatch at row {count}")
            if str(provenance.get("target_contract_hash")) != str(batch["target_contract_hash"]):
                raise ControlledTargetInsertError(f"staging target-contract provenance mismatch at row {count}")
        if count != int(identity_artifact["row_count"]):
            raise ControlledTargetInsertError("deduplicated staging row count does not match identity resolution")

        plan_hash = _sha256_json(plan)
        now = utc_now()
        cur = conn.execute(
            """INSERT INTO db_target_insert_runs(
                insert_uuid,extraction_batch_id,consolidation_id,target_connection_id,target_contract_id,
                target_schema,target_table,insert_plan_version,insert_plan_json,insert_plan_hash,
                staging_path,staging_hash,staging_manifest_hash,extraction_plan_hash,mapping_set_hash,
                target_contract_hash,target_snapshot_hash,row_count,column_order_json,chunk_size,status,
                created_by,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), int(batch["id"]), int(batch["consolidation_id"]), int(target["id"]), int(contract["id"]),
                str(batch["target_schema"]), str(batch["target_table"]), INSERT_PLAN_VERSION, _canonical_json(plan), plan_hash,
                str(identity_artifact["staging_path"]), str(identity_artifact["staging_hash"]), str(identity_artifact["identity_manifest_hash"]), str(batch["extraction_plan_hash"]),
                str(batch["mapping_set_hash"]), str(contract["contract_hash"]), str(target_snapshot["snapshot_hash"]), int(identity_artifact["row_count"]),
                _canonical_json(plan["column_order"]), chunk_size, "draft", str(created_by).strip(), now,
            ),
        )
        run_id = int(cur.lastrowid)
        _event(
            conn, event_type="target_insert_plan_created", insert_run_id=run_id, extraction_batch_id=int(batch["id"]),
            consolidation_id=int(batch["consolidation_id"]), target_connection_id=int(target["id"]),
            payload={
                "insert_plan_hash": plan_hash,
                "staging_hash": str(identity_artifact["staging_hash"]),
                "staging_manifest_hash": str(identity_artifact["identity_manifest_hash"]),
                "target_contract_hash": str(contract["contract_hash"]),
                "target_snapshot_hash": str(target_snapshot["snapshot_hash"]),
                "row_count": int(identity_artifact["row_count"]),
                "identity_resolution_run_id": int(identity_artifact["resolution_run_id"]),
                "column_count": len(plan["column_order"]),
                "write_mode": "INSERT_ONLY",
            },
        )
    return get_target_insert_plan(root_path, run_id)


def _safe_run_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert an insert-run row to a response without any business values or secrets."""
    value = dict(row)
    value["insert_plan"] = json.loads(value.pop("insert_plan_json"))
    value["column_order"] = json.loads(value.pop("column_order_json"))
    return value


def get_target_insert_plan(root: Path | str, insert_run_id: int) -> dict[str, Any]:
    """Return one privacy-safe controlled INSERT plan and its immutable hashes."""
    with _connect(root) as conn:
        migration_38(conn)
        row = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if row is None:
            raise ControlledTargetInsertError("target insert plan not found")
    return {"ok": True, "insert_run": _safe_run_dict(row)}


def _revalidate_run(conn: sqlite3.Connection, row: sqlite3.Row, root: Path) -> tuple[bool, str | None]:
    """Revalidate every upstream artifact/hash immediately before review, approval, or write."""
    batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(row["extraction_batch_id"]),)).fetchone()
    if batch is None or batch["status"] != "validated":
        return False, "extraction_batch_not_validated"
    plan = json.loads(row["insert_plan_json"])
    if not plan.get("identity_resolution_run_id"):
        return False, "identity_resolution_missing_after_v0221_upgrade"
    try:
        from .identity_resolution import get_identity_insert_artifact
        identity_artifact = get_identity_insert_artifact(root, int(batch["id"]))
    except Exception:
        return False, "identity_resolution_not_current"
    if str(identity_artifact["staging_hash"]) != str(row["staging_hash"]) or str(identity_artifact["identity_manifest_hash"]) != str(row["staging_manifest_hash"]):
        return False, "identity_staging_binding_drift"
    if int(identity_artifact["row_count"]) != int(row["row_count"]):
        return False, "identity_row_count_drift"
    if str(batch["extraction_plan_hash"]) != str(row["extraction_plan_hash"]):
        return False, "extraction_plan_drift"
    if str(batch["mapping_set_hash"]) != str(row["mapping_set_hash"]):
        return False, "mapping_set_drift"
    contract = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(row["target_contract_id"]),)).fetchone()
    if contract is None or contract["status"] != "approved" or str(contract["contract_hash"]) != str(row["target_contract_hash"]):
        return False, "target_contract_drift"
    target_snapshot = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(contract["target_snapshot_id"]),)).fetchone()
    if target_snapshot is None or target_snapshot["status"] != "active" or str(target_snapshot["snapshot_hash"]) != str(row["target_snapshot_hash"]):
        return False, "target_schema_drift"
    target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(row["target_connection_id"]),)).fetchone()
    if target is None or target["role"] != "TARGET" or target["status"] != "active":
        return False, "target_connection_not_active"
    consolidation = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(row["consolidation_id"]),)).fetchone()
    if consolidation is None or int(consolidation["target_connection_id"]) != int(row["target_connection_id"]):
        return False, "target_changed_in_consolidation"
    if _sha256_json(plan) != str(row["insert_plan_hash"]):
        return False, "insert_plan_hash_mismatch"
    path = (root / str(row["staging_path"])).resolve()
    runtime_root = (root / ".agents/runtime/data-staging").resolve()
    try:
        path.relative_to(runtime_root)
    except ValueError:
        return False, "staging_path_escape"
    if not path.is_file() or _sha256_file(path) != str(row["staging_hash"]):
        return False, "staging_artifact_tampered"
    return True, None


@governed_mutation("db.target_insert.review")
def review_target_insert_plan(root: Path | str, insert_run_id: int, *, reviewed_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Record explicit human review of one immutable draft INSERT plan."""
    if not human_confirmed or not str(reviewed_by).strip():
        raise ControlledTargetInsertError("explicit human confirmation and reviewed_by are required")
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_38(conn)
        row = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if row is None or row["status"] != "draft":
            raise ControlledTargetInsertError("only draft insert plans can be reviewed")
        current, reason = _revalidate_run(conn, row, root_path)
        if not current:
            conn.execute("UPDATE db_target_insert_runs SET status='stale',failure_reason=? WHERE id=?", (reason, int(insert_run_id)))
            raise ControlledTargetInsertError(f"insert plan is stale: {reason}")
        now = utc_now()
        conn.execute("UPDATE db_target_insert_runs SET status='reviewed',reviewed_by=?,reviewed_at=? WHERE id=?", (str(reviewed_by).strip(), now, int(insert_run_id)))
        _event(conn, event_type="target_insert_plan_reviewed", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
               consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
               payload={"reviewed_by": str(reviewed_by).strip(), "insert_plan_hash": str(row["insert_plan_hash"])})
    return get_target_insert_plan(root_path, int(insert_run_id))


@governed_mutation("db.target_insert.approve")
def approve_target_insert_plan(root: Path | str, insert_run_id: int, *, approved_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Approve one reviewed plan, binding approval to its immutable plan/staging hashes."""
    if not human_confirmed or not str(approved_by).strip():
        raise ControlledTargetInsertError("explicit human confirmation and approved_by are required")
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_38(conn)
        row = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if row is None or row["status"] != "reviewed":
            raise ControlledTargetInsertError("insert plan must be reviewed before approval")
        current, reason = _revalidate_run(conn, row, root_path)
        if not current:
            conn.execute("UPDATE db_target_insert_runs SET status='stale',failure_reason=? WHERE id=?", (reason, int(insert_run_id)))
            raise ControlledTargetInsertError(f"insert plan is stale: {reason}")
        now = utc_now()
        conn.execute("UPDATE db_target_insert_runs SET status='approved',approved_by=?,approved_at=? WHERE id=?", (str(approved_by).strip(), now, int(insert_run_id)))
        _event(conn, event_type="target_insert_plan_approved", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
               consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
               payload={
                   "approved_by": str(approved_by).strip(), "insert_plan_hash": str(row["insert_plan_hash"]),
                   "staging_hash": str(row["staging_hash"]), "target_contract_hash": str(row["target_contract_hash"]),
               })
    return get_target_insert_plan(root_path, int(insert_run_id))


def _placeholder_sql(engine: str, count: int) -> list[str]:
    """Return driver placeholders for one row without embedding any value."""
    if engine in {"postgresql", "mysql"}:
        return ["%s"] * count
    if engine == "mssql":
        return ["?"] * count
    if engine == "oracle":
        return [f":{i}" for i in range(1, count + 1)]
    raise ControlledTargetInsertError(f"unsupported engine: {engine}")


def build_insert_spec(root: Path | str, insert_run_id: int) -> dict[str, Any]:
    """Build generated INSERT-only prepared-statement metadata without values."""
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_38(conn)
        row = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if row is None:
            raise ControlledTargetInsertError("target insert plan not found")
        target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(row["target_connection_id"]),)).fetchone()
        engine = str(target["engine"])
        columns = json.loads(row["column_order_json"])
    qschema = _quote_identifier(engine, str(row["target_schema"]))
    qtable = _quote_identifier(engine, str(row["target_table"]))
    qcols = ", ".join(_quote_identifier(engine, str(c)) for c in columns)
    placeholders = ", ".join(_placeholder_sql(engine, len(columns)))
    sql = f"INSERT INTO {qschema}.{qtable} ({qcols}) VALUES ({placeholders})"
    return {
        "ok": True,
        "generated": True,
        "engine": engine,
        "statement_class": "INSERT_ONLY",
        "sql": sql,
        "columns": columns,
        "row_values_included": False,
        "raw_sql": False,
        "upsert": False,
        "update": False,
        "delete": False,
        "ddl": False,
    }


def _open_target_connection(connection: sqlite3.Row, secret: dict[str, Any]):
    """Open a TLS-capable TARGET DB-API connection with autocommit disabled."""
    engine = str(connection["engine"])
    host, port, database = str(connection["host"]), int(connection["port"]), str(connection["database_name"])
    user = secret.get("user") or secret.get("username")
    password = secret.get("password")
    if not user or password is None:
        raise ControlledTargetInsertError("resolved TARGET secret requires user/username and password")
    try:
        if engine == "postgresql":
            try:
                import psycopg  # type: ignore
                return psycopg.connect(host=host, port=port, dbname=database, user=user, password=password, sslmode="require", autocommit=False)
            except ImportError:
                import psycopg2  # type: ignore
                conn = psycopg2.connect(host=host, port=port, dbname=database, user=user, password=password, sslmode="require")
                conn.autocommit = False
                return conn
        if engine == "mysql":
            try:
                import pymysql  # type: ignore
                return pymysql.connect(host=host, port=port, database=database, user=user, password=password, ssl={"check_hostname": True}, autocommit=False)
            except ImportError:
                import mysql.connector  # type: ignore
                return mysql.connector.connect(host=host, port=port, database=database, user=user, password=password, ssl_disabled=False, autocommit=False)
        if engine == "mssql":
            import pyodbc  # type: ignore
            driver = secret.get("odbc_driver", "ODBC Driver 18 for SQL Server")
            conn_str = (
                f"DRIVER={{{driver}}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password};"
                "Encrypt=yes;TrustServerCertificate=no;"
            )
            return pyodbc.connect(conn_str, autocommit=False)
        if engine == "oracle":
            import oracledb  # type: ignore
            dsn = secret.get("dsn") or f"tcps://{host}:{port}/{database}"
            if not str(dsn).lower().startswith("tcps://"):
                raise ControlledTargetInsertError("Oracle TARGET requires a tcps:// DSN")
            return oracledb.connect(user=user, password=password, dsn=dsn)
    except ControlledTargetInsertError:
        raise
    except ImportError as exc:
        raise ControlledTargetInsertError(f"optional database driver is not installed for TARGET engine {engine}: {exc}") from exc
    except Exception as exc:
        raise ControlledTargetInsertError(f"TARGET connection failed for engine {engine}: {type(exc).__name__}") from exc
    raise ControlledTargetInsertError(f"unsupported TARGET engine: {engine}")


def _decode_staging_value(value: Any, canonical_type: str) -> Any:
    """Convert deterministic staging JSON back to driver-friendly scalar values."""
    if value is None:
        return None
    ctype = str(canonical_type)
    if isinstance(value, dict) and set(value) == {"$binary_base64"}:
        try:
            return base64.b64decode(str(value["$binary_base64"]), validate=True)
        except Exception as exc:
            raise ControlledTargetInsertError("invalid staged binary value") from exc
    if ctype == "date" and isinstance(value, str):
        return date.fromisoformat(value)
    if ctype == "datetime" and isinstance(value, str):
        return datetime.fromisoformat(value)
    if ctype in {"decimal", "numeric"} and isinstance(value, str):
        return Decimal(value)
    if ctype == "uuid" and isinstance(value, str):
        return str(uuid.UUID(value))
    if ctype in {"json", "object", "array"} and not isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _iter_target_parameter_rows(path: Path, plan: dict[str, Any]) -> Iterator[tuple[Any, ...]]:
    """Yield prepared-statement tuples from validated staging without exposing values."""
    columns = list(plan["column_order"])
    types = dict(plan["column_types"])
    expected_target = {"schema": plan["target_schema"], "table": plan["target_table"]}
    for ordinal, record in enumerate(_load_staging_records(path), start=1):
        if record.get("target") != expected_target:
            raise ControlledTargetInsertError(f"staging target drift at row {ordinal}")
        values = record["values"]
        if set(values.keys()) != set(columns):
            raise ControlledTargetInsertError(f"staging column drift at row {ordinal}")
        provenance = record.get("provenance") or {}
        if str(provenance.get("mapping_set_hash")) != str(plan["mapping_set_hash"]):
            raise ControlledTargetInsertError(f"staging mapping provenance drift at row {ordinal}")
        if str(provenance.get("target_contract_hash")) != str(plan["target_contract_hash"]):
            raise ControlledTargetInsertError(f"staging target-contract provenance drift at row {ordinal}")
        try:
            yield tuple(_decode_staging_value(values[c], types[c]) for c in columns)
        except Exception as exc:
            if isinstance(exc, ControlledTargetInsertError):
                raise
            raise ControlledTargetInsertError(f"staged value decode failed at row {ordinal}: {type(exc).__name__}") from exc


def _chunks(rows: Iterable[tuple[Any, ...]], size: int) -> Iterator[list[tuple[Any, ...]]]:
    """Yield bounded lists for DB-API executemany."""
    chunk: list[tuple[Any, ...]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


@governed_mutation("db.target_insert.execute")
def execute_target_insert(
    root: Path | str,
    insert_run_id: int,
    *,
    secret_resolver: Callable[[str], dict[str, Any]] | None = None,
    target_connection_factory: Callable[[sqlite3.Row, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Execute exactly one approved INSERT-only transaction against the configured TARGET.

    Args:
        root: Active AgentOS project root.
        insert_run_id: Human-reviewed and human-approved insert run.
        secret_resolver: Optional trusted secret resolver; default accepts env:// JSON only.
        target_connection_factory: Optional trusted DB-API factory for tests/integration adapters.

    Returns:
        Privacy-safe committed receipt with row count and immutable hashes only.

    Raises:
        ControlledTargetInsertError: On stale approval, staging tamper, external write failure, or uncertain commit.

    Side Effects:
        Performs INSERT statements against the configured TARGET database only after all gates pass.
        SOURCE databases are never opened by this function.
    """
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_38(conn)
        row = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if row is None:
            raise ControlledTargetInsertError("target insert plan not found")
        retryable_failed = row["status"] == "failed" and row["failure_stage"] in {"preconnect", "precommit", "reconciled_not_committed"}
        if row["status"] != "approved" and not retryable_failed:
            if row["status"] in {"running", "committing", "in_doubt"}:
                raise ControlledTargetInsertError("insert run has an uncertain/prior execution state; automatic retry is forbidden")
            raise ControlledTargetInsertError("only approved, safely rolled-back precommit, or human-reconciled not-committed plans can execute")
        current, reason = _revalidate_run(conn, row, root_path)
        if not current:
            conn.execute("UPDATE db_target_insert_runs SET status='stale',failure_reason=? WHERE id=?", (reason, int(insert_run_id)))
            raise ControlledTargetInsertError(f"insert plan is stale: {reason}")
        target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(row["target_connection_id"]),)).fetchone()
        # Generic/raw INSERT remains denied. The controlled module is the only write boundary.
        raw_decision = authorize_operation(root_path, int(target["id"]), "insert")
        if raw_decision.get("allowed"):
            raise ControlledTargetInsertError("generic TARGET INSERT unexpectedly became authorized; refusing controlled execution")
        # SOURCE connections in this consolidation must remain read-only verified and write-disabled.
        sources = conn.execute(
            """SELECT c.* FROM db_consolidation_sources s JOIN db_connections c ON c.id=s.source_connection_id
               WHERE s.consolidation_id=?""",
            (int(row["consolidation_id"]),),
        ).fetchall()
        for source in sources:
            if source["role"] != "SOURCE" or not int(source["readonly_verified"]) or int(source["data_write_enabled"]) != 0:
                raise ControlledTargetInsertError("SOURCE read-only invariant failed before TARGET write")
        plan = json.loads(row["insert_plan_json"])
        staging_path = (root_path / str(row["staging_path"])).resolve()
        credential_ref = str(target["credential_ref"])
        conn.execute(
            "UPDATE db_target_insert_runs SET status='running',started_at=?,failure_stage=NULL,failure_reason=NULL,attempted_rows=0 WHERE id=?",
            (utc_now(), int(insert_run_id)),
        )
        _event(conn, event_type="target_insert_started", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
               consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
               payload={"insert_plan_hash": str(row["insert_plan_hash"]), "row_count": int(row["row_count"]), "write_mode": "INSERT_ONLY"})

    resolver = secret_resolver or _resolve_env_secret
    try:
        secret = resolver(credential_ref)
        if not isinstance(secret, dict):
            raise ControlledTargetInsertError("TARGET secret resolver must return an object")
    except Exception as exc:
        with _connect(root_path) as conn:
            migration_38(conn)
            conn.execute("UPDATE db_target_insert_runs SET status='failed',failed_at=?,failure_stage='preconnect',failure_reason=? WHERE id=?",
                         (utc_now(), type(exc).__name__, int(insert_run_id)))
            _event(conn, event_type="target_insert_preconnect_failed", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
                   consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
                   payload={"error_type": type(exc).__name__, "external_write_started": False, "manual_retry_allowed": True})
        if isinstance(exc, ControlledTargetInsertError):
            raise
        raise ControlledTargetInsertError("TARGET credential resolution failed") from exc

    factory = target_connection_factory or _open_target_connection
    target_conn = None
    attempted = 0
    try:
        target_conn = factory(target, secret)
        cursor = target_conn.cursor()
        try:
            spec = build_insert_spec(root_path, int(insert_run_id))
            rows = _iter_target_parameter_rows(staging_path, plan)
            for chunk in _chunks(rows, int(row["chunk_size"])):
                cursor.executemany(spec["sql"], chunk)
                attempted += len(chunk)
                with _connect(root_path) as local:
                    migration_38(local)
                    local.execute("UPDATE db_target_insert_runs SET attempted_rows=? WHERE id=?", (attempted, int(insert_run_id)))
            if attempted != int(row["row_count"]):
                raise ControlledTargetInsertError("staging row count changed during execution")
        finally:
            cursor.close()
    except Exception as exc:
        if target_conn is not None:
            try:
                target_conn.rollback()
            except Exception:
                pass
            try:
                target_conn.close()
            except Exception:
                pass
        with _connect(root_path) as conn:
            migration_38(conn)
            conn.execute(
                "UPDATE db_target_insert_runs SET status='failed',failed_at=?,failure_stage='precommit',failure_reason=?,attempted_rows=? WHERE id=?",
                (utc_now(), type(exc).__name__, attempted, int(insert_run_id)),
            )
            _event(conn, event_type="target_insert_rolled_back", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
                   consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
                   payload={"attempted_rows": attempted, "error_type": type(exc).__name__, "external_transaction_rolled_back": True})
        if isinstance(exc, ControlledTargetInsertError):
            raise
        raise ControlledTargetInsertError(f"TARGET INSERT failed before commit: {type(exc).__name__}") from exc

    # Persist a local committing marker before the external commit. If the process dies after this marker,
    # the run is intentionally ambiguous and cannot be auto-retried.
    with _connect(root_path) as conn:
        migration_38(conn)
        conn.execute("UPDATE db_target_insert_runs SET status='committing',committing_at=?,attempted_rows=? WHERE id=?", (utc_now(), attempted, int(insert_run_id)))
        _event(conn, event_type="target_insert_committing", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
               consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
               payload={"attempted_rows": attempted, "automatic_retry_allowed": False})
    try:
        target_conn.commit()
    except Exception as exc:
        try:
            target_conn.close()
        except Exception:
            pass
        with _connect(root_path) as conn:
            migration_38(conn)
            conn.execute(
                "UPDATE db_target_insert_runs SET status='in_doubt',failed_at=?,failure_stage='commit',failure_reason=?,attempted_rows=? WHERE id=?",
                (utc_now(), type(exc).__name__, attempted, int(insert_run_id)),
            )
            _event(conn, event_type="target_insert_commit_in_doubt", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
                   consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
                   payload={"attempted_rows": attempted, "error_type": type(exc).__name__, "automatic_retry_allowed": False})
        raise ControlledTargetInsertError("TARGET commit outcome is uncertain; run marked in_doubt and automatic retry is forbidden") from exc
    finally:
        try:
            target_conn.close()
        except Exception:
            pass

    receipt = {
        "insert_uuid": str(row["insert_uuid"]),
        "extraction_batch_id": int(row["extraction_batch_id"]),
        "target_connection_id": int(row["target_connection_id"]),
        "target_schema": str(row["target_schema"]),
        "target_table": str(row["target_table"]),
        "committed_rows": attempted,
        "insert_plan_hash": str(row["insert_plan_hash"]),
        "staging_hash": str(row["staging_hash"]),
        "target_contract_hash": str(row["target_contract_hash"]),
        "mapping_set_hash": str(row["mapping_set_hash"]),
        "write_mode": "INSERT_ONLY",
    }
    receipt_hash = _sha256_json(receipt)
    with _connect(root_path) as conn:
        migration_38(conn)
        conn.execute(
            """UPDATE db_target_insert_runs SET status='committed',committed_at=?,committed_rows=?,commit_receipt_hash=?,failure_stage=NULL,failure_reason=NULL
               WHERE id=?""",
            (utc_now(), attempted, receipt_hash, int(insert_run_id)),
        )
        _event(conn, event_type="target_insert_committed", insert_run_id=int(insert_run_id), extraction_batch_id=int(row["extraction_batch_id"]),
               consolidation_id=int(row["consolidation_id"]), target_connection_id=int(row["target_connection_id"]),
               payload={"committed_rows": attempted, "commit_receipt_hash": receipt_hash, "write_mode": "INSERT_ONLY"})
    try:
        from .identity_resolution import finalize_insert_lineage, migration_39
        finalize_insert_lineage(root_path, int(insert_run_id))
        with _connect(root_path) as conn:
            migration_39(conn)
            conn.execute("UPDATE db_target_insert_runs SET lineage_status='complete',lineage_finalized_at=? WHERE id=?", (utc_now(), int(insert_run_id)))
    except Exception as exc:
        try:
            from .identity_resolution import migration_39
            with _connect(root_path) as conn:
                migration_39(conn)
                conn.execute("UPDATE db_target_insert_runs SET lineage_status='pending' WHERE id=?", (int(insert_run_id),))
        except Exception:
            pass
        raise ControlledTargetInsertError("TARGET INSERT committed but lineage finalization is pending; do not retry the INSERT") from exc
    return get_target_insert_receipt(root_path, int(insert_run_id))


def get_target_insert_readiness(root: Path | str, insert_run_id: int) -> dict[str, Any]:
    """Return current controlled-write readiness without mutating or resolving credentials."""
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_38(conn)
        row = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if row is None:
            raise ControlledTargetInsertError("target insert plan not found")
        current, reason = _revalidate_run(conn, row, root_path)
    return {
        "ok": True,
        "insert_run_id": int(insert_run_id),
        "status": str(row["status"]),
        "current": current,
        "stale_reason": reason,
        "reviewed": bool(row["reviewed_by"]),
        "approved": bool(row["approved_by"]),
        "eligible_to_execute": current and (row["status"] == "approved" or (row["status"] == "failed" and row["failure_stage"] in {"preconnect", "precommit", "reconciled_not_committed"})),
        "manual_retry_allowed": current and row["status"] == "failed" and row["failure_stage"] in {"preconnect", "precommit", "reconciled_not_committed"},
        "raw_insert_allowed": False,
        "arbitrary_sql_allowed": False,
        "source_write_allowed": False,
        "automatic_retry_after_committing_or_in_doubt": False,
    }


def get_target_insert_receipt(root: Path | str, insert_run_id: int) -> dict[str, Any]:
    """Return a privacy-safe batch receipt; no inserted row values are exposed."""
    with _connect(root) as conn:
        migration_38(conn)
        row = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if row is None:
            raise ControlledTargetInsertError("target insert plan not found")
    return {
        "ok": True,
        "insert_run_id": int(row["id"]),
        "insert_uuid": str(row["insert_uuid"]),
        "status": str(row["status"]),
        "extraction_batch_id": int(row["extraction_batch_id"]),
        "target_connection_id": int(row["target_connection_id"]),
        "target_schema": str(row["target_schema"]),
        "target_table": str(row["target_table"]),
        "row_count": int(row["row_count"]),
        "attempted_rows": int(row["attempted_rows"]),
        "committed_rows": int(row["committed_rows"]),
        "insert_plan_hash": str(row["insert_plan_hash"]),
        "staging_hash": str(row["staging_hash"]),
        "target_contract_hash": str(row["target_contract_hash"]),
        "mapping_set_hash": str(row["mapping_set_hash"]),
        "commit_receipt_hash": row["commit_receipt_hash"],
        "failure_stage": row["failure_stage"],
        "failure_reason": row["failure_reason"],
        "manual_retry_allowed": row["status"] == "failed" and row["failure_stage"] in {"preconnect", "precommit", "reconciled_not_committed"},
        "automatic_retry_allowed": False,
        "lineage_status": row["lineage_status"] if "lineage_status" in row.keys() else "not_required_v0220",
        "lineage_finalized_at": row["lineage_finalized_at"] if "lineage_finalized_at" in row.keys() else None,
    }


def docs_check_v0220(root: Path | str) -> dict[str, Any]:
    """Validate v0.22.0 docs, version, governance policy, and schema 38."""
    root_path = Path(root).resolve()
    required = [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        ".agents/docs/CONTROLLED_TARGET_INSERT.md", ".agents/docs/USAGE_V0220.md",
    ]
    missing = [item for item in required if not (root_path / item).exists()]
    version = (root_path / "VERSION").read_text(encoding="utf-8").strip() if (root_path / "VERSION").exists() else None
    governance = json.loads((root_path / ".agents/config/governance.json").read_text(encoding="utf-8"))
    policy = governance.get("controlled_target_insert_policy")
    schema = sync_controlled_target_insert_schema(root_path)
    ok = (
        not missing and version == "0.22.0"
        and governance.get("version", governance.get("governance_version")) == "0.22.0"
        and isinstance(policy, dict)
        and policy.get("controlled_insert_enabled") is True
        and policy.get("raw_target_insert_allowed") is False
        and policy.get("source_write_allowed") is False
        and schema["ok"]
    )
    return {
        "ok": ok,
        "missing": missing,
        "version": version,
        "governance_version": governance.get("version", governance.get("governance_version")),
        "database_schema": schema["schema"],
        "controlled_insert_enabled": policy.get("controlled_insert_enabled") if isinstance(policy, dict) else None,
        "raw_target_insert_allowed": policy.get("raw_target_insert_allowed") if isinstance(policy, dict) else None,
        "source_write_allowed": policy.get("source_write_allowed") if isinstance(policy, dict) else None,
    }
