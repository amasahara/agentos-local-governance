"""
File: .agents/agentos/schema_mapping.py

Purpose:
    Implement AgentOS v0.21.1 Target Schema Contract and Cross-DB Field Mapping.

Responsibilities:
    - Store metadata-only schema snapshots for registered SOURCE/TARGET connections.
    - Require a TARGET schema snapshot before authoring a target contract.
    - Validate target contracts against the actual registered TARGET snapshot.
    - Version and human-approve immutable target schema contracts.
    - Map SOURCE fields directionally into an approved TARGET contract.
    - Compute canonical type compatibility and require explicit transformations when needed.
    - Bind mappings to source snapshot and target contract hashes so schema drift makes mappings stale.
    - Provide read-only lexical/type mapping suggestions without persisting them.
    - Keep all data extraction and TARGET INSERT disabled until later roadmap nodes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable
import uuid
from contextlib import contextmanager

from .db import connect as central_connect
from .governance_enforcement import governed_mutation, mirror_domain_event


from .database_boundary import DatabaseBoundaryError, migration_35

MIGRATION_VERSION = 36
SNAPSHOT_SCHEMA_VERSION = 1
TARGET_CONTRACT_SCHEMA_VERSION = 1
CANONICAL_TYPES = {
    "string", "integer", "decimal", "float", "boolean", "date", "datetime", "time",
    "uuid", "json", "binary", "text", "code", "other",
}
MATCH_METHODS = {"manual", "lexical", "dictionary", "semantic", "human"}
MAPPING_STATUSES = {"proposed", "confirmed", "rejected", "stale"}
CONTRACT_STATUSES = {"draft", "reviewed", "approved", "superseded"}
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#@.-]{0,127}$")

# Canonical type families that can be transformed without semantic reinterpretation.
COERCIBLE_TYPES = {
    ("string", "text"), ("text", "string"), ("code", "string"), ("string", "code"),
    ("integer", "decimal"), ("integer", "float"), ("decimal", "float"), ("float", "decimal"),
    ("date", "datetime"), ("datetime", "date"), ("uuid", "string"), ("string", "uuid"),
    ("boolean", "integer"), ("integer", "boolean"), ("json", "text"), ("text", "json"),
}


class SchemaMappingError(RuntimeError):
    """Raised when a v0.21.1 schema-contract or mapping invariant is violated."""


def utc_now() -> str:
    """Return current UTC time as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for hashing and evidence."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    """Return SHA-256 over canonical JSON."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _db_path(root: Path | str) -> Path:
    """Return active AgentOS state database path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


@contextmanager
def _connect(root: Path | str):
    """Open the shared AgentOS governance database connection."""
    with central_connect(Path(root)) as conn:
        yield conn


def migration_36(conn: sqlite3.Connection) -> None:
    """Apply additive schema 36 for metadata-only schema contracts and field mapping."""
    migration_35(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS db_schema_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_uuid TEXT NOT NULL UNIQUE,
            connection_id INTEGER NOT NULL,
            connection_role TEXT NOT NULL,
            engine TEXT NOT NULL,
            manifest_version INTEGER NOT NULL,
            manifest_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            table_count INTEGER NOT NULL,
            column_count INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            captured_by TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            FOREIGN KEY(connection_id) REFERENCES db_connections(id)
        );
        CREATE TABLE IF NOT EXISTS target_schema_contracts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            target_connection_id INTEGER NOT NULL,
            target_snapshot_id INTEGER NOT NULL,
            contract_version INTEGER NOT NULL,
            contract_schema_version INTEGER NOT NULL,
            contract_json TEXT NOT NULL,
            contract_hash TEXT NOT NULL,
            target_snapshot_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(target_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(target_snapshot_id) REFERENCES db_schema_snapshots(id),
            UNIQUE(consolidation_id, contract_version)
        );
        CREATE TABLE IF NOT EXISTS db_field_mappings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapping_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_column TEXT NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_column TEXT NOT NULL,
            source_canonical_type TEXT NOT NULL,
            target_canonical_type TEXT NOT NULL,
            type_compatibility TEXT NOT NULL,
            transform_rule TEXT,
            transform_output_type TEXT,
            validation_rule_json TEXT,
            confidence REAL NOT NULL,
            match_method TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            mapping_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            confirmed_by TEXT,
            confirmed_at TEXT,
            rejected_by TEXT,
            rejected_at TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(source_connection_id) REFERENCES db_connections(id),
            FOREIGN KEY(source_snapshot_id) REFERENCES db_schema_snapshots(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id),
            UNIQUE(consolidation_id, source_snapshot_id, target_contract_id, source_schema, source_table, source_column, target_schema, target_table, target_column)
        );
        CREATE TABLE IF NOT EXISTS db_schema_mapping_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER,
            snapshot_id INTEGER,
            contract_id INTEGER,
            mapping_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_db_schema_snapshots_connection
            ON db_schema_snapshots(connection_id, status, captured_at);
        CREATE INDEX IF NOT EXISTS idx_target_schema_contracts_consolidation
            ON target_schema_contracts(consolidation_id, status, contract_version);
        CREATE INDEX IF NOT EXISTS idx_db_field_mappings_plan
            ON db_field_mappings(consolidation_id, target_contract_id, source_connection_id, status);
        """
    )


