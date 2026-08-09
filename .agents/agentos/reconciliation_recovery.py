"""
File: .agents/agentos/reconciliation_recovery.py

Purpose:
    Implement AgentOS v0.22.2 reconciliation and fail-closed recovery for
    controlled TARGET inserts without introducing SOURCE writes or arbitrary
    TARGET mutation.

Responsibilities:
    - Build immutable reconciliation plans from v0.22.1 identity-bound insert runs.
    - Re-read only the TARGET rows addressed by approved business keys.
    - Compare keyed whole-row fingerprints instead of persisting business values.
    - Reconcile extraction, identity, insert, and lineage counts/hashes.
    - Classify committed/in_doubt outcomes without automatically changing write state.
    - Require explicit human decisions before resolving uncertain commit outcomes.
    - Allow manual retry only after a read-only `observed_none` reconciliation is confirmed.
    - Recover local lineage idempotently after a committed external write.
    - Persist privacy-safe findings, recovery cases, checkpoints, and evidence hashes.
    - Keep UPDATE/UPSERT/MERGE/DELETE/DDL and SOURCE writes forbidden.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Iterable, Iterator
import uuid
from contextlib import contextmanager

from .db import connect as central_connect
from .governance_enforcement import governed_mutation, mirror_domain_event


from .controlled_target_insert import (
    ControlledTargetInsertError,
    _open_target_connection,
    _quote_identifier,
    migration_38,
)
from .identity_resolution import (
    IdentityResolutionError,
    _lineage_key,
    _normalize,
    finalize_insert_lineage,
    migration_39,
)

MIGRATION_VERSION = 40
RECONCILIATION_VERSION = 1
SUPPORTED_INSERT_STATES = {"committed", "in_doubt", "committing"}
RECONCILIATION_OUTCOMES = {"matched", "observed_none", "observed_partial", "mismatch"}
RECOVERY_CASE_TYPES = {"COMMIT_OUTCOME", "LINEAGE_FINALIZATION"}
MAX_QUERY_KEYS = 200


class ReconciliationRecoveryError(RuntimeError):
    """Raised when a v0.22.2 reconciliation/recovery invariant is violated."""


def utc_now() -> str:
    """Return current UTC time as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    """Convert common database values to deterministic JSON representations."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return {"$binary_sha256": hashlib.sha256(value).hexdigest()}
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for immutable evidence hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _sha256_json(value: Any) -> str:
    """Return SHA-256 of canonical JSON."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return SHA-256 of one local file without loading it fully into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _db_path(root: Path | str) -> Path:
    """Return the active AgentOS local SQLite state path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


@contextmanager
def _connect(root: Path | str):
    """Open the shared AgentOS governance database connection."""
    with central_connect(Path(root)) as conn:
        yield conn


def migration_40(conn: sqlite3.Connection) -> None:
    """Apply additive schema 40 for reconciliation, checkpoints, and recovery evidence."""
    migration_39(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS db_reconciliation_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_uuid TEXT NOT NULL UNIQUE,
            insert_run_id INTEGER NOT NULL,
            reconciliation_version INTEGER NOT NULL,
            plan_json TEXT NOT NULL,
            plan_hash TEXT NOT NULL,
            expected_row_count INTEGER NOT NULL,
            expected_row_set_hash TEXT NOT NULL,
            observed_row_count INTEGER NOT NULL DEFAULT 0,
            observed_row_set_hash TEXT,
            matching_rows INTEGER NOT NULL DEFAULT 0,
            missing_rows INTEGER NOT NULL DEFAULT 0,
            unexpected_rows INTEGER NOT NULL DEFAULT 0,
            duplicate_rows INTEGER NOT NULL DEFAULT 0,
            outcome TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            evidence_hash TEXT,
            started_at TEXT,
            completed_at TEXT,
            failure_reason TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id)
        );
        CREATE TABLE IF NOT EXISTS db_reconciliation_findings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_run_id INTEGER NOT NULL,
            finding_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            count_value INTEGER NOT NULL DEFAULT 0,
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(reconciliation_run_id) REFERENCES db_reconciliation_runs(id)
        );
        CREATE TABLE IF NOT EXISTS db_recovery_cases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_uuid TEXT NOT NULL UNIQUE,
            insert_run_id INTEGER NOT NULL,
            reconciliation_run_id INTEGER,
            case_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            evidence_hash TEXT,
            decision TEXT,
            decided_by TEXT,
            decided_at TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id),
            FOREIGN KEY(reconciliation_run_id) REFERENCES db_reconciliation_runs(id)
        );
        CREATE TABLE IF NOT EXISTS db_recovery_checkpoints(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_run_id INTEGER NOT NULL,
            reconciliation_run_id INTEGER,
            checkpoint_type TEXT NOT NULL,
            checkpoint_hash TEXT NOT NULL,
            checkpoint_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id),
            FOREIGN KEY(reconciliation_run_id) REFERENCES db_reconciliation_runs(id)
        );
        CREATE TABLE IF NOT EXISTS db_recovery_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insert_run_id INTEGER,
            reconciliation_run_id INTEGER,
            recovery_case_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_db_reconciliation_insert
            ON db_reconciliation_runs(insert_run_id,status,id);
        CREATE INDEX IF NOT EXISTS idx_db_reconciliation_findings_run
            ON db_reconciliation_findings(reconciliation_run_id,severity);
        CREATE INDEX IF NOT EXISTS idx_db_recovery_cases_status
            ON db_recovery_cases(status,case_type,insert_run_id);
        CREATE INDEX IF NOT EXISTS idx_db_recovery_checkpoints_insert
            ON db_recovery_checkpoints(insert_run_id,reconciliation_run_id,id);
        """
    )


