"""
File: .agents/agentos/identity_resolution.py

Purpose:
    Govern identity resolution, deduplication, and privacy-safe lineage for AgentOS v0.22.1.

Responsibilities:
    - Define human-approved deterministic identity policies bound to an approved TARGET contract.
    - Resolve exact business-key duplicates without allowing LLM-authored identity decisions.
    - Surface strong multi-field matches as candidates that require explicit human decisions.
    - Produce immutable deduplicated staging artifacts for controlled TARGET INSERT.
    - Maintain pseudonymous source-to-canonical-to-target lineage without raw business values in SQLite/audit.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Iterable
import uuid
from contextlib import contextmanager

from .db import connect as central_connect
from .governance_enforcement import governed_mutation, mirror_domain_event
from .secret_lineage import active_key, lookup_keys


from .controlled_target_insert import migration_38

MIGRATION_VERSION = 39
POLICY_VERSION = 1
RESOLUTION_VERSION = 1
KEY_FILE = ".agents/state/identity_lineage.key"
ALLOWED_NORMALIZERS = {"exact", "trim_casefold"}


class IdentityResolutionError(RuntimeError):
    """Raised when identity/dedup/lineage invariants fail closed."""


def utc_now() -> str:
    """Return an RFC3339 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for hashes and manifests."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: Any) -> Any:
    """Encode supported non-JSON scalar types deterministically."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__binary_sha256__": hashlib.sha256(bytes(value)).hexdigest()}
    raise TypeError(type(value).__name__)


def _sha256_json(value: Any) -> str:
    """Hash canonical JSON."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    """Hash a file without loading it fully into memory."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _db_path(root: Path | str) -> Path:
    """Return the local AgentOS SQLite path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


@contextmanager
def _connect(root: Path | str):
    """Open the shared AgentOS governance database connection."""
    with central_connect(Path(root)) as conn:
        yield conn


def migration_39(conn: sqlite3.Connection) -> None:
    """Apply additive schema 39 for identity, deduplication, and lineage."""
    migration_38(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS identity_resolution_policies(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            target_contract_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            policy_version INTEGER NOT NULL,
            policy_json TEXT NOT NULL,
            policy_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(target_contract_id) REFERENCES target_schema_contracts(id)
        );
        CREATE TABLE IF NOT EXISTS identity_resolution_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resolution_uuid TEXT NOT NULL UNIQUE,
            extraction_batch_id INTEGER NOT NULL UNIQUE,
            policy_id INTEGER NOT NULL,
            input_staging_path TEXT NOT NULL,
            input_staging_hash TEXT NOT NULL,
            output_staging_path TEXT,
            output_staging_hash TEXT,
            manifest_path TEXT,
            manifest_hash TEXT,
            input_rows INTEGER NOT NULL DEFAULT 0,
            output_rows INTEGER NOT NULL DEFAULT 0,
            duplicate_rows INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'planned',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            failure_reason TEXT,
            FOREIGN KEY(extraction_batch_id) REFERENCES db_extraction_batches(id),
            FOREIGN KEY(policy_id) REFERENCES identity_resolution_policies(id)
        );
        CREATE TABLE IF NOT EXISTS canonical_entities(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_uuid TEXT NOT NULL UNIQUE,
            consolidation_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            exact_key_fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(consolidation_id,target_schema,target_table,exact_key_fingerprint)
        );
        CREATE TABLE IF NOT EXISTS identity_bindings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_entity_id INTEGER NOT NULL,
            resolution_run_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_locator_hash TEXT NOT NULL,
            source_record_token TEXT NOT NULL UNIQUE,
            exact_key_fingerprint TEXT NOT NULL,
            strong_fingerprint TEXT,
            decision_type TEXT NOT NULL,
            decision_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id),
            FOREIGN KEY(resolution_run_id) REFERENCES identity_resolution_runs(id)
        );
        CREATE TABLE IF NOT EXISTS identity_candidates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resolution_run_id INTEGER NOT NULL,
            source_record_token TEXT NOT NULL,
            matched_entity_uuid TEXT NOT NULL,
            candidate_hash TEXT NOT NULL UNIQUE,
            match_method TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            decided_by TEXT,
            decided_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(resolution_run_id) REFERENCES identity_resolution_runs(id)
        );
        CREATE TABLE IF NOT EXISTS target_record_lineage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_entity_id INTEGER NOT NULL,
            insert_run_id INTEGER NOT NULL,
            extraction_batch_id INTEGER NOT NULL,
            target_connection_id INTEGER NOT NULL,
            target_schema TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_record_token TEXT NOT NULL,
            source_record_token TEXT NOT NULL,
            source_connection_id INTEGER NOT NULL,
            source_snapshot_hash TEXT NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_locator_hash TEXT NOT NULL,
            mapping_set_hash TEXT NOT NULL,
            target_contract_hash TEXT NOT NULL,
            commit_receipt_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(insert_run_id,source_record_token),
            FOREIGN KEY(canonical_entity_id) REFERENCES canonical_entities(id),
            FOREIGN KEY(insert_run_id) REFERENCES db_target_insert_runs(id)
        );
        CREATE TABLE IF NOT EXISTS identity_resolution_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_id INTEGER,
            resolution_run_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_identity_bindings_exact
            ON identity_bindings(exact_key_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_identity_bindings_strong
            ON identity_bindings(strong_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_identity_candidates_run
            ON identity_candidates(resolution_run_id,status);
        CREATE INDEX IF NOT EXISTS idx_target_record_lineage_entity
            ON target_record_lineage(canonical_entity_id,insert_run_id);
        """
    )
    insert_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(db_target_insert_runs)")}
    if "lineage_status" not in insert_cols:
        conn.execute("ALTER TABLE db_target_insert_runs ADD COLUMN lineage_status TEXT NOT NULL DEFAULT 'not_required_v0220'")
    if "lineage_finalized_at" not in insert_cols:
        conn.execute("ALTER TABLE db_target_insert_runs ADD COLUMN lineage_finalized_at TEXT")


