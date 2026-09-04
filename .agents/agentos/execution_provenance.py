"""
File: .agents/agentos/execution_provenance.py

Purpose:
    Persist privacy-safe execution identity and provider/model provenance for
    AgentOS-governed executions without granting instruction authority.

Responsibilities:
    - Create schema-65 execution provenance without altering historical task_outcomes.
    - Bind provider/model declarations to immutable local or explicit execution refs.
    - Bind current Context Authority hashes and optional architecture/plan hashes.
    - Persist provider request identifiers only as SHA-256 hashes.
    - Link new task outcomes through a separate table.
    - Never persist credentials, endpoint URLs, raw prompts, or raw responses.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .db import connect, connect_read_only
from .policy import load_policy

MIGRATION_VERSION = 65
PROVENANCE_VERSION = 1
EXECUTION_REF_TYPES = {"async_job", "governed_operation", "external_agent_run"}
ENDPOINT_CLASSES = {"local", "remote_api", "managed_service", "unknown"}
VERIFICATION_CLASSES = {"declared", "runtime_bound"}


class ExecutionProvenanceError(RuntimeError):
    """Raised when execution/model provenance cannot be safely established."""


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_sha(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _safe_label(
    value: Any,
    *,
    field: str,
    required: bool = False,
    limit: int = 192,
) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ExecutionProvenanceError(field + "_required")
        return None
    if len(text) > limit:
        raise ExecutionProvenanceError(field + "_too_long")
    if any(ord(ch) < 32 for ch in text):
        raise ExecutionProvenanceError(field + "_control_character_forbidden")
    lowered = text.lower()
    secret_markers = (
        "bearer ",
        "api_key=",
        "apikey=",
        "password=",
        "secret=",
        "token=",
        "authorization:",
    )
    if any(marker in lowered for marker in secret_markers):
        raise ExecutionProvenanceError(field + "_secret_material_forbidden")
    if text.startswith("sk-") and len(text) > 20:
        raise ExecutionProvenanceError(field + "_secret_material_forbidden")
    if "://" in text:
        raise ExecutionProvenanceError(field + "_url_forbidden")
    return text


def _policy(root: Path) -> dict[str, Any]:
    section = load_policy(root).get("execution_identity_policy")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        raise ExecutionProvenanceError("execution_identity_policy_required")

    required_true = (
        "provider_required",
        "model_required",
        "agent_id_required",
        "recorded_by_required",
        "execution_reference_required",
        "runtime_bound_verification_supported",
        "external_declaration_supported",
        "context_hash_binding_required",
        "provider_request_id_hash_only",
        "separate_outcome_link_required",
        "learning_effectiveness_provider_model_matching_required",
    )
    for key in required_true:
        if section.get(key) is not True:
            raise ExecutionProvenanceError(
                "execution_identity_required_invariant_disabled:" + key
            )

    required_false = (
        "remote_provider_cryptographic_attestation_claimed",
        "endpoint_url_persistence_allowed",
        "credential_or_secret_persistence_allowed",
        "raw_prompt_persistence_allowed",
        "raw_response_persistence_allowed",
        "context_authority_affected",
        "instruction_authority",
        "automatic_model_provider_selection",
        "agent_plane_registration_allowed",
        "mcp_mutation_allowed",
    )
    for key in required_false:
        if section.get(key) is not False:
            raise ExecutionProvenanceError(
                "execution_identity_nonclaim_or_authority_violation:" + key
            )

    if int(section.get("provenance_version", 0)) != PROVENANCE_VERSION:
        raise ExecutionProvenanceError("execution_provenance_version_invalid")
    if int(section.get("database_schema", 0)) != MIGRATION_VERSION:
        raise ExecutionProvenanceError("execution_provenance_schema_invalid")
    if set(section.get("execution_ref_types", [])) != EXECUTION_REF_TYPES:
        raise ExecutionProvenanceError("execution_reference_registry_invalid")
    if set(section.get("endpoint_classes", [])) != ENDPOINT_CLASSES:
        raise ExecutionProvenanceError("execution_endpoint_class_registry_invalid")
    if set(section.get("verification_classes", [])) != VERIFICATION_CLASSES:
        raise ExecutionProvenanceError("execution_verification_registry_invalid")
    return section


def migration_65(c: Any) -> None:
    """Create durable execution provenance and separate outcome linkage."""
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS execution_provenance(
            provenance_id TEXT PRIMARY KEY,
            provenance_version INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            execution_ref_type TEXT NOT NULL,
            execution_ref_id TEXT NOT NULL,
            execution_ref_hash TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            model_revision TEXT,
            deployment_id TEXT,
            provider_request_id_hash TEXT,
            agent_id TEXT NOT NULL,
            runtime_id TEXT,
            runtime_version TEXT,
            endpoint_class TEXT NOT NULL,
            recorded_by TEXT NOT NULL,
            source_class TEXT NOT NULL,
            verification_class TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            context_authority_hash TEXT NOT NULL,
            provenance_manifest_hash TEXT NOT NULL,
            architecture_baseline_hash TEXT,
            plan_hash TEXT,
            policy_revision TEXT NOT NULL,
            declaration_hash TEXT NOT NULL,
            binding_hash TEXT NOT NULL UNIQUE,
            secrets_included INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(execution_ref_type,execution_ref_id)
        );
        CREATE INDEX IF NOT EXISTS idx_execution_provenance_task
            ON execution_provenance(task_id,session_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_execution_provenance_model
            ON execution_provenance(
                provider_id,model_id,verification_class,created_at
            );

        CREATE TABLE IF NOT EXISTS task_outcome_provenance_links(
            outcome_id INTEGER PRIMARY KEY,
            provenance_id TEXT NOT NULL,
            link_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(outcome_id)
                REFERENCES task_outcomes(id)
                ON DELETE CASCADE,
            FOREIGN KEY(provenance_id)
                REFERENCES execution_provenance(provenance_id)
        );
        CREATE INDEX IF NOT EXISTS idx_outcome_provenance_lookup
            ON task_outcome_provenance_links(provenance_id,outcome_id);
        """
    )


