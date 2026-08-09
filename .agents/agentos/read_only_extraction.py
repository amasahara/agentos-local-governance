"""
File: .agents/agentos/read_only_extraction.py

Purpose:
    Implement AgentOS v0.21.2 read-only SOURCE extraction, transformation,
    validation, local staging, and privacy-safe quarantine evidence.

Responsibilities:
    - Build immutable extraction batches from confirmed/current v0.21.1 mappings.
    - Generate engine-specific SELECT-only statements from mapped columns only.
    - Re-verify SOURCE read-only boundary, schema hashes, contract hashes, and mapping hashes before reads.
    - Execute SOURCE reads through optional DB-API adapters without exposing arbitrary SQL.
    - Apply an allowlisted transformation registry; never eval mapping text.
    - Validate target-shaped rows against target contract and mapping validation rules.
    - Write valid target-shaped rows to local chmod-0600 staging JSONL artifacts.
    - Record rejected rows as value-hash/issue evidence without raw business values in SQLite/audit.
    - Keep all TARGET database writes disabled until v0.22.0.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, time, timezone
from decimal import Decimal
import base64
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
from .secret_lineage import resolve_runtime_secret


from .database_boundary import DatabaseBoundaryError, authorize_operation
from .schema_mapping import SchemaMappingError, migration_36

MIGRATION_VERSION = 37
EXTRACTION_PLAN_VERSION = 1
BATCH_STATUSES = {"planned", "running", "validated", "completed_with_rejections", "failed", "stale"}
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#@.-]{0,127}$")
SAFE_REGEX_MAX_LENGTH = 512
MAX_ROWS_LIMIT = 10_000_000
MAX_CHUNK_SIZE = 10_000
DEFAULT_CHUNK_SIZE = 1000

BUILTIN_TRANSFORMS = {
    "identity",
    "datetime_to_date",
    "date_to_datetime",
    "integer_to_boolean",
    "boolean_to_integer",
    "stringify",
    "uuid_to_string",
    "string_to_uuid",
    "json_to_text",
    "text_to_json",
    "trim_string",
    "uppercase_string",
    "lowercase_string",
}


class ReadOnlyExtractionError(RuntimeError):
    """Raised when a v0.21.2 extraction or validation invariant is violated."""


def utc_now() -> str:
    """Return current UTC time as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for hashing/evidence."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _sha256_json(value: Any) -> str:
    """Return SHA-256 of canonical JSON."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    """Return SHA-256 of bytes."""
    return hashlib.sha256(value).hexdigest()


def _json_default(value: Any) -> Any:
    """Convert common DB-driver values to deterministic JSON-safe forms."""
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
    """Return active AgentOS state database path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


@contextmanager
def _connect(root: Path | str):
    """Open the shared AgentOS governance database connection."""
    with central_connect(Path(root)) as conn:
        yield conn


def migration_37(conn: sqlite3.Connection) -> None:
    """Apply additive schema 37 for read-only extraction and validation."""
    migration_36(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS db_extraction_batches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            extraction_plan_version INTEGER NOT NULL,
            extraction_plan_json TEXT NOT NULL,
            extraction_plan_hash TEXT NOT NULL,
            mapping_set_hash TEXT NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            max_rows INTEGER NOT NULL,
            chunk_size INTEGER NOT NULL,
            selected_rows INTEGER NOT NULL DEFAULT 0,
            valid_rows INTEGER NOT NULL DEFAULT 0,
            rejected_rows INTEGER NOT NULL DEFAULT 0,
            staging_path TEXT,
            staging_hash TEXT,
            quarantine_path TEXT,
            quarantine_hash TEXT,
            manifest_path TEXT,
            manifest_hash TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            failure_reason TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(source_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(source_snapshot_id) REFERENCES db_schema_snapshots(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id)
        );
        CREATE TABLE IF NOT EXISTS db_extraction_batch_mappings(
            batch_id INTEGER NOT NULL,
            mapping_id INTEGER NOT NULL,
            mapping_hash TEXT NOT NULL,
            PRIMARY KEY(batch_id, mapping_id),
            FOREIGN KEY(batch_id) REFERENCES db_extraction_batches(id),
            FOREIGN KEY(mapping_id) REFERENCES db_field_mappings(id)
        );
        CREATE TABLE IF NOT EXISTS db_validation_findings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            row_ordinal INTEGER NOT NULL,
            source_locator_hash TEXT NOT NULL,
            target_field TEXT,
            rule_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            value_hash TEXT,
            raw_value_stored INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES db_extraction_batches(id)
        );
        CREATE TABLE IF NOT EXISTS db_extraction_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            consolidation_id INTEGER,
            source_connection_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_db_extraction_batches_plan
            ON db_extraction_batches(consolidation_id, source_connection_id, target_contract_id, status);
        CREATE INDEX IF NOT EXISTS idx_db_validation_findings_batch
            ON db_validation_findings(batch_id, row_ordinal, severity);
        CREATE INDEX IF NOT EXISTS idx_db_extraction_events_batch
            ON db_extraction_events(batch_id, created_at);
        """
    )


def sync_read_only_extraction_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema 37 and report v0.21.2 tables."""
    required = {
        "db_extraction_batches", "db_extraction_batch_mappings",
        "db_validation_findings", "db_extraction_events",
    }
    with _connect(root) as conn:
        migration_37(conn)
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"ok": required <= tables, "schema": MIGRATION_VERSION, "tables": sorted(required)}


def _event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    payload: Any,
    batch_id: int | None = None,
    consolidation_id: int | None = None,
    source_connection_id: int | None = None,
) -> None:
    """Append privacy-safe extraction evidence; payload must never contain record values."""
    _assert_no_record_values_in_event(payload)
    mirror = mirror_domain_event(event_type, payload)
    conn.execute(
        "INSERT INTO db_extraction_events(batch_id,consolidation_id,source_connection_id,event_type,event_json,created_at,governed_operation_id,external_event_hash) VALUES(?,?,?,?,?,?,?,?)",
        (batch_id, consolidation_id, source_connection_id, event_type, _canonical_json(payload), utc_now(), mirror["governed_operation_id"], mirror["external_event_hash"]),
    )


