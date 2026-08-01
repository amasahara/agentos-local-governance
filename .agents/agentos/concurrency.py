"""
File: .agents/agentos/concurrency.py

Purpose:
    Coordinate concurrent AgentOS tasks, sessions, and file mutations.

Responsibilities:
    - Acquire, renew, inspect, and release resource leases atomically.
    - Detect stale writes using expected content hashes.
    - Perform crash-safe atomic file replacement.
    - Track task ownership, heartbeat, and explicit handoff.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect
from .policy import load_policy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def file_hash(path: Path) -> str | None:
    """Return the SHA-256 hash of a file, or None when it does not exist."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_resource(root: Path, resource_type: str, resource: str) -> tuple[str, str]:
    """Normalize a resource into a stable key within the project boundary."""
    if resource_type not in {"file", "directory", "symbol", "governance"}:
        raise RuntimeError("unsupported resource type")
    if resource_type == "symbol":
        if "::" not in resource:
            raise RuntimeError("symbol resource must use path::qualname")
        file_part, qualname = resource.split("::", 1)
        _, rel = normalize_resource(root, "file", file_part)
        return resource_type, f"{rel}::{qualname}"
    base = root.resolve()
    candidate = Path(resource)
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    try:
        rel = resolved.relative_to(base).as_posix()
    except ValueError as exc:
        raise RuntimeError("resource is outside project root") from exc
    return resource_type, rel


