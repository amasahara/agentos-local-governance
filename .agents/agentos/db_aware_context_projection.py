"""
File: .agents/agentos/db_aware_context_projection.py

Purpose:
    Provide deterministic, reversible, DB-aware structural projection codecs for
    schema, field-mapping, and manifest evidence used by AgentOS context transport.

Responsibilities:
    - Detect supported structured schema/mapping/manifest JSON evidence.
    - Encode repeated object keys through a deterministic key dictionary.
    - Preserve JSON structure and scalar values without LLM summarization.
    - Decode projections back to the same canonical JSON structure.
    - Persist hash/count-only projection telemetry; never persist raw projected data.
    - Expose read-only status for operator/MCP inspection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MIGRATION_VERSION = 49
CODEC_VERSION = 1
CODECS = {
    "schema": "db_schema_keydict_v1",
    "mapping": "db_mapping_keydict_v1",
    "manifest": "db_manifest_keydict_v1",
}


class DBAwareProjectionError(RuntimeError):
    """Raised when a DB-aware projection cannot be encoded/decoded safely."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def migration_49(conn: Any) -> None:
    """Create schema-49 hash/count-only DB-aware context projection telemetry."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS context_db_projection_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            transport_revision INTEGER NOT NULL,
            candidate_id TEXT NOT NULL,
            source_kind TEXT NOT NULL CHECK(source_kind IN ('schema','mapping','manifest')),
            codec TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_structure_hash TEXT NOT NULL,
            projection_hash TEXT NOT NULL,
            source_bytes INTEGER NOT NULL,
            projected_bytes INTEGER NOT NULL,
            projected_tokens INTEGER NOT NULL,
            reversible INTEGER NOT NULL CHECK(reversible=1),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(transport_pack_id,candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_context_db_projection_task
            ON context_db_projection_events(task_id,transport_revision,source_kind);
        """
    )


def _collect_keys(value: Any, counts: dict[str, int]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key)
            counts[name] = counts.get(name, 0) + 1
            _collect_keys(child, counts)
    elif isinstance(value, list):
        for child in value:
            _collect_keys(child, counts)


def _encode_node(value: Any, key_index: dict[str, int]) -> Any:
    # Compact tagged arrays avoid repeating JSON object wrapper keys.
    # [0,[key_index,value],...] = object; [1,value,...] = array.
    # Primitive JSON scalars are stored directly.
    if isinstance(value, dict):
        return [0] + [
            [key_index[str(key)], _encode_node(child, key_index)]
            for key, child in sorted(value.items(), key=lambda kv: str(kv[0]))
        ]
    if isinstance(value, list):
        return [1] + [_encode_node(child, key_index) for child in value]
    return value


def _decode_node(node: Any, keys: list[str]) -> Any:
    if not isinstance(node, list):
        return node
    if not node:
        raise DBAwareProjectionError("invalid_projection_node")
    tag = node[0]
    if tag == 1:
        return [_decode_node(child, keys) for child in node[1:]]
    if tag == 0:
        result: dict[str, Any] = {}
        for pair in node[1:]:
            if not isinstance(pair, list) or len(pair) != 2:
                raise DBAwareProjectionError("invalid_projection_pair")
            index = int(pair[0])
            if index < 0 or index >= len(keys):
                raise DBAwareProjectionError("projection_key_index_out_of_range")
            result[keys[index]] = _decode_node(pair[1], keys)
        return result
    # Primitive JSON arrays begin with values other than reserved integer tags only
    # after wrapping by tag=1; seeing another tag here is invalid.
    raise DBAwareProjectionError("unknown_projection_node")


