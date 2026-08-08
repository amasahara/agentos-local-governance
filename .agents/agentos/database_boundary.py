"""
File: .agents/agentos/database_boundary.py

Purpose:
    Implement AgentOS v0.21.0 Source/Target Database Boundary.

Responsibilities:
    - Register database endpoints without storing raw credentials.
    - Distinguish immutable SOURCE connections from the single TARGET connection.
    - Require verified read-only posture before a SOURCE may join a consolidation.
    - Enforce same-domain consolidation and prevent a connection from being both source and target.
    - Deny all database writes in v0.21.0, including writes to TARGET; controlled INSERT starts in v0.22.0.
    - Expose abstract operation authorization rather than arbitrary SQL execution.
    - Record boundary evidence in the local AgentOS database.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
import uuid

SCHEMA_VERSION = 35
SUPPORTED_ENGINES = {"mysql", "mssql", "postgresql", "oracle"}
ROLES = {"SOURCE", "TARGET"}
SOURCE_ALLOWED_OPERATIONS = {"catalog_read", "select_read", "connection_metadata_read"}
TARGET_ALLOWED_OPERATIONS_V0210 = {"catalog_read", "select_read", "connection_metadata_read"}
WRITE_OPERATIONS = {"insert", "update", "delete", "merge", "upsert", "ddl", "execute_side_effect"}
READONLY_VERIFICATION_METHODS = {"grant_review", "account_policy", "session_readonly", "external_attestation"}
SECRET_REF_SCHEMES = ("secret://", "env://", "keychain://", "vault://", "file-secret://")


class DatabaseBoundaryError(RuntimeError):
    """Raised when a database boundary invariant would be violated."""


def utc_now() -> str:
    """Return current UTC timestamp as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for evidence storage."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _db_path(root: Path | str) -> Path:
    """Return the active project's AgentOS SQLite path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


def _connect(root: Path | str) -> sqlite3.Connection:
    """Open the active project's AgentOS database only."""
    path = _db_path(root)
    if not path.exists():
        raise DatabaseBoundaryError(f"AgentOS database is missing: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migration_35(conn: sqlite3.Connection) -> None:
    """Apply additive schema 35 for database source/target boundaries."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS db_connections(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_uuid TEXT NOT NULL UNIQUE,
            connection_alias TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL,
            engine TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            database_name TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            credential_ref TEXT NOT NULL,
            tls_required INTEGER NOT NULL DEFAULT 1,
            readonly_verified INTEGER NOT NULL DEFAULT 0,
            readonly_verification_method TEXT,
            readonly_verified_by TEXT,
            readonly_verified_at TEXT,
            data_write_enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS db_consolidations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_connection_id INTEGER NOT NULL,
            domain_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(target_connection_id) REFERENCES db_connections(id)
        );
        CREATE TABLE IF NOT EXISTS db_consolidation_sources(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            source_connection_id INTEGER NOT NULL,
            readonly_verified_at_registration INTEGER NOT NULL,
            registered_by TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            FOREIGN KEY(consolidation_id) REFERENCES db_consolidations(id),
            FOREIGN KEY(source_connection_id) REFERENCES db_connections(id),
            UNIQUE(consolidation_id, source_connection_id)
        );
        CREATE TABLE IF NOT EXISTS db_boundary_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER,
            connection_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_db_connections_role_domain
            ON db_connections(role, domain_id, status);
        CREATE INDEX IF NOT EXISTS idx_db_consolidations_target
            ON db_consolidations(target_connection_id, status);
        CREATE INDEX IF NOT EXISTS idx_db_consolidation_sources
            ON db_consolidation_sources(consolidation_id, source_connection_id);
        """
    )


