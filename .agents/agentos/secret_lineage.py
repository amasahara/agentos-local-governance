"""
File: .agents/agentos/secret_lineage.py

Purpose:
    Provide the v0.22.6 trusted secret resolver registry and versioned lineage-key lifecycle.

Responsibilities:
    - Resolve credential references through built-in, hash-pinned, human-approved providers.
    - Keep credential values memory-only and redact resolver evidence.
    - Migrate the legacy single lineage key into a versioned keyring without re-HMACing history.
    - Rotate, retire, revoke, and inspect lineage keys under governed human workflows.
"""
from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import os
import secrets
import sqlite3
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from .database_boundary import authorize_operation
from .db import connect
from .governance_enforcement import governed_mutation, mirror_domain_event
from datetime import datetime, timezone


def utc_now() -> str:
    """Return one timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()

MIGRATION_VERSION = 42
PROVIDER_API_VERSION = "secret-resolver-v1"
KEYRING_DIR = ".agents/state/lineage-keys"
LEGACY_KEY_FILE = ".agents/state/identity_lineage.key"
SECRET_FILE_ROOT = ".agents/state/secrets"
ALLOWED_KEY_STATUS = {"active", "retired", "revoked"}
ALLOWED_SECRET_CAPABILITIES = {
    "db.source.select",
    "db.target.controlled_insert",
    "db.target.reconciliation_select",
    "process.exec.credential",
}


class SecretLineageError(RuntimeError):
    """Raised when secret or lineage-key governance fails closed."""


@dataclass(frozen=True)
class Provider:
    """Describe one statically registered trusted resolver implementation."""

    scheme: str
    provider_id: str
    version: str
    resolver: Callable[[Path, str, dict[str, Any]], dict[str, Any]]

    @property
    def implementation_hash(self) -> str:
        """Return a stable hash pin for the shipped provider implementation."""
        source = inspect.getsource(self.resolver).encode("utf-8")
        payload = b"\n".join((self.provider_id.encode(), self.version.encode(), source))
        return hashlib.sha256(payload).hexdigest()


def _json(value: Any) -> str:
    """Return canonical JSON used by plan and evidence hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    """Hash canonical JSON without exposing the value itself."""
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _add_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    """Add a column only when an older schema does not contain it."""
    cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def migration_42(conn: sqlite3.Connection) -> None:
    """Add persistent resolver approvals and lineage keyring metadata for schema 42."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS secret_resolver_approvals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id TEXT NOT NULL,
            scheme TEXT NOT NULL,
            provider_version TEXT NOT NULL,
            provider_hash TEXT NOT NULL,
            capabilities_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('approved','revoked')),
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            revoked_by TEXT,
            revoked_at TEXT,
            UNIQUE(provider_id,provider_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_secret_resolver_approvals_scheme
            ON secret_resolver_approvals(scheme,status);
        CREATE TABLE IF NOT EXISTS secret_resolver_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            provider_id TEXT,
            scheme TEXT,
            reference_hash TEXT,
            capability TEXT,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            governed_operation_id TEXT,
            external_event_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS lineage_keys(
            key_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK(status IN ('active','retired','revoked')),
            material_path TEXT NOT NULL,
            material_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            activated_at TEXT,
            retired_at TEXT,
            revoked_at TEXT,
            predecessor_key_id TEXT,
            rotation_plan_id INTEGER,
            provenance TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_lineage_one_active
            ON lineage_keys(status) WHERE status='active';
        CREATE TABLE IF NOT EXISTS lineage_key_rotation_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_uuid TEXT NOT NULL UNIQUE,
            predecessor_key_id TEXT NOT NULL,
            plan_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('planned','reviewed','approved','executed','cancelled')),
            reason_hash TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            executed_by TEXT,
            executed_at TEXT,
            new_key_id TEXT
        );
        CREATE TABLE IF NOT EXISTS lineage_rekey_plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_uuid TEXT NOT NULL UNIQUE,
            source_connection_id INTEGER NOT NULL,
            from_key_id TEXT NOT NULL,
            to_key_id TEXT NOT NULL,
            plan_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('planned','reviewed','approved','ready_for_source_reread','completed','cancelled')),
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            completed_at TEXT
        );
        """
    )
    for table in ("identity_resolution_runs", "canonical_entities", "identity_bindings", "identity_candidates", "target_record_lineage"):
        _add_column(conn, table, "key_id", "TEXT")
    _add_column(conn, "target_record_lineage", "source_key_id", "TEXT")
    _add_column(conn, "target_record_lineage", "target_key_id", "TEXT")