def _detect_kind(path_text: str, value: Any) -> str | None:
    """Classify only strongly-signalled structured DB artifacts."""
    if not isinstance(value, (dict, list)):
        return None
    path = path_text.replace("\\", "/").lower()
    name = Path(path).name

    keys: set[str] = set()
    if isinstance(value, dict):
        keys = {str(k).lower() for k in value.keys()}

    schema_path = any(token in name for token in ("schema", "contract")) or "/schema" in path
    schema_keys = bool(keys & {"tables", "columns", "foreign_keys", "indexes", "schema", "target_schema"})
    if schema_path and schema_keys:
        return "schema"

    mapping_path = "mapping" in name or "/mapping" in path
    mapping_keys = bool(keys & {"mappings", "field_mappings", "source_field", "target_field", "source_column", "target_column"})
    if mapping_path and mapping_keys:
        return "mapping"

    manifest_path = "manifest" in name or name in {"checksums.json", "release_manifest.json"}
    manifest_keys = bool(keys & {"files", "entries", "sources", "artifacts", "checksums", "manifest"})
    if manifest_path and manifest_keys:
        return "manifest"

    return None


def encode_projection(kind: str, value: Any) -> dict[str, Any]:
    """Encode one JSON value into a deterministic reversible key-dictionary form."""
    if kind not in CODECS:
        raise DBAwareProjectionError(f"unsupported_projection_kind:{kind}")
    counts: dict[str, int] = {}
    _collect_keys(value, counts)
    keys = sorted(counts, key=lambda key: (-counts[key], key))
    key_index = {key: idx for idx, key in enumerate(keys)}
    source_canonical = _canonical_json(value)
    payload = {
        "c": CODECS[kind],
        "v": CODEC_VERSION,
        "k": keys,
        "d": _encode_node(value, key_index),
    }
    projection_text = _canonical_json(payload)
    decoded = decode_projection(payload)
    if _canonical_json(decoded) != source_canonical:
        raise DBAwareProjectionError("projection_roundtrip_mismatch")
    return {
        "kind": kind,
        "codec": CODECS[kind],
        "projection": payload,
        "projection_text": projection_text,
        "source_structure_hash": _sha256_text(source_canonical),
        "projection_hash": _sha256_text(projection_text),
        "source_bytes": len(source_canonical.encode("utf-8")),
        "projected_bytes": len(projection_text.encode("utf-8")),
        "reversible": True,
    }