def sync_database_boundary_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema 35 and report required tables."""
    required = {"db_connections", "db_consolidations", "db_consolidation_sources", "db_boundary_events"}
    with _connect(root) as conn:
        migration_35(conn)
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"ok": required <= tables, "schema": SCHEMA_VERSION, "tables": sorted(required)}


def _event(conn: sqlite3.Connection, *, event_type: str, payload: Any, connection_id: int | None = None, consolidation_id: int | None = None) -> None:
    """Append local evidence for a boundary decision."""
    conn.execute(
        "INSERT INTO db_boundary_events(consolidation_id,connection_id,event_type,event_json,created_at) VALUES(?,?,?,?,?)",
        (consolidation_id, connection_id, event_type, _canonical_json(payload), utc_now()),
    )


def _validate_alias(alias: str) -> str:
    """Validate a stable human-readable connection alias."""
    value = alias.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,79}", value):
        raise DatabaseBoundaryError("connection_alias must be 2-80 safe identifier characters")
    return value


def _validate_credential_ref(value: str) -> str:
    """Accept secret references while rejecting embedded credentials/DSNs."""
    text = value.strip()
    lowered = text.lower()
    if not text.startswith(SECRET_REF_SCHEMES):
        raise DatabaseBoundaryError("credential_ref must use an approved reference scheme; raw credentials are forbidden")
    forbidden = ("password=", "pwd=", "user id=", "username=", "postgresql://", "mysql://", "oracle://", "sqlserver://")
    if any(token in lowered for token in forbidden) or "@" in text.split("://", 1)[-1]:
        raise DatabaseBoundaryError("credential_ref appears to contain a credential or DSN")
    return text


def _default_port(engine: str) -> int:
    return {"mysql": 3306, "mssql": 1433, "postgresql": 5432, "oracle": 1521}[engine]


def register_connection(
    root: Path | str,
    *,
    connection_alias: str,
    role: str,
    engine: str,
    host: str,
    database_name: str,
    domain_id: str,
    credential_ref: str,
    created_by: str,
    port: int | None = None,
    tls_required: bool = True,
) -> dict[str, Any]:
    """Register a SOURCE or TARGET endpoint without opening it or storing a secret.

    Args:
        root: Active AgentOS project root.
        connection_alias: Stable local alias.
        role: SOURCE or TARGET.
        engine: mysql, mssql, postgresql, or oracle.
        host: Database hostname/IP metadata.
        database_name: Database/service name metadata.
        domain_id: Business domain identifier shared by a consolidation.
        credential_ref: Reference to an external/local secret provider, never a raw credential.
        created_by: Human/operator identity.
        port: Optional TCP port; engine default is used when omitted.
        tls_required: Must remain true in v0.21.0.

    Returns:
        Registered connection metadata with secret reference redacted.
    """
    alias = _validate_alias(connection_alias)
    role_value = role.strip().upper()
    engine_value = engine.strip().lower()
    if role_value not in ROLES:
        raise DatabaseBoundaryError(f"unsupported role: {role}")
    if engine_value not in SUPPORTED_ENGINES:
        raise DatabaseBoundaryError(f"unsupported engine: {engine}")
    if not host.strip() or not database_name.strip() or not domain_id.strip() or not created_by.strip():
        raise DatabaseBoundaryError("host, database_name, domain_id, and created_by are required")
    if not tls_required:
        raise DatabaseBoundaryError("TLS is mandatory for registered network database endpoints")
    ref = _validate_credential_ref(credential_ref)
    resolved_port = int(port or _default_port(engine_value))
    if resolved_port <= 0 or resolved_port > 65535:
        raise DatabaseBoundaryError("invalid TCP port")
    now = utc_now()
    with _connect(root) as conn:
        migration_35(conn)
        try:
            cur = conn.execute(
                """INSERT INTO db_connections(
                    connection_uuid,connection_alias,role,engine,host,port,database_name,domain_id,
                    credential_ref,tls_required,readonly_verified,data_write_enabled,status,created_by,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), alias, role_value, engine_value, host.strip(), resolved_port, database_name.strip(), domain_id.strip(), ref, 1, 0, 0, "active", created_by.strip(), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise DatabaseBoundaryError(f"connection alias already exists: {alias}") from exc
        connection_id = int(cur.lastrowid)
        _event(conn, event_type="connection_registered", connection_id=connection_id, payload={"alias": alias, "role": role_value, "engine": engine_value, "domain_id": domain_id.strip(), "tls_required": True, "data_write_enabled": False})
    return get_connection(root, connection_id)


