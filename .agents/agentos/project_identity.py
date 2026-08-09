"""
File: .agents/agentos/project_identity.py

Purpose:
    Provide stable project identity, local instance identity, project-purpose
    contracts, clone/fork detection, schema-32 migration helpers, and local
    registry enforcement for AgentOS v0.20.0.

Responsibilities:
    - Keep project UUID stable across directory relocation.
    - Give each working copy an instance UUID stored outside committed config.
    - Detect accidental directory copies that duplicate an instance UUID.
    - Require explicit human confirmation before purpose or fork mutations.
    - Persist project purpose as business-domain metadata.
    - Provide additive SQLite migration 32 without removing v0.19.5 data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Iterable
from uuid import UUID, uuid4

IDENTITY_VERSION = 1
SCHEMA_VERSION = 32
MIGRATION_VERSION = SCHEMA_VERSION  # unified CLI compatibility alias
PROJECT_ID_REL = Path(".agents/config/project.id")
PURPOSE_REL = Path(".agents/config/project.purpose.json")
INSTANCE_ID_REL = Path(".agents/state/project.instance.json")
IDENTITY_EVENTS_REL = Path(".agents/state/project_identity_events.jsonl")
ROLE_VALUES = {
    "core_application",
    "integration_adapter",
    "service",
    "library",
    "data_pipeline",
    "governance_platform",
    "other",
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class ProjectIdentityError(RuntimeError):
    """Raised when a project identity operation violates the v0.20.0 contract."""


@dataclass(frozen=True)
class IdentityPaths:
    """Resolved identity-related paths for one AgentOS project.

    Args:
        root: Project root containing `.agents/`.

    Returns:
        Dataclass fields point to project, purpose, instance, and event files.
    """

    root: Path
    project_id: Path
    purpose: Path
    instance_id: Path
    events: Path


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp in stable ISO-8601 form."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def paths_for(root: Path | str) -> IdentityPaths:
    """Resolve identity file locations under a project root.

    Args:
        root: Project root path.

    Returns:
        IdentityPaths with absolute normalized paths.
    """
    resolved = Path(root).resolve()
    return IdentityPaths(
        root=resolved,
        project_id=resolved / PROJECT_ID_REL,
        purpose=resolved / PURPOSE_REL,
        instance_id=resolved / INSTANCE_ID_REL,
        events=resolved / IDENTITY_EVENTS_REL,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_payload(value: dict[str, Any], hash_key: str) -> str:
    clean = dict(value)
    clean.pop(hash_key, None)
    return hashlib.sha256(_canonical_json(clean).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectIdentityError(f"missing identity file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectIdentityError(f"invalid JSON in identity file: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectIdentityError(f"identity file must contain a JSON object: {path}")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _validate_uuid(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise ProjectIdentityError(f"{field} must be a UUID string")
    try:
        UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ProjectIdentityError(f"{field} is not a valid UUID: {value!r}") from exc
    return value


def _is_uuid_string(value: str) -> bool:
    """Return whether a string is a syntactically valid UUID."""
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _validate_slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise ProjectIdentityError(
            f"{field} must use lowercase snake_case business identifiers, got {value!r}"
        )
    return value


def _normalize_capabilities(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _validate_slug(str(raw).strip(), "capability")
        if value not in seen:
            result.append(value)
            seen.add(value)
    if not result:
        raise ProjectIdentityError("at least one project capability is required")
    return result


def _registry_home(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    configured = os.environ.get("AGENTOS_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".agentos").resolve()


def _registry_path(explicit: Path | str | None = None) -> Path:
    return _registry_home(explicit) / "projects" / "registry.json"


def _with_registry_lock(path: Path, timeout_seconds: float = 3.0):
    class _Lock:
        def __init__(self) -> None:
            self.lock_path = path.with_suffix(path.suffix + ".lock")
            self.fd: int | None = None

        def __enter__(self):
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    self.fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.write(self.fd, f"pid={os.getpid()} at={utc_now()}\n".encode())
                    return self
                except FileExistsError:
                    try:
                        stale = time.time() - self.lock_path.stat().st_mtime > 30
                    except FileNotFoundError:
                        continue
                    if stale:
                        try:
                            self.lock_path.unlink()
                        except FileNotFoundError:
                            pass
                        continue
                    if time.monotonic() >= deadline:
                        raise ProjectIdentityError("project registry lock timeout")
                    time.sleep(0.05)

        def __exit__(self, exc_type, exc, tb):
            if self.fd is not None:
                os.close(self.fd)
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    return _Lock()


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"registry_version": 1, "instances": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectIdentityError(f"invalid AgentOS project registry: {path}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("instances", {}), dict):
        raise ProjectIdentityError(f"invalid AgentOS project registry structure: {path}")
    value.setdefault("registry_version", 1)
    value.setdefault("instances", {})
    return value


def _append_event(root: Path, event_type: str, payload: dict[str, Any]) -> None:
    p = paths_for(root).events
    p.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_type": event_type,
        "recorded_at": utc_now(),
        "payload": payload,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(_canonical_json(event) + "\n")


def ensure_project_id(
    root: Path | str,
    *,
    created_by: str = "agentos_v0.20.0_migration",
    project_uuid: str | None = None,
    origin_project_uuid: str | None = None,
    audit_project_id: str | None = None,
) -> dict[str, Any]:
    """Create or load the stable project UUID file.

    Args:
        root: AgentOS project root.
        created_by: Human/installer/migration actor label for first creation.
        project_uuid: Optional explicit UUID for controlled import scenarios.
        origin_project_uuid: Optional lineage UUID when creating a fork.
        audit_project_id: Stable signed-audit namespace. During v0.19.5 upgrade
            this is initialized from the legacy path-derived identifier so the
            existing external audit chain keeps the same namespace.

    Returns:
        Validated project identity object.

    Raises:
        ProjectIdentityError: If an existing identity is malformed.

    Side Effects:
        Creates `.agents/config/project.id` atomically when absent.
    """
    p = paths_for(root)
    if p.project_id.exists():
        value = _read_json(p.project_id)
        validate_project_id(value)
        return value
    if not created_by.strip():
        raise ProjectIdentityError("created_by is required")
    pid = project_uuid or str(uuid4())
    _validate_uuid(pid, "project_uuid")
    _validate_uuid(origin_project_uuid, "origin_project_uuid", nullable=True)
    stable_audit_id = audit_project_id or pid
    if not isinstance(stable_audit_id, str) or not stable_audit_id.strip():
        raise ProjectIdentityError("audit_project_id is required")
    value: dict[str, Any] = {
        "identity_version": IDENTITY_VERSION,
        "project_uuid": pid,
        "origin_project_uuid": origin_project_uuid,
        "audit_project_id": stable_audit_id.strip(),
        "created_at": utc_now(),
        "created_by": created_by.strip(),
    }
    value["identity_hash"] = _hash_payload(value, "identity_hash")
    _atomic_json(p.project_id, value)
    _append_event(p.root, "project_identity_created", {"project_uuid": pid, "created_by": created_by})
    return value


def validate_project_id(value: dict[str, Any]) -> None:
    """Validate a project UUID document and its integrity hash.

    Args:
        value: Parsed project identity JSON object.

    Returns:
        None when valid.

    Raises:
        ProjectIdentityError: On invalid version, UUID, actor, or hash.
    """
    if value.get("identity_version") != IDENTITY_VERSION:
        raise ProjectIdentityError(
            f"unsupported identity_version={value.get('identity_version')!r}; expected {IDENTITY_VERSION}"
        )
    _validate_uuid(value.get("project_uuid"), "project_uuid")
    _validate_uuid(value.get("origin_project_uuid"), "origin_project_uuid", nullable=True)
    audit_project_id = value.get("audit_project_id")
    if not isinstance(audit_project_id, str) or not audit_project_id.strip():
        raise ProjectIdentityError("audit_project_id is required")
    if not (
        re.fullmatch(r"[0-9a-f]{64}", audit_project_id)
        or _is_uuid_string(audit_project_id)
    ):
        raise ProjectIdentityError("audit_project_id must be a UUID or legacy SHA-256 identifier")
    if not isinstance(value.get("created_at"), str) or not value["created_at"]:
        raise ProjectIdentityError("created_at is required")
    if not isinstance(value.get("created_by"), str) or not value["created_by"].strip():
        raise ProjectIdentityError("created_by is required")
    expected = _hash_payload(value, "identity_hash")
    if value.get("identity_hash") != expected:
        raise ProjectIdentityError("project.id integrity hash mismatch")


def ensure_instance_id(root: Path | str) -> dict[str, Any]:
    """Create or load the local working-copy instance UUID.

    Args:
        root: AgentOS project root.

    Returns:
        Instance identity object.

    Side Effects:
        Creates `.agents/state/project.instance.json` when absent. This file is
        local operational state and should not be committed into templates.
    """
    p = paths_for(root)
    if p.instance_id.exists():
        value = _read_json(p.instance_id)
        _validate_uuid(value.get("instance_uuid"), "instance_uuid")
        expected = _hash_payload(value, "instance_hash")
        if value.get("instance_hash") != expected:
            raise ProjectIdentityError("project instance integrity hash mismatch")
        return value
    value = {
        "instance_uuid": str(uuid4()),
        "created_at": utc_now(),
    }
    value["instance_hash"] = _hash_payload(value, "instance_hash")
    _atomic_json(p.instance_id, value)
    _append_event(p.root, "project_instance_created", {"instance_uuid": value["instance_uuid"]})
    return value


def load_purpose(root: Path | str, *, required: bool = False) -> dict[str, Any] | None:
    """Load and validate the project-purpose contract.

    Args:
        root: AgentOS project root.
        required: Raise instead of returning None when purpose is missing.

    Returns:
        Purpose object or None.
    """
    p = paths_for(root).purpose
    if not p.exists():
        if required:
            raise ProjectIdentityError("project purpose has not been human-confirmed")
        return None
    value = _read_json(p)
    validate_purpose(value)
    return value


def validate_purpose(value: dict[str, Any]) -> None:
    """Validate a business-domain project purpose document.

    Args:
        value: Parsed purpose JSON object.

    Returns:
        None when valid.

    Raises:
        ProjectIdentityError: If required semantic fields are missing or invalid.
    """
    if value.get("purpose_version") != 1:
        raise ProjectIdentityError("purpose_version must be 1")
    if not isinstance(value.get("name"), str) or not value["name"].strip():
        raise ProjectIdentityError("project name is required")
    domain = value.get("domain")
    purpose = value.get("purpose")
    if not isinstance(domain, dict) or not isinstance(purpose, dict):
        raise ProjectIdentityError("domain and purpose must be JSON objects")
    _validate_slug(domain.get("id"), "domain.id")
    if not isinstance(domain.get("name"), str) or not domain["name"].strip():
        raise ProjectIdentityError("domain.name is required")
    _validate_slug(purpose.get("id"), "purpose.id")
    if not isinstance(purpose.get("description"), str) or len(purpose["description"].strip()) < 8:
        raise ProjectIdentityError("purpose.description must contain a meaningful business description")
    role = value.get("role")
    if role not in ROLE_VALUES:
        raise ProjectIdentityError(f"role must be one of {sorted(ROLE_VALUES)}, got {role!r}")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list):
        raise ProjectIdentityError("capabilities must be a list")
    _normalize_capabilities(str(item) for item in capabilities)
    confirmation = value.get("human_confirmation")
    if not isinstance(confirmation, dict):
        raise ProjectIdentityError("human_confirmation is required")
    if confirmation.get("confirmed") is not True:
        raise ProjectIdentityError("project purpose must be explicitly human-confirmed")
    if not isinstance(confirmation.get("confirmed_by"), str) or not confirmation["confirmed_by"].strip():
        raise ProjectIdentityError("human_confirmation.confirmed_by is required")
    expected = _hash_payload(value, "purpose_hash")
    if value.get("purpose_hash") != expected:
        raise ProjectIdentityError("project purpose integrity hash mismatch")


def set_purpose(
    root: Path | str,
    *,
    name: str,
    domain_id: str,
    domain_name: str,
    purpose_id: str,
    purpose_description: str,
    capabilities: Iterable[str],
    role: str,
    confirmed_by: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Persist the human-approved business purpose for a project.

    Args:
        root: AgentOS project root.
        name: Human-readable project name.
        domain_id: Stable lowercase snake_case business-domain identifier.
        domain_name: Human-readable business domain.
        purpose_id: Stable lowercase snake_case purpose-family identifier.
        purpose_description: Business outcome/purpose description.
        capabilities: Business capabilities provided by the project.
        role: Project role from ROLE_VALUES.
        confirmed_by: Human actor responsible for this declaration.
        human_confirmed: Must be True; an LLM must not self-confirm purpose.

    Returns:
        Persisted purpose object.

    Raises:
        ProjectIdentityError: If confirmation or semantic fields are invalid.

    Side Effects:
        Replaces `.agents/config/project.purpose.json` atomically and records an event.
    """
    if human_confirmed is not True:
        raise ProjectIdentityError("purpose mutation requires explicit human confirmation")
    if not confirmed_by.strip():
        raise ProjectIdentityError("confirmed_by is required")
    ensure_project_id(root)
    normalized_caps = _normalize_capabilities(capabilities)
    value: dict[str, Any] = {
        "purpose_version": 1,
        "name": name.strip(),
        "domain": {"id": _validate_slug(domain_id, "domain.id"), "name": domain_name.strip()},
        "purpose": {
            "id": _validate_slug(purpose_id, "purpose.id"),
            "description": purpose_description.strip(),
        },
        "capabilities": normalized_caps,
        "role": role,
        "human_confirmation": {
            "confirmed": True,
            "confirmed_by": confirmed_by.strip(),
            "confirmed_at": utc_now(),
        },
    }
    value["purpose_hash"] = _hash_payload(value, "purpose_hash")
    validate_purpose(value)
    _atomic_json(paths_for(root).purpose, value)
    _append_event(
        paths_for(root).root,
        "project_purpose_confirmed",
        {"domain_id": domain_id, "purpose_id": purpose_id, "confirmed_by": confirmed_by},
    )
    return value