def _latest_context_pins(c: Any, task_id: str) -> dict[str, Any]:
    row = c.execute(
        """
        SELECT context_revision,provenance_manifest_hash,context_authority_hash
        FROM context_authority_evaluations
        WHERE task_id=?
        ORDER BY context_revision DESC,id DESC
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    if not row:
        raise ExecutionProvenanceError(
            "execution_context_authority_evaluation_required"
        )
    provenance_hash = str(row["provenance_manifest_hash"] or "").lower()
    authority_hash = str(row["context_authority_hash"] or "").lower()
    if not _valid_sha(provenance_hash):
        raise ExecutionProvenanceError(
            "execution_provenance_manifest_hash_invalid"
        )
    if not _valid_sha(authority_hash):
        raise ExecutionProvenanceError(
            "execution_context_authority_hash_invalid"
        )
    return {
        "context_revision": int(row["context_revision"]),
        "provenance_manifest_hash": provenance_hash,
        "context_authority_hash": authority_hash,
    }


def _active_architecture_hash(c: Any) -> str | None:
    row = c.execute(
        """
        SELECT baseline_hash
        FROM architecture_baselines
        WHERE status='active'
        ORDER BY activated_at DESC,rowid DESC
        LIMIT 1
        """
    ).fetchone()
    value = str(row["baseline_hash"] or "") if row else ""
    return value.lower() if _valid_sha(value) else None


def _active_plan_hash(c: Any, task_id: str) -> str | None:
    row = c.execute(
        """
        SELECT plan_hash
        FROM task_plans
        WHERE task_id=? AND status='active'
        ORDER BY revision DESC,rowid DESC
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    value = str(row["plan_hash"] or "") if row else ""
    return value.lower() if _valid_sha(value) else None


def _resolve_reference(
    c: Any,
    *,
    task_id: str,
    session_id: str,
    execution_ref_type: str,
    execution_ref_id: str,
) -> dict[str, str]:
    if execution_ref_type == "async_job":
        row = c.execute(
            """
            SELECT task_id,session_id,spec_hash
            FROM async_jobs
            WHERE job_id=?
            """,
            (execution_ref_id,),
        ).fetchone()
        if not row:
            raise ExecutionProvenanceError("execution_async_job_missing")
        if (
            str(row["task_id"]) != task_id
            or str(row["session_id"]) != session_id
        ):
            raise ExecutionProvenanceError(
                "execution_async_job_identity_mismatch"
            )
        digest = str(row["spec_hash"] or "").lower()
        if not _valid_sha(digest):
            raise ExecutionProvenanceError(
                "execution_async_job_spec_hash_invalid"
            )
        return {
            "execution_ref_hash": digest,
            "source_class": "immutable_runtime_spec",
            "verification_class": "runtime_bound",
        }

    if execution_ref_type == "governed_operation":
        row = c.execute(
            """
            SELECT task_id,session_id,capability,intent_hash,
                   execution_token_hash,external_request_hash
            FROM governed_operations
            WHERE operation_id=?
            """,
            (execution_ref_id,),
        ).fetchone()
        if not row:
            raise ExecutionProvenanceError(
                "execution_governed_operation_missing"
            )
        if (
            str(row["task_id"]) != task_id
            or str(row["session_id"]) != session_id
        ):
            raise ExecutionProvenanceError(
                "execution_governed_operation_identity_mismatch"
            )
        return {
            "execution_ref_hash": _sha(
                {
                    "operation_id": execution_ref_id,
                    "capability": row["capability"],
                    "intent_hash": row["intent_hash"],
                    "execution_token_hash": row["execution_token_hash"],
                    "external_request_hash": row["external_request_hash"],
                }
            ),
            "source_class": "immutable_runtime_spec",
            "verification_class": "runtime_bound",
        }

    if execution_ref_type == "external_agent_run":
        return {
            "execution_ref_hash": _sha(
                {
                    "execution_ref_type": execution_ref_type,
                    "execution_ref_id": execution_ref_id,
                    "task_id": task_id,
                    "session_id": session_id,
                }
            ),
            "source_class": "explicit_declaration",
            "verification_class": "declared",
        }

    raise ExecutionProvenanceError("execution_reference_type_unsupported")


def register_execution_provenance(
    root: Path,
    *,
    task_id: str,
    session_id: str,
    execution_ref_type: str,
    execution_ref_id: str,
    provider_id: str,
    model_id: str,
    agent_id: str,
    endpoint_class: str,
    recorded_by: str,
    model_revision: str | None = None,
    deployment_id: str | None = None,
    provider_request_id: str | None = None,
    runtime_id: str | None = None,
    runtime_version: str | None = None,
) -> dict[str, Any]:
    """Persist one privileged provider/model declaration bound to an execution."""
    _policy(root)
    release_policy = load_policy(root)
    policy_revision = str(release_policy.get("version") or "").strip()
    if not policy_revision:
        raise ExecutionProvenanceError("execution_policy_revision_missing")

    task = _safe_label(task_id, field="task_id", required=True)
    session = _safe_label(session_id, field="session_id", required=True)
    ref_type = str(execution_ref_type or "").strip()
    ref_id = _safe_label(
        execution_ref_id,
        field="execution_ref_id",
        required=True,
        limit=256,
    )
    provider = _safe_label(provider_id, field="provider_id", required=True)
    model = _safe_label(model_id, field="model_id", required=True)
    agent = _safe_label(agent_id, field="agent_id", required=True)
    actor = _safe_label(recorded_by, field="recorded_by", required=True)
    model_rev = _safe_label(model_revision, field="model_revision")
    deployment = _safe_label(deployment_id, field="deployment_id")
    runtime = _safe_label(runtime_id, field="runtime_id")
    runtime_ver = _safe_label(runtime_version, field="runtime_version")
    provider_request = _safe_label(
        provider_request_id,
        field="provider_request_id",
        limit=512,
    )
    endpoint = str(endpoint_class or "").strip()

    if ref_type not in EXECUTION_REF_TYPES:
        raise ExecutionProvenanceError("execution_reference_type_unsupported")
    if endpoint not in ENDPOINT_CLASSES:
        raise ExecutionProvenanceError("endpoint_class_invalid")

    provider_request_hash = (
        _sha(provider_request)
        if provider_request is not None
        else None
    )

    with connect(root, immediate=True) as c:
        if not c.execute(
            "SELECT 1 FROM tasks WHERE id=?",
            (task,),
        ).fetchone():
            raise ExecutionProvenanceError("execution_provenance_task_missing")

        reference = _resolve_reference(
            c,
            task_id=str(task),
            session_id=str(session),
            execution_ref_type=ref_type,
            execution_ref_id=str(ref_id),
        )
        context = _latest_context_pins(c, str(task))
        architecture_hash = _active_architecture_hash(c)
        plan_hash = _active_plan_hash(c, str(task))

        declaration = {
            "provider_id": provider,
            "model_id": model,
            "model_revision": model_rev,
            "deployment_id": deployment,
            "provider_request_id_hash": provider_request_hash,
            "agent_id": agent,
            "runtime_id": runtime,
            "runtime_version": runtime_ver,
            "endpoint_class": endpoint,
            "recorded_by": actor,
        }
        declaration_hash = _sha(declaration)

        binding = {
            "v": PROVENANCE_VERSION,
            "task_id": task,
            "session_id": session,
            "execution_ref_type": ref_type,
            "execution_ref_id": ref_id,
            "execution_ref_hash": reference["execution_ref_hash"],
            "declaration_hash": declaration_hash,
            "verification_class": reference["verification_class"],
            "context_revision": context["context_revision"],
            "context_authority_hash": context["context_authority_hash"],
            "provenance_manifest_hash": context["provenance_manifest_hash"],
            "architecture_baseline_hash": architecture_hash,
            "plan_hash": plan_hash,
            "policy_revision": policy_revision,
        }
        binding_hash = _sha(binding)
        provenance_id = "EP-" + binding_hash[:24].upper()

        old = c.execute(
            """
            SELECT *
            FROM execution_provenance
            WHERE execution_ref_type=? AND execution_ref_id=?
            """,
            (ref_type, ref_id),
        ).fetchone()
        if old:
            if str(old["binding_hash"]) != binding_hash:
                raise ExecutionProvenanceError(
                    "execution_reference_already_bound_to_different_provenance"
                )
            return {
                **dict(old),
                "created": False,
                "idempotent": True,
                "remote_provider_cryptographic_attestation": False,
                "instruction_authority": False,
            }

        values = (
            provenance_id,
            PROVENANCE_VERSION,
            task,
            session,
            ref_type,
            ref_id,
            reference["execution_ref_hash"],
            provider,
            model,
            model_rev,
            deployment,
            provider_request_hash,
            agent,
            runtime,
            runtime_ver,
            endpoint,
            actor,
            reference["source_class"],
            reference["verification_class"],
            context["context_revision"],
            context["context_authority_hash"],
            context["provenance_manifest_hash"],
            architecture_hash,
            plan_hash,
            policy_revision,
            declaration_hash,
            binding_hash,
        )
        placeholders = ",".join("?" for _ in values)
        c.execute(
            f"""
            INSERT INTO execution_provenance(
                provenance_id,provenance_version,task_id,session_id,
                execution_ref_type,execution_ref_id,execution_ref_hash,
                provider_id,model_id,model_revision,deployment_id,
                provider_request_id_hash,agent_id,runtime_id,runtime_version,
                endpoint_class,recorded_by,source_class,verification_class,
                context_revision,context_authority_hash,provenance_manifest_hash,
                architecture_baseline_hash,plan_hash,policy_revision,
                declaration_hash,binding_hash,secrets_included
            ) VALUES({placeholders},0)
            """,
            values,
        )
        row = c.execute(
            "SELECT * FROM execution_provenance WHERE provenance_id=?",
            (provenance_id,),
        ).fetchone()

    return {
        **dict(row),
        "created": True,
        "idempotent": False,
        "remote_provider_cryptographic_attestation": False,
        "instruction_authority": False,
    }


def resolve_provenance_for_outcome(
    c: Any,
    *,
    task_id: str,
    provenance_id: str,
    session_id: str | None = None,
    caller_agent_id: str | None = None,
    caller_model_id: str | None = None,
    caller_policy_revision: str | None = None,
    caller_context_revision: Any = None,
) -> dict[str, Any]:
    """Resolve canonical provenance for atomic task-outcome insertion."""
    row = c.execute(
        "SELECT * FROM execution_provenance WHERE provenance_id=?",
        (str(provenance_id),),
    ).fetchone()
    if not row:
        raise ExecutionProvenanceError("outcome_execution_provenance_missing")
    value = dict(row)

    if str(value["task_id"]) != str(task_id):
        raise ExecutionProvenanceError(
            "outcome_execution_provenance_task_mismatch"
        )
    if session_id and str(value["session_id"]) != str(session_id):
        raise ExecutionProvenanceError(
            "outcome_execution_provenance_session_mismatch"
        )
    if caller_agent_id and str(caller_agent_id) != str(value["agent_id"]):
        raise ExecutionProvenanceError(
            "outcome_agent_id_conflicts_with_provenance"
        )
    if caller_model_id and str(caller_model_id) != str(value["model_id"]):
        raise ExecutionProvenanceError(
            "outcome_model_id_conflicts_with_provenance"
        )
    if (
        caller_policy_revision
        and str(caller_policy_revision) != str(value["policy_revision"])
    ):
        raise ExecutionProvenanceError(
            "outcome_policy_revision_conflicts_with_provenance"
        )
    if (
        caller_context_revision is not None
        and str(caller_context_revision) != str(value["context_revision"])
    ):
        raise ExecutionProvenanceError(
            "outcome_context_revision_conflicts_with_provenance"
        )
    if int(value.get("secrets_included") or 0) != 0:
        raise ExecutionProvenanceError(
            "outcome_execution_provenance_secret_flag_invalid"
        )
    return value


def link_outcome_provenance(
    c: Any,
    *,
    outcome_id: int,
    provenance_id: str,
) -> dict[str, Any]:
    """Bind one task outcome to exactly one execution provenance record."""
    link_hash = _sha(
        {
            "outcome_id": int(outcome_id),
            "provenance_id": str(provenance_id),
        }
    )
    old = c.execute(
        "SELECT * FROM task_outcome_provenance_links WHERE outcome_id=?",
        (int(outcome_id),),
    ).fetchone()
    if old:
        if str(old["provenance_id"]) != str(provenance_id):
            raise ExecutionProvenanceError(
                "outcome_provenance_conflicting_link"
            )
        return {**dict(old), "created": False, "idempotent": True}

    c.execute(
        """
        INSERT INTO task_outcome_provenance_links(
            outcome_id,provenance_id,link_hash
        ) VALUES(?,?,?)
        """,
        (int(outcome_id), str(provenance_id), link_hash),
    )
    return {
        "outcome_id": int(outcome_id),
        "provenance_id": str(provenance_id),
        "link_hash": link_hash,
        "created": True,
        "idempotent": False,
    }


def get_execution_provenance(
    root: Path,
    provenance_id: str,
) -> dict[str, Any]:
    """Return one privacy-safe execution provenance record."""
    _policy(root)
    with connect_read_only(root) as c:
        row = c.execute(
            "SELECT * FROM execution_provenance WHERE provenance_id=?",
            (str(provenance_id),),
        ).fetchone()
    if not row:
        raise ExecutionProvenanceError("execution_provenance_missing")
    return {
        "ok": True,
        "provenance": dict(row),
        "remote_provider_cryptographic_attestation": False,
        "instruction_authority": False,
    }


def execution_provenance_status(root: Path) -> dict[str, Any]:
    """Return schema-65 execution provenance counts and bounded non-claims."""
    _policy(root)
    with connect_read_only(root) as c:
        total = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM execution_provenance"
            ).fetchone()["n"]
        )
        declared = int(
            c.execute(
                """
                SELECT COUNT(*) AS n
                FROM execution_provenance
                WHERE verification_class='declared'
                """
            ).fetchone()["n"]
        )
        runtime_bound = int(
            c.execute(
                """
                SELECT COUNT(*) AS n
                FROM execution_provenance
                WHERE verification_class='runtime_bound'
                """
            ).fetchone()["n"]
        )
        linked_outcomes = int(
            c.execute(
                "SELECT COUNT(*) AS n FROM task_outcome_provenance_links"
            ).fetchone()["n"]
        )

    return {
        "ok": True,
        "schema": MIGRATION_VERSION,
        "provenance_version": PROVENANCE_VERSION,
        "record_count": total,
        "declared_count": declared,
        "runtime_bound_count": runtime_bound,
        "linked_outcome_count": linked_outcomes,
        "remote_provider_cryptographic_attestation": False,
        "raw_prompt_persisted": False,
        "raw_response_persisted": False,
        "credential_or_secret_persisted": False,
        "endpoint_url_persisted": False,
        "provider_request_id_raw_persisted": False,
        "automatic_model_provider_selection": False,
        "context_authority_affected": False,
        "instruction_authority": False,
        "agent_plane_registration_allowed": False,
        "mcp_mutation_allowed": False,
    }


def schema_contract() -> dict[str, Any]:
    """Return the bounded privacy and authority contract of schema 65."""
    return {
        "migration_version": MIGRATION_VERSION,
        "provenance_version": PROVENANCE_VERSION,
        "historical_task_outcome_shape_modified": False,
        "outcome_link_table_separate": True,
        "provider_required": True,
        "model_required": True,
        "agent_id_required": True,
        "recorded_by_required": True,
        "provider_request_id_hash_only": True,
        "raw_prompt_persisted": False,
        "raw_response_persisted": False,
        "endpoint_url_persisted": False,
        "credential_or_secret_persisted": False,
        "remote_provider_cryptographic_attestation": False,
        "automatic_model_provider_selection": False,
        "context_authority_affected": False,
        "instruction_authority": False,
    }