def sync_reconciliation_recovery_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema 40 and report required v0.22.2 state tables."""
    required = {
        "db_reconciliation_runs", "db_reconciliation_findings", "db_recovery_cases",
        "db_recovery_checkpoints", "db_recovery_events",
    }
    with _connect(root) as conn:
        migration_40(conn)
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"ok": required <= tables, "schema": MIGRATION_VERSION, "tables": sorted(required)}


def _privacy_safe(payload: Any) -> None:
    """Reject event/checkpoint payloads that could persist raw records or credentials."""
    forbidden = {
        "row", "rows", "record", "records", "value", "values", "raw_value",
        "password", "credential", "credential_ref", "dsn", "connection_string",
        "business_key_values", "query_parameters",
    }

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, value in item.items():
                if str(key).lower() in forbidden:
                    raise ReconciliationRecoveryError(f"record/secret-bearing recovery key is forbidden: {key}")
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(payload)


def _event(
    conn: sqlite3.Connection,
    event_type: str,
    payload: dict[str, Any],
    *,
    insert_run_id: int | None = None,
    reconciliation_run_id: int | None = None,
    recovery_case_id: int | None = None,
) -> None:
    """Persist one privacy-safe reconciliation/recovery event."""
    _privacy_safe(payload)
    mirror = mirror_domain_event(event_type, payload)
    conn.execute(
        """INSERT INTO db_recovery_events(
            insert_run_id,reconciliation_run_id,recovery_case_id,event_type,event_json,created_at,governed_operation_id,external_event_hash
        ) VALUES(?,?,?,?,?,?,?,?)""",
        (insert_run_id, reconciliation_run_id, recovery_case_id, event_type, _canonical_json(payload), utc_now(), mirror["governed_operation_id"], mirror["external_event_hash"]),
    )


def _checkpoint(
    conn: sqlite3.Connection,
    *,
    insert_run_id: int,
    reconciliation_run_id: int | None,
    checkpoint_type: str,
    payload: dict[str, Any],
) -> str:
    """Persist an immutable privacy-safe local recovery checkpoint and return its hash."""
    _privacy_safe(payload)
    checkpoint = {
        "checkpoint_type": checkpoint_type,
        "insert_run_id": int(insert_run_id),
        "reconciliation_run_id": reconciliation_run_id,
        "payload": payload,
    }
    digest = _sha256_json(checkpoint)
    conn.execute(
        """INSERT INTO db_recovery_checkpoints(
            insert_run_id,reconciliation_run_id,checkpoint_type,checkpoint_hash,checkpoint_json,created_at
        ) VALUES(?,?,?,?,?,?)""",
        (int(insert_run_id), reconciliation_run_id, checkpoint_type, digest, _canonical_json(checkpoint), utc_now()),
    )
    return digest


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield object records from a local JSONL staging artifact."""
    with path.open("r", encoding="utf-8") as handle:
        for ordinal, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReconciliationRecoveryError(f"reconciliation staging JSON is invalid at row {ordinal}") from exc
            if not isinstance(value, dict):
                raise ReconciliationRecoveryError(f"reconciliation staging row {ordinal} is not an object")
            yield value


def _row_fingerprint(key: bytes, columns: list[str], values: dict[str, Any]) -> str:
    """Create a keyed whole-row fingerprint without persisting the underlying values."""
    payload: list[list[Any]] = []
    for column in columns:
        if column not in values:
            raise ReconciliationRecoveryError(f"TARGET reconciliation row is missing column: {column}")
        payload.append([column, values[column]])
    message = ("reconciliation-row\n" + _canonical_json(payload)).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _exact_key_fingerprint(key: bytes, values: dict[str, Any], fields: list[str], normalizer: str) -> str:
    """Recreate the v0.22.1 keyed exact business-key fingerprint transiently."""
    payload: list[list[Any]] = []
    for field in fields:
        if field not in values:
            raise ReconciliationRecoveryError(f"TARGET reconciliation row is missing business-key field: {field}")
        normalized = _normalize(values[field], normalizer)
        if normalized in (None, ""):
            raise ReconciliationRecoveryError("TARGET reconciliation business key contains null/blank value")
        payload.append([field, normalized])
    message = ("exact-identity\n" + _canonical_json(payload)).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _load_context(conn: sqlite3.Connection, insert_run_id: int, root: Path) -> dict[str, Any]:
    """Load and verify one identity-bound insert run for reconciliation planning."""
    insert = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
    if insert is None:
        raise ReconciliationRecoveryError("target insert run not found")
    if str(insert["status"]) not in SUPPORTED_INSERT_STATES:
        raise ReconciliationRecoveryError("reconciliation requires committed, committing, or in_doubt insert state")
    plan = json.loads(insert["insert_plan_json"])
    resolution_id = plan.get("identity_resolution_run_id")
    if not resolution_id:
        raise ReconciliationRecoveryError("identity-bound v0.22.1 insert plan is required")
    resolution = conn.execute("SELECT * FROM identity_resolution_runs WHERE id=?", (int(resolution_id),)).fetchone()
    if resolution is None or str(resolution["status"]) != "resolved":
        raise ReconciliationRecoveryError("resolved identity run is required")
    policy = conn.execute("SELECT * FROM identity_resolution_policies WHERE id=?", (int(resolution["policy_id"]),)).fetchone()
    if policy is None or str(policy["status"]) != "approved":
        raise ReconciliationRecoveryError("approved identity policy is required")
    target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(insert["target_connection_id"]),)).fetchone()
    if target is None or str(target["role"]) != "TARGET" or str(target["status"]) != "active":
        raise ReconciliationRecoveryError("active TARGET connection is required")
    staging_path = (root / str(insert["staging_path"])).resolve()
    runtime_root = (root / ".agents/runtime/data-staging").resolve()
    try:
        staging_path.relative_to(runtime_root)
    except ValueError as exc:
        raise ReconciliationRecoveryError("insert staging escaped local runtime") from exc
    if not staging_path.is_file() or _sha256_file(staging_path) != str(insert["staging_hash"]):
        raise ReconciliationRecoveryError("insert staging artifact was modified")
    identity_policy = json.loads(policy["policy_json"])
    business_fields = [str(x) for x in identity_policy.get("exact_key_fields") or []]
    if not business_fields:
        raise ReconciliationRecoveryError("approved exact business key is required for TARGET reconciliation")
    columns = [str(x) for x in json.loads(insert["column_order_json"])]
    if any(field not in columns for field in business_fields):
        raise ReconciliationRecoveryError("business key is absent from inserted column set")
    return {
        "insert": insert, "plan": plan, "resolution": resolution, "policy": policy,
        "identity_policy": identity_policy, "target": target, "staging_path": staging_path,
        "columns": columns, "business_fields": business_fields,
    }