def sync_identity_resolution_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema 39 and report required tables."""
    required = {
        "identity_resolution_policies", "identity_resolution_runs", "canonical_entities",
        "identity_bindings", "identity_candidates", "target_record_lineage", "identity_resolution_events",
    }
    with _connect(root) as conn:
        migration_39(conn)
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"ok": required <= tables, "schema": MIGRATION_VERSION, "tables": sorted(required)}


def _privacy_safe(payload: Any) -> None:
    """Reject event payloads that may contain raw identity/business values or secrets."""
    forbidden = {"value", "values", "row", "rows", "record", "records", "password", "credential", "credential_ref", "dsn"}
    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for k, v in item.items():
                if str(k).lower() in forbidden:
                    raise IdentityResolutionError(f"identity event key is forbidden: {k}")
                walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)
    walk(payload)


def _event(conn: sqlite3.Connection, event_type: str, payload: dict[str, Any], *, policy_id: int | None = None, run_id: int | None = None) -> None:
    """Persist privacy-safe identity evidence."""
    _privacy_safe(payload)
    mirror = mirror_domain_event(event_type, payload)
    conn.execute(
        "INSERT INTO identity_resolution_events(policy_id,resolution_run_id,event_type,event_json,created_at,governed_operation_id,external_event_hash) VALUES(?,?,?,?,?,?,?)",
        (policy_id, run_id, event_type, _canonical_json(payload), utc_now(), mirror["governed_operation_id"], mirror["external_event_hash"]),
    )


def _lineage_key(root: Path) -> bytes:
    """Return active key material from the v0.22.6 versioned keyring."""
    return active_key(root)[1]


def _token(key: bytes, namespace: str, payload: Any) -> str:
    """Create a keyed pseudonymous token; raw business values are not persisted."""
    msg = (namespace + "\n" + _canonical_json(payload)).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _contract_table(contract: dict[str, Any], schema: str, table: str) -> dict[str, Any]:
    """Return one TARGET table from a contract."""
    for item in contract.get("tables", []):
        if str(item.get("schema", "")).lower() == schema.lower() and str(item.get("name", "")).lower() == table.lower():
            return item
    raise IdentityResolutionError("TARGET table is absent from approved contract")


def _normalize(value: Any, mode: str) -> Any:
    """Normalize one identity field using an explicitly allowlisted deterministic method."""
    if mode not in ALLOWED_NORMALIZERS:
        raise IdentityResolutionError(f"unsupported identity normalizer: {mode}")
    if value is None:
        return None
    if isinstance(value, str):
        return value if mode == "exact" else value.strip().casefold()
    if isinstance(value, (datetime, date, time, Decimal, uuid.UUID)):
        return _json_default(value)
    return value


def _field_fingerprint(key: bytes, namespace: str, values: dict[str, Any], fields: list[str], normalizer: str) -> str:
    """Create a keyed fingerprint for an ordered identity field set."""
    if not fields:
        raise IdentityResolutionError("identity field set must not be empty")
    payload = []
    for field in fields:
        if field not in values:
            raise IdentityResolutionError(f"identity field missing from staging: {field}")
        payload.append([field, _normalize(values.get(field), normalizer)])
    if any(v is None or v == "" for _, v in payload):
        raise IdentityResolutionError("exact identity key contains null/blank value")
    return _token(key, namespace, payload)


@governed_mutation("db.identity.policy.create")
def create_identity_policy(
    root: Path | str,
    *,
    consolidation_id: int,
    target_contract_id: int,
    target_schema: str,
    target_table: str,
    exact_key_fields: list[str],
    strong_match_fields: list[str] | None,
    created_by: str,
    normalizer: str = "trim_casefold",
) -> dict[str, Any]:
    """Create a draft deterministic identity policy bound to an approved TARGET contract."""
    if not str(created_by).strip():
        raise IdentityResolutionError("created_by is required")
    if normalizer not in ALLOWED_NORMALIZERS:
        raise IdentityResolutionError("unsupported identity normalizer")
    exact = [str(x) for x in exact_key_fields]
    strong = [str(x) for x in (strong_match_fields or [])]
    if not exact or len(set(exact)) != len(exact) or len(set(strong)) != len(strong):
        raise IdentityResolutionError("identity field lists must be unique and exact key must be non-empty")
    with _connect(root) as conn:
        migration_39(conn)
        consolidation = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(consolidation_id),)).fetchone()
        contract = conn.execute("SELECT * FROM target_schema_contracts WHERE id=?", (int(target_contract_id),)).fetchone()
        if consolidation is None or contract is None or contract["status"] != "approved":
            raise IdentityResolutionError("active consolidation and approved TARGET contract are required")
        if int(contract["consolidation_id"]) != int(consolidation_id):
            raise IdentityResolutionError("TARGET contract does not belong to consolidation")
        contract_json = json.loads(contract["contract_json"])
        table_contract = _contract_table(contract_json, target_schema, target_table)
        columns = {str(c["name"]) for c in table_contract.get("columns", [])}
        if any(f not in columns for f in exact + strong):
            raise IdentityResolutionError("identity policy references a field absent from TARGET contract")
        business_keys = [[str(x) for x in group] for group in table_contract.get("business_keys", [])]
        if exact not in business_keys:
            raise IdentityResolutionError("exact identity key must equal one approved TARGET business key")
        policy = {
            "policy_version": POLICY_VERSION,
            "consolidation_id": int(consolidation_id),
            "target_contract_id": int(target_contract_id),
            "target_contract_hash": str(contract["contract_hash"]),
            "target_schema": str(target_schema),
            "target_table": str(target_table),
            "exact_key_fields": exact,
            "strong_match_fields": strong,
            "normalizer": normalizer,
            "exact_business_key_auto_bind": True,
            "strong_match_requires_human_decision": True,
            "llm_may_decide_identity": False,
        }
        policy_hash = _sha256_json(policy)
        cur = conn.execute(
            """INSERT INTO identity_resolution_policies(
                consolidation_id,target_contract_id,target_schema,target_table,policy_version,policy_json,policy_hash,status,created_by,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (int(consolidation_id), int(target_contract_id), target_schema, target_table, POLICY_VERSION,
             _canonical_json(policy), policy_hash, "draft", str(created_by).strip(), utc_now()),
        )
        pid = int(cur.lastrowid)
        _event(conn, "identity_policy_created", {"policy_hash": policy_hash, "exact_field_count": len(exact), "strong_field_count": len(strong)}, policy_id=pid)
    return get_identity_policy(root, pid)