def decode_projection(payload: dict[str, Any] | str) -> Any:
    """Decode a DB-aware projection into its canonical JSON structure."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise DBAwareProjectionError("invalid_projection_payload")
    codec = str(payload.get("c") or "")
    if codec not in CODECS.values():
        raise DBAwareProjectionError(f"unsupported_projection_codec:{codec}")
    if int(payload.get("v", -1)) != CODEC_VERSION:
        raise DBAwareProjectionError("unsupported_projection_version")
    keys = payload.get("k")
    if not isinstance(keys, list) or not all(isinstance(x, str) for x in keys):
        raise DBAwareProjectionError("invalid_projection_key_dictionary")
    return _decode_node(payload.get("d"), keys)


def project_db_aware_candidate(path_text: str, text: str) -> tuple[str, dict[str, Any]] | None:
    """Return a reversible structural projection for a supported JSON DB artifact."""
    if not text.strip():
        return None
    try:
        value = json.loads(text)
    except Exception:
        return None
    kind = _detect_kind(path_text, value)
    if kind is None:
        return None
    encoded = encode_projection(kind, value)
    if encoded["projected_bytes"] >= len(text.encode("utf-8")):
        return None
    meta = {
        "codec": encoded["codec"],
        "db_aware": True,
        "source_kind": kind,
        "reversible": True,
        "source_structure_hash": encoded["source_structure_hash"],
        "projection_hash": encoded["projection_hash"],
        "source_bytes": len(text.encode("utf-8")),
        "projected_bytes": encoded["projected_bytes"],
    }
    return str(encoded["projection_text"]), meta


def _projection_rows(
    pack_id: int,
    task_id: str,
    context_revision: int,
    transport_revision: int,
    evidence: dict[str, Any],
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for item in evidence.get("included", []):
        projection = item.get("projection")
        if not isinstance(projection, dict) or projection.get("db_aware") is not True:
            continue
        rows.append(
            (
                int(pack_id),
                str(task_id),
                int(context_revision),
                int(transport_revision),
                str(item.get("candidate_id") or ""),
                str(projection.get("source_kind") or ""),
                str(projection.get("codec") or ""),
                str(item.get("source_hash") or ""),
                str(projection.get("source_structure_hash") or ""),
                str(projection.get("projection_hash") or ""),
                int(projection.get("source_bytes") or 0),
                int(projection.get("projected_bytes") or 0),
                int(item.get("tokens") or 0),
            )
        )
    return rows


def persist_projection_telemetry_conn(
    conn: Any,
    pack_id: int,
    task_id: str,
    context_revision: int,
    transport_revision: int,
    evidence: dict[str, Any],
) -> int:
    """Persist telemetry through the caller's transport-pack transaction."""
    rows = _projection_rows(pack_id, task_id, context_revision, transport_revision, evidence)
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO context_db_projection_events(
            transport_pack_id,task_id,context_revision,transport_revision,candidate_id,
            source_kind,codec,source_hash,source_structure_hash,projection_hash,
            source_bytes,projected_bytes,projected_tokens,reversible
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        ON CONFLICT(transport_pack_id,candidate_id) DO NOTHING
        """,
        rows,
    )
    return len(rows)


def persist_projection_telemetry(
    root: Path,
    pack_id: int,
    task_id: str,
    context_revision: int,
    transport_revision: int,
    evidence: dict[str, Any],
) -> int:
    """Persist hash/count-only telemetry in a standalone governed DB transaction."""
    from .db import connect
    with connect(root, immediate=True) as conn:
        return persist_projection_telemetry_conn(
            conn, pack_id, task_id, context_revision, transport_revision, evidence
        )


def projection_status(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Return hash/count-only projection telemetry through strict read-only state access."""
    from .db import connect_read_only
    root = root.resolve()
    with connect_read_only(root) as conn:
        sql = """
            SELECT transport_pack_id,task_id,context_revision,transport_revision,candidate_id,
                   source_kind,codec,source_hash,source_structure_hash,projection_hash,
                   source_bytes,projected_bytes,projected_tokens,reversible,created_at
            FROM context_db_projection_events
            WHERE task_id=?
        """
        args: list[Any] = [str(task_id)]
        if revision is not None:
            sql += " AND transport_revision=?"
            args.append(int(revision))
        sql += " ORDER BY transport_revision,candidate_id"
        rows = [dict(row) for row in conn.execute(sql, tuple(args)).fetchall()]
    total_source = sum(int(row["source_bytes"]) for row in rows)
    total_projected = sum(int(row["projected_bytes"]) for row in rows)
    return {
        "ok": True,
        "task_id": str(task_id),
        "transport_revision": revision,
        "projection_count": len(rows),
        "source_bytes": total_source,
        "projected_bytes": total_projected,
        "saved_bytes": max(0, total_source - total_projected),
        "rows": rows,
        "raw_content_persisted": False,
        "read_only": True,
    }


def preview_file(root: Path, relative_path: str) -> dict[str, Any]:
    """Read and project one local file without persisting any content or telemetry."""
    root = root.resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise DBAwareProjectionError("projection_path_outside_project") from exc
    if not target.is_file():
        raise DBAwareProjectionError("projection_source_not_found")
    text = target.read_text(encoding="utf-8", errors="strict")
    result = project_db_aware_candidate(target.relative_to(root).as_posix(), text)
    if result is None:
        return {"ok": True, "eligible": False, "path": target.relative_to(root).as_posix(), "read_only": True}
    projected, meta = result
    return {
        "ok": True,
        "eligible": True,
        "path": target.relative_to(root).as_posix(),
        "projection": meta,
        "projected_text": projected,
        "read_only": True,
        "persisted": False,
    }