def verify_source_readonly(
    root: Path | str,
    connection_id: int,
    *,
    verified_by: str,
    method: str,
    evidence: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Record an explicit read-only attestation for a SOURCE without probing by write.

    Args:
        root: Active AgentOS root.
        connection_id: SOURCE connection id.
        verified_by: Human/operator performing verification.
        method: Approved verification method.
        evidence: Concise local evidence/reference; must not contain credentials.
        human_confirmed: Explicit confirmation gate.

    Returns:
        Updated connection metadata.
    """
    method_value = method.strip().lower()
    if not human_confirmed:
        raise DatabaseBoundaryError("human confirmation is required for SOURCE read-only verification")
    if method_value not in READONLY_VERIFICATION_METHODS:
        raise DatabaseBoundaryError(f"unsupported readonly verification method: {method}")
    if not verified_by.strip() or not evidence.strip():
        raise DatabaseBoundaryError("verified_by and evidence are required")
    _validate_no_secret_text(evidence)
    with _connect(root) as conn:
        migration_35(conn)
        row = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(connection_id),)).fetchone()
        if row is None:
            raise DatabaseBoundaryError("connection not found")
        if row["role"] != "SOURCE":
            raise DatabaseBoundaryError("read-only verification applies only to SOURCE connections")
        now = utc_now()
        conn.execute(
            "UPDATE db_connections SET readonly_verified=1,readonly_verification_method=?,readonly_verified_by=?,readonly_verified_at=?,updated_at=? WHERE id=?",
            (method_value, verified_by.strip(), now, now, int(connection_id)),
        )
        _event(conn, event_type="source_readonly_verified", connection_id=int(connection_id), payload={"method": method_value, "verified_by": verified_by.strip(), "evidence": evidence.strip(), "write_probe_used": False})
    return get_connection(root, int(connection_id))


def _validate_no_secret_text(value: str) -> None:
    """Reject likely credentials in evidence or operator notes."""
    lowered = value.lower()
    if any(token in lowered for token in ("password=", "pwd=", "authorization:", "bearer ", "api_key=", "apikey=")):
        raise DatabaseBoundaryError("evidence text appears to contain a secret")


def _row_to_connection(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["credential_ref"] = "<redacted-ref>"
    value["tls_required"] = bool(value["tls_required"])
    value["readonly_verified"] = bool(value["readonly_verified"])
    value["data_write_enabled"] = bool(value["data_write_enabled"])
    return value


def get_connection(root: Path | str, connection_id: int) -> dict[str, Any]:
    """Return connection metadata without revealing credential_ref."""
    with _connect(root) as conn:
        migration_35(conn)
        row = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(connection_id),)).fetchone()
        if row is None:
            raise DatabaseBoundaryError("connection not found")
    return {"ok": True, "connection": _row_to_connection(row)}


def create_consolidation(root: Path | str, *, target_connection_id: int, created_by: str) -> dict[str, Any]:
    """Create a database consolidation with exactly one TARGET and zero initial sources."""
    if not created_by.strip():
        raise DatabaseBoundaryError("created_by is required")
    with _connect(root) as conn:
        migration_35(conn)
        target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(target_connection_id),)).fetchone()
        if target is None:
            raise DatabaseBoundaryError("target connection not found")
        if target["role"] != "TARGET":
            raise DatabaseBoundaryError("target_connection_id must reference a TARGET connection")
        if target["status"] != "active":
            raise DatabaseBoundaryError("target connection is not active")
        if int(target["data_write_enabled"]) != 0:
            raise DatabaseBoundaryError("v0.21.0 target data_write_enabled must remain false")
        now = utc_now()
        cur = conn.execute(
            "INSERT INTO db_consolidations(target_connection_id,domain_id,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (int(target_connection_id), str(target["domain_id"]), "draft", created_by.strip(), now, now),
        )
        cid = int(cur.lastrowid)
        _event(conn, event_type="db_consolidation_created", consolidation_id=cid, connection_id=int(target_connection_id), payload={"target_connection_id": int(target_connection_id), "domain_id": str(target["domain_id"]), "target_data_write_enabled": False})
    return get_consolidation(root, cid)


def add_source(root: Path | str, consolidation_id: int, source_connection_id: int, *, registered_by: str) -> dict[str, Any]:
    """Attach a verified SOURCE to a consolidation without opening or modifying the source DB."""
    if not registered_by.strip():
        raise DatabaseBoundaryError("registered_by is required")
    with _connect(root) as conn:
        migration_35(conn)
        plan = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(consolidation_id),)).fetchone()
        if plan is None:
            raise DatabaseBoundaryError("database consolidation not found")
        if plan["status"] != "draft":
            raise DatabaseBoundaryError("sources can only be added while consolidation is draft")
        source = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(source_connection_id),)).fetchone()
        if source is None:
            raise DatabaseBoundaryError("source connection not found")
        if source["role"] != "SOURCE":
            raise DatabaseBoundaryError("source_connection_id must reference a SOURCE connection")
        if int(source["id"]) == int(plan["target_connection_id"]):
            raise DatabaseBoundaryError("a connection cannot be both SOURCE and TARGET in one consolidation")
        if not int(source["readonly_verified"]):
            raise DatabaseBoundaryError("SOURCE must be read-only verified before registration")
        if source["domain_id"] != plan["domain_id"]:
            raise DatabaseBoundaryError("SOURCE and TARGET business domains must match")
        try:
            conn.execute(
                "INSERT INTO db_consolidation_sources(consolidation_id,source_connection_id,readonly_verified_at_registration,registered_by,registered_at) VALUES(?,?,?,?,?)",
                (int(consolidation_id), int(source_connection_id), 1, registered_by.strip(), utc_now()),
            )
        except sqlite3.IntegrityError as exc:
            raise DatabaseBoundaryError("SOURCE is already registered in this consolidation") from exc
        _event(conn, event_type="source_registered", consolidation_id=int(consolidation_id), connection_id=int(source_connection_id), payload={"source_connection_id": int(source_connection_id), "readonly_verified": True, "domain_id": str(source["domain_id"])})
    return get_consolidation(root, int(consolidation_id))


def authorize_operation(root: Path | str, connection_id: int, operation: str) -> dict[str, Any]:
    """Authorize an abstract database operation under v0.21.0 boundary policy.

    Args:
        root: Active AgentOS root.
        connection_id: Registered database connection.
        operation: Abstract operation such as catalog_read or insert.

    Returns:
        Structured allow/deny decision. This function never executes SQL.
    """
    op = operation.strip().lower()
    with _connect(root) as conn:
        migration_35(conn)
        row = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(connection_id),)).fetchone()
        if row is None:
            raise DatabaseBoundaryError("connection not found")
        if row["status"] != "active":
            decision = {"ok": False, "allowed": False, "reason": "connection_not_active", "role": row["role"], "operation": op}
        elif row["role"] == "SOURCE":
            if not int(row["readonly_verified"]):
                decision = {"ok": False, "allowed": False, "reason": "source_not_readonly_verified", "role": "SOURCE", "operation": op}
            elif op in SOURCE_ALLOWED_OPERATIONS:
                decision = {"ok": True, "allowed": True, "reason": "source_read_only_operation", "role": "SOURCE", "operation": op}
            else:
                decision = {"ok": False, "allowed": False, "reason": "source_write_forbidden", "role": "SOURCE", "operation": op}
        elif row["role"] == "TARGET":
            if op in TARGET_ALLOWED_OPERATIONS_V0210:
                decision = {"ok": True, "allowed": True, "reason": "target_read_operation", "role": "TARGET", "operation": op}
            elif op in WRITE_OPERATIONS or op not in TARGET_ALLOWED_OPERATIONS_V0210:
                decision = {"ok": False, "allowed": False, "reason": "target_data_write_not_enabled_until_v0.22.0", "role": "TARGET", "operation": op}
            else:
                decision = {"ok": False, "allowed": False, "reason": "operation_denied", "role": "TARGET", "operation": op}
        else:
            decision = {"ok": False, "allowed": False, "reason": "unknown_role", "role": row["role"], "operation": op}
        _event(conn, event_type="operation_authorization", connection_id=int(connection_id), payload=decision)
    return decision


def get_consolidation(root: Path | str, consolidation_id: int) -> dict[str, Any]:
    """Return a database consolidation with redacted connection metadata."""
    with _connect(root) as conn:
        migration_35(conn)
        plan = conn.execute("SELECT * FROM db_consolidations WHERE id=?", (int(consolidation_id),)).fetchone()
        if plan is None:
            raise DatabaseBoundaryError("database consolidation not found")
        target = conn.execute("SELECT * FROM db_connections WHERE id=?", (int(plan["target_connection_id"]),)).fetchone()
        sources = conn.execute(
            """SELECT c.* FROM db_consolidation_sources s JOIN db_connections c ON c.id=s.source_connection_id
               WHERE s.consolidation_id=? ORDER BY s.id""",
            (int(consolidation_id),),
        ).fetchall()
    return {
        "ok": True,
        "consolidation": dict(plan),
        "target": _row_to_connection(target),
        "sources": [_row_to_connection(row) for row in sources],
        "invariants": {
            "exactly_one_target": True,
            "source_select_only": True,
            "source_write_forbidden": True,
            "target_data_write_enabled": False,
            "arbitrary_sql_exposed": False,
        },
    }


def docs_check_v0210(root: Path | str) -> dict[str, Any]:
    """Validate v0.21.0 version, bilingual landing docs, policy, and database schema."""
    root_path = Path(root).resolve()
    required = [
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        ".agents/docs/SOURCE_TARGET_DATABASE_BOUNDARY.md", ".agents/docs/USAGE_V0210.md",
    ]
    missing = [item for item in required if not (root_path / item).exists()]
    version = (root_path / "VERSION").read_text(encoding="utf-8").strip() if (root_path / "VERSION").exists() else None
    governance = json.loads((root_path / ".agents/config/governance.json").read_text(encoding="utf-8"))
    policy = governance.get("database_boundary_policy")
    schema = sync_database_boundary_schema(root_path)
    return {
        "ok": not missing and version == "0.21.0" and governance.get("version", governance.get("governance_version")) == "0.21.0" and isinstance(policy, dict) and schema["ok"],
        "missing": missing,
        "version": version,
        "governance_version": governance.get("version", governance.get("governance_version")),
        "database_schema": schema["schema"],
        "readme_language_links": all((root_path / name).exists() for name in ("README.vi.md", "README.en.md")),
    }
