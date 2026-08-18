# AgentOS v0.27.0 — Governed Skill Contract v2

Version: **0.27.0**
Database schema: **58**

## Purpose

v0.27.0 upgrades the existing human-approved procedural skill lifecycle into a governed construction contract. It does not introduce automatic skill authority or a new orchestration subsystem.

## Contract fields

```text
contract_version
skill_key
skill_version
inputs
outputs
required_architecture_sections
required_capabilities
required_tools
allowed_read_scope
allowed_write_scope
allowed_dependencies
allowed_external_services
preconditions
postconditions
risk_tier
test_contract
architecture_constraints
```

The contract is canonicalized to deterministic JSON and SHA-256 hashed.

## Lifecycle

```text
verified procedural memory
        ↓
candidate + v2 least-authority draft
        ↓
contract drafting
        ↓
deterministic validation
        ↓
architecture binding when required
        ↓
HUMAN graduation
        ↓
graduated skill
```

Drafting and validation do not grant execution authority. Graduation remains human-only and signed. Revocation remains human-only.

## Architecture binding

Architecture-neutral contracts may validate without an ACTIVE Architecture Baseline. A contract becomes architecture-sensitive when it declares required architecture sections, dependencies, external services, or architecture constraints.

Architecture-sensitive validation requires an ACTIVE human-approved baseline. Successful validation pins:

```text
architecture_baseline_id
architecture_baseline_hash
contract_hash
```

Explicit `ARCH-02.allowed_dependencies` and `ARCH-13.allowed_hosts` / `allowed_external_services` act as ceilings when present. Missing allowlists are not invented by AgentOS.

If an architecture-sensitive candidate was previously validated and the ACTIVE Architecture Baseline later changes, the contract becomes `stale_architecture`. AgentOS does not silently re-pin it to the new baseline; the candidate contract must be deliberately re-drafted/reconfirmed and validated again before human graduation.

## Legacy v1

Existing v1 skills are marked `legacy_v1` by schema migration 58. Their approved artifacts are not rewritten. A legacy skill that needs v2 semantics should receive a successor candidate/version and a new human review.

## Authority invariants

- Skill Contract v2 cannot exceed task or Architecture Authority.
- Empty read/write/capability/tool lists are the default least-authority state.
- Unsafe absolute/path-traversal scopes are rejected.
- Unknown `ARCH-*` identifiers are rejected.
- MCP does not expose set/validate/graduation/revocation mutation.
- v0.27.0 does not automatically select skills; v0.27.1 is reserved for Architecture-Aware Skill Selection & Evaluation.

## Schema 58

Migration 58 adds contract metadata to `promoted_skills` and introduces:

```text
skill_contracts
skill_contract_events
```

## CLI

```text
skill-contract-set
skill-contract-show
skill-contract-validate
skill-contract-status
```

Existing commands remain:

```text
skill-promote
skill-list
skill-graduate
skill-match
skill-revoke
```

`skill-match` remains deterministic lexical matching in v0.27.0 and does not gain automatic authority.

## MCP

Read-only tools:

```text
agentos.skill_contract_get
agentos.skill_contract_status_get
agentos.skill_contracts_list
```

No contract mutation, graduation, revocation, approval, activation, or execution tool is exposed.

## Distribution

v0.27.0 uses the latest-full-release model described in `INSTALL_LATEST_RELEASE.md`. No version-specific updater script is required.
