# AgentOS Local Governance v0.29.3 — Sandbox Configuration & Credential Boundary

v0.29.3 activates governed **sandbox configuration + process credential
boundary** for **AgentOS-mediated process execution**, inheriting v0.29.1
Windows process-tree containment and v0.29.2 sandbox/runtime profiles.

## Enforcement activated

- effective-policy sandbox configuration with deterministic configuration hash;
- fail-closed runtime-profile security floor;
- `secret://alias`-only process credential references;
- existing trusted Secret Resolver with provider identity/hash/capability approval;
- synchronous launch-time credential resolution;
- asynchronous credential hash/count binding and launch-time resolution;
- immutable async `spec_hash` verification before Secret Resolver invocation;
- no raw credential values in configuration/spec/audit evidence;
- secret-independent sync environment evidence;
- exact-value sync stdout/stderr redaction;
- credential-bearing async stdout/stderr persistence disabled;
- Windows `file-secret` process projection blocked pending ACL attestation;
- focused credential-boundary CI on Ubuntu and Windows;
- inherited v0.29.1 containment and v0.29.2 sandbox activation regressions.

## Release attestation

```text
sandbox_configuration_attested = true
credential_boundary_enabled = true
credential_boundary_attested = true
sync_credential_boundary_attested = true
async_credential_boundary_attested = true
scope = agentos_mediated_process_execution
```

These claims remain false:

```text
credential_isolation_attested = false
restricted_token_attested = false
low_integrity_attested = false
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
same_user_host_bypass_resistance_claimed = false
```

The release therefore does not claim OS-level credential isolation, Restricted
Token, Low Integrity, host-filesystem confinement, OS write confinement, or
same-user host-bypass resistance.

## Schema

Database schema remains **62**. There is no v0.29.3 schema migration.

## Finalization

After activation, regenerate deterministic effective governance,
`PACKAGE_COMPLETENESS.json`, `MANIFEST.json`, and `CHECKSUMS.sha256`; then run
full regression and release gates before staging/commit/tagging.
