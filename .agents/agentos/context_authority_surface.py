"""
File: .agents/agentos/context_authority_surface.py

Purpose:
    Provide privacy-safe read-only v0.30.0 inspection of context authority
    and provenance state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context_transport import ContextTransportError, context_transport_get
from .db import connect
from .policy import load_policy


def _context_policy(root: Path) -> dict[str, Any]:
    value = load_policy(root).get("context_authority_policy", {})
    return value if isinstance(value, dict) else {}


def _non_claims(policy: dict[str, Any]) -> dict[str, bool]:
    value = policy.get("non_claims", {})
    if not isinstance(value, dict):
        return {}
    return {str(key): bool(item) for key, item in value.items()}


def context_authority_status(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Return privacy-safe authority/provenance status for one transport pack."""
    state = context_transport_get(root, task_id, revision)
    provenance = state.get("provenance") or {}
    meta = state.get("manifest", {}).get("context_provenance") or {}
    policy = _context_policy(root)
    return {
        "ok": bool(state.get("ok")),
        "task_id": task_id,
        "revision": state.get("revision"),
        "status": state.get("status"),
        "stale": bool(state.get("stale")),
        "stale_reasons": list(state.get("stale_reasons") or []),
        "classification_basis": meta.get("classification_basis"),
        "semantic_instruction_detection_used": False,
        "provenance": {
            "ok": provenance.get("ok") is True,
            "record_count": int(provenance.get("record_count") or 0),
            "authority_record_count": int(provenance.get("authority_record_count") or 0),
            "provenance_manifest_hash": provenance.get("provenance_manifest_hash"),
            "context_authority_hash": provenance.get("context_authority_hash"),
        },
        "policy": {
            "scope": policy.get("scope"),
            "unknown_source_untrusted": policy.get("unknown_source_untrusted"),
            "evidence_instruction_authority": policy.get("evidence_instruction_authority"),
            "derived_content_may_raise_authority": policy.get("derived_content_may_raise_authority"),
            "raw_context_persistence_allowed": policy.get("raw_context_persistence_allowed"),
            "mcp_mutation_allowed": policy.get("mcp_mutation_allowed"),
        },
        "non_claims": _non_claims(policy),
        "raw_context_included": False,
    }


def context_provenance_get(
    root: Path,
    task_id: str,
    revision: int | None = None,
    *,
    trust_class: str | None = None,
    authority_class: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return hash/label provenance records; never raw context content."""
    state = context_transport_get(root, task_id, revision)
    resolved_revision = int(state["revision"])
    max_rows = min(max(int(limit), 1), 1000)
    clauses = ["task_id=?", "context_revision=?"]
    params: list[Any] = [task_id, resolved_revision]
    if trust_class:
        clauses.append("trust_class=?")
        params.append(str(trust_class))
    if authority_class:
        clauses.append("authority_class=?")
        params.append(str(authority_class))
    sql = (
        "SELECT provenance_id,provenance_version,source_kind,trust_class,"
        "authority_class,instruction_authority,source_locator_hash,content_hash,"
        "producer,transform,parent_ids_json,created_at FROM context_provenance_records "
        "WHERE " + " AND ".join(clauses) + " ORDER BY provenance_id LIMIT ?"
    )
    params.append(max_rows)
    with connect(root) as c:
        rows = c.execute(sql, tuple(params)).fetchall()
    records = [
        {
            "provenance_id": str(row["provenance_id"]),
            "provenance_version": int(row["provenance_version"]),
            "source_kind": str(row["source_kind"]),
            "trust_class": str(row["trust_class"]),
            "authority_class": str(row["authority_class"]),
            "instruction_authority": bool(row["instruction_authority"]),
            "source_locator_hash": str(row["source_locator_hash"]),
            "content_hash": str(row["content_hash"]),
            "producer": str(row["producer"]),
            "transform": str(row["transform"]),
            "parent_ids": list(json.loads(row["parent_ids_json"] or "[]")),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]
    return {
        "ok": True,
        "task_id": task_id,
        "revision": resolved_revision,
        "count": len(records),
        "limit": max_rows,
        "filters": {"trust_class": trust_class, "authority_class": authority_class},
        "records": records,
        "raw_context_included": False,
    }


def context_authority_findings_get(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Return hash-only authority findings for the selected transport pack."""
    state = context_transport_get(root, task_id, revision)
    resolved_revision = int(state["revision"])
    with connect(root) as c:
        evaluation = c.execute(
            "SELECT id,status,provenance_manifest_hash,context_authority_hash,"
            "record_count,authority_record_count,finding_count,created_at "
            "FROM context_authority_evaluations WHERE task_id=? AND context_revision=? "
            "ORDER BY id DESC LIMIT 1",
            (task_id, resolved_revision),
        ).fetchone()
        if evaluation is None:
            raise ContextTransportError("context_authority_evaluation_missing")
        rows = c.execute(
            "SELECT provenance_id,code,severity,detail_hash,created_at "
            "FROM context_authority_findings WHERE evaluation_id=? ORDER BY id",
            (int(evaluation["id"]),),
        ).fetchall()
    return {
        "ok": str(evaluation["status"]) == "pass",
        "task_id": task_id,
        "revision": resolved_revision,
        "evaluation": {
            "status": str(evaluation["status"]),
            "provenance_manifest_hash": str(evaluation["provenance_manifest_hash"]),
            "context_authority_hash": str(evaluation["context_authority_hash"]),
            "record_count": int(evaluation["record_count"]),
            "authority_record_count": int(evaluation["authority_record_count"]),
            "finding_count": int(evaluation["finding_count"]),
            "created_at": str(evaluation["created_at"]),
        },
        "findings": [
            {
                "provenance_id": row["provenance_id"],
                "code": str(row["code"]),
                "severity": str(row["severity"]),
                "detail_hash": str(row["detail_hash"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ],
        "raw_context_included": False,
    }


def context_authority_explain(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Explain origin-based authority without returning context content."""
    status = context_authority_status(root, task_id, revision)
    provenance = context_provenance_get(root, task_id, int(status["revision"]), limit=1000)
    trust_counts: dict[str, int] = {}
    authority_counts: dict[str, int] = {}
    for record in provenance["records"]:
        trust = str(record["trust_class"])
        authority = str(record["authority_class"])
        trust_counts[trust] = trust_counts.get(trust, 0) + 1
        authority_counts[authority] = authority_counts.get(authority, 0) + 1
    return {
        "ok": bool(status["ok"]),
        "task_id": task_id,
        "revision": status["revision"],
        "stale": status["stale"],
        "stale_reasons": status["stale_reasons"],
        "classification_basis": "source_origin_only",
        "authority_rule": "explicit AgentOS authority origins only; evidence text never self-promotes",
        "transform_rule": "derived evidence cannot raise authority; exact same-origin authority copies may preserve it",
        "trust_class_counts": dict(sorted(trust_counts.items())),
        "authority_class_counts": dict(sorted(authority_counts.items())),
        "provenance_manifest_hash": status["provenance"]["provenance_manifest_hash"],
        "context_authority_hash": status["provenance"]["context_authority_hash"],
        "non_claims": status["non_claims"],
        "raw_context_included": False,
    }