def _expected_evidence(context: dict[str, Any], key: bytes) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    """Load expected transient key values plus privacy-safe keyed row/key fingerprints."""
    key_rows: list[dict[str, Any]] = []
    row_fps: Counter[str] = Counter()
    key_fps: Counter[str] = Counter()
    columns = context["columns"]
    business_fields = context["business_fields"]
    normalizer = str(context["identity_policy"]["normalizer"])
    for record in _iter_jsonl(context["staging_path"]):
        values = record.get("values")
        if not isinstance(values, dict):
            raise ReconciliationRecoveryError("deduplicated staging row has no values object")
        key_rows.append({field: values[field] for field in business_fields})
        row_fps[_row_fingerprint(key, columns, values)] += 1
        key_fps[_exact_key_fingerprint(key, values, business_fields, normalizer)] += 1
    if sum(row_fps.values()) != int(context["insert"]["row_count"]):
        raise ReconciliationRecoveryError("reconciliation staging row count drift")
    return key_rows, row_fps, key_fps


@governed_mutation("db.reconciliation.plan.create")
def create_reconciliation_run(root: Path | str, *, insert_run_id: int, created_by: str) -> dict[str, Any]:
    """Create an immutable read-only reconciliation plan for one insert run."""
    if not str(created_by).strip():
        raise ReconciliationRecoveryError("created_by is required")
    root_path = Path(root).resolve()
    key = _lineage_key(root_path)
    with _connect(root_path) as conn:
        migration_40(conn)
        context = _load_context(conn, int(insert_run_id), root_path)
        _, row_fps, key_fps = _expected_evidence(context, key)
        insert = context["insert"]
        plan = {
            "reconciliation_version": RECONCILIATION_VERSION,
            "insert_run_id": int(insert_run_id),
            "insert_uuid": str(insert["insert_uuid"]),
            "insert_status_at_plan": str(insert["status"]),
            "insert_plan_hash": str(insert["insert_plan_hash"]),
            "commit_receipt_hash": insert["commit_receipt_hash"],
            "target_connection_id": int(insert["target_connection_id"]),
            "target_schema": str(insert["target_schema"]),
            "target_table": str(insert["target_table"]),
            "target_contract_hash": str(insert["target_contract_hash"]),
            "target_snapshot_hash": str(insert["target_snapshot_hash"]),
            "mapping_set_hash": str(insert["mapping_set_hash"]),
            "identity_resolution_run_id": int(context["resolution"]["id"]),
            "identity_manifest_hash": str(context["resolution"]["manifest_hash"]),
            "business_key_fields": context["business_fields"],
            "column_order": context["columns"],
            "expected_row_count": sum(row_fps.values()),
            "expected_row_set_hash": _sha256_json(sorted(row_fps.items())),
            "expected_key_set_hash": _sha256_json(sorted(key_fps.items())),
            "raw_values_stored": False,
            "target_write_allowed": False,
        }
        plan_hash = _sha256_json(plan)
        cur = conn.execute(
            """INSERT INTO db_reconciliation_runs(
                reconciliation_uuid,insert_run_id,reconciliation_version,plan_json,plan_hash,
                expected_row_count,expected_row_set_hash,status,created_by,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), int(insert_run_id), RECONCILIATION_VERSION, _canonical_json(plan), plan_hash,
             int(plan["expected_row_count"]), str(plan["expected_row_set_hash"]), "planned", str(created_by), utc_now()),
        )
        run_id = int(cur.lastrowid)
        _checkpoint(conn, insert_run_id=int(insert_run_id), reconciliation_run_id=run_id,
                    checkpoint_type="reconciliation_planned", payload={"plan_hash": plan_hash, "expected_row_count": int(plan["expected_row_count"])})
        _event(conn, "reconciliation_planned", {"plan_hash": plan_hash, "expected_row_count": int(plan["expected_row_count"]), "target_write_allowed": False},
               insert_run_id=int(insert_run_id), reconciliation_run_id=run_id)
    return get_reconciliation_run(root_path, run_id)


def _placeholders(engine: str, start: int, count: int) -> list[str]:
    """Return DB-API placeholders for one read-only reconciliation predicate."""
    if engine in {"postgresql", "mysql"}:
        return ["%s"] * count
    if engine == "mssql":
        return ["?"] * count
    if engine == "oracle":
        return [f":{start + i}" for i in range(count)]
    raise ReconciliationRecoveryError(f"unsupported TARGET engine: {engine}")


def _build_select_sql(engine: str, schema: str, table: str, columns: list[str], business_fields: list[str], key_count: int) -> str:
    """Build a bounded SELECT-only query targeting only expected business keys."""
    if key_count <= 0:
        raise ReconciliationRecoveryError("reconciliation query needs at least one expected key")
    projected = ",".join(_quote_identifier(engine, c) for c in columns)
    table_sql = f"{_quote_identifier(engine, schema)}.{_quote_identifier(engine, table)}"
    predicates: list[str] = []
    bind_index = 1
    for _ in range(key_count):
        markers = _placeholders(engine, bind_index, len(business_fields))
        bind_index += len(business_fields)
        predicates.append("(" + " AND ".join(f"{_quote_identifier(engine, field)} = {marker}" for field, marker in zip(business_fields, markers)) + ")")
    return f"SELECT {projected} FROM {table_sql} WHERE " + " OR ".join(predicates)


def build_reconciliation_spec(root: Path | str, reconciliation_run_id: int) -> dict[str, Any]:
    """Return a privacy-safe SELECT-only spec without query parameters or business values."""
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_40(conn)
        run = conn.execute("SELECT * FROM db_reconciliation_runs WHERE id=?", (int(reconciliation_run_id),)).fetchone()
        if run is None:
            raise ReconciliationRecoveryError("reconciliation run not found")
        context = _load_context(conn, int(run["insert_run_id"]), root_path)
        engine = str(context["target"]["engine"])
        chunk = max(1, min(MAX_QUERY_KEYS, 1800 // max(1, len(context["business_fields"]))))
        sample_sql = _build_select_sql(engine, str(context["insert"]["target_schema"]), str(context["insert"]["target_table"]),
                                       context["columns"], context["business_fields"], 1)
    return {
        "ok": True,
        "reconciliation_run_id": int(reconciliation_run_id),
        "statement_class": "SELECT_ONLY",
        "target_connection_id": int(context["insert"]["target_connection_id"]),
        "target_schema": str(context["insert"]["target_schema"]),
        "target_table": str(context["insert"]["target_table"]),
        "projected_columns": context["columns"],
        "business_key_fields": context["business_fields"],
        "max_key_chunk": chunk,
        "sql_shape": sample_sql,
        "query_parameters_included": False,
        "raw_business_values_included": False,
        "target_write_allowed": False,
    }


def _rows_from_target(
    context: dict[str, Any],
    key_rows: list[dict[str, Any]],
    *,
    secret_resolver: Callable[[str], dict[str, Any]],
    target_connection_factory: Callable[[sqlite3.Row, dict[str, Any]], Any],
) -> list[dict[str, Any]]:
    """Read only TARGET rows matching expected keys; raw values remain in process memory only."""
    target = context["target"]
    engine = str(target["engine"])
    chunk_size = max(1, min(MAX_QUERY_KEYS, 1800 // max(1, len(context["business_fields"]))))
    try:
        secret = secret_resolver(str(target["credential_ref"]))
        if not isinstance(secret, dict):
            raise ReconciliationRecoveryError("TARGET secret resolver must return an object")
        db = target_connection_factory(target, secret)
    except Exception as exc:
        if isinstance(exc, ReconciliationRecoveryError):
            raise
        raise ReconciliationRecoveryError(f"TARGET reconciliation connection failed: {type(exc).__name__}") from exc
    output: list[dict[str, Any]] = []
    try:
        cursor = db.cursor()
        try:
            for offset in range(0, len(key_rows), chunk_size):
                chunk = key_rows[offset:offset + chunk_size]
                sql = _build_select_sql(engine, str(context["insert"]["target_schema"]), str(context["insert"]["target_table"]),
                                        context["columns"], context["business_fields"], len(chunk))
                params: list[Any] = []
                for key_row in chunk:
                    params.extend(key_row[field] for field in context["business_fields"])
                cursor.execute(sql, tuple(params))
                description = [str(item[0]) for item in (cursor.description or [])]
                if not description:
                    raise ReconciliationRecoveryError("TARGET reconciliation cursor returned no column metadata")
                while True:
                    rows = cursor.fetchmany(500)
                    if not rows:
                        break
                    for row in rows:
                        if isinstance(row, dict):
                            output.append({str(k): v for k, v in row.items()})
                        else:
                            output.append({description[i]: row[i] for i in range(len(description))})
        finally:
            cursor.close()
    finally:
        try:
            db.close()
        except Exception:
            pass
    return output


@governed_mutation("db.reconciliation.run")
def run_reconciliation(
    root: Path | str,
    reconciliation_run_id: int,
    *,
    target_row_provider: Callable[[list[str], list[str], list[dict[str, Any]]], Iterable[dict[str, Any]]] | None = None,
    secret_resolver: Callable[[str], dict[str, Any]] | None = None,
    target_connection_factory: Callable[[sqlite3.Row, dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Execute read-only TARGET reconciliation and persist only keyed hashes/counts.

    Args:
        root: Active AgentOS project root.
        reconciliation_run_id: Planned reconciliation run.
        target_row_provider: Optional trusted read-only row provider for tests/integration adapters.
        secret_resolver: Optional trusted secret resolver for production TARGET reads.
        target_connection_factory: Optional trusted DB-API TARGET connection factory.

    Returns:
        Privacy-safe reconciliation summary containing counts, outcome, and evidence hash.

    Raises:
        ReconciliationRecoveryError: On stale plans, TARGET read failure, or privacy/invariant violation.

    Side Effects:
        Performs SELECT-only TARGET reads and updates only local AgentOS reconciliation state.
    """
    root_path = Path(root).resolve()
    key = _lineage_key(root_path)
    with _connect(root_path) as conn:
        migration_40(conn)
        run = conn.execute("SELECT * FROM db_reconciliation_runs WHERE id=?", (int(reconciliation_run_id),)).fetchone()
        if run is None or str(run["status"]) not in {"planned", "failed"}:
            raise ReconciliationRecoveryError("reconciliation run is not runnable")
        context = _load_context(conn, int(run["insert_run_id"]), root_path)
        plan = json.loads(run["plan_json"])
        if _sha256_json(plan) != str(run["plan_hash"]):
            raise ReconciliationRecoveryError("reconciliation plan hash mismatch")
        if str(context["insert"]["insert_plan_hash"]) != str(plan["insert_plan_hash"]):
            raise ReconciliationRecoveryError("insert plan drifted after reconciliation planning")
        if str(context["resolution"]["manifest_hash"]) != str(plan["identity_manifest_hash"]):
            raise ReconciliationRecoveryError("identity manifest drifted after reconciliation planning")
        key_rows, expected_rows, expected_keys = _expected_evidence(context, key)
        if _sha256_json(sorted(expected_rows.items())) != str(run["expected_row_set_hash"]):
            raise ReconciliationRecoveryError("expected reconciliation evidence drifted")
        conn.execute("UPDATE db_reconciliation_runs SET status='running',started_at=?,failure_reason=NULL WHERE id=?", (utc_now(), int(reconciliation_run_id)))
        _checkpoint(conn, insert_run_id=int(run["insert_run_id"]), reconciliation_run_id=int(reconciliation_run_id),
                    checkpoint_type="target_read_started", payload={"plan_hash": str(run["plan_hash"]), "expected_row_count": sum(expected_rows.values())})

    try:
        if target_row_provider is not None:
            observed_values = list(target_row_provider(context["columns"], context["business_fields"], key_rows))
        else:
            from .read_only_extraction import _resolve_env_secret
            observed_values = _rows_from_target(
                context, key_rows,
                secret_resolver=secret_resolver or _resolve_env_secret,
                target_connection_factory=target_connection_factory or _open_target_connection,
            )
        observed_rows: Counter[str] = Counter()
        observed_keys: Counter[str] = Counter()
        for values in observed_values:
            if not isinstance(values, dict):
                raise ReconciliationRecoveryError("TARGET reconciliation provider returned a non-object row")
            observed_rows[_row_fingerprint(key, context["columns"], values)] += 1
            observed_keys[_exact_key_fingerprint(key, values, context["business_fields"], str(context["identity_policy"]["normalizer"]))] += 1
    except Exception as exc:
        with _connect(root_path) as conn:
            migration_40(conn)
            conn.execute("UPDATE db_reconciliation_runs SET status='failed',failure_reason=? WHERE id=?", (type(exc).__name__, int(reconciliation_run_id)))
            _event(conn, "reconciliation_failed", {"error_type": type(exc).__name__, "target_write_attempted": False},
                   insert_run_id=int(run["insert_run_id"]), reconciliation_run_id=int(reconciliation_run_id))
        if isinstance(exc, ReconciliationRecoveryError):
            raise
        raise ReconciliationRecoveryError(f"TARGET reconciliation failed: {type(exc).__name__}") from exc

    intersection = expected_rows & observed_rows
    matching = sum(intersection.values())
    missing = sum((expected_rows - observed_rows).values())
    unexpected = sum((observed_rows - expected_rows).values())
    duplicate = sum(max(0, count - expected_keys.get(fp, 0)) for fp, count in observed_keys.items())
    observed_count = sum(observed_rows.values())
    if observed_count == 0:
        outcome = "observed_none"
    elif missing == 0 and unexpected == 0 and duplicate == 0 and observed_count == sum(expected_rows.values()):
        outcome = "matched"
    elif matching > 0:
        outcome = "observed_partial"
    else:
        outcome = "mismatch"
    evidence = {
        "plan_hash": str(run["plan_hash"]),
        "expected_row_set_hash": _sha256_json(sorted(expected_rows.items())),
        "observed_row_set_hash": _sha256_json(sorted(observed_rows.items())),
        "expected_key_set_hash": _sha256_json(sorted(expected_keys.items())),
        "observed_key_set_hash": _sha256_json(sorted(observed_keys.items())),
        "expected_rows": sum(expected_rows.values()),
        "observed_rows": observed_count,
        "matching_rows": matching,
        "missing_rows": missing,
        "unexpected_rows": unexpected,
        "duplicate_rows": duplicate,
        "outcome": outcome,
        "target_write_attempted": False,
        "raw_values_stored": False,
    }
    evidence_hash = _sha256_json(evidence)
    with _connect(root_path) as conn:
        migration_40(conn)
        conn.execute(
            """UPDATE db_reconciliation_runs SET status='completed',observed_row_count=?,observed_row_set_hash=?,matching_rows=?,missing_rows=?,
               unexpected_rows=?,duplicate_rows=?,outcome=?,evidence_hash=?,completed_at=?,failure_reason=NULL WHERE id=?""",
            (observed_count, evidence["observed_row_set_hash"], matching, missing, unexpected, duplicate, outcome, evidence_hash, utc_now(), int(reconciliation_run_id)),
        )
        conn.execute("DELETE FROM db_reconciliation_findings WHERE reconciliation_run_id=?", (int(reconciliation_run_id),))
        findings = [
            ("missing_target_rows", "error", missing),
            ("unexpected_target_rows", "error", unexpected),
            ("duplicate_target_business_keys", "error", duplicate),
        ]
        for code, severity, count in findings:
            if count:
                conn.execute(
                    "INSERT INTO db_reconciliation_findings(reconciliation_run_id,finding_code,severity,count_value,evidence_json,created_at) VALUES(?,?,?,?,?,?)",
                    (int(reconciliation_run_id), code, severity, int(count), _canonical_json({"count": int(count), "raw_values_stored": False}), utc_now()),
                )
        _checkpoint(conn, insert_run_id=int(run["insert_run_id"]), reconciliation_run_id=int(reconciliation_run_id),
                    checkpoint_type="target_read_completed", payload={"evidence_hash": evidence_hash, "outcome": outcome, "observed_rows": observed_count})
        _event(conn, "reconciliation_completed", {"evidence_hash": evidence_hash, "outcome": outcome, "expected_rows": evidence["expected_rows"],
                                                   "observed_rows": observed_count, "raw_values_stored": False},
               insert_run_id=int(run["insert_run_id"]), reconciliation_run_id=int(reconciliation_run_id))
    return get_reconciliation_run(root_path, int(reconciliation_run_id))


def get_reconciliation_run(root: Path | str, reconciliation_run_id: int) -> dict[str, Any]:
    """Return one privacy-safe reconciliation run without business values or query parameters."""
    with _connect(root) as conn:
        migration_40(conn)
        row = conn.execute("SELECT * FROM db_reconciliation_runs WHERE id=?", (int(reconciliation_run_id),)).fetchone()
        if row is None:
            raise ReconciliationRecoveryError("reconciliation run not found")
    return {"ok": True, "reconciliation": {
        "id": int(row["id"]), "reconciliation_uuid": str(row["reconciliation_uuid"]), "insert_run_id": int(row["insert_run_id"]),
        "status": str(row["status"]), "plan_hash": str(row["plan_hash"]), "expected_row_count": int(row["expected_row_count"]),
        "observed_row_count": int(row["observed_row_count"]), "matching_rows": int(row["matching_rows"]), "missing_rows": int(row["missing_rows"]),
        "unexpected_rows": int(row["unexpected_rows"]), "duplicate_rows": int(row["duplicate_rows"]), "outcome": row["outcome"],
        "evidence_hash": row["evidence_hash"], "failure_reason": row["failure_reason"], "target_write_attempted": False,
        "raw_values_included": False,
    }}


def get_reconciliation_summary(root: Path | str, reconciliation_run_id: int) -> dict[str, Any]:
    """Return end-to-end extraction→identity→insert→lineage reconciliation counts."""
    with _connect(root) as conn:
        migration_40(conn)
        recon = conn.execute("SELECT * FROM db_reconciliation_runs WHERE id=?", (int(reconciliation_run_id),)).fetchone()
        if recon is None:
            raise ReconciliationRecoveryError("reconciliation run not found")
        insert = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(recon["insert_run_id"]),)).fetchone()
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(insert["extraction_batch_id"]),)).fetchone()
        plan = json.loads(insert["insert_plan_json"])
        resolution = conn.execute("SELECT * FROM identity_resolution_runs WHERE id=?", (int(plan["identity_resolution_run_id"]),)).fetchone()
        binding_count = int(conn.execute("SELECT COUNT(*) FROM identity_bindings WHERE resolution_run_id=?", (int(resolution["id"]),)).fetchone()[0])
        lineage_count = int(conn.execute("SELECT COUNT(*) FROM target_record_lineage WHERE extraction_batch_id=?", (int(batch["id"]),)).fetchone()[0])
        finding_count = int(conn.execute("SELECT COUNT(*) FROM db_reconciliation_findings WHERE reconciliation_run_id=?", (int(reconciliation_run_id),)).fetchone()[0])
    return {
        "ok": True,
        "reconciliation_run_id": int(reconciliation_run_id),
        "source_selected_rows": int(batch["selected_rows"]),
        "validated_rows": int(batch["valid_rows"]),
        "rejected_rows": int(batch["rejected_rows"]),
        "identity_input_rows": int(resolution["input_rows"]),
        "identity_output_rows": int(resolution["output_rows"]),
        "identity_duplicate_rows": int(resolution["duplicate_rows"]),
        "identity_bindings": binding_count,
        "insert_status": str(insert["status"]),
        "insert_expected_rows": int(insert["row_count"]),
        "insert_committed_rows": int(insert["committed_rows"]),
        "lineage_rows_for_batch": lineage_count,
        "lineage_status": str(insert["lineage_status"]),
        "reconciliation_outcome": recon["outcome"],
        "reconciliation_findings": finding_count,
        "evidence_hash": recon["evidence_hash"],
        "raw_values_included": False,
    }