def sync_schema_mapping_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema 36 and report required v0.21.1 tables."""
    required = {"db_schema_snapshots", "target_schema_contracts", "db_field_mappings", "db_schema_mapping_events"}
    with _connect(root) as conn:
        migration_36(conn)
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"ok": required <= tables, "schema": MIGRATION_VERSION, "tables": sorted(required)}


def _event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    payload: Any,
    consolidation_id: int | None = None,
    snapshot_id: int | None = None,
    contract_id: int | None = None,
    mapping_id: int | None = None,
) -> None:
    """Append local evidence for v0.21.1 state changes."""
    mirror = mirror_domain_event(event_type, payload)
    conn.execute(
        """INSERT INTO db_schema_mapping_events(
            consolidation_id,snapshot_id,contract_id,mapping_id,event_type,event_json,created_at,governed_operation_id,external_event_hash
        ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (consolidation_id, snapshot_id, contract_id, mapping_id, event_type, _canonical_json(payload), utc_now(), mirror["governed_operation_id"], mirror["external_event_hash"]),
    )


def _require_identifier(value: str, label: str) -> str:
    """Validate a catalog identifier without interpreting SQL."""
    text = str(value).strip()
    if not text or not SAFE_IDENTIFIER.fullmatch(text):
        raise SchemaMappingError(f"invalid {label}: {value!r}")
    return text


def _canonical_type(value: str) -> str:
    """Validate a canonical type used across heterogeneous engines."""
    text = str(value).strip().lower()
    if text not in CANONICAL_TYPES:
        raise SchemaMappingError(f"unsupported canonical_type: {value}")
    return text


def _validate_no_secret_payload(value: Any) -> None:
    """Reject likely raw credentials in mapping/contract evidence payloads."""
    text = _canonical_json(value).lower()
    forbidden = ("password=", "pwd=", "authorization:", "bearer ", "api_key=", "apikey=", "postgresql://", "mysql://", "oracle://", "sqlserver://")
    if any(token in text for token in forbidden):
        raise SchemaMappingError("metadata/evidence appears to contain a raw credential or DSN")


def _normalize_column(column: dict[str, Any]) -> dict[str, Any]:
    """Normalize one schema-manifest column without reading record data."""
    if not isinstance(column, dict):
        raise SchemaMappingError("column entries must be objects")
    name = _require_identifier(column.get("name", ""), "column name")
    canonical_type = _canonical_type(column.get("canonical_type", ""))
    native_type = str(column.get("native_type", "")).strip()
    if not native_type:
        raise SchemaMappingError(f"native_type is required for column {name}")
    return {
        "name": name,
        "native_type": native_type,
        "canonical_type": canonical_type,
        "nullable": bool(column.get("nullable", True)),
        "ordinal": int(column.get("ordinal", 0)),
    }


def normalize_schema_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize metadata-only schema manifest input.

    Args:
        manifest: Structured catalog metadata. Record values are not accepted.

    Returns:
        Deterministic manifest containing schemas/tables/columns/keys only.
    """
    if not isinstance(manifest, dict):
        raise SchemaMappingError("schema manifest must be an object")
    _validate_no_secret_payload(manifest)
    if int(manifest.get("manifest_version", 0)) != SNAPSHOT_SCHEMA_VERSION:
        raise SchemaMappingError(f"manifest_version must be {SNAPSHOT_SCHEMA_VERSION}")
    raw_tables = manifest.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise SchemaMappingError("schema manifest requires at least one table")
    tables: list[dict[str, Any]] = []
    seen_tables: set[tuple[str, str]] = set()
    for raw in raw_tables:
        if not isinstance(raw, dict):
            raise SchemaMappingError("table entries must be objects")
        schema = _require_identifier(raw.get("schema", "public"), "schema name")
        name = _require_identifier(raw.get("name", ""), "table name")
        key = (schema.lower(), name.lower())
        if key in seen_tables:
            raise SchemaMappingError(f"duplicate table in manifest: {schema}.{name}")
        seen_tables.add(key)
        raw_columns = raw.get("columns")
        if not isinstance(raw_columns, list) or not raw_columns:
            raise SchemaMappingError(f"table {schema}.{name} requires columns")
        columns = [_normalize_column(item) for item in raw_columns]
        column_names = [item["name"].lower() for item in columns]
        if len(column_names) != len(set(column_names)):
            raise SchemaMappingError(f"duplicate column in table {schema}.{name}")
        primary_key = [str(x) for x in raw.get("primary_key", [])]
        for item in primary_key:
            if item.lower() not in column_names:
                raise SchemaMappingError(f"primary key column not found: {schema}.{name}.{item}")
        unique_keys: list[list[str]] = []
        for group in raw.get("unique_keys", []):
            if not isinstance(group, list) or not group:
                raise SchemaMappingError("unique_keys entries must be non-empty lists")
            normalized_group = [str(x) for x in group]
            if any(x.lower() not in column_names for x in normalized_group):
                raise SchemaMappingError(f"unique key references missing column in {schema}.{name}")
            unique_keys.append(normalized_group)
        tables.append({
            "schema": schema,
            "name": name,
            "columns": sorted(columns, key=lambda c: (c["ordinal"], c["name"].lower())),
            "primary_key": primary_key,
            "unique_keys": unique_keys,
        })
    return {"manifest_version": SNAPSHOT_SCHEMA_VERSION, "tables": sorted(tables, key=lambda t: (t["schema"].lower(), t["name"].lower()))}


def _table_index(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Build case-insensitive table index for normalized manifest/contract data."""
    return {(t["schema"].lower(), t["name"].lower()): t for t in manifest.get("tables", [])}