def _assert_no_record_values_in_event(payload: Any) -> None:
    """Reject known value-bearing keys from SQLite/audit event payloads."""
    forbidden_keys = {"row", "rows", "value", "values", "raw_value", "record", "records", "password", "credential", "credential_ref"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in forbidden_keys:
                    raise ReadOnlyExtractionError(f"record/secret-bearing event key is forbidden: {key}")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(payload)


def _require_identifier(value: str, label: str) -> str:
    """Validate one catalog identifier; this is not a SQL parser."""
    text = str(value).strip()
    if not SAFE_IDENTIFIER.fullmatch(text):
        raise ReadOnlyExtractionError(f"invalid {label}: {value!r}")
    return text


def _rowdict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert SQLite row to plain dict."""
    return dict(row)


def _mapping_current(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Check that mapping remains bound to active SOURCE snapshot and approved TARGET contract hashes."""
    snap = conn.execute("SELECT status,snapshot_hash FROM db_schema_snapshots WHERE id=?", (int(row["source_snapshot_id"]),)).fetchone()
    contract = conn.execute("SELECT status,contract_hash FROM target_schema_contracts WHERE id=?", (int(row["target_contract_id"]),)).fetchone()
    return bool(
        snap and contract
        and snap["status"] == "active"
        and contract["status"] == "approved"
        and str(snap["snapshot_hash"]) == str(row["source_snapshot_hash"])
        and str(contract["contract_hash"]) == str(row["target_contract_hash"])
    )


def _contract_target_column(contract: dict[str, Any], schema: str, table: str, column: str) -> dict[str, Any]:
    """Find target column metadata in approved contract."""
    for t in contract.get("tables", []):
        if str(t.get("schema", "")).lower() == schema.lower() and str(t.get("name", "")).lower() == table.lower():
            for c in t.get("columns", []):
                if str(c.get("name", "")).lower() == column.lower():
                    return c
    raise ReadOnlyExtractionError(f"target contract column not found: {schema}.{table}.{column}")


def _contract_target_table(contract: dict[str, Any], schema: str, table: str) -> dict[str, Any]:
    """Find target table metadata in approved contract."""
    for t in contract.get("tables", []):
        if str(t.get("schema", "")).lower() == schema.lower() and str(t.get("name", "")).lower() == table.lower():
            return t
    raise ReadOnlyExtractionError(f"target contract table not found: {schema}.{table}")


def _mapping_to_plan_item(row: sqlite3.Row) -> dict[str, Any]:
    """Convert confirmed mapping row into immutable execution metadata."""
    validation = json.loads(row["validation_rule_json"]) if row["validation_rule_json"] else None
    return {
        "mapping_id": int(row["id"]),
        "mapping_hash": str(row["mapping_hash"]),
        "source_column": str(row["source_column"]),
        "source_canonical_type": str(row["source_canonical_type"]),
        "target_column": str(row["target_column"]),
        "target_canonical_type": str(row["target_canonical_type"]),
        "type_compatibility": str(row["type_compatibility"]),
        "transform_rule": row["transform_rule"],
        "transform_output_type": row["transform_output_type"],
        "validation_rule": validation,
    }


def _validate_transform_rule(item: dict[str, Any]) -> None:
    """Require an allowlisted transform before a production extraction batch can be created."""
    rule = item.get("transform_rule") or "identity"
    if rule not in BUILTIN_TRANSFORMS:
        raise ReadOnlyExtractionError(
            f"mapping {item['mapping_id']} transform_rule {rule!r} is not executable in v0.21.2; "
            "use an allowlisted built-in transform or revise mapping"
        )
    if item["type_compatibility"] != "exact" and rule == "identity":
        raise ReadOnlyExtractionError(f"mapping {item['mapping_id']} requires an explicit transform")


@governed_mutation("db.extraction.batch.create")
def create_extraction_batch(
    root: Path | str,
    *,
    consolidation_id: int,
    source_snapshot_id: int,
    target_contract_id: int,
    source_schema: str,
    source_table: str,
    target_schema: str,
    target_table: str,
    created_by: str,
    max_rows: int = 100000,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Create one immutable SOURCE-table -> TARGET-table extraction/validation batch.

    The batch contains only confirmed mappings. It does not access the external DB.
    All required TARGET fields for the selected target table must be mapped by this
    SOURCE table in the batch, so output rows are independently valid target-row candidates.
    """
    if not created_by.strip():
        raise ReadOnlyExtractionError("created_by is required")
    source_schema = _require_identifier(source_schema, "source schema")
    source_table = _require_identifier(source_table, "source table")
    target_schema = _require_identifier(target_schema, "target schema")
    target_table = _require_identifier(target_table, "target table")
    max_rows = int(max_rows)
    chunk_size = int(chunk_size)
    if max_rows < 1 or max_rows > MAX_ROWS_LIMIT:
        raise ReadOnlyExtractionError(f"max_rows must be between 1 and {MAX_ROWS_LIMIT}")
    if chunk_size < 1 or chunk_size > MAX_CHUNK_SIZE:
        raise ReadOnlyExtractionError(f"chunk_size must be between 1 and {MAX_CHUNK_SIZE}")

    with _connect(root) as conn:
        migration_37(conn)
        plan = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(consolidation_id),)).fetchone()
        if plan is None:
            raise ReadOnlyExtractionError("database consolidation not found")
        snap = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(source_snapshot_id),)).fetchone()
        if snap is None or snap["connection_role"] != "SOURCE" or snap["status"] != "active":
            raise ReadOnlyExtractionError("active SOURCE schema snapshot required")
        source_conn = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(snap["connection_id"]),)).fetchone()
        if source_conn is None or source_conn["role"] != "SOURCE" or source_conn["status"] != "active":
            raise ReadOnlyExtractionError("active SOURCE connection required")
        if not int(source_conn["readonly_verified"]):
            raise ReadOnlyExtractionError("SOURCE must remain read-only verified")
        registered = conn.execute(
            "SELECT 1 FROM db_consolidation_sources WHERE consolidation_id=? AND source_connection_id=?",
            (int(consolidation_id), int(source_conn["id"])),
        ).fetchone()
        if registered is None:
            raise ReadOnlyExtractionError("SOURCE is not registered in consolidation")
        contract_row = conn.execute(
            "SELECT * FROM target_schema_contracts WHERE id=? AND consolidation_id=?",
            (int(target_contract_id), int(consolidation_id)),
        ).fetchone()
        if contract_row is None or contract_row["status"] != "approved":
            raise ReadOnlyExtractionError("approved TARGET schema contract required")
        if int(contract_row["target_connection_id"]) != int(plan["target_connection_id"]):
            raise ReadOnlyExtractionError("target contract does not belong to consolidation TARGET")
        if int(source_conn["data_write_enabled"]) != 0:
            raise ReadOnlyExtractionError("SOURCE data_write_enabled must remain false")

        mappings = conn.execute(
            """SELECT * FROM db_field_mappings
               WHERE consolidation_id=? AND source_connection_id=? AND source_snapshot_id=? AND target_contract_id=?
                 AND lower(source_schema)=lower(?) AND lower(source_table)=lower(?)
                 AND lower(target_schema)=lower(?) AND lower(target_table)=lower(?) AND status='confirmed'
               ORDER BY id""",
            (int(consolidation_id), int(source_conn["id"]), int(source_snapshot_id), int(target_contract_id),
             source_schema, source_table, target_schema, target_table),
        ).fetchall()
        if not mappings:
            raise ReadOnlyExtractionError("no confirmed mappings exist for selected SOURCE/TARGET table pair")
        for row in mappings:
            if not _mapping_current(conn, row):
                raise ReadOnlyExtractionError(f"mapping {row['id']} is stale")

        items = [_mapping_to_plan_item(row) for row in mappings]
        target_seen: set[str] = set()
        for item in items:
            key = item["target_column"].lower()
            if key in target_seen:
                raise ReadOnlyExtractionError(f"multiple mappings target the same output column: {item['target_column']}")
            target_seen.add(key)
            _validate_transform_rule(item)

        contract = json.loads(contract_row["contract_json"])
        table_contract = _contract_target_table(contract, target_schema, target_table)
        required = {str(c["name"]).lower() for c in table_contract["columns"] if c.get("required")}
        missing_required = sorted(required - target_seen)
        if missing_required:
            raise ReadOnlyExtractionError("required TARGET fields missing from this extraction batch: " + ", ".join(missing_required))

        # A v0.21.2 batch selects only columns represented by confirmed mappings.
        selected_columns = []
        seen_source: set[str] = set()
        for item in items:
            key = item["source_column"].lower()
            if key not in seen_source:
                selected_columns.append(item["source_column"])
                seen_source.add(key)
        mapping_set = [{"id": x["mapping_id"], "hash": x["mapping_hash"]} for x in items]
        mapping_set_hash = _sha256_json(mapping_set)
        extraction_plan = {
            "plan_version": EXTRACTION_PLAN_VERSION,
            "consolidation_id": int(consolidation_id),
            "source_connection_id": int(source_conn["id"]),
            "source_snapshot_id": int(source_snapshot_id),
            "source_snapshot_hash": str(snap["snapshot_hash"]),
            "source_engine": str(source_conn["engine"]),
            "source_schema": source_schema,
            "source_table": source_table,
            "selected_columns": selected_columns,
            "target_contract_id": int(target_contract_id),
            "target_contract_hash": str(contract_row["contract_hash"]),
            "target_schema": target_schema,
            "target_table": target_table,
            "mappings": items,
            "max_rows": max_rows,
            "chunk_size": chunk_size,
            "select_star": False,
            "target_write": False,
        }
        plan_hash = _sha256_json(extraction_plan)
        now = utc_now()
        cur = conn.execute(
            """INSERT INTO db_extraction_batches(
                batch_uuid,consolidation_id,source_connection_id,source_snapshot_id,target_contract_id,
                source_schema,source_table,target_schema,target_table,extraction_plan_version,extraction_plan_json,
                extraction_plan_hash,mapping_set_hash,source_snapshot_hash,target_contract_hash,status,max_rows,chunk_size,
                created_by,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), int(consolidation_id), int(source_conn["id"]), int(source_snapshot_id), int(target_contract_id),
             source_schema, source_table, target_schema, target_table, EXTRACTION_PLAN_VERSION, _canonical_json(extraction_plan),
             plan_hash, mapping_set_hash, str(snap["snapshot_hash"]), str(contract_row["contract_hash"]), "planned",
             max_rows, chunk_size, created_by.strip(), now),
        )
        batch_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO db_extraction_batch_mappings(batch_id,mapping_id,mapping_hash) VALUES(?,?,?)",
            [(batch_id, x["mapping_id"], x["mapping_hash"]) for x in items],
        )
        _event(conn, event_type="extraction_batch_created", batch_id=batch_id, consolidation_id=int(consolidation_id),
               source_connection_id=int(source_conn["id"]), payload={
                   "extraction_plan_hash": plan_hash,
                   "mapping_set_hash": mapping_set_hash,
                   "mapped_column_count": len(selected_columns),
                   "mapping_count": len(items),
                   "max_rows": max_rows,
                   "chunk_size": chunk_size,
                   "select_star": False,
                   "target_write": False,
               })
    return get_extraction_batch(root, batch_id)