@governed_mutation("db.recovery.scan")
def scan_recovery_cases(root: Path | str) -> dict[str, Any]:
    """Discover unresolved insert/lineage states and create idempotent local recovery cases."""
    with _connect(root) as conn:
        migration_40(conn)
        rows = conn.execute(
            """SELECT * FROM db_target_insert_runs
               WHERE status IN ('committing','in_doubt') OR (status='committed' AND lineage_status!='complete')
               ORDER BY id"""
        ).fetchall()
        created = 0
        for row in rows:
            case_type = "COMMIT_OUTCOME" if str(row["status"]) in {"committing", "in_doubt"} else "LINEAGE_FINALIZATION"
            existing = conn.execute(
                "SELECT id FROM db_recovery_cases WHERE insert_run_id=? AND case_type=? AND status IN ('open','manual_intervention') ORDER BY id DESC LIMIT 1",
                (int(row["id"]), case_type),
            ).fetchone()
            if existing is not None:
                continue
            evidence = {
                "insert_run_id": int(row["id"]), "insert_status": str(row["status"]), "lineage_status": str(row["lineage_status"]),
                "insert_plan_hash": str(row["insert_plan_hash"]), "commit_receipt_hash": row["commit_receipt_hash"], "raw_values_stored": False,
            }
            cur = conn.execute(
                "INSERT INTO db_recovery_cases(case_uuid,insert_run_id,case_type,status,evidence_hash,created_at) VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), int(row["id"]), case_type, "open", _sha256_json(evidence), utc_now()),
            )
            case_id = int(cur.lastrowid)
            _checkpoint(conn, insert_run_id=int(row["id"]), reconciliation_run_id=None, checkpoint_type="recovery_case_opened",
                        payload={"recovery_case_id": case_id, "case_type": case_type, "evidence_hash": _sha256_json(evidence)})
            _event(conn, "recovery_case_opened", {"case_type": case_type, "evidence_hash": _sha256_json(evidence)},
                   insert_run_id=int(row["id"]), recovery_case_id=case_id)
            created += 1
    return {"ok": True, "created_cases": created, "cases": list_recovery_cases(root)["cases"]}