def sync_schema(root: Path | str) -> dict[str, Any]:
    """Ensure schema 42 is available through the unified database connection."""
    with connect(Path(root).resolve()) as conn:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return {"ok": int(row[0] or 0) >= MIGRATION_VERSION, "schema": int(row[0] or 0)}


def _event(root: Path, event_type: str, *, provider: Provider | None = None, ref: str | None = None,
           capability: str | None = None, payload: dict[str, Any] | None = None) -> None:
    """Persist redacted event metadata and mirror it into signed external audit."""
    safe = dict(payload or {})
    forbidden = {"secret", "credential", "password", "token", "value", "dsn", "raw"}
    if any(k.lower() in forbidden for k in safe):
        raise SecretLineageError("sensitive resolver event payload rejected")
    mirror = mirror_domain_event(event_type, safe)
    with connect(root) as conn:
        conn.execute(
            """INSERT INTO secret_resolver_events(event_type,provider_id,scheme,reference_hash,capability,event_json,created_at,governed_operation_id,external_event_hash)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (event_type, provider.provider_id if provider else None, provider.scheme if provider else None,
             hashlib.sha256(ref.encode()).hexdigest() if ref else None, capability, _json(safe), utc_now(),
             mirror.get("governed_operation_id"), mirror.get("external_event_hash")),
        )


def _env_provider(root: Path, target: str, options: dict[str, Any]) -> dict[str, Any]:
    """Resolve an env://NAME reference containing one JSON object."""
    del root, options
    name = target.strip("/")
    if not name or name not in os.environ:
        raise SecretLineageError("env secret is unavailable")
    try:
        value = json.loads(os.environ[name])
    except json.JSONDecodeError as exc:
        raise SecretLineageError("env secret must contain one JSON object") from exc
    if not isinstance(value, dict):
        raise SecretLineageError("env secret must resolve to an object")
    return value


def _keychain_provider(root: Path, target: str, options: dict[str, Any]) -> dict[str, Any]:
    """Resolve keychain://service/account using the optional keyring package."""
    del root, options
    parts = [unquote(x) for x in target.strip("/").split("/", 1)]
    if len(parts) != 2 or not all(parts):
        raise SecretLineageError("keychain reference must be keychain://service/account")
    try:
        import keyring  # type: ignore
    except ImportError as exc:
        raise SecretLineageError("trusted keychain provider dependency is unavailable") from exc
    raw = keyring.get_password(parts[0], parts[1])
    if raw is None:
        raise SecretLineageError("keychain secret is unavailable")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretLineageError("keychain secret must contain one JSON object") from exc
    if not isinstance(value, dict):
        raise SecretLineageError("keychain secret must resolve to an object")
    return value


def _vault_provider(root: Path, target: str, options: dict[str, Any]) -> dict[str, Any]:
    """Resolve vault://mount/path#field with hvac and memory-only Vault credentials."""
    del root
    try:
        import hvac  # type: ignore
    except ImportError as exc:
        raise SecretLineageError("trusted vault provider dependency is unavailable") from exc
    mount, sep, path = target.strip("/").partition("/")
    if not sep or not mount or not path:
        raise SecretLineageError("vault reference must include mount/path")
    client = hvac.Client(url=os.environ.get("VAULT_ADDR"), token=os.environ.get("VAULT_TOKEN"))
    if not client.is_authenticated():
        raise SecretLineageError("vault authentication failed")
    response = client.secrets.kv.v2.read_secret_version(path=path, mount_point=mount)
    data = response.get("data", {}).get("data", {})
    field = options.get("fragment")
    value = data.get(field) if field else data
    if field and isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SecretLineageError("vault selected field must contain one JSON object") from exc
    if not isinstance(value, dict):
        raise SecretLineageError("vault secret must resolve to an object")
    return value


def _file_provider(root: Path, target: str, options: dict[str, Any]) -> dict[str, Any]:
    """Resolve owner-only JSON files under .agents/state/secrets only."""
    del options
    base = (root / SECRET_FILE_ROOT).resolve()
    path = (base / unquote(target.strip("/"))).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise SecretLineageError("file-secret escaped the dedicated secret root") from exc
    if not path.is_file():
        raise SecretLineageError("file-secret is unavailable")
    mode = stat.S_IMODE(path.stat().st_mode)
    if os.name != "nt" and mode & 0o077:
        raise SecretLineageError("file-secret permissions must be owner-only")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SecretLineageError("file-secret must resolve to an object")
    return value


PROVIDERS: dict[str, Provider] = {
    p.scheme: p
    for p in (
        Provider("env", "agentos.builtin.env_json", "1", _env_provider),
        Provider("keychain", "agentos.builtin.os_keychain_json", "1", _keychain_provider),
        Provider("vault", "agentos.builtin.hashicorp_vault_kv2", "1", _vault_provider),
        Provider("file-secret", "agentos.builtin.local_file_json", "1", _file_provider),
    )
}


def provider_catalog() -> list[dict[str, Any]]:
    """Return public resolver identities and pins without credentials."""
    return [
        {"scheme": p.scheme, "provider_id": p.provider_id, "version": p.version, "provider_hash": p.implementation_hash}
        for p in sorted(PROVIDERS.values(), key=lambda x: x.scheme)
    ]


@governed_mutation("secret.resolver.approve")
def approve_provider(root: Path | str, scheme: str, *, capabilities: list[str], approved_by: str,
                     human_confirmed: bool) -> dict[str, Any]:
    """Human-approve one shipped provider identity/hash for bounded capabilities."""
    if not human_confirmed or not approved_by.strip():
        raise SecretLineageError("human-confirmed provider approval is required")
    provider = PROVIDERS.get(scheme.lower())
    if provider is None:
        raise SecretLineageError("resolver scheme is not in the trusted built-in registry")
    caps = sorted({str(x).strip() for x in capabilities if str(x).strip()})
    if not caps:
        raise SecretLineageError("at least one resolver capability is required")
    unknown = sorted(set(caps) - ALLOWED_SECRET_CAPABILITIES)
    if unknown:
        raise SecretLineageError("resolver capability is not in the production allowlist: " + ",".join(unknown))
    with connect(Path(root).resolve()) as conn:
        migration_42(conn)
        conn.execute(
            """INSERT INTO secret_resolver_approvals(provider_id,scheme,provider_version,provider_hash,capabilities_json,status,approved_by,approved_at)
               VALUES(?,?,?,?,?,'approved',?,?)
               ON CONFLICT(provider_id,provider_hash) DO UPDATE SET capabilities_json=excluded.capabilities_json,status='approved',approved_by=excluded.approved_by,approved_at=excluded.approved_at,revoked_by=NULL,revoked_at=NULL""",
            (provider.provider_id, provider.scheme, provider.version, provider.implementation_hash, _json(caps), approved_by.strip(), utc_now()),
        )
    _event(Path(root).resolve(), "secret_resolver_provider_approved", provider=provider, capability="operator_approval",
           payload={"provider_hash": provider.implementation_hash, "capability_count": len(caps)})
    return {"ok": True, "provider": provider_catalog_item(provider), "capabilities": caps, "secret_included": False}


def provider_catalog_item(provider: Provider) -> dict[str, Any]:
    """Render one non-sensitive provider descriptor."""
    return {"scheme": provider.scheme, "provider_id": provider.provider_id, "version": provider.version, "provider_hash": provider.implementation_hash}


@governed_mutation("secret.resolver.revoke")
def revoke_provider(root: Path | str, scheme: str, *, revoked_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Revoke a previously approved provider pin."""
    if not human_confirmed or not revoked_by.strip():
        raise SecretLineageError("human-confirmed provider revocation is required")
    provider = PROVIDERS.get(scheme.lower())
    if provider is None:
        raise SecretLineageError("resolver scheme is not trusted")
    with connect(Path(root).resolve()) as conn:
        cur = conn.execute(
            "UPDATE secret_resolver_approvals SET status='revoked',revoked_by=?,revoked_at=? WHERE provider_id=? AND provider_hash=? AND status='approved'",
            (revoked_by.strip(), utc_now(), provider.provider_id, provider.implementation_hash),
        )
        if cur.rowcount != 1:
            raise SecretLineageError("active provider approval not found")
    _event(Path(root).resolve(), "secret_resolver_provider_revoked", provider=provider, payload={"revoked": True})
    return {"ok": True, "provider": provider_catalog_item(provider), "revoked": True}


def _resolve_alias(root: Path, alias: str) -> str:
    """Resolve secret://alias from governance metadata without allowing code references."""
    cfg_path = root / ".agents/config/governance.json"
    if not cfg_path.is_file():
        raise SecretLineageError("secret alias configuration is unavailable")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    aliases = cfg.get("secret_resolver_policy", {}).get("aliases", {})
    ref = aliases.get(alias)
    if not isinstance(ref, str) or "://" not in ref:
        raise SecretLineageError("secret alias is undefined")
    if "module:" in ref or "function:" in ref or "importlib" in ref:
        raise SecretLineageError("dynamic resolver references are forbidden")
    return ref


def _approved(root: Path, provider: Provider, capability: str) -> bool:
    """Check exact provider identity/version/hash and capability approval."""
    with connect(root) as conn:
        migration_42(conn)
        row = conn.execute(
            """SELECT capabilities_json FROM secret_resolver_approvals
               WHERE provider_id=? AND scheme=? AND provider_version=? AND provider_hash=? AND status='approved' ORDER BY id DESC LIMIT 1""",
            (provider.provider_id, provider.scheme, provider.version, provider.implementation_hash),
        ).fetchone()
    return bool(row and capability in json.loads(row[0]))


def resolve_secret(root: Path | str, credential_ref: str, *, capability: str) -> dict[str, Any]:
    """Resolve one trusted URI in memory; persist only redacted resolver evidence."""
    root_path = Path(root).resolve()
    ref = str(credential_ref).strip()

    if not ref or "://" not in ref:
        raise SecretLineageError(
            "credential reference must use an approved URI scheme"
        )

    parsed = urlparse(ref)

    if parsed.scheme == "secret":
        alias = (
            parsed.netloc
            + parsed.path
        ).strip("/")
        if not alias:
            raise SecretLineageError(
                "secret alias is empty"
            )
        ref = _resolve_alias(
            root_path,
            alias,
        )
        parsed = urlparse(ref)

    provider = PROVIDERS.get(
        parsed.scheme.lower()
    )
    if provider is None:
        raise SecretLineageError(
            "resolver is missing or is not in the trusted allowlist"
        )

    if (
        capability
        == "process.exec.credential"
        and os.name == "nt"
        and provider.scheme == "file-secret"
    ):
        raise SecretLineageError(
            "Windows file-secret process credential projection "
            "requires a future ACL attestation"
        )

    if not _approved(
        root_path,
        provider,
        capability,
    ):
        raise SecretLineageError(
            "resolver provider pin/capability is not human-approved"
        )

    target = (
        parsed.netloc
        + parsed.path
    ).lstrip("/")

    value = provider.resolver(
        root_path,
        target,
        {
            "fragment": parsed.fragment,
        },
    )

    if not isinstance(value, dict):
        raise SecretLineageError(
            "trusted resolver returned an invalid credential object"
        )

    _event(
        root_path,
        "secret_resolved",
        provider=provider,
        ref=credential_ref,
        capability=capability,
        payload={
            "resolved": True,
            "field_count": len(value),
            "secret_included": False,
        },
    )

    return value

def _is_governed_root(root: Path) -> bool:
    """Return whether callback injection must be denied for a production AgentOS root."""
    return (root / "AGENTS.md").is_file() and (root / "VERSION").is_file() and (root / ".agents/config/governance.json").is_file()


def resolve_runtime_secret(
    root: Path | str,
    credential_ref: str,
    *,
    capability: str,
    compatibility_resolver: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a pipeline credential while rejecting injected callbacks on governed roots.

    ``compatibility_resolver`` exists only to preserve the v0.22.5 library/test adapter
    contract for minimal, non-governed roots. Production AgentOS projects always use
    the static trusted registry and its exact provider identity/version/hash approval.
    """
    root_path = Path(root).resolve()
    if capability not in ALLOWED_SECRET_CAPABILITIES:
        raise SecretLineageError("secret capability is not in the production allowlist")
    if compatibility_resolver is not None:
        if _is_governed_root(root_path):
            raise SecretLineageError("external secret resolver callback injection is forbidden for governed AgentOS roots")
        value = compatibility_resolver(str(credential_ref))
        if not isinstance(value, dict):
            raise SecretLineageError("compatibility secret resolver returned an invalid credential object")
        return value
    return resolve_secret(root_path, credential_ref, capability=capability)


def _key_path(root: Path, key_id: str) -> Path:
    """Return an owner-local lineage material path."""
    return (root / KEYRING_DIR / f"{key_id}.key").resolve()


def _write_key(path: Path, material: bytes) -> None:
    """Create exact binary key material and verify the persisted bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    with path.open("xb") as handle:
        handle.write(material)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        path.chmod(0o600)
    except OSError:
        pass
    persisted = path.read_bytes()
    if persisted != material or hashlib.sha256(persisted).digest() != hashlib.sha256(material).digest():
        try:
            path.unlink()
        except OSError:
            pass
        raise SecretLineageError("lineage key bytes changed during persistence")


def _new_key_id(material: bytes) -> str:
    """Derive a non-secret stable identifier from key material."""
    return "lk_" + hashlib.sha256(material).hexdigest()[:24]


def _has_historical_identity(conn: sqlite3.Connection) -> bool:
    """Detect history that requires the legacy material to remain verifiable."""
    for table in ("canonical_entities", "identity_bindings", "target_record_lineage"):
        if int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]):
            return True
    return False


def _recover_unregistered_key(root: Path) -> tuple[bytes, Path] | None:
    """Recover one crash-left key file only when its filename matches its material hash.

    This makes legacy-key migration and first initialization restart-safe without
    guessing between multiple orphaned materials. No database row is created here.
    """
    base = (root / KEYRING_DIR).resolve()
    if not base.is_dir():
        return None
    candidates: list[tuple[bytes, Path]] = []
    for path in sorted(base.glob("lk_*.key")):
        try:
            material = path.read_bytes()
        except OSError:
            continue
        if len(material) < 32 or path.stem != _new_key_id(material):
            continue
        candidates.append((material, path.resolve()))
    if not candidates:
        return None
    if len(candidates) != 1:
        raise SecretLineageError("multiple unregistered lineage key materials require operator recovery")
    return candidates[0]


@governed_mutation("identity.lineage.key.initialize")
def ensure_keyring(root: Path | str) -> dict[str, Any]:
    """Initialize the versioned keyring without changing historical HMACs.

    If a legacy ``identity_lineage.key`` exists, its exact bytes are atomically moved
    into the versioned keyring and historical rows are backfilled with only ``key_id``.
    No historical fingerprint/token is recomputed.
    """
    root_path = Path(root).resolve()
    with connect(root_path) as conn:
        migration_42(conn)
        row = conn.execute("SELECT * FROM lineage_keys WHERE status='active'").fetchone()
        if row is not None:
            return _key_metadata(row)
        legacy = root_path / LEGACY_KEY_FILE
        recovered = None if legacy.exists() else _recover_unregistered_key(root_path)
        if legacy.exists():
            material = legacy.read_bytes()
            provenance = "legacy_v0221_import"
        elif recovered is not None:
            material, recovered_path = recovered
            provenance = "legacy_v0221_import_recovered" if _has_historical_identity(conn) else "v0226_initial_recovered"
        else:
            if _has_historical_identity(conn):
                raise SecretLineageError("historical lineage exists but legacy key material is unavailable")
            material = secrets.token_bytes(32)
            provenance = "v0226_initial"
        if len(material) < 32:
            raise SecretLineageError("lineage key material is invalid")
        key_id = _new_key_id(material)
        path = recovered_path if recovered is not None else _key_path(root_path, key_id)
        if path != _key_path(root_path, key_id):
            raise SecretLineageError("recovered lineage key path does not match its key_id")
        if legacy.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.parent.chmod(0o700)
            except OSError:
                pass
            if path.exists():
                if path.read_bytes() != material:
                    raise SecretLineageError("versioned lineage key path conflicts with legacy key material")
                legacy.unlink()
            else:
                os.replace(legacy, path)
                try:
                    path.chmod(0o600)
                except OSError:
                    pass
        elif not path.exists():
            _write_key(path, material)
        conn.execute(
            """INSERT OR IGNORE INTO lineage_keys(key_id,status,material_path,material_hash,created_at,activated_at,provenance)
               VALUES(?,'active',?,?,?,?,?)""",
            (key_id, str(path.relative_to(root_path)), hashlib.sha256(material).hexdigest(), utc_now(), utc_now(), provenance),
        )
        for table in ("identity_resolution_runs", "canonical_entities", "identity_bindings", "identity_candidates", "target_record_lineage"):
            conn.execute(f"UPDATE {table} SET key_id=? WHERE key_id IS NULL", (key_id,))
        conn.execute("UPDATE target_record_lineage SET source_key_id=COALESCE(source_key_id,key_id), target_key_id=COALESCE(target_key_id,key_id)")
        row = conn.execute("SELECT * FROM lineage_keys WHERE key_id=?", (key_id,)).fetchone()
    return _key_metadata(row)


def _key_metadata(row: sqlite3.Row) -> dict[str, Any]:
    """Return key metadata without material or material path."""
    return {"key_id": str(row["key_id"]), "status": str(row["status"]), "created_at": str(row["created_at"]),
            "activated_at": row["activated_at"], "retired_at": row["retired_at"], "revoked_at": row["revoked_at"],
            "predecessor_key_id": row["predecessor_key_id"]}


def keyring_status(root: Path | str) -> dict[str, Any]:
    """Return public key metadata without initializing or loading key material."""
    root_path = Path(root).resolve()
    with connect(root_path) as conn:
        rows = conn.execute("SELECT * FROM lineage_keys ORDER BY created_at,key_id").fetchall()
    return {
        "ok": True,
        "initialized": bool(rows),
        "keys": [_key_metadata(r) for r in rows],
        "material_included": False,
        "legacy_key_present": (root_path / LEGACY_KEY_FILE).is_file(),
    }


def load_key(root: Path | str, key_id: str, *, allow_retired: bool = True) -> bytes:
    """Load key material into memory only when its lifecycle permits verification."""
    root_path = Path(root).resolve()
    with connect(root_path) as conn:
        row = conn.execute("SELECT * FROM lineage_keys WHERE key_id=?", (str(key_id),)).fetchone()
    if row is None or row["status"] == "revoked" or (row["status"] == "retired" and not allow_retired):
        raise SecretLineageError("lineage key is unavailable for this operation")
    path = (root_path / str(row["material_path"])).resolve()
    expected_path = _key_path(root_path, str(key_id))
    if path != expected_path:
        raise SecretLineageError("lineage key material path is outside the trusted keyring layout")
    material = path.read_bytes() if path.is_file() else b""
    if not material or _new_key_id(material) != str(key_id) or hashlib.sha256(material).hexdigest() != row["material_hash"]:
        raise SecretLineageError("lineage key material hash mismatch")
    return material


def active_key(root: Path | str) -> tuple[str, bytes]:
    """Return active key id and material for new tokens."""
    meta = ensure_keyring(root)
    return meta["key_id"], load_key(root, meta["key_id"], allow_retired=False)


def lookup_keys(root: Path | str) -> list[tuple[str, bytes]]:
    """Return active+retired keys for deterministic lookup; revoked keys are excluded."""
    ensure_keyring(root)
    with connect(Path(root).resolve()) as conn:
        rows = conn.execute("SELECT key_id FROM lineage_keys WHERE status IN ('active','retired') ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,created_at DESC").fetchall()
    return [(str(r[0]), load_key(root, str(r[0]))) for r in rows]


@governed_mutation("identity.lineage.key.rotate.plan")
def create_rotation_plan(root: Path | str, *, reason: str, created_by: str) -> dict[str, Any]:
    """Create an immutable lineage-key rotation plan; no new key material exists yet."""
    if not reason.strip() or not created_by.strip():
        raise SecretLineageError("rotation reason and creator are required")
    active = ensure_keyring(root)
    payload = {"predecessor_key_id": active["key_id"], "reason_hash": hashlib.sha256(reason.encode()).hexdigest(), "nonce": uuid.uuid4().hex}
    plan_hash = _sha(payload)
    with connect(Path(root).resolve()) as conn:
        cur = conn.execute(
            """INSERT INTO lineage_key_rotation_plans(plan_uuid,predecessor_key_id,plan_hash,status,reason_hash,created_by,created_at)
               VALUES(?,?,?,'planned',?,?,?)""",
            (uuid.uuid4().hex, active["key_id"], plan_hash, payload["reason_hash"], created_by.strip(), utc_now()),
        )
        plan_id = int(cur.lastrowid)
    _event(Path(root).resolve(), "lineage_key_rotation_planned", payload={"plan_id": plan_id, "predecessor_key_id": active["key_id"], "plan_hash": plan_hash})
    return rotation_plan_get(root, plan_id)


@governed_mutation("identity.lineage.key.rotate.review")
def review_rotation_plan(root: Path | str, plan_id: int, *, reviewed_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Record human review of the exact immutable plan hash."""
    if not human_confirmed or not reviewed_by.strip():
        raise SecretLineageError("human review is required")
    with connect(Path(root).resolve()) as conn:
        cur = conn.execute("UPDATE lineage_key_rotation_plans SET status='reviewed',reviewed_by=?,reviewed_at=? WHERE id=? AND status='planned'", (reviewed_by.strip(), utc_now(), int(plan_id)))
        if cur.rowcount != 1:
            raise SecretLineageError("rotation plan is not reviewable")
    _event(Path(root).resolve(), "lineage_key_rotation_reviewed", payload={"plan_id": int(plan_id), "reviewed": True})
    return rotation_plan_get(root, plan_id)


@governed_mutation("identity.lineage.key.rotate.approve")
def approve_rotation_plan(root: Path | str, plan_id: int, *, approved_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Human-approve the reviewed immutable rotation plan."""
    if not human_confirmed or not approved_by.strip():
        raise SecretLineageError("human approval is required")
    with connect(Path(root).resolve()) as conn:
        cur = conn.execute("UPDATE lineage_key_rotation_plans SET status='approved',approved_by=?,approved_at=? WHERE id=? AND status='reviewed'", (approved_by.strip(), utc_now(), int(plan_id)))
        if cur.rowcount != 1:
            raise SecretLineageError("rotation plan is not approvable")
    _event(Path(root).resolve(), "lineage_key_rotation_approved", payload={"plan_id": int(plan_id), "approved": True})
    return rotation_plan_get(root, plan_id)


@governed_mutation("identity.lineage.key.rotate.execute")
def execute_rotation_plan(root: Path | str, plan_id: int, *, executed_by: str) -> dict[str, Any]:
    """Retire the old key and create exactly one new active key after approval."""
    if not executed_by.strip():
        raise SecretLineageError("rotation executor is required")
    root_path = Path(root).resolve()
    with connect(root_path) as conn:
        plan = conn.execute("SELECT * FROM lineage_key_rotation_plans WHERE id=?", (int(plan_id),)).fetchone()
        active = conn.execute("SELECT * FROM lineage_keys WHERE status='active'").fetchone()
        if plan is None or plan["status"] != "approved" or active is None or active["key_id"] != plan["predecessor_key_id"]:
            raise SecretLineageError("approved rotation plan no longer matches the active key")
        material = secrets.token_bytes(32)
        key_id = _new_key_id(material)
        path = _key_path(root_path, key_id)
        _write_key(path, material)
        now = utc_now()
        conn.execute("UPDATE lineage_keys SET status='retired',retired_at=? WHERE key_id=? AND status='active'", (now, active["key_id"]))
        conn.execute(
            """INSERT INTO lineage_keys(key_id,status,material_path,material_hash,created_at,activated_at,predecessor_key_id,rotation_plan_id,provenance)
               VALUES(?,'active',?,?,?,?,?,?,?)""",
            (key_id, str(path.relative_to(root_path)), hashlib.sha256(material).hexdigest(), now, now, active["key_id"], int(plan_id), "human_approved_rotation"),
        )
        conn.execute("UPDATE lineage_key_rotation_plans SET status='executed',executed_by=?,executed_at=?,new_key_id=? WHERE id=?", (executed_by.strip(), now, key_id, int(plan_id)))
    _event(root_path, "lineage_key_rotated", payload={"plan_id": int(plan_id), "predecessor_key_id": active["key_id"], "new_key_id": key_id})
    return rotation_plan_get(root_path, plan_id)


@governed_mutation("identity.lineage.key.revoke")
def revoke_key(root: Path | str, key_id: str, *, revoked_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Revoke a retired key; active-key revocation is refused to avoid implicit rotation."""
    if not human_confirmed or not revoked_by.strip():
        raise SecretLineageError("human-confirmed revocation is required")
    with connect(Path(root).resolve()) as conn:
        row = conn.execute("SELECT status FROM lineage_keys WHERE key_id=?", (str(key_id),)).fetchone()
        if row is None or row[0] != "retired":
            raise SecretLineageError("only retired keys can be revoked")
        conn.execute("UPDATE lineage_keys SET status='revoked',revoked_at=? WHERE key_id=?", (utc_now(), str(key_id)))
    _event(Path(root).resolve(), "lineage_key_revoked", payload={"key_id": str(key_id), "revoked": True})
    return keyring_status(root)


def rotation_plan_get(root: Path | str, plan_id: int) -> dict[str, Any]:
    """Read one rotation plan without sensitive material."""
    with connect(Path(root).resolve()) as conn:
        row = conn.execute("SELECT * FROM lineage_key_rotation_plans WHERE id=?", (int(plan_id),)).fetchone()
    if row is None:
        raise SecretLineageError("rotation plan not found")
    return {"ok": True, "plan": dict(row), "material_included": False}


@governed_mutation("identity.lineage.rekey.plan")
def create_rekey_plan(root: Path | str, *, source_connection_id: int, from_key_id: str, created_by: str) -> dict[str, Any]:
    """Plan a rekey that can only proceed by governed SOURCE re-read of raw identifiers."""
    active = ensure_keyring(root)
    if from_key_id == active["key_id"]:
        raise SecretLineageError("rekey source key must differ from active key")
    if not created_by.strip():
        raise SecretLineageError("rekey creator is required")
    decision = authorize_operation(root, int(source_connection_id), "select_read")
    if not decision.get("allowed") or decision.get("role") != "SOURCE":
        raise SecretLineageError("rekey SOURCE SELECT authority is not available")
    payload = {"source_connection_id": int(source_connection_id), "from_key_id": from_key_id, "to_key_id": active["key_id"]}
    plan_hash = _sha(payload)
    with connect(Path(root).resolve()) as conn:
        cur = conn.execute(
            """INSERT INTO lineage_rekey_plans(plan_uuid,source_connection_id,from_key_id,to_key_id,plan_hash,status,created_by,created_at)
               VALUES(?,?,?,?,?,'planned',?,?)""",
            (uuid.uuid4().hex, int(source_connection_id), from_key_id, active["key_id"], plan_hash, created_by.strip(), utc_now()),
        )
        return rekey_plan_get(root, int(cur.lastrowid))


@governed_mutation("identity.lineage.rekey.review")
def review_rekey_plan(root: Path | str, plan_id: int, *, reviewed_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Human-review a SOURCE-reread rekey plan."""
    if not human_confirmed or not reviewed_by.strip():
        raise SecretLineageError("human review is required")
    with connect(Path(root).resolve()) as conn:
        if conn.execute("UPDATE lineage_rekey_plans SET status='reviewed',reviewed_by=?,reviewed_at=? WHERE id=? AND status='planned'", (reviewed_by.strip(), utc_now(), int(plan_id))).rowcount != 1:
            raise SecretLineageError("rekey plan is not reviewable")
    return rekey_plan_get(root, plan_id)


@governed_mutation("identity.lineage.rekey.approve")
def approve_rekey_plan(root: Path | str, plan_id: int, *, approved_by: str, human_confirmed: bool) -> dict[str, Any]:
    """Human-approve rekey while preserving the requirement to re-read SOURCE."""
    if not human_confirmed or not approved_by.strip():
        raise SecretLineageError("human approval is required")
    with connect(Path(root).resolve()) as conn:
        if conn.execute("UPDATE lineage_rekey_plans SET status='approved',approved_by=?,approved_at=? WHERE id=? AND status='reviewed'", (approved_by.strip(), utc_now(), int(plan_id))).rowcount != 1:
            raise SecretLineageError("rekey plan is not approvable")
    return rekey_plan_get(root, plan_id)


@governed_mutation("identity.lineage.rekey.authorize_source_reread")
def authorize_rekey_source_reread(root: Path | str, plan_id: int) -> dict[str, Any]:
    """Re-check SOURCE SELECT authority and mark the plan ready; never reconstruct HMACs from hashes alone."""
    plan = rekey_plan_get(root, plan_id)["plan"]
    if plan["status"] != "approved":
        raise SecretLineageError("approved rekey plan is required")
    decision = authorize_operation(root, int(plan["source_connection_id"]), "select_read")
    if not decision.get("allowed") or decision.get("role") != "SOURCE":
        raise SecretLineageError("SOURCE SELECT re-read is not authorized")
    with connect(Path(root).resolve()) as conn:
        conn.execute("UPDATE lineage_rekey_plans SET status='ready_for_source_reread' WHERE id=? AND status='approved'", (int(plan_id),))
    _event(Path(root).resolve(), "lineage_rekey_source_reread_authorized", payload={"plan_id": int(plan_id), "source_connection_id": int(plan["source_connection_id"]), "raw_identifier_required": True})
    return {**rekey_plan_get(root, plan_id), "raw_identifier_required": True, "historical_rehmac_without_raw_forbidden": True}


def rekey_plan_get(root: Path | str, plan_id: int) -> dict[str, Any]:
    """Read rekey metadata; raw identifiers are never stored in the plan."""
    with connect(Path(root).resolve()) as conn:
        row = conn.execute("SELECT * FROM lineage_rekey_plans WHERE id=?", (int(plan_id),)).fetchone()
    if row is None:
        raise SecretLineageError("rekey plan not found")
    return {"ok": True, "plan": dict(row), "raw_identifier_included": False}