def _column_index(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build case-insensitive column index for one table."""
    return {c["name"].lower(): c for c in table.get("columns", [])}


@governed_mutation("db.schema.snapshot.register")
def register_schema_snapshot(
    root: Path | str,
    *,
    connection_id: int,
    manifest: dict[str, Any],
    captured_by: str,
) -> dict[str, Any]:
    """Register a metadata-only schema snapshot for a registered database connection.

    The function never opens the external database. Metadata must already have been
    collected through an operator-controlled catalog process. Registering a newer
    SOURCE snapshot marks mappings bound to older snapshots of that SOURCE as stale.
    """
    if not captured_by.strip():
        raise SchemaMappingError("captured_by is required")
    normalized = normalize_schema_manifest(manifest)
    manifest_hash = _sha256_json(normalized)
    table_count = len(normalized["tables"])
    column_count = sum(len(t["columns"]) for t in normalized["tables"])
    now = utc_now()
    with _connect(root) as conn:
        migration_36(conn)
        db = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(connection_id),)).fetchone()
        if db is None:
            raise SchemaMappingError("connection not found")
        if db["status"] != "active":
            raise SchemaMappingError("connection is not active")
        if db["role"] == "SOURCE" and not int(db["readonly_verified"]):
            raise SchemaMappingError("SOURCE must be read-only verified before schema snapshot registration")
        previous = conn.execute(
            "SELECT id,snapshot_hash FROM db_schema_snapshots WHERE connection_id=? AND status='active' ORDER BY id DESC",
            (int(connection_id),),
        ).fetchall()
        if previous and str(previous[0]["snapshot_hash"]) == manifest_hash:
            existing_id = int(previous[0]["id"])
            _event(conn, event_type="schema_snapshot_unchanged", snapshot_id=existing_id, payload={
                "connection_id": int(connection_id), "snapshot_hash": manifest_hash, "record_data_read": False,
            })
            row = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (existing_id,)).fetchone()
            value = dict(row)
            value["manifest"] = json.loads(value.pop("manifest_json"))
            return {"ok": True, "snapshot": value, "unchanged": True}
        cur = conn.execute(
            """INSERT INTO db_schema_snapshots(
                snapshot_uuid,connection_id,connection_role,engine,manifest_version,manifest_json,snapshot_hash,
                table_count,column_count,status,captured_by,captured_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), int(connection_id), str(db["role"]), str(db["engine"]), SNAPSHOT_SCHEMA_VERSION,
             _canonical_json(normalized), manifest_hash, table_count, column_count, "active", captured_by.strip(), now),
        )
        sid = int(cur.lastrowid)
        if previous:
            old_ids = [int(row["id"]) for row in previous]
            conn.executemany("UPDATE db_schema_snapshots SET status='superseded' WHERE id=?", [(x,) for x in old_ids])
            placeholders = ",".join("?" for _ in old_ids)
            if db["role"] == "SOURCE":
                conn.execute(
                    f"UPDATE db_field_mappings SET status='stale' WHERE source_snapshot_id IN ({placeholders}) AND status IN ('proposed','confirmed')",
                    old_ids,
                )
            else:
                contract_rows = conn.execute(
                    f"SELECT id FROM target_schema_contracts WHERE target_snapshot_id IN ({placeholders}) AND status IN ('draft','reviewed','approved')",
                    old_ids,
                ).fetchall()
                contract_ids = [int(row["id"]) for row in contract_rows]
                if contract_ids:
                    cp = ",".join("?" for _ in contract_ids)
                    conn.execute(f"UPDATE target_schema_contracts SET status='superseded' WHERE id IN ({cp})", contract_ids)
                    conn.execute(f"UPDATE db_field_mappings SET status='stale' WHERE target_contract_id IN ({cp}) AND status IN ('proposed','confirmed')", contract_ids)
        _event(conn, event_type="schema_snapshot_registered", snapshot_id=sid, payload={
            "connection_id": int(connection_id), "role": db["role"], "snapshot_hash": manifest_hash,
            "table_count": table_count, "column_count": column_count, "record_data_read": False,
        })
    return get_schema_snapshot(root, sid)


def get_schema_snapshot(root: Path | str, snapshot_id: int) -> dict[str, Any]:
    """Return one local metadata-only schema snapshot."""
    with _connect(root) as conn:
        migration_36(conn)
        row = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(snapshot_id),)).fetchone()
        if row is None:
            raise SchemaMappingError("schema snapshot not found")
    value = dict(row)
    value["manifest"] = json.loads(value.pop("manifest_json"))
    return {"ok": True, "snapshot": value}