def list_recovery_cases(root: Path | str, *, status: str | None = None) -> dict[str, Any]:
    """List privacy-safe recovery cases for human/operator handling."""
    with _connect(root) as conn:
        migration_40(conn)
        if status:
            rows = conn.execute("SELECT * FROM db_recovery_cases WHERE status=? ORDER BY id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM db_recovery_cases ORDER BY id").fetchall()
    return {"ok": True, "cases": [{
        "id": int(r["id"]), "case_uuid": str(r["case_uuid"]), "insert_run_id": int(r["insert_run_id"]),
        "reconciliation_run_id": r["reconciliation_run_id"], "case_type": str(r["case_type"]), "status": str(r["status"]),
        "evidence_hash": r["evidence_hash"], "decision": r["decision"], "decided_by": r["decided_by"], "raw_values_included": False,
    } for r in rows]}


def _latest_completed_reconciliation(conn: sqlite3.Connection, insert_run_id: int) -> sqlite3.Row | None:
    """Return the most recent completed reconciliation for one insert run."""
    return conn.execute(
        "SELECT * FROM db_reconciliation_runs WHERE insert_run_id=? AND status='completed' ORDER BY id DESC LIMIT 1",
        (int(insert_run_id),),
    ).fetchone()


@governed_mutation("db.recovery.commit.decide")
def resolve_commit_outcome(
    root: Path | str,
    recovery_case_id: int,
    *,
    decision: str,
    decided_by: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Resolve one uncertain commit outcome using read-only evidence plus explicit human confirmation.

    `committed_verified` is allowed only after a `matched` reconciliation. `not_committed_verified`
    is allowed only after `observed_none`. Partial/mismatch outcomes stay manual-intervention.
    """
    if not human_confirmed or not str(decided_by).strip():
        raise ReconciliationRecoveryError("human-confirmed recovery decision is required")
    if decision not in {"committed_verified", "not_committed_verified", "manual_intervention"}:
        raise ReconciliationRecoveryError("invalid commit recovery decision")
    root_path = Path(root).resolve()
    finalize_lineage = False
    insert_id = 0
    with _connect(root_path) as conn:
        migration_40(conn)
        case = conn.execute("SELECT * FROM db_recovery_cases WHERE id=?", (int(recovery_case_id),)).fetchone()
        if case is None or str(case["case_type"]) != "COMMIT_OUTCOME" or str(case["status"]) not in {"open", "manual_intervention"}:
            raise ReconciliationRecoveryError("open COMMIT_OUTCOME recovery case is required")
        insert_id = int(case["insert_run_id"])
        insert = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (insert_id,)).fetchone()
        if insert is None or str(insert["status"]) not in {"committing", "in_doubt"}:
            raise ReconciliationRecoveryError("insert run is no longer uncertain")
        recon = _latest_completed_reconciliation(conn, insert_id)
        if recon is None:
            raise ReconciliationRecoveryError("completed read-only reconciliation is required before commit recovery")
        outcome = str(recon["outcome"])
        if decision == "committed_verified" and outcome != "matched":
            raise ReconciliationRecoveryError("committed_verified requires a matched reconciliation")
        if decision == "not_committed_verified" and outcome != "observed_none":
            raise ReconciliationRecoveryError("not_committed_verified requires observed_none reconciliation")
        if outcome in {"observed_partial", "mismatch"} and decision != "manual_intervention":
            raise ReconciliationRecoveryError("partial/mismatched TARGET state requires manual intervention")
        if decision == "manual_intervention":
            conn.execute(
                "UPDATE db_recovery_cases SET status='manual_intervention',reconciliation_run_id=?,decision=?,decided_by=?,decided_at=? WHERE id=?",
                (int(recon["id"]), decision, str(decided_by), utc_now(), int(recovery_case_id)),
            )
            _event(conn, "commit_recovery_manual_intervention", {"outcome": outcome, "evidence_hash": str(recon["evidence_hash"]), "automatic_target_repair": False},
                   insert_run_id=insert_id, reconciliation_run_id=int(recon["id"]), recovery_case_id=int(recovery_case_id))
            return {"ok": True, "recovery_case_id": int(recovery_case_id), "status": "manual_intervention", "automatic_target_repair": False}
        if decision == "committed_verified":
            recovery_receipt = {
                "insert_run_id": insert_id, "insert_plan_hash": str(insert["insert_plan_hash"]), "reconciliation_evidence_hash": str(recon["evidence_hash"]),
                "decision": decision, "decision_by": str(decided_by), "expected_rows": int(recon["expected_row_count"]), "write_mode": "INSERT_ONLY_RECOVERED",
            }
            receipt_hash = _sha256_json(recovery_receipt)
            conn.execute(
                """UPDATE db_target_insert_runs SET status='committed',committed_at=?,committed_rows=?,commit_receipt_hash=?,
                   failure_stage=NULL,failure_reason=NULL WHERE id=?""",
                (utc_now(), int(recon["expected_row_count"]), receipt_hash, insert_id),
            )
            finalize_lineage = True
        else:
            conn.execute(
                """UPDATE db_target_insert_runs SET status='failed',failed_at=?,failure_stage='reconciled_not_committed',
                   failure_reason='human_verified_not_committed',committed_rows=0,commit_receipt_hash=NULL WHERE id=?""",
                (utc_now(), insert_id),
            )
        conn.execute(
            """UPDATE db_recovery_cases SET status='resolved',reconciliation_run_id=?,evidence_hash=?,decision=?,decided_by=?,decided_at=?,resolved_at=?
               WHERE id=?""",
            (int(recon["id"]), str(recon["evidence_hash"]), decision, str(decided_by), utc_now(), utc_now(), int(recovery_case_id)),
        )
        _checkpoint(conn, insert_run_id=insert_id, reconciliation_run_id=int(recon["id"]), checkpoint_type="commit_outcome_resolved",
                    payload={"recovery_case_id": int(recovery_case_id), "decision": decision, "evidence_hash": str(recon["evidence_hash"])})
        _event(conn, "commit_outcome_resolved", {"decision": decision, "outcome": outcome, "evidence_hash": str(recon["evidence_hash"]), "automatic_retry": False},
               insert_run_id=insert_id, reconciliation_run_id=int(recon["id"]), recovery_case_id=int(recovery_case_id))
    if finalize_lineage:
        try:
            finalize_insert_lineage(root_path, insert_id)
            with _connect(root_path) as conn:
                migration_40(conn)
                conn.execute("UPDATE db_target_insert_runs SET lineage_status='complete',lineage_finalized_at=? WHERE id=?", (utc_now(), insert_id))
                _event(conn, "recovered_commit_lineage_finalized", {"raw_values_stored": False}, insert_run_id=insert_id, recovery_case_id=int(recovery_case_id))
        except Exception as exc:
            with _connect(root_path) as conn:
                migration_40(conn)
                conn.execute("UPDATE db_target_insert_runs SET lineage_status='pending' WHERE id=?", (insert_id,))
                _event(conn, "recovered_commit_lineage_pending", {"error_type": type(exc).__name__, "target_write_retry_allowed": False}, insert_run_id=insert_id, recovery_case_id=int(recovery_case_id))
    return {"ok": True, "recovery_case_id": int(recovery_case_id), "decision": decision, "insert_run_id": insert_id,
            "insert_status": "committed" if decision == "committed_verified" else "failed", "automatic_retry": False}


@governed_mutation("db.recovery.lineage.finalize")
def recover_pending_lineage(root: Path | str, recovery_case_id: int, *, recovered_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Idempotently recover local lineage after a known committed external insert."""
    if not human_confirmed or not str(recovered_by).strip():
        raise ReconciliationRecoveryError("human-confirmed lineage recovery is required")
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_40(conn)
        case = conn.execute("SELECT * FROM db_recovery_cases WHERE id=?", (int(recovery_case_id),)).fetchone()
        if case is None or str(case["case_type"]) != "LINEAGE_FINALIZATION" or str(case["status"]) != "open":
            raise ReconciliationRecoveryError("open LINEAGE_FINALIZATION recovery case is required")
        insert = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(case["insert_run_id"]),)).fetchone()
        if insert is None or str(insert["status"]) != "committed" or not insert["commit_receipt_hash"]:
            raise ReconciliationRecoveryError("known committed insert receipt is required")
        insert_id = int(insert["id"])
    try:
        result = finalize_insert_lineage(root_path, insert_id)
    except (IdentityResolutionError, ControlledTargetInsertError, Exception) as exc:
        with _connect(root_path) as conn:
            migration_40(conn)
            _event(conn, "lineage_recovery_failed", {"error_type": type(exc).__name__, "target_write_attempted": False}, insert_run_id=insert_id, recovery_case_id=int(recovery_case_id))
        raise ReconciliationRecoveryError("lineage recovery failed; TARGET INSERT must not be retried") from exc
    with _connect(root_path) as conn:
        migration_40(conn)
        conn.execute("UPDATE db_target_insert_runs SET lineage_status='complete',lineage_finalized_at=? WHERE id=?", (utc_now(), insert_id))
        conn.execute(
            "UPDATE db_recovery_cases SET status='resolved',decision='lineage_rebuilt',decided_by=?,decided_at=?,resolved_at=? WHERE id=?",
            (str(recovered_by), utc_now(), utc_now(), int(recovery_case_id)),
        )
        _checkpoint(conn, insert_run_id=insert_id, reconciliation_run_id=None, checkpoint_type="lineage_recovered",
                    payload={"recovery_case_id": int(recovery_case_id), "lineage_rows": int(result["lineage_rows"])})
        _event(conn, "lineage_recovered", {"lineage_rows": int(result["lineage_rows"]), "target_write_attempted": False},
               insert_run_id=insert_id, recovery_case_id=int(recovery_case_id))
    return {"ok": True, "recovery_case_id": int(recovery_case_id), "insert_run_id": insert_id,
            "lineage_status": "complete", "lineage_rows": int(result["lineage_rows"]), "target_write_attempted": False}