def _batch_is_current(conn: sqlite3.Connection, batch: sqlite3.Row) -> tuple[bool, str | None]:
    """Revalidate all immutable hashes before external SOURCE access."""
    snap = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(batch["source_snapshot_id"]),)).fetchone()
    if snap is None or snap["status"] != "active" or str(snap["snapshot_hash"]) != str(batch["source_snapshot_hash"]):
        return False, "source_schema_drift"
    contract = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(batch["target_contract_id"]),)).fetchone()
    if contract is None or contract["status"] != "approved" or str(contract["contract_hash"]) != str(batch["target_contract_hash"]):
        return False, "target_contract_drift"
    plan = json.loads(batch["extraction_plan_json"])
    if _sha256_json(plan) != str(batch["extraction_plan_hash"]):
        return False, "extraction_plan_hash_mismatch"
    rows = conn.execute(
        """SELECT m.* FROM db_extraction_batch_mappings bm
           JOIN db_field_mappings m ON m.id=bm.mapping_id WHERE bm.batch_id=? ORDER BY m.id""",
        (int(batch["id"]),),
    ).fetchall()
    mapping_set = []
    for row in rows:
        if row["status"] != "confirmed" or not _mapping_current(conn, row):
            return False, f"mapping_not_current:{row['id']}"
        stored = conn.execute("SELECT mapping_hash FROM db_extraction_batch_mappings WHERE batch_id=? AND mapping_id=?", (int(batch["id"]), int(row["id"]))).fetchone()
        if stored is None or str(stored["mapping_hash"]) != str(row["mapping_hash"]):
            return False, f"mapping_hash_mismatch:{row['id']}"
        mapping_set.append({"id": int(row["id"]), "hash": str(row["mapping_hash"])})
    if _sha256_json(mapping_set) != str(batch["mapping_set_hash"]):
        return False, "mapping_set_hash_mismatch"
    return True, None


