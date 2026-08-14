"""
File: .agents/agentos/mcp_feature_handlers.py

Purpose:
    Own runtime-native MCP feature tool definitions and read-only handlers that
    were historically embedded in version-forwarding mcp_*_gateway modules.

Responsibilities:
    - Preserve the exact public tool names/schemas for migrated feature families.
    - Dispatch directly to domain modules in-process.
    - Exclude subprocess/version forwarding from the active handler path.
    - Keep mutation, approval, secret resolution, and TARGET writes outside MCP.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .project_identity import ensure_instance_id, ensure_project_id, load_purpose, verify_identity
from .project_selection import get_candidate_set, get_primary_selection, recommend_primary
from .project_consolidation import get_consolidation as get_project_consolidation
from .database_boundary import authorize_operation, get_connection, get_consolidation as get_db_consolidation
from .schema_mapping import (
    get_schema_snapshot,
    get_target_contract,
    list_field_mappings,
    mapping_readiness,
    suggest_field_mappings,
)
from .read_only_extraction import (
    get_extraction_batch,
    get_extraction_summary,
    get_validation_findings,
    verify_staging_artifact,
)
from .controlled_target_insert import (
    build_insert_spec,
    get_target_insert_plan,
    get_target_insert_readiness,
    get_target_insert_receipt,
)
from .identity_resolution import (
    get_entity_lineage,
    get_identity_policy,
    get_identity_readiness,
    get_identity_resolution_run,
    list_identity_candidates,
)
from .reconciliation_recovery import (
    build_reconciliation_spec,
    get_reconciliation_run,
    get_reconciliation_summary,
    get_recovery_readiness,
    list_recovery_cases,
    list_recovery_checkpoints,
)

FeatureHandler = Callable[[str, dict[str, Any], Path], dict[str, Any]]

TOOL_GROUPS = {'IDENTITY': [{'name': 'agentos.project_identity_get',
               'description': 'Read the stable project UUID and local instance UUID. Read-only.',
               'inputSchema': {'type': 'object', 'properties': {}}},
              {'name': 'agentos.project_identity_verify',
               'description': 'Verify stable identity, purpose completeness, relocation, and clone collision state. Read-only.',
               'inputSchema': {'type': 'object', 'properties': {}}},
              {'name': 'agentos.project_purpose_get',
               'description': 'Read the human-confirmed business domain, purpose, capabilities, and role. Read-only.',
               'inputSchema': {'type': 'object', 'properties': {}}}],
 'SELECTION': [{'name': 'agentos.project_candidate_set_get',
                'description': 'Read a registered multi-project candidate set and its compatibility matrix. Read-only.',
                'inputSchema': {'type': 'object',
                                'properties': {'candidate_set_id': {'type': 'integer'}},
                                'required': ['candidate_set_id']}},
               {'name': 'agentos.project_domain_compatibility_get',
                'description': 'Read deterministic business-domain and purpose compatibility evidence. Read-only.',
                'inputSchema': {'type': 'object',
                                'properties': {'candidate_set_id': {'type': 'integer'}},
                                'required': ['candidate_set_id']}},
               {'name': 'agentos.project_primary_recommend',
                'description': 'Return an advisory primary-project ranking. Never selects or approves a primary project.',
                'inputSchema': {'type': 'object',
                                'properties': {'candidate_set_id': {'type': 'integer'}},
                                'required': ['candidate_set_id']}},
               {'name': 'agentos.project_primary_selection_get',
                'description': 'Read the human-selected primary project, if selection has been committed. Read-only.',
                'inputSchema': {'type': 'object',
                                'properties': {'candidate_set_id': {'type': 'integer'}},
                                'required': ['candidate_set_id']}}],
 'CONSOLIDATION': [{'name': 'agentos.project_consolidation_get',
                    'description': 'Read a Primary-Project Consolidation, its sources, mappings, approval state and provenance. Read-only.',
                    'inputSchema': {'type': 'object',
                                    'properties': {'consolidation_id': {'type': 'integer'}},
                                    'required': ['consolidation_id']}},
                   {'name': 'agentos.project_consolidation_plan_get',
                    'description': 'Read the current consolidation plan and plan hash. Read-only; cannot review or approve.',
                    'inputSchema': {'type': 'object',
                                    'properties': {'consolidation_id': {'type': 'integer'}},
                                    'required': ['consolidation_id']}},
                   {'name': 'agentos.project_consolidation_provenance_get',
                    'description': 'Read per-component consolidation provenance and rollback state. Read-only.',
                    'inputSchema': {'type': 'object',
                                    'properties': {'consolidation_id': {'type': 'integer'}},
                                    'required': ['consolidation_id']}}],
 'DATABASE_BOUNDARY': [{'name': 'agentos.db_connection_get',
                        'description': 'Read redacted SOURCE/TARGET connection metadata. Read-only; credentials are never returned.',
                        'inputSchema': {'type': 'object',
                                        'properties': {'connection_id': {'type': 'integer'}},
                                        'required': ['connection_id']}},
                       {'name': 'agentos.db_consolidation_get',
                        'description': 'Read a one-target database consolidation and its verified SOURCE connections. Read-only.',
                        'inputSchema': {'type': 'object',
                                        'properties': {'consolidation_id': {'type': 'integer'}},
                                        'required': ['consolidation_id']}},
                       {'name': 'agentos.db_boundary_check',
                        'description': 'Check whether an abstract database operation is allowed by v0.21.0 boundary policy. Does not '
                                       'execute SQL.',
                        'inputSchema': {'type': 'object',
                                        'properties': {'connection_id': {'type': 'integer'}, 'operation': {'type': 'string'}},
                                        'required': ['connection_id', 'operation']}}],
 'SCHEMA_MAPPING': [{'name': 'agentos.db_schema_snapshot_get',
                     'description': 'Read a metadata-only database schema snapshot. No record data or credentials are returned.',
                     'inputSchema': {'type': 'object', 'properties': {'snapshot_id': {'type': 'integer'}}, 'required': ['snapshot_id']}},
                    {'name': 'agentos.db_target_contract_get',
                     'description': 'Read a versioned target schema contract and its immutable hashes. Read-only.',
                     'inputSchema': {'type': 'object', 'properties': {'contract_id': {'type': 'integer'}}, 'required': ['contract_id']}},
                    {'name': 'agentos.db_field_mappings_get',
                     'description': 'List directional SOURCE-to-TARGET field mappings for one database consolidation. Read-only.',
                     'inputSchema': {'type': 'object',
                                     'properties': {'consolidation_id': {'type': 'integer'}, 'status': {'type': 'string'}},
                                     'required': ['consolidation_id']}},
                    {'name': 'agentos.db_field_mapping_suggest',
                     'description': 'Compute advisory local lexical/type mapping suggestions. Does not persist or confirm mappings.',
                     'inputSchema': {'type': 'object',
                                     'properties': {'consolidation_id': {'type': 'integer'},
                                                    'source_snapshot_id': {'type': 'integer'},
                                                    'target_contract_id': {'type': 'integer'},
                                                    'limit': {'type': 'integer'}},
                                     'required': ['consolidation_id', 'source_snapshot_id', 'target_contract_id']}},
                    {'name': 'agentos.db_mapping_readiness_get',
                     'description': 'Read whether confirmed current mappings are ready for v0.21.2 extraction/validation. Does not extract '
                                    'data.',
                     'inputSchema': {'type': 'object',
                                     'properties': {'consolidation_id': {'type': 'integer'}, 'target_contract_id': {'type': 'integer'}},
                                     'required': ['consolidation_id', 'target_contract_id']}}],
 'READ_ONLY_EXTRACTION': [{'name': 'agentos.db_extraction_batch_get',
                           'description': 'Read v0.21.2 extraction batch metadata and immutable hashes. Does not return record values.',
                           'inputSchema': {'type': 'object', 'properties': {'batch_id': {'type': 'integer'}}, 'required': ['batch_id']}},
                          {'name': 'agentos.db_extraction_summary_get',
                           'description': 'Read privacy-safe extraction/validation counts, artifact hashes, and v0.22.0 readiness.',
                           'inputSchema': {'type': 'object', 'properties': {'batch_id': {'type': 'integer'}}, 'required': ['batch_id']}},
                          {'name': 'agentos.db_validation_findings_get',
                           'description': 'Read validation issues with value hashes only; raw business values are never returned.',
                           'inputSchema': {'type': 'object',
                                           'properties': {'batch_id': {'type': 'integer'}, 'limit': {'type': 'integer'}},
                                           'required': ['batch_id']}},
                          {'name': 'agentos.db_staging_integrity_get',
                           'description': 'Verify staging/quarantine/manifest artifact hashes without returning artifact contents.',
                           'inputSchema': {'type': 'object', 'properties': {'batch_id': {'type': 'integer'}}, 'required': ['batch_id']}}],
 'CONTROLLED_TARGET_INSERT': [{'name': 'agentos.db_target_insert_plan_get',
                               'description': 'Read v0.22.0 immutable controlled TARGET INSERT plan metadata and hashes. No row values or '
                                              'credentials are returned.',
                               'inputSchema': {'type': 'object',
                                               'properties': {'insert_run_id': {'type': 'integer'}},
                                               'required': ['insert_run_id']}},
                              {'name': 'agentos.db_target_insert_readiness_get',
                               'description': 'Read current human-approval, staging-integrity, and contract readiness for a controlled '
                                              'TARGET INSERT run.',
                               'inputSchema': {'type': 'object',
                                               'properties': {'insert_run_id': {'type': 'integer'}},
                                               'required': ['insert_run_id']}},
                              {'name': 'agentos.db_target_insert_spec_get',
                               'description': 'Read the generated parameterized INSERT-only statement shape. No parameter values are '
                                              'returned and raw SQL execution is not exposed.',
                               'inputSchema': {'type': 'object',
                                               'properties': {'insert_run_id': {'type': 'integer'}},
                                               'required': ['insert_run_id']}},
                              {'name': 'agentos.db_target_insert_receipt_get',
                               'description': 'Read privacy-safe TARGET insert status/receipt hashes and row counts. No inserted business '
                                              'values are returned.',
                               'inputSchema': {'type': 'object',
                                               'properties': {'insert_run_id': {'type': 'integer'}},
                                               'required': ['insert_run_id']}}],
 'IDENTITY_RESOLUTION': [{'name': 'agentos.db_identity_policy_get',
                          'description': 'Read an approved/draft deterministic identity policy. No business values are returned.',
                          'inputSchema': {'type': 'object', 'properties': {'policy_id': {'type': 'integer'}}, 'required': ['policy_id']}},
                         {'name': 'agentos.db_identity_resolution_get',
                          'description': 'Read v0.22.1 identity-resolution status, counts, and hashes only.',
                          'inputSchema': {'type': 'object',
                                          'properties': {'resolution_run_id': {'type': 'integer'}},
                                          'required': ['resolution_run_id']}},
                         {'name': 'agentos.db_identity_candidates_get',
                          'description': 'Read privacy-safe strong-match candidates. LLM cannot confirm/reject identity candidates.',
                          'inputSchema': {'type': 'object',
                                          'properties': {'resolution_run_id': {'type': 'integer'}},
                                          'required': ['resolution_run_id']}},
                         {'name': 'agentos.db_identity_readiness_get',
                          'description': 'Read whether an extraction batch has completed human-governed identity/dedup resolution before '
                                         'TARGET INSERT.',
                          'inputSchema': {'type': 'object',
                                          'properties': {'extraction_batch_id': {'type': 'integer'}},
                                          'required': ['extraction_batch_id']}},
                         {'name': 'agentos.db_entity_lineage_get',
                          'description': 'Read pseudonymous source-to-target lineage for a canonical entity UUID. No raw identity values '
                                         'are returned.',
                          'inputSchema': {'type': 'object',
                                          'properties': {'entity_uuid': {'type': 'string'}},
                                          'required': ['entity_uuid']}}],
 'RECONCILIATION_RECOVERY': [{'name': 'agentos.db_reconciliation_get',
                              'description': 'Read one privacy-safe TARGET reconciliation result.',
                              'inputSchema': {'type': 'object',
                                              'properties': {'reconciliation_run_id': {'type': 'integer'}},
                                              'required': ['reconciliation_run_id']}},
                             {'name': 'agentos.db_reconciliation_summary_get',
                              'description': 'Read extraction→identity→insert→lineage reconciliation counts.',
                              'inputSchema': {'type': 'object',
                                              'properties': {'reconciliation_run_id': {'type': 'integer'}},
                                              'required': ['reconciliation_run_id']}},
                             {'name': 'agentos.db_reconciliation_spec_get',
                              'description': 'Read the SELECT-only reconciliation query shape without parameters or values.',
                              'inputSchema': {'type': 'object',
                                              'properties': {'reconciliation_run_id': {'type': 'integer'}},
                                              'required': ['reconciliation_run_id']}},
                             {'name': 'agentos.db_recovery_cases_get',
                              'description': 'List privacy-safe recovery cases; no recovery mutation is available over MCP.',
                              'inputSchema': {'type': 'object', 'properties': {'status': {'type': 'string'}}}},
                             {'name': 'agentos.db_recovery_readiness_get',
                              'description': 'Read fail-closed recovery readiness for one insert run.',
                              'inputSchema': {'type': 'object',
                                              'properties': {'insert_run_id': {'type': 'integer'}},
                                              'required': ['insert_run_id']}},
                             {'name': 'agentos.db_recovery_checkpoints_get',
                              'description': 'Read privacy-safe recovery checkpoint hashes for one insert run.',
                              'inputSchema': {'type': 'object',
                                              'properties': {'insert_run_id': {'type': 'integer'}},
                                              'required': ['insert_run_id']}}]}

IDENTITY_TOOLS = TOOL_GROUPS["IDENTITY"]
SELECTION_TOOLS = TOOL_GROUPS["SELECTION"]
CONSOLIDATION_TOOLS = TOOL_GROUPS["CONSOLIDATION"]
DATABASE_BOUNDARY_TOOLS = TOOL_GROUPS["DATABASE_BOUNDARY"]
SCHEMA_MAPPING_TOOLS = TOOL_GROUPS["SCHEMA_MAPPING"]
READ_ONLY_EXTRACTION_TOOLS = TOOL_GROUPS["READ_ONLY_EXTRACTION"]
CONTROLLED_TARGET_INSERT_TOOLS = TOOL_GROUPS["CONTROLLED_TARGET_INSERT"]
IDENTITY_RESOLUTION_TOOLS = TOOL_GROUPS["IDENTITY_RESOLUTION"]
RECONCILIATION_RECOVERY_TOOLS = TOOL_GROUPS["RECONCILIATION_RECOVERY"]


def _identity_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    del arguments
    if name == "agentos.project_identity_get":
        return {"project": ensure_project_id(root), "instance": ensure_instance_id(root)}
    if name == "agentos.project_identity_verify":
        return verify_identity(root)
    if name == "agentos.project_purpose_get":
        return {"purpose": load_purpose(root)}
    raise RuntimeError(f"unknown project identity MCP tool: {name}")


def _selection_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    candidate_set_id = int(arguments["candidate_set_id"])
    if name == "agentos.project_candidate_set_get":
        return get_candidate_set(root, candidate_set_id)
    if name == "agentos.project_domain_compatibility_get":
        state = get_candidate_set(root, candidate_set_id)
        return {"ok": True, "candidate_set_id": candidate_set_id, "compatibility": state["compatibility"]}
    if name == "agentos.project_primary_recommend":
        return recommend_primary(root, candidate_set_id)
    if name == "agentos.project_primary_selection_get":
        return get_primary_selection(root, candidate_set_id)
    raise RuntimeError(f"unknown project selection MCP tool: {name}")


def _consolidation_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    state = get_project_consolidation(root, int(arguments["consolidation_id"]))
    if name == "agentos.project_consolidation_get":
        return state
    if name == "agentos.project_consolidation_plan_get":
        return {
            "ok": True,
            "consolidation": state["consolidation"],
            "sources": state["sources"],
            "mappings": state["mappings"],
            "review": state["review"],
            "approval": state["approval"],
            "current_plan_hash": state["current_plan_hash"],
        }
    if name == "agentos.project_consolidation_provenance_get":
        return {
            "ok": True,
            "consolidation_id": arguments["consolidation_id"],
            "provenance": state["provenance"],
        }
    raise RuntimeError(f"unknown project consolidation MCP tool: {name}")


def _database_boundary_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name == "agentos.db_connection_get":
        return get_connection(root, int(arguments["connection_id"]))
    if name == "agentos.db_consolidation_get":
        return get_db_consolidation(root, int(arguments["consolidation_id"]))
    if name == "agentos.db_boundary_check":
        return authorize_operation(root, int(arguments["connection_id"]), str(arguments["operation"]))
    raise RuntimeError(f"unknown database boundary MCP tool: {name}")


def _schema_mapping_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name == "agentos.db_schema_snapshot_get":
        return get_schema_snapshot(root, int(arguments["snapshot_id"]))
    if name == "agentos.db_target_contract_get":
        return get_target_contract(root, int(arguments["contract_id"]))
    if name == "agentos.db_field_mappings_get":
        return list_field_mappings(root, int(arguments["consolidation_id"]), status=arguments.get("status"))
    if name == "agentos.db_field_mapping_suggest":
        return suggest_field_mappings(
            root,
            consolidation_id=int(arguments["consolidation_id"]),
            source_snapshot_id=int(arguments["source_snapshot_id"]),
            target_contract_id=int(arguments["target_contract_id"]),
            limit=int(arguments.get("limit", 50)),
        )
    if name == "agentos.db_mapping_readiness_get":
        return mapping_readiness(
            root,
            int(arguments["consolidation_id"]),
            int(arguments["target_contract_id"]),
        )
    raise RuntimeError(f"unknown schema mapping MCP tool: {name}")


def _read_only_extraction_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name == "agentos.db_extraction_batch_get":
        return get_extraction_batch(root, int(arguments["batch_id"]))
    if name == "agentos.db_extraction_summary_get":
        return get_extraction_summary(root, int(arguments["batch_id"]))
    if name == "agentos.db_validation_findings_get":
        return get_validation_findings(
            root,
            int(arguments["batch_id"]),
            limit=int(arguments.get("limit", 1000)),
        )
    if name == "agentos.db_staging_integrity_get":
        return verify_staging_artifact(root, int(arguments["batch_id"]))
    raise RuntimeError(f"unknown read-only extraction MCP tool: {name}")


def _controlled_target_insert_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    run_id = int(arguments["insert_run_id"])
    if name == "agentos.db_target_insert_plan_get":
        return get_target_insert_plan(root, run_id)
    if name == "agentos.db_target_insert_readiness_get":
        return get_target_insert_readiness(root, run_id)
    if name == "agentos.db_target_insert_spec_get":
        return build_insert_spec(root, run_id)
    if name == "agentos.db_target_insert_receipt_get":
        return get_target_insert_receipt(root, run_id)
    raise RuntimeError(f"unknown controlled TARGET insert MCP tool: {name}")


def _identity_resolution_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name == "agentos.db_identity_policy_get":
        return get_identity_policy(root, int(arguments["policy_id"]))
    if name == "agentos.db_identity_resolution_get":
        return get_identity_resolution_run(root, int(arguments["resolution_run_id"]))
    if name == "agentos.db_identity_candidates_get":
        return list_identity_candidates(root, int(arguments["resolution_run_id"]))
    if name == "agentos.db_identity_readiness_get":
        return get_identity_readiness(root, int(arguments["extraction_batch_id"]))
    if name == "agentos.db_entity_lineage_get":
        return get_entity_lineage(root, str(arguments["entity_uuid"]))
    raise RuntimeError(f"unknown identity resolution MCP tool: {name}")


def _reconciliation_recovery_call(name: str, arguments: dict[str, Any], root: Path) -> dict[str, Any]:
    if name == "agentos.db_reconciliation_get":
        return get_reconciliation_run(root, int(arguments["reconciliation_run_id"]))
    if name == "agentos.db_reconciliation_summary_get":
        return get_reconciliation_summary(root, int(arguments["reconciliation_run_id"]))
    if name == "agentos.db_reconciliation_spec_get":
        return build_reconciliation_spec(root, int(arguments["reconciliation_run_id"]))
    if name == "agentos.db_recovery_cases_get":
        return list_recovery_cases(root, status=arguments.get("status"))
    if name == "agentos.db_recovery_readiness_get":
        return get_recovery_readiness(root, int(arguments["insert_run_id"]))
    if name == "agentos.db_recovery_checkpoints_get":
        return list_recovery_checkpoints(root, int(arguments["insert_run_id"]))
    raise RuntimeError(f"unknown reconciliation/recovery MCP tool: {name}")


REGISTRATIONS: tuple[tuple[list[dict[str, Any]], FeatureHandler], ...] = (
    (IDENTITY_TOOLS, _identity_call),
    (SELECTION_TOOLS, _selection_call),
    (CONSOLIDATION_TOOLS, _consolidation_call),
    (DATABASE_BOUNDARY_TOOLS, _database_boundary_call),
    (SCHEMA_MAPPING_TOOLS, _schema_mapping_call),
    (READ_ONLY_EXTRACTION_TOOLS, _read_only_extraction_call),
    (CONTROLLED_TARGET_INSERT_TOOLS, _controlled_target_insert_call),
    (IDENTITY_RESOLUTION_TOOLS, _identity_resolution_call),
    (RECONCILIATION_RECOVERY_TOOLS, _reconciliation_recovery_call),
)

MIGRATED_TOOL_COUNT = sum(len(definitions) for definitions, _ in REGISTRATIONS)
assert MIGRATED_TOOL_COUNT == 37
