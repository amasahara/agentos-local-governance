# AgentOS v0.25.4 — Architecture Drift & Compliance Engine

**Release:** 0.25.4 — Architecture Drift & Compliance Engine

v0.25.4 converts the v0.25.2 Architecture Contract plus v0.25.3 deterministic discovery/evidence into an enforceable compliance gate **only when a human-approved ACTIVE architecture baseline exists**.

## Authority boundary

- ACTIVE Architecture Contract = human authority.
- Observed Architecture = deterministic evidence, never authority.
- No active baseline = compliance status `not_evaluable`; historical task behavior is not blocked.
- Active baseline + hard-contract violation = `block`.
- Discovery-only discrepancy without a hard rule = `warn`.
- AI/MCP cannot approve, activate, waive, acknowledge, or rewrite architecture to make a violation pass.

## Schema 52

Adds:

- `architecture_compliance_runs`
- `architecture_compliance_findings`

The migration is additive. Architecture baselines, section revisions, scans, observations and evidence remain intact.

## Machine-readable hard-contract vocabulary

AgentOS v0.25.4 interprets only explicit keys inside the existing section `payload`. Other project-specific payload fields remain opaque.

- `ARCH-02`: `allowed_languages`, `forbidden_languages`, `allowed_dependencies`, `forbidden_dependencies`, `required_dependencies`.
- `ARCH-03`: `allowed_top_level`, `forbidden_top_level`, `allowed_write_roots`, `forbidden_paths`.
- `ARCH-05`: `allowed_module_roots`, `forbidden_module_paths`.
- `ARCH-10`: `allowed_cli_commands`, `forbidden_cli_commands`, `allowed_mcp_tools`, `forbidden_mcp_tools`.
- `ARCH-12`: `forbidden_imports`, `forbidden_import_edges` (`from`, `import`).
- `ARCH-13`: `allowed_domains`, `forbidden_domains`.
- `ARCH-14`: `allowed_environment_variables`, `forbidden_environment_variables`, `forbid_committed_env_files`.
- Any section may pin evidence objects containing `source_path`/`path` plus `sha256`/`source_hash`/`content_hash`.

## Scanner v2

Static discovery remains no-exec/no-network/no-symlink-following/no-raw-source-persistence. It adds:

- `ARCH-05 module_inventory`
- `ARCH-13 external_service_domains` (hostname only)
- `ARCH-14 environment_variables` (variable name only)

No URL query, credential, environment value or raw source body is persisted.

## Enforcement integration

- `check_write` / `prepare_change`: immediate path/module target boundary.
- `precommit-check`: refreshes deterministic evidence and blocks hard violations.
- `report`: final architecture compliance gate before workflow report completion.

## CLI

- `architecture-compliance-check`
- `architecture-compliance-show`
- `architecture-compliance-findings`
- `architecture-compliance-status`
- `architecture-target-check`

## MCP

Read-only only:

- `agentos.architecture_compliance_get`
- `agentos.architecture_compliance_findings_get`
- `agentos.architecture_compliance_status_get`

There is no MCP compliance execution, waiver, approval, ADR, or baseline mutation operation.

## Drift semantics

`evidence_hash_changed`, unbound evidence, and partial evidence binding remain warnings unless a human baseline explicitly pins a hash or declares a hard machine rule. A section declared `not_applicable` that has observed architecture is blocking while that baseline is active.

Architecture change proposals and ADR lifecycle remain deferred to v0.25.5.