@governed_mutation("db.identity.policy.review")
def review_identity_policy(root: Path | str, policy_id: int, *, reviewed_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Record explicit human review of a deterministic identity policy."""
    if not human_confirmed or not str(reviewed_by).strip():
        raise IdentityResolutionError("explicit human review is required")
    with _connect(root) as conn:
        migration_39(conn)
        row = conn.execute("SELECT * FROM identity_resolution_policies WHERE id=?", (int(policy_id),)).fetchone()
        if row is None or row["status"] != "draft":
            raise IdentityResolutionError("only draft identity policies can be reviewed")
        conn.execute("UPDATE identity_resolution_policies SET status='reviewed',reviewed_by=?,reviewed_at=? WHERE id=?", (reviewed_by, utc_now(), int(policy_id)))
        _event(conn, "identity_policy_reviewed", {"policy_hash": str(row["policy_hash"]), "reviewed_by": reviewed_by}, policy_id=int(policy_id))
    return get_identity_policy(root, int(policy_id))


@governed_mutation("db.identity.policy.approve")
def approve_identity_policy(root: Path | str, policy_id: int, *, approved_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Approve one reviewed identity policy; LLM/MCP cannot call this mutation."""
    if not human_confirmed or not str(approved_by).strip():
        raise IdentityResolutionError("explicit human approval is required")
    with _connect(root) as conn:
        migration_39(conn)
        row = conn.execute("SELECT * FROM identity_resolution_policies WHERE id=?", (int(policy_id),)).fetchone()
        if row is None or row["status"] != "reviewed":
            raise IdentityResolutionError("identity policy must be reviewed before approval")
        conn.execute("UPDATE identity_resolution_policies SET status='approved',approved_by=?,approved_at=? WHERE id=?", (approved_by, utc_now(), int(policy_id)))
        _event(conn, "identity_policy_approved", {"policy_hash": str(row["policy_hash"]), "approved_by": approved_by}, policy_id=int(policy_id))
    return get_identity_policy(root, int(policy_id))


def _safe_policy(row: sqlite3.Row) -> dict[str, Any]:
    """Return privacy-safe policy metadata."""
    return {
        "id": int(row["id"]), "consolidation_id": int(row["consolidation_id"]), "target_contract_id": int(row["target_contract_id"]),
        "target_schema": str(row["target_schema"]), "target_table": str(row["target_table"]), "policy_hash": str(row["policy_hash"]),
        "status": str(row["status"]), "reviewed_by": row["reviewed_by"], "approved_by": row["approved_by"],
        "policy": json.loads(row["policy_json"]),
    }


def get_identity_policy(root: Path | str, policy_id: int) -> dict[str, Any]:
    """Read one identity policy without secrets or record values."""
    with _connect(root) as conn:
        migration_39(conn)
        row = conn.execute("SELECT * FROM identity_resolution_policies WHERE id=?", (int(policy_id),)).fetchone()
        if row is None:
            raise IdentityResolutionError("identity policy not found")
    return {"ok": True, "identity_policy": _safe_policy(row)}


def _load_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Stream local staging JSONL records."""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict) or not isinstance(value.get("values"), dict):
                    raise IdentityResolutionError("identity staging record has invalid shape")
                yield value


def _candidate_decision(conn: sqlite3.Connection, candidate_hash: str) -> sqlite3.Row | None:
    """Return an existing candidate row/decision by immutable candidate hash."""
    return conn.execute("SELECT * FROM identity_candidates WHERE candidate_hash=?", (candidate_hash,)).fetchone()


def _get_or_create_entity(conn: sqlite3.Connection, *, consolidation_id: int, schema: str, table: str, exact_fp: str, key_id: str) -> sqlite3.Row:
    """Get or create a canonical entity and pin the HMAC key used by its primary fingerprint."""
    row = conn.execute(
        "SELECT * FROM canonical_entities WHERE consolidation_id=? AND target_schema=? AND target_table=? AND exact_key_fingerprint=?",
        (consolidation_id, schema, table, exact_fp),
    ).fetchone()
    if row is not None:
        return row
    conn.execute(
        "INSERT INTO canonical_entities(entity_uuid,consolidation_id,target_schema,target_table,exact_key_fingerprint,created_at,key_id) VALUES(?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), consolidation_id, schema, table, exact_fp, utc_now(), key_id),
    )
    return conn.execute("SELECT * FROM canonical_entities WHERE id=last_insert_rowid()").fetchone()


def _existing_entity_for_strong(conn: sqlite3.Connection, strong_fps: list[str]) -> list[sqlite3.Row]:
    """Return entities matching any active/retired-key strong fingerprint."""
    if not strong_fps:
        return []
    marks = ",".join("?" for _ in strong_fps)
    return conn.execute(
        f"""SELECT DISTINCT e.* FROM identity_bindings b JOIN canonical_entities e ON e.id=b.canonical_entity_id
           WHERE b.strong_fingerprint IN ({marks}) ORDER BY e.id""",
        tuple(strong_fps),
    ).fetchall()


@governed_mutation("db.identity.run.create")
def create_identity_resolution_run(root: Path | str, *, extraction_batch_id: int, policy_id: int, created_by: str) -> dict[str, Any]:
    """Create an immutable identity-resolution run for one validated extraction batch."""
    if not str(created_by).strip():
        raise IdentityResolutionError("created_by is required")
    root_path = Path(root).resolve()
    active_key_id, _ = active_key(root_path)
    with _connect(root_path) as conn:
        migration_39(conn)
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(extraction_batch_id),)).fetchone()
        policy = conn.execute("SELECT * FROM identity_resolution_policies WHERE id=?", (int(policy_id),)).fetchone()
        if batch is None or batch["status"] != "validated" or int(batch["rejected_rows"]) != 0:
            raise IdentityResolutionError("fully validated extraction batch with zero rejections is required")
        if policy is None or policy["status"] != "approved":
            raise IdentityResolutionError("approved identity policy is required")
        if int(policy["consolidation_id"]) != int(batch["consolidation_id"]) or int(policy["target_contract_id"]) != int(batch["target_contract_id"]):
            raise IdentityResolutionError("identity policy does not match extraction batch consolidation/contract")
        if str(policy["target_schema"]) != str(batch["target_schema"]) or str(policy["target_table"]) != str(batch["target_table"]):
            raise IdentityResolutionError("identity policy target does not match extraction batch")
        if conn.execute("SELECT 1 FROM identity_resolution_runs WHERE extraction_batch_id=?", (int(extraction_batch_id),)).fetchone():
            raise IdentityResolutionError("identity resolution run already exists for extraction batch")
        path = (root_path / str(batch["staging_path"])).resolve()
        if not path.is_file() or _sha256_file(path) != str(batch["staging_hash"]):
            raise IdentityResolutionError("validated input staging artifact failed integrity check")
        cur = conn.execute(
            """INSERT INTO identity_resolution_runs(
                resolution_uuid,extraction_batch_id,policy_id,input_staging_path,input_staging_hash,input_rows,status,created_by,created_at,key_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), int(extraction_batch_id), int(policy_id), str(batch["staging_path"]), str(batch["staging_hash"]), int(batch["valid_rows"]), "planned", created_by, utc_now(), active_key_id),
        )
        rid = int(cur.lastrowid)
        _event(conn, "identity_resolution_planned", {"input_rows": int(batch["valid_rows"]), "input_staging_hash": str(batch["staging_hash"]), "policy_hash": str(policy["policy_hash"])}, policy_id=int(policy_id), run_id=rid)
    return get_identity_resolution_run(root_path, rid)