def _safe_batch_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert extraction batch to read-safe metadata without business record values."""
    value = dict(row)
    value["extraction_plan"] = json.loads(value.pop("extraction_plan_json"))
    # Paths are local runtime metadata only. They never reveal artifact contents.
    return value


def get_extraction_batch(root: Path | str, batch_id: int) -> dict[str, Any]:
    """Return one extraction batch and mark a planned batch stale if its hashes drifted."""
    with _connect(root) as conn:
        migration_37(conn)
        row = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone()
        if row is None:
            raise ReadOnlyExtractionError("extraction batch not found")
        if row["status"] == "planned":
            current, reason = _batch_is_current(conn, row)
            if not current:
                conn.execute("UPDATE db_extraction_batches SET status='stale',failure_reason=? WHERE id=?", (reason, int(batch_id)))
                row = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone()
    return {"ok": True, "batch": _safe_batch_dict(row), "target_data_write_enabled": False}


def _quote_identifier(engine: str, identifier: str) -> str:
    """Quote a validated identifier for a supported engine."""
    identifier = _require_identifier(identifier, "SQL identifier")
    if engine == "mysql":
        return "`" + identifier.replace("`", "``") + "`"
    if engine == "mssql":
        return "[" + identifier.replace("]", "]]" ) + "]"
    if engine in {"postgresql", "oracle"}:
        return '"' + identifier.replace('"', '""') + '"'
    raise ReadOnlyExtractionError(f"unsupported engine: {engine}")


def build_select_spec(root: Path | str, batch_id: int) -> dict[str, Any]:
    """Build a generated SELECT-only statement from immutable mapped-column metadata."""
    with _connect(root) as conn:
        migration_37(conn)
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone()
        if batch is None:
            raise ReadOnlyExtractionError("extraction batch not found")
        current, reason = _batch_is_current(conn, batch)
        if not current:
            conn.execute("UPDATE db_extraction_batches SET status='stale',failure_reason=? WHERE id=?", (reason, int(batch_id)))
            raise ReadOnlyExtractionError(f"extraction batch is stale: {reason}")
        if batch["status"] != "planned":
            raise ReadOnlyExtractionError("SELECT spec is available only for planned batches")
        source = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(batch["source_connection_id"]),)).fetchone()
        if source is None:
            raise ReadOnlyExtractionError("SOURCE connection not found")
        decision = authorize_operation(root, int(source["id"]), "select_read")
        if not decision.get("allowed"):
            raise ReadOnlyExtractionError(f"SOURCE SELECT denied: {decision.get('reason')}")
        plan = json.loads(batch["extraction_plan_json"])
    engine = str(source["engine"])
    cols = plan["selected_columns"]
    if not cols:
        raise ReadOnlyExtractionError("extraction plan has no mapped columns")
    quoted_cols = ", ".join(_quote_identifier(engine, c) for c in cols)
    qschema = _quote_identifier(engine, plan["source_schema"])
    qtable = _quote_identifier(engine, plan["source_table"])
    limit = int(batch["max_rows"])
    if engine == "mssql":
        sql = f"SELECT TOP {limit} {quoted_cols} FROM {qschema}.{qtable}"
    elif engine in {"mysql", "postgresql"}:
        sql = f"SELECT {quoted_cols} FROM {qschema}.{qtable} LIMIT {limit}"
    elif engine == "oracle":
        sql = f"SELECT {quoted_cols} FROM {qschema}.{qtable} FETCH FIRST {limit} ROWS ONLY"
    else:
        raise ReadOnlyExtractionError(f"unsupported engine: {engine}")
    if "*" in sql:
        raise ReadOnlyExtractionError("SELECT * is forbidden")
    return {
        "ok": True,
        "batch_id": int(batch_id),
        "engine": engine,
        "sql": sql,
        "selected_columns": list(cols),
        "generated": True,
        "arbitrary_sql": False,
        "write_statement": False,
    }


def _resolve_env_secret(credential_ref: str) -> dict[str, Any]:
    """Compatibility-only env:// JSON resolver retained for non-governed library callers.

    The production extraction path does not call this helper in v0.22.6. Governed
    AgentOS roots resolve through the trusted registry with provider pin/capability
    approval via :func:`secret_lineage.resolve_runtime_secret`.
    """
    if not credential_ref.startswith("env://"):
        raise ReadOnlyExtractionError("compatibility env resolver accepts env:// only")
    key = credential_ref[len("env://"):].strip()
    if not key or key not in os.environ:
        raise ReadOnlyExtractionError("credential environment variable is unavailable")
    try:
        value = json.loads(os.environ[key])
    except json.JSONDecodeError as exc:
        raise ReadOnlyExtractionError("credential environment variable must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise ReadOnlyExtractionError("credential secret must resolve to a JSON object")
    return value


def _open_source_connection(connection: sqlite3.Row, secret: dict[str, Any]):
    """Open a TLS-capable DB-API SOURCE connection using optional local drivers.

    Driver imports are lazy. Missing drivers fail closed and do not alter the source.
    """
    engine = str(connection["engine"])
    host, port, database = str(connection["host"]), int(connection["port"]), str(connection["database_name"])
    user = secret.get("user") or secret.get("username")
    password = secret.get("password")
    if not user or password is None:
        raise ReadOnlyExtractionError("resolved secret requires user/username and password")
    try:
        if engine == "postgresql":
            try:
                import psycopg  # type: ignore
                conn = psycopg.connect(host=host, port=port, dbname=database, user=user, password=password, sslmode="require")
            except ImportError:
                import psycopg2  # type: ignore
                conn = psycopg2.connect(host=host, port=port, dbname=database, user=user, password=password, sslmode="require")
            with conn.cursor() as cur:
                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            return conn
        if engine == "mysql":
            try:
                import pymysql  # type: ignore
                conn = pymysql.connect(host=host, port=port, database=database, user=user, password=password, ssl={"check_hostname": True})
            except ImportError:
                import mysql.connector  # type: ignore
                conn = mysql.connector.connect(host=host, port=port, database=database, user=user, password=password, ssl_disabled=False)
            cur = conn.cursor()
            try:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
            finally:
                cur.close()
            return conn
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
                raise ReadOnlyExtractionError("Oracle SOURCE requires a tcps:// DSN")
            conn = oracledb.connect(user=user, password=password, dsn=dsn)
            cur = conn.cursor()
            try:
                cur.execute("SET TRANSACTION READ ONLY")
            finally:
                cur.close()
            return conn
    except ReadOnlyExtractionError:
        raise
    except ImportError as exc:
        raise ReadOnlyExtractionError(f"optional database driver is not installed for engine {engine}: {exc}") from exc
    except Exception as exc:
        # Never include connection/secret details in the error.
        raise ReadOnlyExtractionError(f"SOURCE connection failed for engine {engine}: {type(exc).__name__}") from exc
    raise ReadOnlyExtractionError(f"unsupported engine: {engine}")


def _iter_cursor_rows(cursor: Any, columns: list[str], chunk_size: int) -> Iterator[dict[str, Any]]:
    """Yield DB-API rows as dicts without buffering the full source table."""
    while True:
        chunk = cursor.fetchmany(chunk_size)
        if not chunk:
            return
        for row in chunk:
            if isinstance(row, dict):
                yield {c: row.get(c) for c in columns}
            else:
                yield {columns[i]: row[i] for i in range(min(len(columns), len(row)))}


def _source_rows_from_database(
    root: Path | str,
    batch_id: int,
    *,
    secret_resolver: Callable[[str], dict[str, Any]] | None = None,
) -> Iterable[dict[str, Any]]:
    """Execute the generated SELECT-only statement against one verified SOURCE."""
    spec = build_select_spec(root, batch_id)
    with _connect(root) as conn:
        migration_37(conn)
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone()
        source = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(batch["source_connection_id"]),)).fetchone()
        credential_ref = str(source["credential_ref"])
        chunk_size = int(batch["chunk_size"])
    try:
        secret = resolve_runtime_secret(
            root, credential_ref, capability="db.source.select", compatibility_resolver=secret_resolver
        )
    except Exception as exc:
        if isinstance(exc, ReadOnlyExtractionError):
            raise
        raise ReadOnlyExtractionError("SOURCE credential resolution failed") from exc
    source_conn = _open_source_connection(source, secret)

    def generator() -> Iterator[dict[str, Any]]:
        try:
            cursor = source_conn.cursor()
            try:
                cursor.execute(spec["sql"])
                yield from _iter_cursor_rows(cursor, list(spec["selected_columns"]), chunk_size)
            finally:
                cursor.close()
        finally:
            try:
                source_conn.rollback()
            except Exception:
                pass
            source_conn.close()
    return generator()


def _transform(rule: str | None, value: Any) -> Any:
    """Apply one allowlisted deterministic local transformation."""
    name = rule or "identity"
    if name not in BUILTIN_TRANSFORMS:
        raise ReadOnlyExtractionError(f"unsupported transform_rule at execution: {name}")
    if value is None:
        return None
    if name == "identity":
        return value
    if name == "datetime_to_date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        raise ValueError("expected datetime")
    if name == "date_to_datetime":
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        if isinstance(value, str):
            return datetime.combine(date.fromisoformat(value), time.min)
        raise ValueError("expected date")
    if name == "integer_to_boolean":
        if value in (0, 1, False, True):
            return bool(value)
        raise ValueError("integer_to_boolean accepts only 0/1")
    if name == "boolean_to_integer":
        if isinstance(value, bool):
            return 1 if value else 0
        raise ValueError("expected boolean")
    if name == "stringify":
        return str(value)
    if name == "uuid_to_string":
        return str(value)
    if name == "string_to_uuid":
        return uuid.UUID(str(value))
    if name == "json_to_text":
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if name == "text_to_json":
        return json.loads(str(value))
    if name == "trim_string":
        return str(value).strip()
    if name == "uppercase_string":
        return str(value).upper()
    if name == "lowercase_string":
        return str(value).lower()
    raise AssertionError(name)


def _type_valid(value: Any, canonical_type: str) -> bool:
    """Check transformed Python value against target canonical type."""
    if value is None:
        return True
    if canonical_type in {"string", "text", "code"}:
        return isinstance(value, str)
    if canonical_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if canonical_type in {"decimal", "float"}:
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
    if canonical_type == "boolean":
        return isinstance(value, bool)
    if canonical_type == "date":
        return isinstance(value, date) and not isinstance(value, datetime)
    if canonical_type == "datetime":
        return isinstance(value, datetime)
    if canonical_type == "time":
        return isinstance(value, time)
    if canonical_type == "uuid":
        return isinstance(value, uuid.UUID)
    if canonical_type == "json":
        return isinstance(value, (dict, list, str, int, float, bool))
    if canonical_type == "binary":
        return isinstance(value, (bytes, bytearray, memoryview))
    return True


def _value_hash(value: Any) -> str:
    """Hash one value for privacy-safe findings."""
    return _sha256_json({"v": value})


def _validate_rule(rule: dict[str, Any] | None, value: Any) -> list[tuple[str, str]]:
    """Apply allowlisted field validation rule keys and return (code,message) issues."""
    if rule is None:
        return []
    if not isinstance(rule, dict):
        return [("invalid_validation_rule", "validation rule is not an object")]
    allowed = {"not_null", "allow_blank", "min_length", "max_length", "regex", "enum", "min", "max", "date_min", "date_max"}
    unknown = sorted(set(rule) - allowed)
    if unknown:
        return [("unsupported_validation_rule", "unsupported validation keys: " + ", ".join(unknown))]
    issues: list[tuple[str, str]] = []
    if rule.get("not_null") and value is None:
        issues.append(("not_null", "value must not be null"))
        return issues
    if value is None:
        return issues
    if isinstance(value, str):
        if rule.get("allow_blank") is False and value.strip() == "":
            issues.append(("blank_not_allowed", "blank string is not allowed"))
        if "min_length" in rule and len(value) < int(rule["min_length"]):
            issues.append(("min_length", "value is shorter than minimum length"))
        if "max_length" in rule and len(value) > int(rule["max_length"]):
            issues.append(("max_length", "value exceeds maximum length"))
        if "regex" in rule:
            pattern = str(rule["regex"])
            if len(pattern) > SAFE_REGEX_MAX_LENGTH:
                issues.append(("regex_too_long", "regex validation pattern exceeds safety limit"))
            else:
                try:
                    if re.fullmatch(pattern, value) is None:
                        issues.append(("regex", "value does not match validation pattern"))
                except re.error:
                    issues.append(("invalid_regex", "validation regex is invalid"))
    if "enum" in rule and value not in rule["enum"]:
        issues.append(("enum", "value is outside allowed enumeration"))
    if "min" in rule:
        try:
            if Decimal(str(value)) < Decimal(str(rule["min"])):
                issues.append(("min", "value is below minimum"))
        except Exception:
            issues.append(("min_type", "value cannot be compared to numeric minimum"))
    if "max" in rule:
        try:
            if Decimal(str(value)) > Decimal(str(rule["max"])):
                issues.append(("max", "value exceeds maximum"))
        except Exception:
            issues.append(("max_type", "value cannot be compared to numeric maximum"))
    if "date_min" in rule or "date_max" in rule:
        try:
            d = value.date() if isinstance(value, datetime) else value if isinstance(value, date) else date.fromisoformat(str(value))
            if "date_min" in rule and d < date.fromisoformat(str(rule["date_min"])):
                issues.append(("date_min", "date is before minimum"))
            if "date_max" in rule and d > date.fromisoformat(str(rule["date_max"])):
                issues.append(("date_max", "date is after maximum"))
        except Exception:
            issues.append(("date_type", "value cannot be validated as a date"))
    return issues


def _artifact_dir(root: Path, batch_uuid: str) -> Path:
    """Return local-only staging directory and enforce containment."""
    base = (root / ".agents/runtime/data-staging").resolve()
    path = (base / batch_uuid).resolve()
    if base not in path.parents:
        raise ReadOnlyExtractionError("staging path escaped runtime root")
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def _atomic_write_lines(path: Path, lines: Iterable[str]) -> tuple[int, str]:
    """Write UTF-8 JSONL atomically with owner-only permissions and return bytes/hash."""
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    h = hashlib.sha256()
    count = 0
    with tmp.open("wb") as f:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        for line in lines:
            data = line.encode("utf-8")
            f.write(data)
            h.update(data)
            count += 1
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return count, h.hexdigest()


def _relative_runtime_path(root: Path, path: Path) -> str:
    """Return project-relative runtime artifact path."""
    return str(path.resolve().relative_to(root.resolve()))



def _flush_findings(root: Path, findings: list[tuple[Any, ...]]) -> None:
    """Persist a bounded chunk of privacy-safe validation findings and clear the buffer."""
    if not findings:
        return
    with _connect(root) as conn:
        migration_37(conn)
        conn.executemany(
            """INSERT INTO db_validation_findings(
                batch_id,row_ordinal,source_locator_hash,target_field,rule_code,severity,message,value_hash,raw_value_stored,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            findings,
        )
    findings.clear()

