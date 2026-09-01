# AgentOS v0.29.4 — Windows Restricted Execution

## Scope

v0.29.4 activates native Windows Restricted Token execution for the bounded
scope `agentos_mediated_process_execution`.

This is not a claim that AgentOS isolates arbitrary host processes.

## Runtime chain

```text
AgentOS process.exec
        ↓
sandbox/runtime-profile/credential validation
        ↓
CreateRestrictedToken(DISABLE_MAX_PRIVILEGE | LUA_TOKEN)
        ↓
verify restricted primary token
        ↓
CreateProcessAsUserW(CREATE_SUSPENDED)
        ↓
verify actual child token
        ↓
AssignProcessToJobObject
        ↓
ResumeThread
```

Async execution keeps the AgentOS broker as the trusted named Job Object
lifecycle owner while the governed worker root uses the same Restricted Token
launcher.

## Fail-closed contract

`SANDBOX_INERT` is forbidden. Enabled privileges are limited to
`SeChangeNotifyPrivilege`. The production restricted path has no unrestricted
`CreateProcessW` fallback.

Source-token verification occurs before returning the restricted token handle.
Child-token verification and Job assignment must complete before resume.
Post-create verification, assignment, or resume failure terminates the
suspended/contained child before propagating the error.

Production async launch always requests `restricted_execution = true` and
rejects READY evidence unless token verification and assign-before-resume are
confirmed.

## Release attestation

```text
restricted_token_attested = true
scope = agentos_mediated_process_execution
```

Backed by structural attestation, live Windows sync/async tests, real AgentOS
sandbox read/write probes, negative fail-closed tests, and focused
`windows-latest` CI.

## Explicit nonclaims

```text
low_integrity_attested = false
desktop_isolation_attested = false
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
same_user_host_bypass_resistance_claimed = false
```

The predecessor v0.29.3 sandbox/credential policy remains historically narrow:

```text
credential_isolation_attested = false
restricted_token_attested = false
```

Low Integrity is deferred to the next native physical-isolation node.

## Schema

Database schema remains **62**. v0.29.4 adds no migration.
