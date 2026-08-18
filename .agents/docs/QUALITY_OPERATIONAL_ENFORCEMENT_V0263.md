# AgentOS Local Governance v0.26.3 — Quality/Operational Enforcement

Database schema: **57**.

v0.26.3 extends the human-owned Architecture Governance Plane to `ARCH-15..ARCH-21`.
The engine is deterministic and static: it does not execute project code, access the
network, invent architecture rules, approve ADRs, or waive violations.

## Enforced sections

- `ARCH-15` Logging
- `ARCH-16` Error Handling
- `ARCH-17` Security
- `ARCH-18` Performance
- `ARCH-19` Scalability
- `ARCH-20` Deployment
- `ARCH-21` Testing

## Explicit-contract model

No generic best practice automatically becomes authority. A rule is enforceable only
when the ACTIVE human-approved Architecture Contract declares the corresponding
machine-readable field.

Examples include:

- logging: `required_logging_calls_by_path`, `forbidden_logging_calls`, `forbid_sensitive_log_arguments`;
- errors: `forbid_bare_except`, `forbid_broad_exception_catch`, `required_error_calls_by_path`;
- security: `forbidden_call_patterns`, `forbid_shell_true`, `forbid_tls_verify_false`, `forbid_secret_literals`;
- performance: `max_python_file_lines`, `forbidden_blocking_calls_in_async`;
- scalability: `forbidden_scalability_calls`, `required_scalability_calls_by_path`;
- deployment: `allowed_container_base_images`, `require_non_root_container_user`, `forbid_privileged_container`;
- testing: `required_test_changes_by_source`, `minimum_changed_test_files`, `test_file_patterns`.

## Plan declarations

Tasks that explicitly affect these sections must declare the corresponding impact:

```text
ARCH-15 -> expected_logging_changes
ARCH-16 -> expected_error_handling_changes
ARCH-17 -> expected_security_changes
ARCH-18 -> expected_performance_impacts
ARCH-19 -> expected_scalability_impacts
ARCH-20 -> expected_deployment_changes
ARCH-21 -> expected_test_suites (or the existing tests field)
```

## Runtime flow

```text
ACTIVE Architecture Baseline
        ↓
Architecture-aware plan
        ↓
Quality/Operational plan declaration gate
        ↓
Implementation
        ↓
Static quality/security/operational analysis
        ↓
Precommit gate
        ↓
PASS / WARN / BLOCK
```

A legitimate blocked architecture change must use Architecture Change Proposal + ADR +
human review/approval + successor baseline + re-plan.

## Schema

Schema `56 -> 57` adds:

- `architecture_quality_runs`
- `architecture_quality_findings`

## CLI

```text
architecture-quality-check
architecture-quality-status
architecture-quality-findings
```

## MCP

Read-only tools only:

```text
agentos.architecture_quality_status_get
agentos.architecture_quality_findings_get
agentos.architecture_quality_target_get
```

No architecture approval, activation, waiver, mutation, or execution authority is exposed.