def _artifact_paths(root: Path, resolution_uuid: str) -> tuple[Path, Path]:
    """Return deduplicated staging and identity manifest paths inside local runtime."""
    base = (root / ".agents/runtime/data-staging/identity-resolution" / resolution_uuid).resolve()
    runtime = (root / ".agents/runtime/data-staging").resolve()
    try:
        base.relative_to(runtime)
    except ValueError as exc:
        raise IdentityResolutionError("identity artifact path escaped local runtime") from exc
    base.mkdir(parents=True, exist_ok=True)
    try:
        base.chmod(0o700)
    except OSError:
        pass
    return base / "deduplicated.jsonl", base / "identity-manifest.json"


def _write_atomic(path: Path, data: bytes) -> str:
    """Atomically write an owner-only local identity artifact and return SHA-256."""
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return hashlib.sha256(data).hexdigest()


@governed_mutation("db.identity.run.execute")
def run_identity_resolution(root: Path | str, resolution_run_id: int) -> dict[str, Any]:
    """Resolve exact identities, surface strong candidates, and build deduplicated local staging.

    Strong multi-field matches never auto-merge. If any are pending, the run stops in
    ``awaiting_human`` and must be resumed after human decisions.
    """
    root_path = Path(root).resolve()
    active_key_id, key = active_key(root_path)
    lookup_keyset = lookup_keys(root_path)
    with _connect(root_path) as conn:
        migration_39(conn)
        run = conn.execute("SELECT * FROM identity_resolution_runs WHERE id=?", (int(resolution_run_id),)).fetchone()
        if run is None or run["status"] not in {"planned", "awaiting_human"}:
            raise IdentityResolutionError("identity resolution run is not runnable")
        batch = conn.execute("SELECT * FROM db_extraction_batches WHERE id=?", (int(run["extraction_batch_id"]),)).fetchone()
        policy_row = conn.execute("SELECT * FROM identity_resolution_policies WHERE id=?", (int(run["policy_id"]),)).fetchone()
        if batch is None or batch["status"] != "validated" or policy_row is None or policy_row["status"] != "approved":
            raise IdentityResolutionError("identity upstream state is not current")
        input_path = (root_path / str(run["input_staging_path"])).resolve()
        if not input_path.is_file() or _sha256_file(input_path) != str(run["input_staging_hash"]):
            raise IdentityResolutionError("identity input staging was modified")
        policy = json.loads(policy_row["policy_json"])
        consolidation_row = conn.execute("SELECT target_connection_id FROM db_consolidations WHERE id=?", (int(policy["consolidation_id"]),)).fetchone()
        if consolidation_row is None:
            raise IdentityResolutionError("identity consolidation disappeared")
        target_connection_id = int(consolidation_row["target_connection_id"])
        exact_fields = list(policy["exact_key_fields"])
        strong_fields = list(policy.get("strong_match_fields") or [])
        normalizer = str(policy["normalizer"])
        conn.execute("UPDATE identity_resolution_runs SET status='running',failure_reason=NULL WHERE id=?", (int(resolution_run_id),))

    included: dict[int, dict[str, Any]] = {}
    seen_entities: set[int] = set()
    duplicates = 0
    unresolved = 0
    manifest_rows: list[dict[str, Any]] = []
    all_rows = 0

    for record in _load_jsonl(input_path):
        all_rows += 1
        values = record["values"]
        provenance = record.get("provenance") or {}
        exact_fp = _field_fingerprint(key, "exact-identity", values, exact_fields, normalizer)
        exact_fps = [(kid, _field_fingerprint(kmat, "exact-identity", values, exact_fields, normalizer)) for kid, kmat in lookup_keyset]
        strong_fp = None
        strong_fps: list[tuple[str, str]] = []
        if strong_fields and all(values.get(f) not in (None, "") for f in strong_fields):
            strong_fp = _field_fingerprint(key, "strong-identity", values, strong_fields, normalizer)
            strong_fps = [(kid, _field_fingerprint(kmat, "strong-identity", values, strong_fields, normalizer)) for kid, kmat in lookup_keyset]
        source_payload = {
            "source_connection_id": provenance.get("source_connection_id"),
            "source_snapshot_hash": provenance.get("source_snapshot_hash"),
            "source_schema": provenance.get("source_schema"), "source_table": provenance.get("source_table"),
            "source_locator_hash": provenance.get("source_locator_hash"),
        }
        source_record_token = _token(key, "source-record", source_payload)
        source_tokens = [(kid, _token(kmat, "source-record", source_payload)) for kid, kmat in lookup_keyset]
        with _connect(root_path) as conn:
            migration_39(conn)
            token_values = [tok for _, tok in source_tokens]
            marks = ",".join("?" for _ in token_values)
            existing_binding = conn.execute(f"SELECT b.*,e.entity_uuid FROM identity_bindings b JOIN canonical_entities e ON e.id=b.canonical_entity_id WHERE b.source_record_token IN ({marks}) ORDER BY b.id LIMIT 1", tuple(token_values)).fetchone()
            decision_type = "existing_binding"
            decision_id = None
            if existing_binding is not None:
                entity = conn.execute("SELECT * FROM canonical_entities WHERE id=?", (int(existing_binding["canonical_entity_id"]),)).fetchone()
            else:
                exact_entities = conn.execute(
                    """SELECT DISTINCT e.* FROM canonical_entities e
                       LEFT JOIN identity_bindings b ON b.canonical_entity_id=e.id
                       WHERE e.consolidation_id=? AND e.target_schema=? AND e.target_table=?
                         AND (e.exact_key_fingerprint IN ({marks_fp}) OR b.exact_key_fingerprint IN ({marks_fp})) ORDER BY e.id""".format(
                        marks_fp=",".join("?" for _ in exact_fps)),
                    (int(policy["consolidation_id"]), str(policy["target_schema"]), str(policy["target_table"]),
                     *[fp for _, fp in exact_fps], *[fp for _, fp in exact_fps]),
                ).fetchall()
                if len(exact_entities) > 1:
                    raise IdentityResolutionError("exact identity fingerprint is bound to multiple canonical entities")
                exact_entity = exact_entities[0] if exact_entities else None
                if exact_entity is not None:
                    entity = exact_entity
                    decision_type = "exact_business_key"
                else:
                    strong_entities = _existing_entity_for_strong(conn, [fp for _, fp in strong_fps]) if strong_fp else []
                    if strong_entities:
                        if len(strong_entities) > 1:
                            raise IdentityResolutionError("strong identity fingerprint matches multiple canonical entities; manual policy/data review required")
                        # A strong match can only become an identity link after explicit human decision.
                        matched = strong_entities[0]
                        candidate_payload = {"source_record_token": source_record_token, "matched_entity_uuid": str(matched["entity_uuid"]), "strong_fingerprint": strong_fp}
                        candidate_hash = _sha256_json(candidate_payload)
                        candidate = _candidate_decision(conn, candidate_hash)
                        if candidate is None:
                            cur = conn.execute(
                                """INSERT INTO identity_candidates(resolution_run_id,source_record_token,matched_entity_uuid,candidate_hash,match_method,evidence_json,status,created_at,key_id)
                                   VALUES(?,?,?,?,?,?,?,?,?)""",
                                (int(resolution_run_id), source_record_token, str(matched["entity_uuid"]), candidate_hash, "strong_multifield_exact",
                                 _canonical_json({"strong_fingerprint": strong_fp, "field_count": len(strong_fields), "raw_values_stored": False}), "pending", utc_now(), active_key_id),
                            )
                            candidate = conn.execute("SELECT * FROM identity_candidates WHERE id=?", (int(cur.lastrowid),)).fetchone()
                        if candidate["status"] == "pending":
                            unresolved += 1
                            continue
                        if candidate["status"] == "confirmed":
                            entity = matched
                            decision_type = "human_confirmed_strong_match"
                            decision_id = int(candidate["id"])
                        elif candidate["status"] == "rejected":
                            entity = _get_or_create_entity(conn, consolidation_id=int(policy["consolidation_id"]), schema=str(policy["target_schema"]), table=str(policy["target_table"]), exact_fp=exact_fp, key_id=active_key_id)
                            decision_type = "human_rejected_strong_match_new_entity"
                            decision_id = int(candidate["id"])
                        else:
                            raise IdentityResolutionError("invalid identity candidate status")
                    else:
                        entity = _get_or_create_entity(conn, consolidation_id=int(policy["consolidation_id"]), schema=str(policy["target_schema"]), table=str(policy["target_table"]), exact_fp=exact_fp, key_id=active_key_id)
                        decision_type = "new_exact_identity"
                if existing_binding is None:
                    conn.execute(
                        """INSERT INTO identity_bindings(
                            canonical_entity_id,resolution_run_id,source_connection_id,source_snapshot_hash,source_schema,source_table,
                            source_locator_hash,source_record_token,exact_key_fingerprint,strong_fingerprint,decision_type,decision_id,created_at,key_id
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (int(entity["id"]), int(resolution_run_id), int(provenance["source_connection_id"]), str(provenance["source_snapshot_hash"]),
                         str(provenance["source_schema"]), str(provenance["source_table"]), str(provenance["source_locator_hash"]), source_record_token,
                         exact_fp, strong_fp, decision_type, decision_id, utc_now(), active_key_id),
                    )
            entity_id = int(entity["id"])
            existing_lineage = conn.execute("SELECT * FROM target_record_lineage WHERE canonical_entity_id=? ORDER BY id LIMIT 1", (entity_id,)).fetchone()
            already_committed = existing_lineage is not None
            if already_committed and existing_binding is None:
                # A newly observed SOURCE duplicate of an already committed entity gets a lineage edge immediately,
                # without any new TARGET INSERT. Only pseudonymous tokens/hashes are persisted.
                conn.execute(
                    """INSERT OR IGNORE INTO target_record_lineage(
                        canonical_entity_id,insert_run_id,extraction_batch_id,target_connection_id,target_schema,target_table,target_record_token,
                        source_record_token,source_connection_id,source_snapshot_hash,source_schema,source_table,source_locator_hash,
                        mapping_set_hash,target_contract_hash,commit_receipt_hash,created_at,key_id,source_key_id,target_key_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (entity_id, int(existing_lineage["insert_run_id"]), int(run["extraction_batch_id"]), int(existing_lineage["target_connection_id"]),
                     str(existing_lineage["target_schema"]), str(existing_lineage["target_table"]), str(existing_lineage["target_record_token"]),
                     source_record_token, int(provenance["source_connection_id"]), str(provenance["source_snapshot_hash"]), str(provenance["source_schema"]),
                     str(provenance["source_table"]), str(provenance["source_locator_hash"]), str(provenance["mapping_set_hash"]),
                     str(provenance["target_contract_hash"]), str(existing_lineage["commit_receipt_hash"]), utc_now(), active_key_id, active_key_id,
                     str(existing_lineage["target_key_id"] or existing_lineage["key_id"])),
                )

        target_record_token = _token(key, "target-record", {
            "target_connection_id": target_connection_id,
            "target_schema": str(policy["target_schema"]), "target_table": str(policy["target_table"]),
            "exact_key_fingerprint": exact_fp,
        })
        manifest_rows.append({
            "canonical_entity_uuid": str(entity["entity_uuid"]), "source_record_token": source_record_token,
            "target_record_token": target_record_token, "key_id": active_key_id, "included_for_insert": False,
        })
        if already_committed or entity_id in seen_entities:
            duplicates += 1
            continue
        seen_entities.add(entity_id)
        record["identity"] = {"canonical_entity_uuid": str(entity["entity_uuid"]), "target_record_token": target_record_token, "key_id": active_key_id}
        included[entity_id] = record
        manifest_rows[-1]["included_for_insert"] = True

    with _connect(root_path) as conn:
        migration_39(conn)
        pending = int(conn.execute("SELECT COUNT(*) FROM identity_candidates WHERE resolution_run_id=? AND status='pending'", (int(resolution_run_id),)).fetchone()[0])
        if pending or unresolved:
            count = max(pending, unresolved)
            conn.execute("UPDATE identity_resolution_runs SET status='awaiting_human',candidate_count=? WHERE id=?", (count, int(resolution_run_id)))
            _event(conn, "identity_resolution_waiting_for_human", {"pending_candidates": count, "llm_may_decide": False}, policy_id=int(run["policy_id"]), run_id=int(resolution_run_id))
            conn.commit()
            return get_identity_resolution_run(root_path, int(resolution_run_id))

    dedup_path, manifest_path = _artifact_paths(root_path, str(run["resolution_uuid"]))
    lines = []
    for entity_id in sorted(included):
        lines.append(json.dumps(included[entity_id], ensure_ascii=False, separators=(",", ":"), default=_json_default) + "\n")
    dedup_data = "".join(lines).encode("utf-8")
    dedup_hash = _write_atomic(dedup_path, dedup_data)
    manifest = {
        "resolution_version": RESOLUTION_VERSION,
        "resolution_uuid": str(run["resolution_uuid"]),
        "extraction_batch_id": int(run["extraction_batch_id"]),
        "policy_hash": str(policy_row["policy_hash"]),
        "input_staging_hash": str(run["input_staging_hash"]),
        "output_staging_hash": dedup_hash,
        "input_rows": all_rows,
        "output_rows": len(included),
        "duplicate_rows": duplicates,
        "candidate_count": 0,
        "rows": manifest_rows,
        "raw_business_values_stored": False,
        "key_id": active_key_id,
    }
    manifest_data = (_canonical_json(manifest) + "\n").encode("utf-8")
    manifest_hash = _write_atomic(manifest_path, manifest_data)
    with _connect(root_path) as conn:
        migration_39(conn)
        conn.execute(
            """UPDATE identity_resolution_runs SET status='resolved',output_staging_path=?,output_staging_hash=?,manifest_path=?,manifest_hash=?,
               input_rows=?,output_rows=?,duplicate_rows=?,candidate_count=0,completed_at=? WHERE id=?""",
            (str(dedup_path.relative_to(root_path)), dedup_hash, str(manifest_path.relative_to(root_path)), manifest_hash,
             all_rows, len(included), duplicates, utc_now(), int(resolution_run_id)),
        )
        _event(conn, "identity_resolution_resolved", {"input_rows": all_rows, "output_rows": len(included), "duplicate_rows": duplicates, "manifest_hash": manifest_hash, "raw_values_stored": False}, policy_id=int(run["policy_id"]), run_id=int(resolution_run_id))
    return get_identity_resolution_run(root_path, int(resolution_run_id))


@governed_mutation("db.identity.candidate.decide")
def decide_identity_candidate(root: Path | str, candidate_id: int, *, decision: str, decided_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Confirm or reject one strong-match candidate through an explicit human-only mutation."""
    if not human_confirmed or decision not in {"confirm", "reject"} or not str(decided_by).strip():
        raise IdentityResolutionError("human-confirmed identity decision must be confirm or reject")
    status = "confirmed" if decision == "confirm" else "rejected"
    with _connect(root) as conn:
        migration_39(conn)
        row = conn.execute("SELECT * FROM identity_candidates WHERE id=?", (int(candidate_id),)).fetchone()
        if row is None or row["status"] != "pending":
            raise IdentityResolutionError("only pending identity candidates can be decided")
        conn.execute("UPDATE identity_candidates SET status=?,decided_by=?,decided_at=? WHERE id=?", (status, decided_by, utc_now(), int(candidate_id)))
        _event(conn, "identity_candidate_decided", {"candidate_hash": str(row["candidate_hash"]), "decision": status, "decided_by": decided_by}, run_id=int(row["resolution_run_id"]))
    return get_identity_candidate(root, int(candidate_id))


def get_identity_candidate(root: Path | str, candidate_id: int) -> dict[str, Any]:
    """Read one privacy-safe identity candidate."""
    with _connect(root) as conn:
        migration_39(conn)
        row = conn.execute("SELECT * FROM identity_candidates WHERE id=?", (int(candidate_id),)).fetchone()
        if row is None:
            raise IdentityResolutionError("identity candidate not found")
    return {"ok": True, "candidate": {
        "id": int(row["id"]), "resolution_run_id": int(row["resolution_run_id"]), "candidate_hash": str(row["candidate_hash"]),
        "match_method": str(row["match_method"]), "status": str(row["status"]), "matched_entity_uuid": str(row["matched_entity_uuid"]),
        "evidence": json.loads(row["evidence_json"]), "decided_by": row["decided_by"], "raw_values_included": False,
    }}


def list_identity_candidates(root: Path | str, resolution_run_id: int) -> dict[str, Any]:
    """List privacy-safe candidates for human review."""
    with _connect(root) as conn:
        migration_39(conn)
        rows = conn.execute("SELECT id FROM identity_candidates WHERE resolution_run_id=? ORDER BY id", (int(resolution_run_id),)).fetchall()
    return {"ok": True, "resolution_run_id": int(resolution_run_id), "candidates": [get_identity_candidate(root, int(r["id"]))["candidate"] for r in rows]}


def get_identity_resolution_run(root: Path | str, resolution_run_id: int) -> dict[str, Any]:
    """Read one resolution run without staging record values."""
    with _connect(root) as conn:
        migration_39(conn)
        row = conn.execute("SELECT * FROM identity_resolution_runs WHERE id=?", (int(resolution_run_id),)).fetchone()
        if row is None:
            raise IdentityResolutionError("identity resolution run not found")
    return {"ok": True, "identity_resolution": {
        "id": int(row["id"]), "resolution_uuid": str(row["resolution_uuid"]), "extraction_batch_id": int(row["extraction_batch_id"]),
        "policy_id": int(row["policy_id"]), "status": str(row["status"]), "input_staging_hash": str(row["input_staging_hash"]),
        "output_staging_hash": row["output_staging_hash"], "manifest_hash": row["manifest_hash"], "input_rows": int(row["input_rows"]),
        "output_rows": int(row["output_rows"]), "duplicate_rows": int(row["duplicate_rows"]), "candidate_count": int(row["candidate_count"]),
        "failure_reason": row["failure_reason"], "raw_values_included": False,
    }}


def get_identity_insert_artifact(root: Path | str, extraction_batch_id: int) -> dict[str, Any]:
    """Return the resolved deduplicated staging binding required by v0.22.1 INSERT."""
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_39(conn)
        row = conn.execute("SELECT * FROM identity_resolution_runs WHERE extraction_batch_id=?", (int(extraction_batch_id),)).fetchone()
        if row is None or row["status"] != "resolved":
            raise IdentityResolutionError("resolved identity/deduplication run is required before TARGET INSERT")
        policy = conn.execute("SELECT * FROM identity_resolution_policies WHERE id=?", (int(row["policy_id"]),)).fetchone()
        if policy is None or policy["status"] != "approved":
            raise IdentityResolutionError("approved identity policy is no longer current")
    output_path = (root_path / str(row["output_staging_path"])).resolve()
    manifest_path = (root_path / str(row["manifest_path"])).resolve()
    runtime = (root_path / ".agents/runtime/data-staging").resolve()
    try:
        output_path.relative_to(runtime); manifest_path.relative_to(runtime)
    except ValueError as exc:
        raise IdentityResolutionError("identity artifact escaped local runtime") from exc
    if not output_path.is_file() or _sha256_file(output_path) != str(row["output_staging_hash"]):
        raise IdentityResolutionError("deduplicated staging artifact was modified")
    if not manifest_path.is_file() or _sha256_file(manifest_path) != str(row["manifest_hash"]):
        raise IdentityResolutionError("identity manifest was modified")
    return {
        "ok": True, "resolution_run_id": int(row["id"]), "policy_id": int(row["policy_id"]),
        "staging_path": str(row["output_staging_path"]), "staging_hash": str(row["output_staging_hash"]),
        "identity_manifest_path": str(row["manifest_path"]), "identity_manifest_hash": str(row["manifest_hash"]),
        "row_count": int(row["output_rows"]), "duplicate_rows": int(row["duplicate_rows"]), "raw_values_included": False,
    }


@governed_mutation("db.identity.lineage.finalize")
def finalize_insert_lineage(root: Path | str, insert_run_id: int) -> dict[str, Any]:
    """Attach committed TARGET receipt evidence to every source binding in the resolved batch."""
    root_path = Path(root).resolve()
    with _connect(root_path) as conn:
        migration_39(conn)
        insert = conn.execute("SELECT * FROM db_target_insert_runs WHERE id=?", (int(insert_run_id),)).fetchone()
        if insert is None or insert["status"] != "committed" or not insert["commit_receipt_hash"]:
            raise IdentityResolutionError("committed TARGET insert receipt is required for lineage finalization")
        plan = json.loads(insert["insert_plan_json"])
        resolution_id = plan.get("identity_resolution_run_id")
        if not resolution_id:
            raise IdentityResolutionError("v0.22.1 identity resolution binding is missing from insert plan")
        run = conn.execute("SELECT * FROM identity_resolution_runs WHERE id=?", (int(resolution_id),)).fetchone()
        if run is None or run["status"] != "resolved":
            raise IdentityResolutionError("resolved identity run is required")
        manifest_path = (root_path / str(run["manifest_path"])).resolve()
        if not manifest_path.is_file() or _sha256_file(manifest_path) != str(run["manifest_hash"]):
            raise IdentityResolutionError("identity lineage manifest was modified")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        inserted_entity_uuids = {str(r["canonical_entity_uuid"]): str(r["target_record_token"]) for r in manifest["rows"] if r.get("included_for_insert")}
        bindings = conn.execute(
            """SELECT b.*,e.entity_uuid FROM identity_bindings b JOIN canonical_entities e ON e.id=b.canonical_entity_id
               WHERE b.resolution_run_id=? ORDER BY b.id""", (int(resolution_id),)
        ).fetchall()
        inserted = 0
        for b in bindings:
            token = inserted_entity_uuids.get(str(b["entity_uuid"]))
            if token is None:
                # A duplicate may point to a canonical entity inserted by an earlier committed run; preserve its existing lineage only.
                continue
            conn.execute(
                """INSERT OR IGNORE INTO target_record_lineage(
                    canonical_entity_id,insert_run_id,extraction_batch_id,target_connection_id,target_schema,target_table,target_record_token,
                    source_record_token,source_connection_id,source_snapshot_hash,source_schema,source_table,source_locator_hash,
                    mapping_set_hash,target_contract_hash,commit_receipt_hash,created_at,key_id,source_key_id,target_key_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (int(b["canonical_entity_id"]), int(insert_run_id), int(insert["extraction_batch_id"]), int(insert["target_connection_id"]),
                 str(insert["target_schema"]), str(insert["target_table"]), token, str(b["source_record_token"]), int(b["source_connection_id"]),
                 str(b["source_snapshot_hash"]), str(b["source_schema"]), str(b["source_table"]), str(b["source_locator_hash"]),
                 str(insert["mapping_set_hash"]), str(insert["target_contract_hash"]), str(insert["commit_receipt_hash"]), utc_now(),
                 str(run["key_id"]), str(b["key_id"] or run["key_id"]), str(run["key_id"])),
            )
            inserted += 1
        _event(conn, "target_lineage_finalized", {"insert_run_id": int(insert_run_id), "lineage_rows": inserted, "commit_receipt_hash": str(insert["commit_receipt_hash"]), "raw_values_stored": False}, run_id=int(resolution_id))
    return {"ok": True, "insert_run_id": int(insert_run_id), "lineage_rows": inserted, "raw_values_included": False}


def get_entity_lineage(root: Path | str, entity_uuid: str) -> dict[str, Any]:
    """Read pseudonymous lineage for one canonical entity; raw source/target keys are never returned."""
    with _connect(root) as conn:
        migration_39(conn)
        entity = conn.execute("SELECT * FROM canonical_entities WHERE entity_uuid=?", (str(entity_uuid),)).fetchone()
        if entity is None:
            raise IdentityResolutionError("canonical entity not found")
        rows = conn.execute("SELECT * FROM target_record_lineage WHERE canonical_entity_id=? ORDER BY id", (int(entity["id"]),)).fetchall()
    return {"ok": True, "canonical_entity_uuid": str(entity_uuid), "lineage": [{
        "insert_run_id": int(r["insert_run_id"]), "extraction_batch_id": int(r["extraction_batch_id"]), "target_connection_id": int(r["target_connection_id"]),
        "target_schema": str(r["target_schema"]), "target_table": str(r["target_table"]), "target_record_token": str(r["target_record_token"]),
        "source_record_token": str(r["source_record_token"]), "source_connection_id": int(r["source_connection_id"]), "source_snapshot_hash": str(r["source_snapshot_hash"]),
        "source_schema": str(r["source_schema"]), "source_table": str(r["source_table"]), "source_locator_hash": str(r["source_locator_hash"]),
        "mapping_set_hash": str(r["mapping_set_hash"]), "target_contract_hash": str(r["target_contract_hash"]), "commit_receipt_hash": str(r["commit_receipt_hash"]),
        "key_id": r["key_id"], "source_key_id": r["source_key_id"], "target_key_id": r["target_key_id"],
    } for r in rows], "raw_values_included": False}


def get_identity_readiness(root: Path | str, extraction_batch_id: int) -> dict[str, Any]:
    """Return fail-closed readiness for v0.22.1 controlled insert."""
    try:
        artifact = get_identity_insert_artifact(root, int(extraction_batch_id))
        return {"ok": True, "extraction_batch_id": int(extraction_batch_id), "ready": artifact["row_count"] > 0,
                "resolved": True, "row_count": artifact["row_count"], "duplicate_rows": artifact["duplicate_rows"],
                "identity_manifest_hash": artifact["identity_manifest_hash"], "llm_may_decide_identity": False}
    except IdentityResolutionError as exc:
        return {"ok": True, "extraction_batch_id": int(extraction_batch_id), "ready": False, "resolved": False,
                "reason": str(exc), "llm_may_decide_identity": False}


def docs_check_v0221(root: Path | str) -> dict[str, Any]:
    """Validate v0.22.1 docs, governance, and schema 39."""
    root_path = Path(root).resolve()
    required = [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        ".agents/docs/IDENTITY_RESOLUTION_DEDUPLICATION_LINEAGE.md", ".agents/docs/USAGE_V0221.md",
    ]
    missing = [x for x in required if not (root_path / x).exists()]
    version = (root_path / "VERSION").read_text(encoding="utf-8").strip() if (root_path / "VERSION").exists() else None
    governance = json.loads((root_path / ".agents/config/governance.json").read_text(encoding="utf-8"))
    policy = governance.get("identity_resolution_policy")
    schema = sync_identity_resolution_schema(root_path)
    ok = (
        not missing and version == "0.22.1" and governance.get("version", governance.get("governance_version")) == "0.22.1"
        and isinstance(policy, dict) and policy.get("llm_may_decide_identity") is False
        and policy.get("strong_match_requires_human_decision") is True
        and policy.get("raw_identity_values_in_sqlite_forbidden") is True and schema["ok"]
    )
    return {"ok": ok, "missing": missing, "version": version, "governance_version": governance.get("version", governance.get("governance_version")),
            "database_schema": schema["schema"], "llm_may_decide_identity": policy.get("llm_may_decide_identity") if isinstance(policy, dict) else None}