def _register_instance(
    root: Path,
    project_uuid: str,
    instance_uuid: str,
    registry_home: Path | str | None,
) -> dict[str, Any]:
    registry_path = _registry_path(registry_home)
    with _with_registry_lock(registry_path):
        registry = _read_registry(registry_path)
        key = f"{project_uuid}:{instance_uuid}"
        previous = registry["instances"].get(key)
        root_text = str(root.resolve())
        result = {
            "status": "registered",
            "collision": False,
            "relocated": False,
            "previous_path": None,
            "current_path": root_text,
        }
        if isinstance(previous, dict):
            previous_path_text = str(previous.get("path", ""))
            result["previous_path"] = previous_path_text or None
            if previous_path_text and Path(previous_path_text).resolve() != root.resolve():
                if Path(previous_path_text).exists():
                    result.update(
                        {
                            "status": "instance_clone_conflict",
                            "collision": True,
                        }
                    )
                    return result
                result.update({"status": "relocated", "relocated": True})
        registry["instances"][key] = {
            "project_uuid": project_uuid,
            "instance_uuid": instance_uuid,
            "path": root_text,
            "last_seen_at": utc_now(),
        }
        _atomic_json(registry_path, registry)
        return result


def verify_identity(
    root: Path | str,
    *,
    registry_home: Path | str | None = None,
    require_purpose: bool = True,
) -> dict[str, Any]:
    """Verify project identity, local instance identity, purpose, and clone safety.

    Args:
        root: AgentOS project root.
        registry_home: Optional isolated AgentOS home used by tests/automation.
        require_purpose: Whether a missing purpose makes verification incomplete.

    Returns:
        Structured verification report. Clone conflicts are reported fail-closed.
    """
    p = paths_for(root)
    project = ensure_project_id(p.root)
    validate_project_id(project)
    instance = ensure_instance_id(p.root)
    purpose: dict[str, Any] | None
    purpose_error: str | None = None
    try:
        purpose = load_purpose(p.root, required=require_purpose)
    except ProjectIdentityError as exc:
        purpose = None
        purpose_error = str(exc)
    registry = _register_instance(
        p.root,
        project["project_uuid"],
        instance["instance_uuid"],
        registry_home,
    )
    ok = not registry["collision"] and (purpose is not None or not require_purpose)
    if registry["relocated"]:
        _append_event(
            p.root,
            "project_instance_relocated",
            {"from": registry["previous_path"], "to": registry["current_path"]},
        )
    return {
        "ok": ok,
        "status": "ok" if ok else registry["status"] if registry["collision"] else "purpose_incomplete",
        "project_uuid": project["project_uuid"],
        "instance_uuid": instance["instance_uuid"],
        "origin_project_uuid": project.get("origin_project_uuid"),
        "audit_project_id": project["audit_project_id"],
        "identity_hash": project["identity_hash"],
        "purpose": purpose,
        "purpose_error": purpose_error,
        "registry": registry,
    }