def _normalize_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Validate target contract syntax before validating it against TARGET snapshot."""
    if not isinstance(contract, dict):
        raise SchemaMappingError("target contract must be an object")
    _validate_no_secret_payload(contract)
    if int(contract.get("contract_schema_version", 0)) != TARGET_CONTRACT_SCHEMA_VERSION:
        raise SchemaMappingError(f"contract_schema_version must be {TARGET_CONTRACT_SCHEMA_VERSION}")
    raw_tables = contract.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise SchemaMappingError("target contract requires at least one table")
    tables: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_tables:
        if not isinstance(raw, dict):
            raise SchemaMappingError("target table entries must be objects")
        schema = _require_identifier(raw.get("schema", "public"), "target schema name")
        name = _require_identifier(raw.get("name", ""), "target table name")
        key = (schema.lower(), name.lower())
        if key in seen:
            raise SchemaMappingError(f"duplicate target table: {schema}.{name}")
        seen.add(key)
        columns: list[dict[str, Any]] = []
        raw_columns = raw.get("columns")
        if not isinstance(raw_columns, list) or not raw_columns:
            raise SchemaMappingError(f"target table {schema}.{name} requires columns")
        col_seen: set[str] = set()
        for raw_col in raw_columns:
            if not isinstance(raw_col, dict):
                raise SchemaMappingError("target contract columns must be objects")
            col_name = _require_identifier(raw_col.get("name", ""), "target column name")
            if col_name.lower() in col_seen:
                raise SchemaMappingError(f"duplicate target column: {schema}.{name}.{col_name}")
            col_seen.add(col_name.lower())
            columns.append({
                "name": col_name,
                "canonical_type": _canonical_type(raw_col.get("canonical_type", "")),
                "nullable": bool(raw_col.get("nullable", True)),
                "required": bool(raw_col.get("required", False)),
                "sensitive": bool(raw_col.get("sensitive", False)),
            })
        primary_key = [str(x) for x in raw.get("primary_key", [])]
        business_keys = [[str(x) for x in group] for group in raw.get("business_keys", [])]
        if any(x.lower() not in col_seen for x in primary_key):
            raise SchemaMappingError(f"target primary key references missing column in {schema}.{name}")
        for group in business_keys:
            if not group or any(x.lower() not in col_seen for x in group):
                raise SchemaMappingError(f"target business key references missing column in {schema}.{name}")
        tables.append({
            "schema": schema, "name": name, "columns": sorted(columns, key=lambda c: c["name"].lower()),
            "primary_key": primary_key, "business_keys": business_keys,
        })
    return {"contract_schema_version": TARGET_CONTRACT_SCHEMA_VERSION, "tables": sorted(tables, key=lambda t: (t["schema"].lower(), t["name"].lower()))}


def _validate_contract_against_snapshot(contract: dict[str, Any], snapshot: dict[str, Any]) -> None:
    """Require every contract table/column to exist in TARGET catalog snapshot with matching canonical type."""
    snapshot_tables = _table_index(snapshot)
    for table in contract["tables"]:
        key = (table["schema"].lower(), table["name"].lower())
        actual = snapshot_tables.get(key)
        if actual is None:
            raise SchemaMappingError(f"target contract table absent from TARGET snapshot: {table['schema']}.{table['name']}")
        actual_cols = _column_index(actual)
        for col in table["columns"]:
            actual_col = actual_cols.get(col["name"].lower())
            if actual_col is None:
                raise SchemaMappingError(f"target contract column absent from TARGET snapshot: {table['schema']}.{table['name']}.{col['name']}")
            if actual_col["canonical_type"] != col["canonical_type"]:
                raise SchemaMappingError(
                    f"target contract type mismatch for {table['schema']}.{table['name']}.{col['name']}: "
                    f"snapshot={actual_col['canonical_type']} contract={col['canonical_type']}"
                )


@governed_mutation("db.target_contract.create")
def create_target_contract(
    root: Path | str,
    *,
    consolidation_id: int,
    target_snapshot_id: int,
    contract: dict[str, Any],
    created_by: str,
) -> dict[str, Any]:
    """Create a draft target schema contract backed by the consolidation's TARGET snapshot."""
    if not created_by.strip():
        raise SchemaMappingError("created_by is required")
    normalized = _normalize_contract(contract)
    contract_hash = _sha256_json(normalized)
    now = utc_now()
    with _connect(root) as conn:
        migration_36(conn)
        plan = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(consolidation_id),)).fetchone()
        if plan is None:
            raise SchemaMappingError("database consolidation not found")
        target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(plan["target_connection_id"]),)).fetchone()
        snap = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(target_snapshot_id),)).fetchone()
        if snap is None:
            raise SchemaMappingError("TARGET schema snapshot not found")
        if int(snap["connection_id"]) != int(plan["target_connection_id"]) or snap["connection_role"] != "TARGET":
            raise SchemaMappingError("target_snapshot_id must belong to the consolidation TARGET")
        if snap["status"] != "active":
            raise SchemaMappingError("TARGET schema snapshot must be active")
        snapshot_manifest = json.loads(snap["manifest_json"])
        _validate_contract_against_snapshot(normalized, snapshot_manifest)
        next_version = int(conn.execute(
            "SELECT COALESCE(MAX(contract_version),0)+1 FROM target_schema_contracts WHERE consolidation_id=?",
            (int(consolidation_id),),
        ).fetchone()[0])
        cur = conn.execute(
            """INSERT INTO target_schema_contracts(
                contract_uuid,consolidation_id,target_connection_id,target_snapshot_id,contract_version,contract_schema_version,
                contract_json,contract_hash,target_snapshot_hash,status,created_by,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), int(consolidation_id), int(plan["target_connection_id"]), int(target_snapshot_id), next_version,
             TARGET_CONTRACT_SCHEMA_VERSION, _canonical_json(normalized), contract_hash, str(snap["snapshot_hash"]), "draft", created_by.strip(), now),
        )
        cid = int(cur.lastrowid)
        _event(conn, event_type="target_contract_created", consolidation_id=int(consolidation_id), snapshot_id=int(target_snapshot_id), contract_id=cid,
               payload={"contract_version": next_version, "contract_hash": contract_hash, "target_snapshot_hash": str(snap["snapshot_hash"]), "target_write_enabled": False})
    return get_target_contract(root, cid)


@governed_mutation("db.target_contract.review")
def review_target_contract(root: Path | str, contract_id: int, *, reviewed_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Record human review of a draft target schema contract."""
    if not human_confirmed or not reviewed_by.strip():
        raise SchemaMappingError("explicit human confirmation and reviewed_by are required")
    with _connect(root) as conn:
        migration_36(conn)
        row = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(contract_id),)).fetchone()
        if row is None:
            raise SchemaMappingError("target contract not found")
        if row["status"] != "draft":
            raise SchemaMappingError("only draft target contracts can be reviewed")
        current_snap = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(row["target_snapshot_id"]),)).fetchone()
        if current_snap is None or current_snap["status"] != "active" or current_snap["snapshot_hash"] != row["target_snapshot_hash"]:
            raise SchemaMappingError("target schema snapshot changed; create a new contract")
        now = utc_now()
        conn.execute("UPDATE target_schema_contracts SET status='reviewed',reviewed_by=?,reviewed_at=? WHERE id=?", (reviewed_by.strip(), now, int(contract_id)))
        _event(conn, event_type="target_contract_reviewed", consolidation_id=int(row["consolidation_id"]), contract_id=int(contract_id), payload={"reviewed_by": reviewed_by.strip(), "contract_hash": row["contract_hash"]})
    return get_target_contract(root, int(contract_id))