def get_recovery_readiness(root: Path | str, insert_run_id: int) -> dict[str, Any]:
    """Return fail-closed recovery readiness for one controlled insert run."""
    with _connect(root) as conn:
        migration_40(conn)
        insert = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if insert is None:
            raise ReconciliationRecoveryError("target insert run not found")
        recon = _latest_completed_reconciliation(conn, int(insert_run_id))
        open_cases = int(conn.execute("SELECT COUNT(*) FROM db_recovery_cases WHERE insert_run_id=? AND status IN ('open','manual_intervention')", (int(insert_run_id),)).fetchone()[0])
    outcome = str(recon["outcome"]) if recon is not None else None
    return {
        "ok": True,
        "insert_run_id": int(insert_run_id),
        "insert_status": str(insert["status"]),
        "lineage_status": str(insert["lineage_status"]),
        "latest_reconciliation_outcome": outcome,
        "latest_reconciliation_evidence_hash": recon["evidence_hash"] if recon is not None else None,
        "open_recovery_cases": open_cases,
        "may_mark_committed_verified": str(insert["status"]) in {"committing", "in_doubt"} and outcome == "matched",
        "may_mark_not_committed_verified": str(insert["status"]) in {"committing", "in_doubt"} and outcome == "observed_none",
        "manual_target_intervention_required": outcome in {"observed_partial", "mismatch"},
        "automatic_retry_allowed": False,
        "automatic_target_repair_allowed": False,
        "source_write_allowed": False,
    }


