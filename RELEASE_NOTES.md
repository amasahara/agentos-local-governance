# AgentOS Local Governance v0.29.4 — Windows Restricted Execution

v0.29.4 activates native Windows **Restricted Token** execution for
**AgentOS-mediated process execution**, building on the v0.29.1 Job Object
process-tree boundary, v0.29.2 sandbox/runtime profiles, and v0.29.3
sandbox-configuration/credential boundary.

## Enforcement activated

- restricted primary token creation from the current AgentOS process token;
- `DISABLE_MAX_PRIVILEGE | LUA_TOKEN`; `SANDBOX_INERT` is forbidden;
- enabled privileges limited to `SeChangeNotifyPrivilege`;
- governed workers use `CreateProcessAsUserW(... CREATE_SUSPENDED ...)`;
- source token and actual child token are verified;
- Job Object assignment completes before `ResumeThread`;
- sync production uses the dedicated restricted runner;
- async broker stays the trusted Job Object owner while worker roots are
  restricted;
- production async READY requires restricted execution, token verification and
  assign-before-resume evidence;
- no unrestricted `CreateProcessW` fallback exists on the restricted
  production path;
- fail-closed cleanup covers verification, Job assignment and resume errors;
- live Windows sync/async tests and real sandbox read/write probes;
- dedicated structural attestation and focused `windows-latest` CI.

## Release attestation

```text
restricted_token_attested = true
scope = agentos_mediated_process_execution
```

These claims remain false:

```text
low_integrity_attested = false
desktop_isolation_attested = false
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
same_user_host_bypass_resistance_claimed = false
credential_isolation_attested = false
```

The claim is bounded to AgentOS-mediated process execution and does not imply
general OS isolation or arbitrary host-process containment.

## Schema

Database schema remains **62**. There is no v0.29.4 schema migration.

## Finalization

Regenerate deterministic effective governance, package completeness, manifest
and checksum artifacts with repository tools before final release gates,
commit and tag.