def get_project_uuid(root: Path | str) -> str:
    """Return the stable project UUID used by audit and future consolidation code."""
    return str(ensure_project_id(root)["project_uuid"])


def get_audit_project_id(root: Path | str) -> str:
    """Return the stable external-audit namespace for this project.

    For projects upgraded from v0.19.5 this preserves the legacy path-derived
    identifier once, then remains stable across later directory relocation.
    """
    return str(ensure_project_id(root)["audit_project_id"])


def get_instance_uuid(root: Path | str) -> str:
    """Return the local working-copy UUID used for clone and relocation checks."""
    return str(ensure_instance_id(root)["instance_uuid"])


def fork_project_identity(
    root: Path | str,
    *,
    confirmed_by: str,
    human_confirmed: bool,
    new_name: str | None = None,
) -> dict[str, Any]:
    """Turn a copied/derived repository into a distinct project with lineage.

    Args:
        root: Project root to re-identify.
        confirmed_by: Human actor authorizing the fork.
        human_confirmed: Must be True.
        new_name: Optional new human-readable project name.

    Returns:
        New project identity document.

    Side Effects:
        Replaces project UUID and local instance UUID, keeps
        `origin_project_uuid`, and optionally renames the purpose profile.
    """
    if human_confirmed is not True:
        raise ProjectIdentityError("project fork requires explicit human confirmation")
    if not confirmed_by.strip():
        raise ProjectIdentityError("confirmed_by is required")
    p = paths_for(root)
    old = ensure_project_id(p.root)
    old_uuid = old["project_uuid"]
    new_project_uuid = str(uuid4())
    new_value: dict[str, Any] = {
        "identity_version": IDENTITY_VERSION,
        "project_uuid": new_project_uuid,
        "origin_project_uuid": old_uuid,
        "audit_project_id": new_project_uuid,
        "created_at": utc_now(),
        "created_by": confirmed_by.strip(),
    }
    new_value["identity_hash"] = _hash_payload(new_value, "identity_hash")
    _atomic_json(p.project_id, new_value)
    if p.instance_id.exists():
        p.instance_id.unlink()
    ensure_instance_id(p.root)
    purpose = load_purpose(p.root)
    if purpose is not None and new_name:
        purpose = dict(purpose)
        purpose["name"] = new_name.strip()
        purpose["human_confirmation"] = {
            "confirmed": True,
            "confirmed_by": confirmed_by.strip(),
            "confirmed_at": utc_now(),
        }
        purpose["purpose_hash"] = _hash_payload(purpose, "purpose_hash")
        validate_purpose(purpose)
        _atomic_json(p.purpose, purpose)
    _append_event(
        p.root,
        "project_identity_forked",
        {
            "origin_project_uuid": old_uuid,
            "project_uuid": new_value["project_uuid"],
            "confirmed_by": confirmed_by,
        },
    )
    return new_value


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        is not None
    )