@governed_mutation("db.target_contract.approve")
def approve_target_contract(root: Path | str, contract_id: int, *, approved_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Approve one reviewed target contract and supersede older approved contracts for the consolidation."""
    if not human_confirmed or not approved_by.strip():
        raise SchemaMappingError("explicit human confirmation and approved_by are required")
    with _connect(root) as conn:
        migration_36(conn)
        row = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(contract_id),)).fetchone()
        if row is None:
            raise SchemaMappingError("target contract not found")
        if row["status"] != "reviewed":
            raise SchemaMappingError("target contract must be reviewed before approval")
        snap = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(row["target_snapshot_id"]),)).fetchone()
        if snap is None or snap["status"] != "active" or snap["snapshot_hash"] != row["target_snapshot_hash"]:
            raise SchemaMappingError("target schema snapshot changed; approval blocked")
        now = utc_now()
        old = conn.execute(
            "SELECT id,contract_hash FROM target_schema_contracts WHERE consolidation_id=? AND status='approved' AND id<>?",
            (int(row["consolidation_id"]), int(contract_id)),
        ).fetchall()
        for prior in old:
            conn.execute("UPDATE target_schema_contracts SET status='superseded' WHERE id=?", (int(prior["id"]),))
            conn.execute("UPDATE db_field_mappings SET status='stale' WHERE target_contract_id=? AND status IN ('proposed','confirmed')", (int(prior["id"]),))
        conn.execute("UPDATE target_schema_contracts SET status='approved',approved_by=?,approved_at=? WHERE id=?", (approved_by.strip(), now, int(contract_id)))
        _event(conn, event_type="target_contract_approved", consolidation_id=int(row["consolidation_id"]), contract_id=int(contract_id), payload={"approved_by": approved_by.strip(), "contract_hash": row["contract_hash"], "target_write_enabled": False})
    return get_target_contract(root, int(contract_id))


def get_target_contract(root: Path | str, contract_id: int) -> dict[str, Any]:
    """Return a target schema contract and immutable hashes."""
    with _connect(root) as conn:
        migration_36(conn)
        row = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(contract_id),)).fetchone()
        if row is None:
            raise SchemaMappingError("target contract not found")
    value = dict(row)
    value["contract"] = json.loads(value.pop("contract_json"))
    return {"ok": True, "target_contract": value}


def type_compatibility(source_type: str, target_type: str) -> str:
    """Classify canonical source/target type compatibility."""
    src = _canonical_type(source_type)
    dst = _canonical_type(target_type)
    if src == dst:
        return "exact"
    if (src, dst) in COERCIBLE_TYPES:
        return "coercible"
    return "incompatible"


def _find_source_column(snapshot_manifest: dict[str, Any], schema: str, table: str, column: str) -> dict[str, Any]:
    tables = _table_index(snapshot_manifest)
    table_obj = tables.get((schema.lower(), table.lower()))
    if table_obj is None:
        raise SchemaMappingError(f"source table not found in snapshot: {schema}.{table}")
    col = _column_index(table_obj).get(column.lower())
    if col is None:
        raise SchemaMappingError(f"source column not found in snapshot: {schema}.{table}.{column}")
    return col


def _find_target_column(contract: dict[str, Any], schema: str, table: str, column: str) -> dict[str, Any]:
    tables = _table_index(contract)
    table_obj = tables.get((schema.lower(), table.lower()))
    if table_obj is None:
        raise SchemaMappingError(f"target table not found in approved contract: {schema}.{table}")
    col = _column_index(table_obj).get(column.lower())
    if col is None:
        raise SchemaMappingError(f"target column not found in approved contract: {schema}.{table}.{column}")
    return col


@governed_mutation("db.field_mapping.add")
def add_field_mapping(
    root: Path | str,
    *,
    consolidation_id: int,
    source_snapshot_id: int,
    target_contract_id: int,
    source_schema: str,
    source_table: str,
    source_column: str,
    target_schema: str,
    target_table: str,
    target_column: str,
    confidence: float,
    match_method: str,
    evidence: dict[str, Any],
    created_by: str,
    transform_rule: str | None = None,
    transform_output_type: str | None = None,
    validation_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a proposed directional SOURCE-field -> TARGET-field mapping bound to immutable hashes."""
    if not created_by.strip():
        raise SchemaMappingError("created_by is required")
    method = match_method.strip().lower()
    if method not in MATCH_METHODS:
        raise SchemaMappingError(f"unsupported match_method: {match_method}")
    score = float(confidence)
    if not 0.0 <= score <= 1.0:
        raise SchemaMappingError("confidence must be between 0 and 1")
    if not isinstance(evidence, dict) or not evidence:
        raise SchemaMappingError("mapping evidence is required")
    _validate_no_secret_payload(evidence)
    if validation_rule is not None:
        _validate_no_secret_payload(validation_rule)
    src_schema = _require_identifier(source_schema, "source schema")
    src_table = _require_identifier(source_table, "source table")
    src_column = _require_identifier(source_column, "source column")
    dst_schema = _require_identifier(target_schema, "target schema")
    dst_table = _require_identifier(target_table, "target table")
    dst_column = _require_identifier(target_column, "target column")
    transform = transform_rule.strip() if transform_rule else None
    output_type = _canonical_type(transform_output_type) if transform_output_type else None
    with _connect(root) as conn:
        migration_36(conn)
        plan = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(consolidation_id),)).fetchone()
        if plan is None:
            raise SchemaMappingError("database consolidation not found")
        snap = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(source_snapshot_id),)).fetchone()
        if snap is None or snap["connection_role"] != "SOURCE" or snap["status"] != "active":
            raise SchemaMappingError("source_snapshot_id must reference an active SOURCE snapshot")
        registered = conn.execute(
            "SELECT 1 FROM db_consolidation_sources WHERE consolidation_id=? AND source_connection_id=?",
            (int(consolidation_id), int(snap["connection_id"])),
        ).fetchone()
        if registered is None:
            raise SchemaMappingError("SOURCE snapshot connection is not registered in this consolidation")
        contract = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(target_contract_id),)).fetchone()
        if contract is None or int(contract["consolidation_id"]) != int(consolidation_id):
            raise SchemaMappingError("target contract does not belong to this consolidation")
        if contract["status"] != "approved":
            raise SchemaMappingError("field mappings require an approved target schema contract")
        source_manifest = json.loads(snap["manifest_json"])
        target_contract = json.loads(contract["contract_json"])
        src_col = _find_source_column(source_manifest, src_schema, src_table, src_column)
        dst_col = _find_target_column(target_contract, dst_schema, dst_table, dst_column)
        compatibility = type_compatibility(src_col["canonical_type"], dst_col["canonical_type"])
        if compatibility == "coercible" and not transform:
            raise SchemaMappingError("coercible field mapping requires an explicit transform_rule")
        if compatibility == "incompatible":
            if not transform or output_type != dst_col["canonical_type"]:
                raise SchemaMappingError("incompatible field mapping requires transform_rule and transform_output_type equal to target type")
        if transform and output_type is None:
            output_type = dst_col["canonical_type"]
        mapping_payload = {
            "consolidation_id": int(consolidation_id),
            "source_snapshot_hash": str(snap["snapshot_hash"]),
            "target_contract_hash": str(contract["contract_hash"]),
            "source": [src_schema, src_table, src_column, src_col["canonical_type"]],
            "target": [dst_schema, dst_table, dst_column, dst_col["canonical_type"]],
            "type_compatibility": compatibility,
            "transform_rule": transform,
            "transform_output_type": output_type,
            "validation_rule": validation_rule,
            "match_method": method,
            "evidence": evidence,
        }
        mapping_hash = _sha256_json(mapping_payload)
        try:
            cur = conn.execute(
                """INSERT INTO db_field_mappings(
                    mapping_uuid,consolidation_id,source_connection_id,source_snapshot_id,target_contract_id,
                    source_schema,source_table,source_column,target_schema,target_table,target_column,
                    source_canonical_type,target_canonical_type,type_compatibility,transform_rule,transform_output_type,
                    validation_rule_json,confidence,match_method,evidence_json,source_snapshot_hash,target_contract_hash,
                    mapping_hash,status,created_by,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), int(consolidation_id), int(snap["connection_id"]), int(source_snapshot_id), int(target_contract_id),
                 src_schema, src_table, src_column, dst_schema, dst_table, dst_column,
                 src_col["canonical_type"], dst_col["canonical_type"], compatibility, transform, output_type,
                 _canonical_json(validation_rule) if validation_rule is not None else None, score, method, _canonical_json(evidence),
                 str(snap["snapshot_hash"]), str(contract["contract_hash"]), mapping_hash, "proposed", created_by.strip(), utc_now()),
            )
        except sqlite3.IntegrityError as exc:
            raise SchemaMappingError("this exact field mapping already exists for the bound snapshot/contract") from exc
        mid = int(cur.lastrowid)
        _event(conn, event_type="field_mapping_proposed", consolidation_id=int(consolidation_id), snapshot_id=int(source_snapshot_id), contract_id=int(target_contract_id), mapping_id=mid,
               payload={"mapping_hash": mapping_hash, "type_compatibility": compatibility, "confidence": score, "record_data_read": False})
    return get_field_mapping(root, mid)


def _mapping_is_current(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Return whether a mapping still references active immutable inputs."""
    snap = conn.execute("SELECT status,snapshot_hash FROM db_schema_snapshots WHERE id=?", (int(row["source_snapshot_id"]),)).fetchone()
    contract = conn.execute("SELECT status,contract_hash FROM target_schema_contracts WHERE id=?", (int(row["target_contract_id"]),)).fetchone()
    return bool(
        snap and contract and snap["status"] == "active" and contract["status"] == "approved"
        and snap["snapshot_hash"] == row["source_snapshot_hash"] and contract["contract_hash"] == row["target_contract_hash"]
    )


@governed_mutation("db.field_mapping.confirm")
def confirm_field_mapping(root: Path | str, mapping_id: int, *, confirmed_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Human-confirm one proposed field mapping after re-verifying snapshot/contract hashes."""
    if not human_confirmed or not confirmed_by.strip():
        raise SchemaMappingError("explicit human confirmation and confirmed_by are required")
    with _connect(root) as conn:
        migration_36(conn)
        row = conn.execute("SELECT * FROM db_field_mappings WHERE id=?", (int(mapping_id),)).fetchone()
        if row is None:
            raise SchemaMappingError("field mapping not found")
        if row["status"] != "proposed":
            raise SchemaMappingError("only proposed mappings can be confirmed")
        if not _mapping_is_current(conn, row):
            conn.execute("UPDATE db_field_mappings SET status='stale' WHERE id=?", (int(mapping_id),))
            raise SchemaMappingError("mapping inputs are stale; create a new mapping")
        now = utc_now()
        conn.execute("UPDATE db_field_mappings SET status='confirmed',confirmed_by=?,confirmed_at=? WHERE id=?", (confirmed_by.strip(), now, int(mapping_id)))
        _event(conn, event_type="field_mapping_confirmed", consolidation_id=int(row["consolidation_id"]), snapshot_id=int(row["source_snapshot_id"]), contract_id=int(row["target_contract_id"]), mapping_id=int(mapping_id), payload={"confirmed_by": confirmed_by.strip(), "mapping_hash": row["mapping_hash"]})
    return get_field_mapping(root, int(mapping_id))


@governed_mutation("db.field_mapping.reject")
def reject_field_mapping(root: Path | str, mapping_id: int, *, rejected_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Human-reject a proposed field mapping."""
    if not human_confirmed or not rejected_by.strip():
        raise SchemaMappingError("explicit human confirmation and rejected_by are required")
    with _connect(root) as conn:
        migration_36(conn)
        row = conn.execute("SELECT * FROM db_field_mappings WHERE id=?", (int(mapping_id),)).fetchone()
        if row is None:
            raise SchemaMappingError("field mapping not found")
        if row["status"] not in {"proposed", "confirmed"}:
            raise SchemaMappingError("mapping cannot be rejected from its current status")
        now = utc_now()
        conn.execute("UPDATE db_field_mappings SET status='rejected',rejected_by=?,rejected_at=? WHERE id=?", (rejected_by.strip(), now, int(mapping_id)))
        _event(conn, event_type="field_mapping_rejected", consolidation_id=int(row["consolidation_id"]), mapping_id=int(mapping_id), payload={"rejected_by": rejected_by.strip(), "mapping_hash": row["mapping_hash"]})
    return get_field_mapping(root, int(mapping_id))


def _row_to_mapping(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["evidence"] = json.loads(value.pop("evidence_json"))
    raw_validation = value.pop("validation_rule_json")
    value["validation_rule"] = json.loads(raw_validation) if raw_validation else None
    return value


def get_field_mapping(root: Path | str, mapping_id: int) -> dict[str, Any]:
    """Return one field mapping and refresh stale status if necessary."""
    with _connect(root) as conn:
        migration_36(conn)
        row = conn.execute("SELECT * FROM db_field_mappings WHERE id=?", (int(mapping_id),)).fetchone()
        if row is None:
            raise SchemaMappingError("field mapping not found")
        if row["status"] in {"proposed", "confirmed"} and not _mapping_is_current(conn, row):
            conn.execute("UPDATE db_field_mappings SET status='stale' WHERE id=?", (int(mapping_id),))
            row = conn.execute("SELECT * FROM db_field_mappings WHERE id=?", (int(mapping_id),)).fetchone()
    return {"ok": True, "field_mapping": _row_to_mapping(row)}


def list_field_mappings(root: Path | str, consolidation_id: int, *, status: str | None = None) -> dict[str, Any]:
    """List mappings for one consolidation, optionally filtered by status."""
    if status is not None and status not in MAPPING_STATUSES:
        raise SchemaMappingError(f"unsupported mapping status: {status}")
    with _connect(root) as conn:
        migration_36(conn)
        query = "SELECT * FROM db_field_mappings WHERE consolidation_id=?"
        params: list[Any] = [int(consolidation_id)]
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY id"
        rows = conn.execute(query, params).fetchall()
        refreshed: list[sqlite3.Row] = []
        for row in rows:
            if row["status"] in {"proposed", "confirmed"} and not _mapping_is_current(conn, row):
                conn.execute("UPDATE db_field_mappings SET status='stale' WHERE id=?", (int(row["id"]),))
                row = conn.execute("SELECT * FROM db_field_mappings WHERE id=?", (int(row["id"]),)).fetchone()
            refreshed.append(row)
    return {"ok": True, "consolidation_id": int(consolidation_id), "mappings": [_row_to_mapping(row) for row in refreshed]}


def _tokens(value: str) -> set[str]:
    """Tokenize identifiers for local lexical suggestion without an external model."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {item for item in re.split(r"[^A-Za-z0-9]+", text.lower()) if item}


def _lexical_score(source: str, target: str) -> float:
    """Return deterministic token/Jaccard score plus compact-name equality bonus."""
    a = _tokens(source)
    b = _tokens(target)
    compact_a = re.sub(r"[^a-z0-9]", "", source.lower())
    compact_b = re.sub(r"[^a-z0-9]", "", target.lower())
    if compact_a == compact_b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def suggest_field_mappings(
    root: Path | str,
    *,
    consolidation_id: int,
    source_snapshot_id: int,
    target_contract_id: int,
    limit: int = 50,
) -> dict[str, Any]:
    """Compute read-only lexical/type mapping suggestions; do not persist or confirm them."""
    if limit < 1 or limit > 500:
        raise SchemaMappingError("limit must be between 1 and 500")
    with _connect(root) as conn:
        migration_36(conn)
        snap = conn.execute("SELECT * FROM db_schema_snapshots WHERE id=?", (int(source_snapshot_id),)).fetchone()
        contract = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(target_contract_id),)).fetchone()
        if snap is None or snap["connection_role"] != "SOURCE" or snap["status"] != "active":
            raise SchemaMappingError("active SOURCE snapshot required")
        registered = conn.execute("SELECT 1 FROM db_consolidation_sources WHERE consolidation_id=? AND source_connection_id=?", (int(consolidation_id), int(snap["connection_id"]))).fetchone()
        if registered is None:
            raise SchemaMappingError("SOURCE is not registered in consolidation")
        if contract is None or int(contract["consolidation_id"]) != int(consolidation_id) or contract["status"] != "approved":
            raise SchemaMappingError("approved target contract for consolidation required")
        source_manifest = json.loads(snap["manifest_json"])
        target_manifest = json.loads(contract["contract_json"])
    candidates: list[dict[str, Any]] = []
    for st in source_manifest["tables"]:
        for sc in st["columns"]:
            for tt in target_manifest["tables"]:
                table_score = _lexical_score(st["name"], tt["name"])
                for tc in tt["columns"]:
                    compat = type_compatibility(sc["canonical_type"], tc["canonical_type"])
                    if compat == "incompatible":
                        continue
                    column_score = _lexical_score(sc["name"], tc["name"])
                    type_bonus = 0.25 if compat == "exact" else 0.10
                    score = min(1.0, 0.65 * column_score + 0.10 * table_score + type_bonus)
                    if score <= 0.10:
                        continue
                    candidates.append({
                        "source": {"schema": st["schema"], "table": st["name"], "column": sc["name"], "canonical_type": sc["canonical_type"]},
                        "target": {"schema": tt["schema"], "table": tt["name"], "column": tc["name"], "canonical_type": tc["canonical_type"]},
                        "type_compatibility": compat,
                        "confidence": round(score, 4),
                        "match_method": "lexical",
                        "persisted": False,
                        "human_confirmed": False,
                    })
    candidates.sort(key=lambda item: (-item["confidence"], item["source"]["table"], item["source"]["column"], item["target"]["table"], item["target"]["column"]))
    return {"ok": True, "suggestions": candidates[:limit], "advisory_only": True, "record_data_read": False}


def mapping_readiness(root: Path | str, consolidation_id: int, target_contract_id: int) -> dict[str, Any]:
    """Report whether v0.21.1 metadata is ready to be consumed by v0.21.2 extraction."""
    with _connect(root) as conn:
        migration_36(conn)
        contract = conn.execute("SELECT * FROM target_schema_contracts WHERE id=? AND consolidation_id=?", (int(target_contract_id), int(consolidation_id))).fetchone()
        if contract is None:
            raise SchemaMappingError("target contract not found for consolidation")
        sources = conn.execute("SELECT source_connection_id FROM db_consolidation_sources WHERE consolidation_id=? ORDER BY id", (int(consolidation_id),)).fetchall()
        confirmed = conn.execute("SELECT * FROM db_field_mappings WHERE consolidation_id=? AND target_contract_id=? AND status='confirmed'", (int(consolidation_id), int(target_contract_id))).fetchall()
        current_confirmed = [row for row in confirmed if _mapping_is_current(conn, row)]
        mapped_source_ids = {int(row["source_connection_id"]) for row in current_confirmed}
        source_ids = {int(row["source_connection_id"]) for row in sources}
        stale_count = int(conn.execute("SELECT COUNT(*) FROM db_field_mappings WHERE consolidation_id=? AND target_contract_id=? AND status='stale'", (int(consolidation_id), int(target_contract_id))).fetchone()[0])
        contract_json = json.loads(contract["contract_json"])
        required_targets = {
            (table["schema"].lower(), table["name"].lower(), column["name"].lower())
            for table in contract_json["tables"] for column in table["columns"] if column.get("required")
        }
        mapped_targets = {
            (str(row["target_schema"]).lower(), str(row["target_table"]).lower(), str(row["target_column"]).lower())
            for row in current_confirmed
        }
        missing_required = sorted(".".join(item) for item in (required_targets - mapped_targets))
    ready = contract["status"] == "approved" and bool(source_ids) and source_ids <= mapped_source_ids and stale_count == 0 and not missing_required
    return {
        "ok": True,
        "ready_for_v0.21.2": ready,
        "contract_status": contract["status"],
        "source_count": len(source_ids),
        "sources_with_confirmed_mapping": len(source_ids & mapped_source_ids),
        "confirmed_mapping_count": len(current_confirmed),
        "stale_mapping_count": stale_count,
        "required_target_field_count": len(required_targets),
        "unmapped_required_target_fields": missing_required,
        "target_data_write_enabled": False,
    }


def docs_check_v0211(root: Path | str) -> dict[str, Any]:
    """Validate v0.21.1 version, bilingual docs, policy, and schema 36."""
    root_path = Path(root).resolve()
    required = [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        ".agents/docs/TARGET_SCHEMA_CONTRACT_AND_FIELD_MAPPING.md", ".agents/docs/USAGE_V0211.md",
        ".agents/config/schema_mapping_policy.v0211.json",
    ]
    missing = [item for item in required if not (root_path / item).exists()]
    version = (root_path / "VERSION").read_text(encoding="utf-8").strip() if (root_path / "VERSION").exists() else None
    try:
        governance = json.loads((root_path / ".agents/config/governance.json").read_text(encoding="utf-8"))
    except Exception:
        governance = {}
    policy = governance.get("schema_mapping_policy")
    schema = sync_schema_mapping_schema(root_path)
    return {
        "ok": not missing and version == "0.21.1" and governance.get("version", governance.get("governance_version")) == "0.21.1" and isinstance(policy, dict) and schema["ok"],
        "missing": missing,
        "version": version,
        "governance_version": governance.get("version", governance.get("governance_version")),
        "database_schema": schema["schema"],
        "readme_language_links": all((root_path / name).exists() for name in ("README.vi.md", "README.en.md")),
        "target_data_write_enabled": False,
    }
