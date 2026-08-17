# AgentOS v0.26.2 — Runtime/Data/API & Business Boundary Enforcement

v0.26.2 extends the human-owned Architecture Authority into runtime-facing project boundaries without executing project code and without giving an LLM architecture authority.

## Enforced architecture sections

- `ARCH-06` Request Flow
- `ARCH-07` Authentication
- `ARCH-08` Authorization
- `ARCH-09` Database / Data boundaries
- `ARCH-10` API Architecture
- `ARCH-11` Business Flow
- `ARCH-13` External Services
- `ARCH-14` Configuration / secret access boundaries

## Enforcement model

The engine has two deterministic gates:

1. **Plan-time declaration gate.** If a plan declares one of the runtime boundary sections as affected, it must explicitly declare the corresponding runtime impact (calls, data operations, API routes, business calls, external services, or configuration keys). Those declarations are checked against the exact ACTIVE Architecture Baseline before the immutable plan is persisted.
2. **Post-change static gate.** At pre-commit, changed files are inspected statically for bounded facts: Python call names, SQL operation/object literals, HTTP route decorators, URL literals, and environment-variable access. Contract violations block readiness.

The engine does not execute project code, perform network access, infer business policy with an LLM, approve a waiver, or modify Architecture Authority.

## Contract payload keys

### ARCH-06 — Request Flow
- `forbidden_call_patterns`
- `required_calls_by_path`: list of `{paths, calls, severity?}`

### ARCH-07 — Authentication
- `forbidden_auth_calls`
- `required_auth_calls_by_path`

### ARCH-08 — Authorization
- `forbidden_authorization_calls`
- `required_authorization_calls_by_path`

### ARCH-09 — Database / Data
- `allowed_sql_operations`
- `forbidden_sql_operations`
- `allowed_data_objects`
- `data_write_allowed_paths`
- `data_access_file_patterns`

### ARCH-10 — API Architecture
- `allowed_http_methods`
- `allowed_route_prefixes`
- `forbidden_routes`

### ARCH-11 — Business Flow
- `forbidden_business_calls`
- `required_business_guard_calls_by_path`

### ARCH-13 — External Services
- `allowed_hosts`
- `forbidden_hosts`
- `allowed_url_schemes`

### ARCH-14 — Configuration
- `allowed_env_vars`
- `forbidden_env_vars`
- `secret_env_vars`
- `secret_access_allowed_paths`
- `forbidden_config_paths`

## Plan declaration fields

When the corresponding section is affected, plans must explicitly include the field even when the intended set is empty:

- `expected_runtime_calls`
- `expected_data_operations`
- `expected_api_routes`
- `expected_business_calls`
- `expected_external_services`
- `expected_config_keys`

This prevents a plan from silently crossing a runtime/data/API boundary merely because the implementation has not yet been written.

## CLI

```bash
agentos architecture-runtime-status
agentos architecture-runtime-check --task-id TASK-1 --changed-file src/api/users.py
agentos architecture-runtime-findings --task-id TASK-1
```

## MCP boundary

Read-only only:

- `agentos.architecture_runtime_status_get`
- `agentos.architecture_runtime_findings_get`
- `agentos.architecture_runtime_target_get`

MCP cannot run the enforcement scan, approve/waive findings, modify contracts, or activate architecture.
