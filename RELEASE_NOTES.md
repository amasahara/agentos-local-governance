# AgentOS Local Governance v0.29.5 — Native Physical Isolation Extensions

v0.29.5 strengthens Windows execution for the bounded
**AgentOS-mediated process execution** scope by combining the v0.29.4
Restricted Token boundary with Windows Mandatory Integrity Control (MIC).

## Runtime boundary

The production Windows path is now:

```text
AgentOS sandbox creation
        ↓
verified Low mandatory label + bounded current-user DACL
        ↓
Restricted primary token
        ↓
set TokenIntegrityLevel = Low
        ↓
verify Restricted + Low source token
        ↓
CreateProcessAsUserW(... CREATE_SUSPENDED ...)
        ↓
verify actual child Restricted + Low
        ↓
assign Job Object
        ↓
ResumeThread
```

Synchronous `process.exec` uses this path directly. For asynchronous execution,
the broker remains the trusted lifecycle owner of the named Job Object while
the governed worker root runs under Restricted + Low Integrity.

## Sandbox integrity boundary

The AgentOS-managed execution sandbox uses:

```text
Low SID: S-1-16-4096
Low RID: 4096
Directory label: S:(ML;OICI;NW;;;LW)
File label:      S:(ML;;NW;;;LW)
```

Existing sandbox objects are explicitly labeled and verified. Directory labels
carry object/container inheritance for future descendants.

The sandbox DACL preserves existing entries and adds a bounded allow ACE for
the current user SID so Restricted/LUA workers can operate inside the sandbox.
It does not grant `Everyone` or broad security-descriptor control such as
`WRITE_DAC`, `WRITE_OWNER`, or `ACCESS_SYSTEM_SECURITY`.

Production sandbox creation additionally requires the controlled
`*.agentos-sandboxes` ancestry. The generic Low-MIC primitive remains root-local
and does not rewrite unrelated parent directories.

## Runtime verification

The release contains live Windows coverage for:

- Restricted + Low primary-token creation;
- Low mandatory-label application and inspection;
- DACL accessibility under Restricted/LUA execution;
- synchronous child Restricted + Low verification;
- asynchronous broker/worker Restricted + Low verification;
- assign-before-resume ordering;
- successful writes inside the Low-labeled sandbox;
- denied writes from Low workers to controlled Medium-integrity targets;
- predecessor v0.29.4 Restricted Token and Job Object regressions.

## Release attestation

The following claims are active only within:

```text
scope = agentos_mediated_process_execution
```

```text
restricted_token_attested = true
low_integrity_attested = true
sandbox_low_integrity_label_attested = true
```

The physical-isolation attester also verifies the sync and async production
routes, controlled sandbox ancestry, Low-token identity, MIC/DACL contracts,
fail-closed downgrade prevention, and focused `windows-latest` CI coverage.

## Explicit non-claims

v0.29.5 does **not** claim:

```text
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
primary_root_write_up_prevention_attested = false
desktop_isolation_attested = false
credential_isolation_attested = false
same_user_host_bypass_resistance_claimed = false
```

Low Integrity is a Windows MIC boundary, not a namespace or container. A Low
process may still read many Medium objects and may write other Low-labeled
objects when the DACL permits. Therefore the release does not represent the
bounded write-up probes as complete host-filesystem confinement.

## Compatibility

v0.29.5 preserves:

- the v0.29.4 Restricted Token profile and scoped attestation;
- the v0.29.1 Job Object process-tree containment contract;
- the v0.29.2 sandbox/runtime profile lifecycle;
- the v0.29.3 credential boundary;
- the trusted asynchronous broker lifecycle;
- conservative global non-claim projections.

The v0.29.4 `windows_restricted_execution_policy.low_integrity_attested`
remains `false`; Low Integrity attestation belongs to the new bounded
`windows_physical_isolation_policy`.

## Schema

Database schema remains **62**. There is no v0.29.5 database migration.

## Finalization

Before commit/tag, regenerate deterministic effective governance, package
completeness, manifest, and checksum artifacts with repository tools; then run
full Windows regression and the standard release-integrity gates.