@governed_mutation("db.extraction.run")
def run_extraction_validation(
    root: Path | str,
    batch_id: int,
    *,
    row_provider: Iterable[dict[str, Any]] | None = None,
    secret_resolver: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one read-only extraction and validation batch.

    Args:
        root: Active AgentOS project root.
        batch_id: Planned extraction batch id.
        row_provider: Optional trusted iterable for tests/offline adapters. Production CLI leaves this None,
            causing the generated SELECT-only adapter path to be used.
        secret_resolver: Optional trusted secret resolver for non-env secret backends.

    Returns:
        Privacy-safe batch summary and local staging/quarantine hashes. No row values are returned.
    """
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_37(conn)
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone()
        if batch is None:
            raise ReadOnlyExtractionError("extraction batch not found")
        if batch["status"] != "planned":
            raise ReadOnlyExtractionError("only planned batches can run")
        current, reason = _batch_is_current(conn, batch)
        if not current:
            conn.execute("UPDATE db_extraction_batches SET status='stale',failure_reason=? WHERE id=?", (reason, int(batch_id)))
            raise ReadOnlyExtractionError(f"extraction batch is stale: {reason}")
        source = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(batch["source_connection_id"]),)).fetchone()
        if source is None or source["role"] != "SOURCE" or not int(source["readonly_verified"]):
            raise ReadOnlyExtractionError("SOURCE boundary verification failed")
        if int(source["data_write_enabled"]) != 0:
            raise ReadOnlyExtractionError("SOURCE write capability must remain disabled")
        target = conn.execute(
            "SELECT c.* FROM db_consolidations p JOIN db_connections c ON c.id=p.target_connection_id WHERE p.id=?",
            (int(batch["consolidation_id"]),),
        ).fetchone()
        if target is None or int(target["data_write_enabled"]) != 0:
            raise ReadOnlyExtractionError("TARGET data writes must remain disabled in v0.21.2")
        decision = authorize_operation(root_path, int(source["id"]), "select_read")
        if not decision.get("allowed"):
            raise ReadOnlyExtractionError(f"SOURCE SELECT denied: {decision.get('reason')}")
        conn.execute("UPDATE db_extraction_batches SET status='running',started_at=?,failure_reason=NULL WHERE id=?", (utc_now(), int(batch_id)))
        _event(conn, event_type="extraction_started", batch_id=int(batch_id), consolidation_id=int(batch["consolidation_id"]),
               source_connection_id=int(source["id"]), payload={
                   "extraction_plan_hash": str(batch["extraction_plan_hash"]),
                   "select_only": True,
                   "target_write": False,
                   "provider": "injected" if row_provider is not None else "database_adapter",
               })
        plan = json.loads(batch["extraction_plan_json"])
        contract_row = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(batch["target_contract_id"]),)).fetchone()
        contract = json.loads(contract_row["contract_json"])
        target_table_contract = _contract_target_table(contract, str(batch["target_schema"]), str(batch["target_table"]))

    rows = row_provider if row_provider is not None else _source_rows_from_database(root_path, int(batch_id), secret_resolver=secret_resolver)
    out_dir = _artifact_dir(root_path, str(batch["batch_uuid"]))
    staging_path = out_dir / "valid.jsonl"
    quarantine_path = out_dir / "quarantine.jsonl"
    manifest_path = out_dir / "manifest.json"
    staging_tmp = staging_path.with_name(staging_path.name + ".tmp-" + uuid.uuid4().hex)
    quarantine_tmp = quarantine_path.with_name(quarantine_path.name + ".tmp-" + uuid.uuid4().hex)

    selected_rows = valid_rows = rejected_rows = 0
    findings_to_insert: list[tuple[Any, ...]] = []
    mappings = list(plan["mappings"])
    max_rows = int(batch["max_rows"])
    staging_hasher = hashlib.sha256()
    quarantine_hasher = hashlib.sha256()

    try:
        with staging_tmp.open("wb") as staging_file, quarantine_tmp.open("wb") as quarantine_file:
            for file_path in (staging_tmp, quarantine_tmp):
                try:
                    os.chmod(file_path, 0o600)
                except OSError:
                    pass
            for ordinal, source_row in enumerate(rows, start=1):
                if ordinal > max_rows:
                    break
                if not isinstance(source_row, dict):
                    raise ReadOnlyExtractionError("SOURCE adapter yielded a non-object row")
                selected_rows += 1
                locator_hash = _sha256_json({
                    "batch_uuid": str(batch["batch_uuid"]),
                    "row_ordinal": ordinal,
                    "selected_value_hashes": {c: _value_hash(source_row.get(c)) for c in plan["selected_columns"]},
                })
                target_values: dict[str, Any] = {}
                issues: list[dict[str, Any]] = []
                for item in mappings:
                    src_col = item["source_column"]
                    tgt_col = item["target_column"]
                    raw = source_row.get(src_col)
                    if src_col not in source_row:
                        issues.append({"field": tgt_col, "rule": "source_column_missing", "message": "mapped SOURCE column is missing", "value_hash": None})
                        continue
                    try:
                        transformed = _transform(item.get("transform_rule"), raw)
                    except Exception as exc:
                        issues.append({"field": tgt_col, "rule": "transform_failed", "message": f"transform failed: {type(exc).__name__}", "value_hash": _value_hash(raw)})
                        continue
                    target_meta = _contract_target_column(contract, str(batch["target_schema"]), str(batch["target_table"]), tgt_col)
                    if transformed is None and (target_meta.get("required") or not target_meta.get("nullable", True)):
                        issues.append({"field": tgt_col, "rule": "required", "message": "required target value is null", "value_hash": _value_hash(transformed)})
                    elif not _type_valid(transformed, str(item["target_canonical_type"])):
                        issues.append({"field": tgt_col, "rule": "canonical_type", "message": "transformed value does not match target canonical type", "value_hash": _value_hash(transformed)})
                    else:
                        for code, message in _validate_rule(item.get("validation_rule"), transformed):
                            issues.append({"field": tgt_col, "rule": code, "message": message, "value_hash": _value_hash(transformed)})
                    target_values[tgt_col] = transformed

                for col in target_table_contract["columns"]:
                    if col.get("required") and col["name"] not in target_values:
                        issues.append({"field": col["name"], "rule": "required_unmapped_at_runtime", "message": "required target field was not materialized", "value_hash": None})

                if issues:
                    rejected_rows += 1
                    q = {
                        "row_ordinal": ordinal,
                        "source_locator_hash": locator_hash,
                        "issues": [{"field": i["field"], "rule": i["rule"], "message": i["message"], "value_hash": i["value_hash"]} for i in issues],
                        "raw_values_stored": False,
                    }
                    data = (json.dumps(q, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                    quarantine_file.write(data); quarantine_hasher.update(data)
                    for issue in issues:
                        findings_to_insert.append((int(batch_id), ordinal, locator_hash, issue["field"], issue["rule"], "error", issue["message"], issue["value_hash"], 0, utc_now()))
                    if len(findings_to_insert) >= 1000:
                        _flush_findings(root_path, findings_to_insert)
                else:
                    valid_rows += 1
                    record = {
                        "target": {"schema": str(batch["target_schema"]), "table": str(batch["target_table"])},
                        "values": target_values,
                        "provenance": {
                            "source_connection_id": int(batch["source_connection_id"]),
                            "source_snapshot_hash": str(batch["source_snapshot_hash"]),
                            "source_schema": str(batch["source_schema"]),
                            "source_table": str(batch["source_table"]),
                            "source_row_ordinal": ordinal,
                            "source_locator_hash": locator_hash,
                            "mapping_set_hash": str(batch["mapping_set_hash"]),
                            "target_contract_hash": str(batch["target_contract_hash"]),
                        },
                    }
                    data = (json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=_json_default) + "\n").encode("utf-8")
                    staging_file.write(data); staging_hasher.update(data)
            for f in (staging_file, quarantine_file):
                f.flush(); os.fsync(f.fileno())
        os.replace(staging_tmp, staging_path); os.replace(quarantine_tmp, quarantine_path)
        for file_path in (staging_path, quarantine_path):
            try:
                file_path.chmod(0o600)
            except OSError:
                pass
        staging_hash = staging_hasher.hexdigest()
        quarantine_hash = quarantine_hasher.hexdigest()
        status = "validated" if rejected_rows == 0 else "completed_with_rejections"
        manifest = {
            "manifest_version": 1,
            "batch_uuid": str(batch["batch_uuid"]),
            "batch_id": int(batch_id),
            "status": status,
            "selected_rows": selected_rows,
            "valid_rows": valid_rows,
            "rejected_rows": rejected_rows,
            "staging_hash": staging_hash,
            "quarantine_hash": quarantine_hash,
            "extraction_plan_hash": str(batch["extraction_plan_hash"]),
            "mapping_set_hash": str(batch["mapping_set_hash"]),
            "source_snapshot_hash": str(batch["source_snapshot_hash"]),
            "target_contract_hash": str(batch["target_contract_hash"]),
            "target_write_performed": False,
            "raw_quarantine_values_stored": False,
        }
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        _, manifest_hash = _atomic_write_lines(manifest_path, [manifest_text])
        _flush_findings(root_path, findings_to_insert)
        with _connect(root_path) as conn:
            migration_37(conn)
            conn.execute(
                """UPDATE db_extraction_batches SET status=?,selected_rows=?,valid_rows=?,rejected_rows=?,
                   staging_path=?,staging_hash=?,quarantine_path=?,quarantine_hash=?,manifest_path=?,manifest_hash=?,completed_at=? WHERE id=?""",
                (status, selected_rows, valid_rows, rejected_rows,
                 _relative_runtime_path(root_path, staging_path), staging_hash,
                 _relative_runtime_path(root_path, quarantine_path), quarantine_hash,
                 _relative_runtime_path(root_path, manifest_path), manifest_hash, utc_now(), int(batch_id)),
            )
            _event(conn, event_type="extraction_validated", batch_id=int(batch_id), consolidation_id=int(batch["consolidation_id"]),
                   source_connection_id=int(batch["source_connection_id"]), payload={
                       "status": status,
                       "selected_rows": selected_rows,
                       "valid_rows": valid_rows,
                       "rejected_rows": rejected_rows,
                       "staging_hash": staging_hash,
                       "quarantine_hash": quarantine_hash,
                       "manifest_hash": manifest_hash,
                       "target_write": False,
                       "raw_quarantine_stored": False,
                   })
        return get_extraction_summary(root_path, int(batch_id))
    except Exception as exc:
        for path in (staging_tmp, quarantine_tmp):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        with _connect(root_path) as conn:
            migration_37(conn)
            conn.execute("UPDATE db_extraction_batches SET status='failed',failure_reason=?,completed_at=? WHERE id=?", (type(exc).__name__, utc_now(), int(batch_id)))
            _event(conn, event_type="extraction_failed", batch_id=int(batch_id), consolidation_id=int(batch["consolidation_id"]),
                   source_connection_id=int(batch["source_connection_id"]), payload={"error_type": type(exc).__name__, "target_write": False})
        raise

def get_validation_findings(root: Path | str, batch_id: int, *, limit: int = 1000) -> dict[str, Any]:
    """Return privacy-safe validation findings; raw values are never present."""
    limit = int(limit)
    if limit < 1 or limit > 10000:
        raise ReadOnlyExtractionError("limit must be between 1 and 10000")
    with _connect(root) as conn:
        migration_37(conn)
        if conn.execute("SELECT 1 FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone() is None:
            raise ReadOnlyExtractionError("extraction batch not found")
        rows = conn.execute(
            "SELECT * FROM db_validation_findings WHERE batch_id=? ORDER BY id LIMIT ?", (int(batch_id), limit)
        ).fetchall()
    return {"ok": True, "batch_id": int(batch_id), "findings": [dict(row) for row in rows], "raw_values_returned": False}


def get_extraction_summary(root: Path | str, batch_id: int) -> dict[str, Any]:
    """Return batch counts, integrity hashes, and validation summary without staged business data."""
    with _connect(root) as conn:
        migration_37(conn)
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone()
        if batch is None:
            raise ReadOnlyExtractionError("extraction batch not found")
        by_rule = {str(r["rule_code"]): int(r["n"]) for r in conn.execute(
            "SELECT rule_code,COUNT(*) n FROM db_validation_findings WHERE batch_id=? GROUP BY rule_code", (int(batch_id),)
        ).fetchall()}
    return {
        "ok": True,
        "batch_id": int(batch_id),
        "batch_uuid": str(batch["batch_uuid"]),
        "status": str(batch["status"]),
        "selected_rows": int(batch["selected_rows"]),
        "valid_rows": int(batch["valid_rows"]),
        "rejected_rows": int(batch["rejected_rows"]),
        "findings_by_rule": by_rule,
        "staging_path": batch["staging_path"],
        "staging_hash": batch["staging_hash"],
        "quarantine_path": batch["quarantine_path"],
        "quarantine_hash": batch["quarantine_hash"],
        "manifest_path": batch["manifest_path"],
        "manifest_hash": batch["manifest_hash"],
        "raw_values_returned": False,
        "raw_quarantine_values_stored": False,
        "target_data_write_enabled": False,
        "ready_for_v0.22.0": str(batch["status"]) == "validated" and int(batch["valid_rows"]) > 0 and int(batch["rejected_rows"]) == 0,
    }


def verify_staging_artifact(root: Path | str, batch_id: int) -> dict[str, Any]:
    """Verify local staging/quarantine/manifest hashes without returning artifact content."""
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_37(conn)
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(batch_id),)).fetchone()
        if batch is None:
            raise ReadOnlyExtractionError("extraction batch not found")
    results = {}
    for label in ("staging", "quarantine", "manifest"):
        rel = batch[f"{label}_path"]
        expected = batch[f"{label}_hash"]
        if not rel or not expected:
            results[label] = {"ok": False, "reason": "artifact_not_materialized"}
            continue
        path = (root_path / str(rel)).resolve()
        runtime = (root_path / ".agents/runtime/data-staging").resolve()
        if runtime not in path.parents:
            results[label] = {"ok": False, "reason": "artifact_path_outside_runtime"}
            continue
        if not path.exists():
            results[label] = {"ok": False, "reason": "artifact_missing"}
            continue
        actual = _sha256_bytes(path.read_bytes())
        results[label] = {"ok": actual == expected, "expected_hash": expected, "actual_hash": actual}
    return {"ok": all(item.get("ok") for item in results.values()), "batch_id": int(batch_id), "artifacts": results, "content_returned": False}


def docs_check_v0212(root: Path | str) -> dict[str, Any]:
    """Validate v0.21.2 version, docs, policy, schema 37, and no TARGET-write policy regression."""
    root_path = Path(root).resolve()
    required = [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        ".agents/docs/READ_ONLY_EXTRACTION_AND_DATA_VALIDATION.md", ".agents/docs/USAGE_V0212.md",
        ".agents/config/read_only_extraction_policy.v0212.json", ".gitignore",
    ]
    missing = [item for item in required if not (root_path / item).exists()]
    version = (root_path / "VERSION").read_text(encoding="utf-8").strip() if (root_path / "VERSION").exists() else None
    try:
        governance = json.loads((root_path / ".agents/config/governance.json").read_text(encoding="utf-8"))
    except Exception:
        governance = {}
    policy = governance.get("read_only_extraction_policy")
    boundary = governance.get("database_boundary_policy") or {}
    mapping = governance.get("schema_mapping_policy") or {}
    schema = sync_read_only_extraction_schema(root_path)
    gitignore = (root_path / ".gitignore").read_text(encoding="utf-8") if (root_path / ".gitignore").exists() else ""
    return {
        "ok": (
            not missing and version == "0.21.2"
            and governance.get("version", governance.get("governance_version")) == "0.21.2"
            and isinstance(policy, dict) and schema["ok"]
            and boundary.get("target_data_write_enabled") is False
            and mapping.get("target_data_write_enabled") is False
            and policy.get("target_data_write_enabled") is False
            and ".agents/runtime/data-staging/" in gitignore
        ),
        "missing": missing,
        "version": version,
        "governance_version": governance.get("version", governance.get("governance_version")),
        "database_schema": schema["schema"],
        "target_data_write_enabled": False,
        "source_select_only": True,
        "staging_git_ignored": ".agents/runtime/data-staging/" in gitignore,
    }