def _infer_root_from_connection(conn: sqlite3.Connection) -> Path | None:
    for row in conn.execute("PRAGMA database_list"):
        db_path = str(row[2] or "")
        if not db_path:
            continue
        p = Path(db_path).resolve()
        # Expected: <root>/.agents/state/agentos.db
        if p.parent.name == "state" and p.parent.parent.name == ".agents":
            return p.parent.parent.parent
    return None


def migration_32(conn: sqlite3.Connection) -> None:
    """Apply additive schema 32 for project identity and namespace preparation.

    Args:
        conn: Existing AgentOS SQLite connection managed by v0.19.5 migration code.

    Returns:
        None.

    Side Effects:
        Adds identity/purpose/event tables and nullable `project_uuid` columns to
        multi-project-sensitive tables when they exist. Existing rows are
        backfilled with the stable project UUID when the root can be inferred.
    """
    root = _infer_root_from_connection(conn)
    project_uuid = get_project_uuid(root) if root is not None else None
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_identity(
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            project_uuid TEXT NOT NULL,
            origin_project_uuid TEXT,
            audit_project_id TEXT NOT NULL,
            identity_version INTEGER NOT NULL,
            identity_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_purpose(
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            project_uuid TEXT NOT NULL,
            purpose_json TEXT NOT NULL,
            purpose_hash TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_purpose_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_uuid TEXT NOT NULL,
            purpose_json TEXT NOT NULL,
            purpose_hash TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS project_identity_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_uuid TEXT,
            instance_uuid TEXT,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_project_identity_events_project
            ON project_identity_events(project_uuid, created_at);
        """
    )
    identity_columns = _table_columns(conn, "project_identity")
    if "audit_project_id" not in identity_columns:
        conn.execute('ALTER TABLE "project_identity" ADD COLUMN audit_project_id TEXT')
    if root is not None and project_uuid is not None:
        audit_id = get_audit_project_id(root)
        conn.execute(
            'UPDATE "project_identity" SET audit_project_id=? WHERE audit_project_id IS NULL',
            (audit_id,),
        )

    for table in ("symbol_index", "project_findings", "promoted_skills", "resource_leases"):
        if not _table_exists(conn, table):
            continue
        columns = _table_columns(conn, table)
        if "project_uuid" not in columns:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN project_uuid TEXT')
        if project_uuid is not None:
            conn.execute(f'UPDATE "{table}" SET project_uuid=? WHERE project_uuid IS NULL', (project_uuid,))
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS "idx_{table}_project_uuid" ON "{table}"(project_uuid)'
        )
    if root is not None:
        project = ensure_project_id(root)
        conn.execute(
            """
            INSERT INTO project_identity(
                singleton, project_uuid, origin_project_uuid, audit_project_id, identity_version,
                identity_hash, created_at, created_by
            ) VALUES(1,?,?,?,?,?,?,?)
            ON CONFLICT(singleton) DO UPDATE SET
                project_uuid=excluded.project_uuid,
                origin_project_uuid=excluded.origin_project_uuid,
                audit_project_id=excluded.audit_project_id,
                identity_version=excluded.identity_version,
                identity_hash=excluded.identity_hash,
                created_at=excluded.created_at,
                created_by=excluded.created_by
            """,
            (
                project["project_uuid"],
                project.get("origin_project_uuid"),
                project["audit_project_id"],
                project["identity_version"],
                project["identity_hash"],
                project["created_at"],
                project["created_by"],
            ),
        )
        purpose = load_purpose(root)
        if purpose is not None:
            confirm = purpose["human_confirmation"]
            purpose_json = _canonical_json(purpose)
            conn.execute(
                """
                INSERT INTO project_purpose(
                    singleton, project_uuid, purpose_json, purpose_hash,
                    confirmed_by, confirmed_at, updated_at
                ) VALUES(1,?,?,?,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET
                    project_uuid=excluded.project_uuid,
                    purpose_json=excluded.purpose_json,
                    purpose_hash=excluded.purpose_hash,
                    confirmed_by=excluded.confirmed_by,
                    confirmed_at=excluded.confirmed_at,
                    updated_at=excluded.updated_at
                """,
                (
                    project["project_uuid"],
                    purpose_json,
                    purpose["purpose_hash"],
                    confirm["confirmed_by"],
                    confirm["confirmed_at"],
                    utc_now(),
                ),
            )
            existing_history = conn.execute(
                "SELECT 1 FROM project_purpose_history WHERE project_uuid=? AND purpose_hash=? LIMIT 1",
                (project["project_uuid"], purpose["purpose_hash"]),
            ).fetchone()
            if existing_history is None:
                conn.execute(
                    """
                    INSERT INTO project_purpose_history(
                        project_uuid, purpose_json, purpose_hash, confirmed_by, confirmed_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        project["project_uuid"],
                        purpose_json,
                        purpose["purpose_hash"],
                        confirm["confirmed_by"],
                        confirm["confirmed_at"],
                    ),
                )


def sync_identity_to_database(root: Path | str) -> dict[str, Any]:
    """Apply schema-32 identity state directly to the local AgentOS SQLite DB.

    Args:
        root: AgentOS project root.

    Returns:
        Summary of database path and schema additions.

    Raises:
        ProjectIdentityError: If the baseline DB is missing.
    """
    p = paths_for(root)
    db_path = p.root / ".agents/state/agentos.db"
    if not db_path.exists():
        raise ProjectIdentityError(f"AgentOS database not found: {db_path}")
    with sqlite3.connect(db_path) as conn:
        migration_32(conn)
        conn.commit()
        tables = [str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {"ok": True, "schema": SCHEMA_VERSION, "database": str(db_path), "tables": tables}
