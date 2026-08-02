"""
File: .agents/agentos/external_audit.py

Purpose:
    Persist signed append-only audit records outside the governed repository.

Responsibilities:
    - Maintain an Ed25519 key registry outside the repository.
    - Append hash-linked signed JSONL records or forward them to an external sink.
    - Rotate signing keys without invalidating historical records.
    - Verify signatures, hashes, sequence continuity, and key transitions.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .db import connect


def project_id(root: Path) -> str:
    """Return a stable identifier for one repository path."""
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def audit_home() -> Path:
    """Return the external AgentOS audit home."""
    path = Path(os.environ.get("AGENTOS_AUDIT_HOME", "~/.agentos/audit")).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _keys_dir() -> Path:
    path = audit_home() / "keys"; path.mkdir(parents=True, exist_ok=True); return path


def _active_file() -> Path:
    return audit_home() / "active-key.json"


def _key_id(public: Ed25519PublicKey) -> str:
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def _private_path(key_id: str) -> Path:
    return _keys_dir() / f"{key_id}.private.pem"


def _public_path(key_id: str) -> Path:
    return _keys_dir() / f"{key_id}.public.pem"


def _write_key(private: Ed25519PrivateKey) -> str:
    key_id = _key_id(private.public_key())
    private_path, public_path = _private_path(key_id), _public_path(key_id)
    private_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public_path.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    try:
        os.chmod(private_path, 0o600)
    except OSError:
        pass
    _active_file().write_text(json.dumps({"key_id": key_id}, indent=2), encoding="utf-8")
    return key_id


def ensure_signing_key() -> tuple[Ed25519PrivateKey, str]:
    """Load or create the active Ed25519 key pair."""
    active = _active_file()
    if active.exists():
        key_id = json.loads(active.read_text(encoding="utf-8"))["key_id"]
        private = serialization.load_pem_private_key(_private_path(key_id).read_bytes(), password=None)
        if not isinstance(private, Ed25519PrivateKey):
            raise RuntimeError("external audit key is not Ed25519")
        return private, key_id
    private = Ed25519PrivateKey.generate(); key_id = _write_key(private); return private, key_id


def rotate_signing_key(root: Path, identity: str, reason: str) -> dict[str, Any]:
    """Rotate the active signing key and append a cross-signed transition event."""
    old_private, old_id = ensure_signing_key()
    new_private = Ed25519PrivateKey.generate(); new_id = _key_id(new_private.public_key())
    new_public_raw = new_private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    transition = {
        "old_key_id": old_id,
        "new_key_id": new_id,
        "new_public_key_sha256": hashlib.sha256(new_public_raw).hexdigest(),
        "identity": identity,
        "reason": reason,
        "rotated_at": datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(transition, sort_keys=True, separators=(",", ":")).encode()
    transition["old_key_signature"] = base64.b64encode(old_private.sign(canonical)).decode()
    transition["new_key_signature"] = base64.b64encode(new_private.sign(canonical)).decode()
    _write_key(new_private)
    event = append_signed_event(root, "audit.key_rotated", transition, None, None)
    return {"ok": True, "old_key_id": old_id, "new_key_id": new_id, "event": event}


def log_path(root: Path) -> Path:
    """Return the external JSONL log path for a project."""
    return audit_home() / f"{project_id(root)}.jsonl"


def _sink_mode() -> str:
    return os.environ.get("AGENTOS_AUDIT_SINK", "jsonl").strip().lower()


def _append_local(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush(); os.fsync(handle.fileno())


def _append_remote(record: dict[str, Any]) -> None:
    endpoint = os.environ.get("AGENTOS_AUDIT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("AGENTOS_AUDIT_ENDPOINT is required for remote_http sink")
    data = json.dumps(record, sort_keys=True).encode()
    token = os.environ.get("AGENTOS_AUDIT_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    target = endpoint.rstrip("/") + "/v1/events"
    request = urllib.request.Request(target, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status not in {200, 201, 202, 204}:
            raise RuntimeError(f"remote audit sink rejected event: HTTP {response.status}")


def append_signed_event(root: Path, event_type: str, payload: dict[str, Any], task_id: str | None, session_id: str | None) -> dict[str, Any]:
    """Append one signed, hash-linked external audit event."""
    private, key_id = ensure_signing_key(); path = log_path(root)
    previous_hash, sequence = None, 1
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            last = json.loads(lines[-1]); previous_hash = last["event_hash"]; sequence = int(last["sequence"]) + 1
    body = {"schema": 2, "project_id": project_id(root), "sequence": sequence, "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": event_type, "task_id": task_id, "session_id": session_id, "payload": payload, "previous_hash": previous_hash, "key_id": key_id}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    event_hash = hashlib.sha256(canonical).hexdigest(); signature = base64.b64encode(private.sign(bytes.fromhex(event_hash))).decode()
    record = {**body, "event_hash": event_hash, "signature": signature}
    mode = _sink_mode()
    if mode == "jsonl":
        _append_local(path, record)
    elif mode in {"daemon", "remote_http"}:
        _append_remote(record)
        _append_local(path, record)  # local verifiable mirror/checkpoint
    else:
        raise RuntimeError(f"unsupported external audit sink: {mode}")
    return {"event_hash": event_hash, "signature": signature, "key_id": key_id, "sequence": sequence, "log_path": str(path), "sink": mode}


def _public_key(key_id: str) -> Ed25519PublicKey:
    path = _public_path(key_id)
    if not path.exists():
        raise FileNotFoundError(key_id)
    public = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(public, Ed25519PublicKey):
        raise RuntimeError("invalid public key")
    return public


def verify_external_log(root: Path) -> dict[str, Any]:
    """Verify the complete external signed audit chain against the key registry."""
    path = log_path(root)
    if not path.exists():
        return {"ok": True, "state": "empty", "events": 0, "log_path": str(path)}
    previous, count = None, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1; record = json.loads(line)
        if record.get("sequence") != count or record.get("previous_hash") != previous:
            return {"ok": False, "events": count, "invalid_sequence": count, "reason": "chain_mismatch", "log_path": str(path)}
        unsigned = {k: record[k] for k in ("schema", "project_id", "sequence", "timestamp", "event_type", "task_id", "session_id", "payload", "previous_hash", "key_id")}
        digest = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        if digest != record.get("event_hash"):
            return {"ok": False, "events": count, "invalid_sequence": count, "reason": "hash_mismatch", "log_path": str(path)}
        try:
            _public_key(record["key_id"]).verify(base64.b64decode(record["signature"]), bytes.fromhex(digest))
        except FileNotFoundError:
            return {"ok": False, "events": count, "invalid_sequence": count, "reason": "unknown_key", "key_id": record.get("key_id"), "log_path": str(path)}
        except Exception:
            return {"ok": False, "events": count, "invalid_sequence": count, "reason": "signature_mismatch", "log_path": str(path)}
        previous = digest
    if count and previous:
        last = json.loads([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()][-1])
        with connect(root) as c:
            c.execute("INSERT INTO external_audit_checkpoints(project_id,last_sequence,last_event_hash,key_id) VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET last_sequence=excluded.last_sequence,last_event_hash=excluded.last_event_hash,key_id=excluded.key_id,verified_at=CURRENT_TIMESTAMP", (project_id(root), count, previous, last["key_id"]))
    return {"ok": True, "state": "verified", "events": count, "last_hash": previous, "log_path": str(path)}


def validate_audit_home(root: Path) -> dict[str, Any]:
    """Validate that the external audit home is isolated from the repository."""
    home = audit_home()
    project = root.resolve()
    user_home = Path.home().resolve()
    isolated = home != user_home and home != project and project not in home.parents and home not in project.parents
    return {"ok": isolated, "audit_home": str(home), "reason": None if isolated else "audit_home_not_isolated"}