def acquire_resource(root: Path, task_id: str, session_id: str, resource_type: str, resource: str, mode: str = "exclusive_write", ttl_seconds: int | None = None, base_hash: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Acquire an atomic resource lease for a task and session."""
    if mode not in {"shared_read", "intent_write", "exclusive_write"}:
        raise RuntimeError("invalid lease mode")
    policy = load_policy(root)["concurrency_policy"]
    ttl = int(ttl_seconds or policy.get("default_write_lease_seconds", 300))
    ttl = max(10, min(ttl, int(policy.get("max_lease_seconds", 3600))))
    rtype, key = normalize_resource(root, resource_type, resource)
    now, expires = _now(), _now() + timedelta(seconds=ttl)
    with connect(root, immediate=True) as c:
        c.execute("DELETE FROM resource_leases WHERE status='active' AND expires_at<=?", (_iso(now),))
        task = c.execute("SELECT owner_session_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise RuntimeError(f"task not found: {task_id}")
        owner = task["owner_session_id"]
        if owner and owner != session_id and policy.get("task_single_writer", True) and mode != "shared_read":
            return {"acquired": False, "blocked": True, "reason": "task_owned_by_other_session", "owner_session_id": owner}
        conflicts = c.execute("SELECT id,task_id,session_id,lease_mode,expires_at FROM resource_leases WHERE resource_type=? AND resource_key=? AND status='active'", (rtype, key)).fetchall()
        incompatible = []
        for row in conflicts:
            same_owner = row["task_id"] == task_id and row["session_id"] == session_id
            compatible = mode == "shared_read" and row["lease_mode"] == "shared_read"
            if not same_owner and not compatible:
                incompatible.append(dict(row))
        if incompatible:
            return {"acquired": False, "blocked": True, "reason": "resource_lease_conflict", "resource": f"{rtype}:{key}", "conflicts": incompatible}
        existing = c.execute("SELECT id FROM resource_leases WHERE resource_type=? AND resource_key=? AND task_id=? AND session_id=? AND lease_mode=? AND status='active'", (rtype, key, task_id, session_id, mode)).fetchone()
        if existing:
            c.execute("UPDATE resource_leases SET heartbeat_at=?,expires_at=?,base_hash=?,metadata_json=? WHERE id=?", (_iso(now), _iso(expires), base_hash, json.dumps(metadata or {}, sort_keys=True), existing["id"]))
            lease_id = existing["id"]
        else:
            cur = c.execute("INSERT INTO resource_leases(resource_type,resource_key,task_id,session_id,lease_mode,status,acquired_at,expires_at,heartbeat_at,base_hash,metadata_json) VALUES(?,?,?,?,?,'active',?,?,?,?,?)", (rtype, key, task_id, session_id, mode, _iso(now), _iso(expires), _iso(now), base_hash, json.dumps(metadata or {}, sort_keys=True)))
            lease_id = int(cur.lastrowid)
        c.execute("UPDATE tasks SET owner_session_id=COALESCE(owner_session_id,?), task_state='active', last_heartbeat=? WHERE id=?", (session_id, _iso(now), task_id))
    return {"acquired": True, "lease_id": lease_id, "resource": f"{rtype}:{key}", "mode": mode, "expires_at": _iso(expires), "base_hash": base_hash}


def heartbeat_resource(root: Path, lease_id: int, task_id: str, session_id: str, ttl_seconds: int | None = None) -> dict[str, Any]:
    """Renew an active lease owned by the supplied task and session."""
    policy = load_policy(root)["concurrency_policy"]
    ttl = int(ttl_seconds or policy.get("default_write_lease_seconds", 300))
    now, expires = _now(), _now() + timedelta(seconds=ttl)
    with connect(root, immediate=True) as c:
        cur = c.execute("UPDATE resource_leases SET heartbeat_at=?,expires_at=? WHERE id=? AND task_id=? AND session_id=? AND status='active' AND expires_at>?", (_iso(now), _iso(expires), lease_id, task_id, session_id, _iso(now)))
        if cur.rowcount != 1:
            raise RuntimeError("lease is missing, expired, or owned by another session")
        c.execute("UPDATE tasks SET last_heartbeat=? WHERE id=?", (_iso(now), task_id))
    return {"renewed": True, "lease_id": lease_id, "expires_at": _iso(expires)}


def release_resource(root: Path, lease_id: int, task_id: str, session_id: str) -> dict[str, Any]:
    """Release a lease owned by the supplied task and session."""
    with connect(root, immediate=True) as c:
        cur = c.execute("UPDATE resource_leases SET status='released',released_at=CURRENT_TIMESTAMP WHERE id=? AND task_id=? AND session_id=? AND status='active'", (lease_id, task_id, session_id))
        if cur.rowcount != 1:
            raise RuntimeError("active lease not found for task/session")
    return {"released": True, "lease_id": lease_id}


def list_resources(root: Path, task_id: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
    """List resource leases, optionally restricted to one task."""
    where, params = [], []
    if task_id:
        where.append("task_id=?"); params.append(task_id)
    if active_only:
        where.append("status='active'")
    sql = "SELECT * FROM resource_leases" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
    with connect(root) as c:
        return [dict(row) for row in c.execute(sql, params).fetchall()]


def atomic_write(root: Path, task_id: str, session_id: str, target: str, content: str, expected_hash: str | None, encoding: str = "utf-8") -> dict[str, Any]:
    """Write a file atomically while enforcing a lease and compare-and-swap hash."""
    policy = load_policy(root)["concurrency_policy"]
    base = root.resolve(); path = (base / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
    try:
        rel = path.relative_to(base).as_posix()
    except ValueError as exc:
        raise RuntimeError("write target is outside project root") from exc
    if policy.get("file_write_requires_expected_hash", True) and expected_hash is None and path.exists():
        raise RuntimeError("expected_hash is required for existing files")
    lease = acquire_resource(root, task_id, session_id, "file", rel, "exclusive_write", base_hash=expected_hash)
    if not lease.get("acquired"):
        return lease
    try:
        current = file_hash(path)
        if expected_hash is not None and current != expected_hash:
            with connect(root) as c:
                latest = c.execute("SELECT task_id,session_id,content_hash AS new_hash,created_at FROM file_versions WHERE path=? ORDER BY id DESC LIMIT 1", (rel,)).fetchone()
            return {"allowed": False, "blocked": True, "reason": "stale_write_conflict", "path": rel, "expected_hash": expected_hash, "current_hash": current, "changed_by": dict(latest) if latest else None, "lease_id": lease["lease_id"]}
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = content.encode(encoding)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.agentos-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp_name, path)
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try: os.fsync(dir_fd)
                finally: os.close(dir_fd)
            except OSError:
                pass
        finally:
            if os.path.exists(temp_name): os.unlink(temp_name)
        new_hash = hashlib.sha256(payload).hexdigest()
        with connect(root, immediate=True) as c:
            version = c.execute("SELECT COALESCE(MAX(version),0)+1 AS v FROM file_versions WHERE path=?", (rel,)).fetchone()["v"]
            c.execute("INSERT INTO file_versions(path,version,content_hash,previous_hash,task_id,session_id,lease_id) VALUES(?,?,?,?,?,?,?)", (rel, version, new_hash, current, task_id, session_id, lease["lease_id"]))
        return {"allowed": True, "path": rel, "bytes_written": len(payload), "sha256": new_hash, "previous_hash": current, "version": version, "lease_id": lease["lease_id"], "atomic": True}
    finally:
        try: release_resource(root, lease["lease_id"], task_id, session_id)
        except RuntimeError: pass


def claim_task(root: Path, task_id: str, session_id: str) -> dict[str, Any]:
    """Claim ownership of a task for one writer session."""
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT owner_session_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row: raise RuntimeError(f"task not found: {task_id}")
        if row["owner_session_id"] and row["owner_session_id"] != session_id:
            return {"claimed": False, "blocked": True, "reason": "task_owned_by_other_session", "owner_session_id": row["owner_session_id"]}
        c.execute("UPDATE tasks SET owner_session_id=?,task_state='active',last_heartbeat=? WHERE id=?", (session_id, _iso(_now()), task_id))
    return {"claimed": True, "task_id": task_id, "owner_session_id": session_id}


def handoff_task(root: Path, task_id: str, from_session: str, to_session: str, note: str) -> dict[str, Any]:
    """Transfer task ownership and active leases to another session atomically."""
    if not note.strip(): raise RuntimeError("handoff note is required")
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT owner_session_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row: raise RuntimeError(f"task not found: {task_id}")
        if row["owner_session_id"] != from_session: raise RuntimeError("from_session does not own task")
        c.execute("UPDATE tasks SET owner_session_id=?,task_state='active',last_heartbeat=? WHERE id=?", (to_session, _iso(_now()), task_id))
        c.execute("UPDATE resource_leases SET session_id=? WHERE task_id=? AND session_id=? AND status='active'", (to_session, task_id, from_session))
        c.execute("INSERT INTO task_handoffs(task_id,from_session_id,to_session_id,note) VALUES(?,?,?,?)", (task_id, from_session, to_session, note))
    return {"handed_off": True, "task_id": task_id, "from_session": from_session, "to_session": to_session, "note": note}
