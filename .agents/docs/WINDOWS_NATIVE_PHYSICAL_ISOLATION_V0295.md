# Windows Native Physical Isolation — v0.29.5

## Scope

v0.29.5 applies only to:

```text
agentos_mediated_process_execution
```

It strengthens the existing Windows execution boundary. It does not turn
AgentOS into a general Windows sandbox or container runtime.

## Boundary stack

```text
AgentOS governed execution
        ↓
external AgentOS sandbox workspace
        ↓
bounded current-user DACL
        ↓
Low mandatory integrity label + NO_WRITE_UP
        ↓
Restricted Token + LUA_TOKEN
        ↓
TokenIntegrityLevel = Low
        ↓
CreateProcessAsUserW(CREATE_SUSPENDED)
        ↓
actual child Restricted + Low verification
        ↓
Job Object assignment
        ↓
ResumeThread
```

`SANDBOX_INERT` remains forbidden.

## Mandatory Integrity Control

Low Integrity is represented by:

```text
SID = S-1-16-4096
RID = 4096
```

AgentOS explicitly labels existing sandbox objects. Directories receive an
inheritable Low label with object/container inheritance and `NO_WRITE_UP`;
files receive an explicit Low + `NO_WRITE_UP` label.

Objects without an explicit lower label are treated as Medium by the relevant
MIC boundary, so a verified Low worker cannot write up to a controlled Medium
target even when ordinary DACL permissions would otherwise permit it.

## Sandbox DACL

Restricted/LUA tokens may lose access that previously arrived through group
membership. AgentOS therefore preserves the existing DACL and adds a bounded
allow ACE for the current user SID on the sandbox tree.

The release does not grant:

```text
Everyone
WRITE_DAC
WRITE_OWNER
ACCESS_SYSTEM_SECURITY
```

Production sandbox creation also grants only the required read/traverse access
along the AgentOS-owned `*.agentos-sandboxes` hierarchy. Parents outside that
controlled anchor are not modified.

## Synchronous execution

The production sync path uses a Restricted + Low primary token. The child stays
suspended while AgentOS verifies both the Restricted Token contract and the
actual child Low integrity level. Job Object assignment is verified before
resume. There is no Medium-integrity or unrestricted production fallback.

## Asynchronous execution

The asynchronous broker remains a trusted lifecycle process and named Job
Object owner. The governed worker root receives the Restricted + Low token.

Production READY and completion evidence bind both Restricted and Low execution.
Historical restricted-only/generic broker branches remain compatibility paths;
production job submission requires the Low execution payload and cannot
downgrade to those branches.

## Verification

Windows tests cover:

- Low token creation and SID/RID verification;
- sandbox Low-label application and inspection;
- Restricted/LUA DACL accessibility;
- sync Restricted + Low child verification;
- async Restricted + Low worker verification;
- assign-before-resume ordering;
- sandbox write success;
- denial of writes to controlled Medium targets;
- structural attestation;
- focused `windows-latest` CI;
- release activation.

## Activated claims

```text
restricted_token_attested = true
low_integrity_attested = true
sandbox_low_integrity_label_attested = true
scope = agentos_mediated_process_execution
```

## Non-claims

The release intentionally keeps these false:

```text
primary_root_write_up_prevention_attested = false
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
desktop_isolation_attested = false
credential_isolation_attested = false
same_user_host_bypass_resistance_claimed = false
```

Low Integrity is not a namespace. A Low process can still read many Medium
objects and can write other Low-labeled objects when their DACL permits.
The controlled Medium-target probes therefore support a bounded MIC write-up
claim, not complete host-filesystem isolation.
