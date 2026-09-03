"""
File: .agents/agentos/context_authority.py

Purpose:
    Define deterministic v0.30.0 context authority and untrusted-provenance
    semantics without granting semantic or model-based authority.

Responsibilities:
    - Classify context by origin, not by instruction-like text.
    - Keep provenance/trust separate from instruction authority.
    - Prevent evidence-derived transforms from gaining authority.
    - Produce deterministic provenance/authority manifest hashes.
    - Define schema 63 state that stores hashes/labels only, never raw context.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

MIGRATION_VERSION = 63
PROVENANCE_VERSION = 1

AUTHORITY_NONE = "none"
AUTHORITY_CLASSES = frozenset(
    {
        "none",
        "governance",
        "human_request",
        "approved_task",
        "human_decision",
    }
)

TRUST_CLASSES = frozenset(
    {
        "governance_authority",
        "human_authority",
        "approved_task_authority",
        "project_evidence",
        "tool_evidence",
        "external_untrusted",
        "generated_evidence",
        "unknown_untrusted",
    }
)

_SOURCE_CLASSIFICATION: dict[str, tuple[str, str, bool]] = {
    "agents_md": ("governance_authority", "governance", True),
    "governance_policy": ("governance_authority", "governance", True),
    "architecture_baseline": ("governance_authority", "governance", True),
    "original_request": ("human_authority", "human_request", True),
    "human_decision": ("human_authority", "human_decision", True),
    "approved_scope": ("approved_task_authority", "approved_task", True),
    "active_plan": ("approved_task_authority", "approved_task", True),
    "requirement_ledger": ("approved_task_authority", "approved_task", True),

    "project_file": ("project_evidence", "none", False),
    "source_file": ("project_evidence", "none", False),
    "source_code": ("project_evidence", "none", False),
    "project_document": ("project_evidence", "none", False),
    "knowledge_skill": ("project_evidence", "none", False),
    "knowledge_memory": ("project_evidence", "none", False),
    "knowledge_finding": ("project_evidence", "none", False),
    "architecture_observation": ("project_evidence", "none", False),

    "tool_output": ("tool_evidence", "none", False),
    "command_output": ("tool_evidence", "none", False),
    "test_output": ("tool_evidence", "none", False),
    "mcp_tool_output": ("tool_evidence", "none", False),
    "runtime_report": ("tool_evidence", "none", False),

    "web_content": ("external_untrusted", "none", False),
    "external_document": ("external_untrusted", "none", False),
    "imported_text": ("external_untrusted", "none", False),
    "external_message": ("external_untrusted", "none", False),
    "email_content": ("external_untrusted", "none", False),
    "issue_content": ("external_untrusted", "none", False),
    "user_attachment": ("external_untrusted", "none", False),

    "generated_summary": ("generated_evidence", "none", False),
    "model_summary": ("generated_evidence", "none", False),
    "compressed_summary": ("generated_evidence", "none", False),
}

_AUTHORITY_PRESERVING_TRANSFORMS = frozenset(
    {
        "verbatim",
        "exact_copy",
        "exact_extract",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContextAuthorityError(RuntimeError):
    """Raised when provenance or authority invariants are violated."""


@dataclass(frozen=True)
class ProvenanceRecord:
    """Hash-only provenance envelope suitable for manifests and SQLite state."""

    provenance_id: str
    provenance_version: int
    source_kind: str
    trust_class: str
    authority_class: str
    instruction_authority: bool
    source_locator_hash: str
    content_hash: str
    producer: str
    transform: str
    parent_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_hash(value: str, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise ContextAuthorityError(f"{field}_must_be_sha256")
    return normalized


def classify_source(source_kind: str) -> dict[str, Any]:
    """Classify one origin without examining or interpreting its content."""

    kind = str(source_kind or "").strip().lower()
    trust, authority, instruction = _SOURCE_CLASSIFICATION.get(
        kind,
        ("unknown_untrusted", "none", False),
    )
    return {
        "source_kind": kind or "unknown",
        "trust_class": trust,
        "authority_class": authority,
        "instruction_authority": bool(instruction),
        "known_source": kind in _SOURCE_CLASSIFICATION,
    }


def _authority_kind_matches(
    source_kind: str,
    authority_class: str,
) -> bool:
    classified = classify_source(source_kind)
    return (
        classified["authority_class"] == authority_class
        and classified["instruction_authority"] is True
    )


def make_provenance_record(
    *,
    source_kind: str,
    content_hash: str,
    source_locator: str,
    producer: str,
    transform: str = "verbatim",
    parents: Iterable[ProvenanceRecord] | None = None,
) -> ProvenanceRecord:
    """Create one deterministic provenance record with no raw content storage."""

    content_digest = _validate_hash(content_hash, "content_hash")
    source_locator_hash = _sha256_text(str(source_locator or ""))
    producer_name = str(producer or "unknown").strip() or "unknown"
    transform_name = str(transform or "verbatim").strip().lower() or "verbatim"
    parent_records = tuple(parents or ())
    base = classify_source(source_kind)

    authority_class = str(base["authority_class"])
    instruction_authority = bool(base["instruction_authority"])

    if parent_records:
        parent_authorities = {p.authority_class for p in parent_records}
        all_same_authority = (
            len(parent_authorities) == 1
            and AUTHORITY_NONE not in parent_authorities
        )
        preserved_authority = (
            transform_name in _AUTHORITY_PRESERVING_TRANSFORMS
            and all_same_authority
            and _authority_kind_matches(
                str(base["source_kind"]),
                next(iter(parent_authorities))
                if parent_authorities
                else AUTHORITY_NONE,
            )
        )
        if not preserved_authority:
            authority_class = AUTHORITY_NONE
            instruction_authority = False

    if authority_class not in AUTHORITY_CLASSES:
        raise ContextAuthorityError("invalid_authority_class")
    if str(base["trust_class"]) not in TRUST_CLASSES:
        raise ContextAuthorityError("invalid_trust_class")
    if instruction_authority != (authority_class != AUTHORITY_NONE):
        raise ContextAuthorityError("instruction_authority_class_mismatch")

    parent_ids = tuple(sorted({p.provenance_id for p in parent_records}))
    seed = {
        "provenance_version": PROVENANCE_VERSION,
        "source_kind": str(base["source_kind"]),
        "trust_class": str(base["trust_class"]),
        "authority_class": authority_class,
        "instruction_authority": instruction_authority,
        "source_locator_hash": source_locator_hash,
        "content_hash": content_digest,
        "producer": producer_name,
        "transform": transform_name,
        "parent_ids": list(parent_ids),
    }
    provenance_id = "CTXPROV-" + _sha256_text(_canonical_json(seed))[:24].upper()
    return ProvenanceRecord(
        provenance_id=provenance_id,
        provenance_version=PROVENANCE_VERSION,
        source_kind=str(base["source_kind"]),
        trust_class=str(base["trust_class"]),
        authority_class=authority_class,
        instruction_authority=instruction_authority,
        source_locator_hash=source_locator_hash,
        content_hash=content_digest,
        producer=producer_name,
        transform=transform_name,
        parent_ids=parent_ids,
    )


def evaluate_provenance(
    records: Iterable[ProvenanceRecord],
) -> dict[str, Any]:
    """Evaluate origin/authority consistency without semantic content analysis."""

    items = sorted(records, key=lambda item: item.provenance_id)
    findings: list[dict[str, str]] = []
    for item in items:
        classified = classify_source(item.source_kind)
        if (
            item.authority_class != AUTHORITY_NONE
            and classified["authority_class"] != item.authority_class
        ):
            findings.append(
                {
                    "code": "authority_promotion_attempt",
                    "severity": "block",
                    "provenance_id": item.provenance_id,
                }
            )
        if item.instruction_authority and item.authority_class == AUTHORITY_NONE:
            findings.append(
                {
                    "code": "instruction_authority_without_authority_class",
                    "severity": "block",
                    "provenance_id": item.provenance_id,
                }
            )
        if not classified["known_source"]:
            findings.append(
                {
                    "code": "unknown_source_treated_untrusted",
                    "severity": "info",
                    "provenance_id": item.provenance_id,
                }
            )

    blocking = [item for item in findings if item["severity"] == "block"]
    manifest_rows = [item.as_dict() for item in items]
    provenance_manifest_hash = _sha256_text(_canonical_json(manifest_rows))
    authority_rows = [
        {
            "provenance_id": item.provenance_id,
            "source_kind": item.source_kind,
            "authority_class": item.authority_class,
            "instruction_authority": item.instruction_authority,
            "content_hash": item.content_hash,
        }
        for item in items
        if item.instruction_authority
    ]
    context_authority_hash = _sha256_text(_canonical_json(authority_rows))
    return {
        "ok": not blocking,
        "record_count": len(items),
        "authority_record_count": len(authority_rows),
        "finding_count": len(findings),
        "blocking_finding_count": len(blocking),
        "findings": findings,
        "provenance_manifest_hash": provenance_manifest_hash,
        "context_authority_hash": context_authority_hash,
    }


def migration_63(c: Any) -> None:
    """Create hash-only v0.30.0 context-authority state."""

    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS context_provenance_records(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            transport_pack_id INTEGER,
            provenance_id TEXT NOT NULL,
            provenance_version INTEGER NOT NULL,
            source_kind TEXT NOT NULL,
            trust_class TEXT NOT NULL,
            authority_class TEXT NOT NULL,
            instruction_authority INTEGER NOT NULL DEFAULT 0,
            source_locator_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            producer TEXT NOT NULL,
            transform TEXT NOT NULL,
            parent_ids_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(task_id,context_revision,provenance_id)
        );
        CREATE INDEX IF NOT EXISTS idx_context_provenance_task
            ON context_provenance_records(
                task_id,context_revision,trust_class,authority_class
            );

        CREATE TABLE IF NOT EXISTS context_authority_evaluations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            transport_pack_id INTEGER,
            provenance_manifest_hash TEXT NOT NULL,
            context_authority_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            record_count INTEGER NOT NULL,
            authority_record_count INTEGER NOT NULL,
            finding_count INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_context_authority_eval_task
            ON context_authority_evaluations(
                task_id,context_revision,created_at
            );

        CREATE TABLE IF NOT EXISTS context_authority_findings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL,
            provenance_id TEXT,
            code TEXT NOT NULL,
            severity TEXT NOT NULL,
            detail_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(evaluation_id)
                REFERENCES context_authority_evaluations(id)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_context_authority_findings_eval
            ON context_authority_findings(
                evaluation_id,severity,code
            );
        """
    )

    columns = {
        str(row[1])
        for row in c.execute("PRAGMA table_info(context_transport_packs)")
    }
    if columns:
        if "provenance_manifest_hash" not in columns:
            c.execute(
                "ALTER TABLE context_transport_packs "
                "ADD COLUMN provenance_manifest_hash TEXT"
            )
        if "context_authority_hash" not in columns:
            c.execute(
                "ALTER TABLE context_transport_packs "
                "ADD COLUMN context_authority_hash TEXT"
            )


def schema_contract() -> dict[str, Any]:
    """Return a privacy-safe description of the schema 63 contract."""

    return {
        "migration_version": MIGRATION_VERSION,
        "provenance_version": PROVENANCE_VERSION,
        "raw_context_persisted": False,
        "content_hash_required": True,
        "source_locator_hashed": True,
        "unknown_source_default": "unknown_untrusted",
        "evidence_instruction_authority": False,
        "transform_may_raise_authority": False,
    }