def list_recovery_checkpoints(root: Path | str, insert_run_id: int) -> dict[str, Any]:
    """List privacy-safe checkpoint hashes for one insert recovery history."""
    with _connect(root) as conn:
        migration_40(conn)
        rows = conn.execute("SELECT * FROM db_recovery_checkpoints WHERE insert_run_id=? ORDER BY id", (int(insert_run_id),)).fetchall()
    return {"ok": True, "insert_run_id": int(insert_run_id), "checkpoints": [{
        "id": int(r["id"]), "reconciliation_run_id": r["reconciliation_run_id"], "checkpoint_type": str(r["checkpoint_type"]),
        "checkpoint_hash": str(r["checkpoint_hash"]), "created_at": str(r["created_at"]), "raw_values_included": False,
    } for r in rows]}


def docs_check_v0222(root: Path | str) -> dict[str, Any]:
    """Validate v0.22.2 docs, governance, and schema 40."""
    root_path = Path(root).resolve()
    required = [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        ".agents/docs/RECONCILIATION_AND_RECOVERY.md", ".agents/docs/USAGE_V0222.md",
    ]
    missing = [item for item in required if not (root_path / item).exists()]
    version = (root_path / "VERSION").read_text(encoding="utf-8").strip() if (root_path / "VERSION").exists() else None
    governance = json.loads((root_path / ".agents/config/governance.json").read_text(encoding="utf-8"))
    policy = governance.get("reconciliation_recovery_policy")
    schema = sync_reconciliation_recovery_schema(root_path)
    ok = (
        not missing and version == "0.22.2"
        and governance.get("version", governance.get("governance_version")) == "0.22.2"
        and isinstance(policy, dict)
        and policy.get("in_doubt_auto_retry_allowed") is False
        and policy.get("partial_target_auto_repair_allowed") is False
        and policy.get("source_write_allowed") is False
        and policy.get("raw_values_in_reconciliation_state_allowed") is False
        and schema["ok"]
    )
    return {
        "ok": ok, "missing": missing, "version": version,
        "governance_version": governance.get("version", governance.get("governance_version")),
        "database_schema": schema["schema"],
        "in_doubt_auto_retry_allowed": policy.get("in_doubt_auto_retry_allowed") if isinstance(policy, dict) else None,
        "partial_target_auto_repair_allowed": policy.get("partial_target_auto_repair_allowed") if isinstance(policy, dict) else None,
        "source_write_allowed": policy.get("source_write_allowed") if isinstance(policy, dict) else None,
    }
