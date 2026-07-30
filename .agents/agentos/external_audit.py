"""
File: .agents/agentos/external_audit.py

Purpose:
    Persist signed append-only audit records outside the governed repository.

Responsibilities:
    - Resolve a user-owned external audit directory.
    - Generate and protect an Ed25519 signing key.
    - Append hash-linked signed JSONL records.
    - Verify signatures, hashes, and chain continuity.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import connect

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def project_id(root: Path) -> str:
    """Return a stable identifier for one repository path.

    Args:
        root: Project root.

    Returns:
        Short SHA-256 based project identifier.
    """
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:24]


def audit_home() -> Path:
    """Return the external AgentOS audit home.

    Returns:
        User-owned directory outside the repository by default.
    """
    path = Path(os.environ.get("AGENTOS_AUDIT_HOME", "~/.agentos/audit")).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _key_paths() -> tuple[Path, Path]:
    home = audit_home()
    return home / "signing-key.pem", home / "signing-key.pub.pem"


def ensure_signing_key() -> tuple[Ed25519PrivateKey, str]:
    """Load or create the external Ed25519 key pair.

    Returns:
        Private key and stable key identifier.
    """
    private_path, public_path = _key_paths()
    if private_path.exists():
        private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        if not isinstance(private, Ed25519PrivateKey):
            raise RuntimeError("external audit key is not Ed25519")
    else:
        private = Ed25519PrivateKey.generate()
        private_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        try:
            os.chmod(private_path, 0o600)
        except OSError:
            pass
        public_path.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, hashlib.sha256(public_raw).hexdigest()[:16]


def log_path(root: Path) -> Path:
    """Return the external JSONL log path for a project.

    Args:
        root: Project root.

    Returns:
        External log path.
    """
    return audit_home() / f"{project_id(root)}.jsonl"


def append_signed_event(root: Path, event_type: str, payload: dict[str, Any], task_id: str | None, session_id: str | None) -> dict[str, Any]:
    """Append one signed, hash-linked external audit event.

    Args:
        root: Project root.
        event_type: Stable event type.
        payload: Redacted structured payload.
        task_id: Optional task identifier.
        session_id: Optional session identifier.

    Returns:
        Event metadata including hash, signature, and log path.
    """
    private, key_id = ensure_signing_key()
    path = log_path(root)
    previous_hash = None
    sequence = 1
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            last = json.loads(lines[-1])
            previous_hash = last["event_hash"]
            sequence = int(last["sequence"]) + 1
    body = {
        "schema": 1,
        "project_id": project_id(root),
        "sequence": sequence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "task_id": task_id,
        "session_id": session_id,
        "payload": payload,
        "previous_hash": previous_hash,
        "key_id": key_id,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    event_hash = hashlib.sha256(canonical).hexdigest()
    signature = base64.b64encode(private.sign(bytes.fromhex(event_hash))).decode("ascii")
    record = {**body, "event_hash": event_hash, "signature": signature}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {"event_hash": event_hash, "signature": signature, "key_id": key_id, "sequence": sequence, "log_path": str(path)}


def verify_external_log(root: Path) -> dict[str, Any]:
    """Verify the complete external signed audit chain.

    Args:
        root: Project root.

    Returns:
        Verification result and first invalid sequence when applicable.
    """
    path = log_path(root)
    if not path.exists():
        return {"ok": True, "events": 0, "log_path": str(path), "reason": "not_initialized"}
    _, public_path = _key_paths()
    if not public_path.exists():
        return {"ok": False, "events": 0, "log_path": str(path), "reason": "public_key_missing"}
    public = serialization.load_pem_public_key(public_path.read_bytes())
    if not isinstance(public, Ed25519PublicKey):
        return {"ok": False, "events": 0, "log_path": str(path), "reason": "invalid_public_key"}
    previous = None
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        count += 1
        record = json.loads(line)
        if record.get("sequence") != count or record.get("previous_hash") != previous:
            return {"ok": False, "events": count, "invalid_sequence": count, "reason": "chain_mismatch", "log_path": str(path)}
        unsigned = {k: record[k] for k in ("schema", "project_id", "sequence", "timestamp", "event_type", "task_id", "session_id", "payload", "previous_hash", "key_id")}
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        if digest != record.get("event_hash"):
            return {"ok": False, "events": count, "invalid_sequence": count, "reason": "hash_mismatch", "log_path": str(path)}
        try:
            public.verify(base64.b64decode(record["signature"]), bytes.fromhex(digest))
        except Exception:
            return {"ok": False, "events": count, "invalid_sequence": count, "reason": "signature_mismatch", "log_path": str(path)}
        previous = digest
    if count and previous:
        last = json.loads([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()][-1])
        with connect(root) as c:
            c.execute("INSERT INTO external_audit_checkpoints(project_id,last_sequence,last_event_hash,key_id) VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET last_sequence=excluded.last_sequence,last_event_hash=excluded.last_event_hash,key_id=excluded.key_id,verified_at=CURRENT_TIMESTAMP", (project_id(root), count, previous, last["key_id"]))
    return {"ok": True, "events": count, "last_hash": previous, "log_path": str(path)}
