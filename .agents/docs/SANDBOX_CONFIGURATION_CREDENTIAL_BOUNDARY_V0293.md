# AgentOS v0.29.3 — Sandbox Configuration & Credential Boundary

## Scope

v0.29.3 applies only to **AgentOS-mediated process execution**. It does not
create a separate OS identity and is not a general Windows sandbox.

## Sandbox configuration

Runtime profiles `inspect`, `test`, and `build` are sourced from governed
effective policy, canonicalized, hashed, and revalidated. The v0.29.2 security
floor remains mandatory: snapshot copy, sandbox-only writable scope, no
persistent workspace writes, sandbox-local home/temp/cache, and network policy
`none`.

## Credential reference boundary

Process credentials use `secret://alias` only and reuse the trusted Secret
Resolver introduced in v0.22.6. Provider identity/hash/capability approval is
revalidated before resolution. Raw credential values are forbidden in runtime
profile configuration.

## Sync

Sync credentials resolve immediately before guarded process launch. Only the
selected field is projected into the allowlisted environment target. Persisted
environment evidence is independent of credential values, and exact projected
values are redacted from captured stdout/stderr.

## Async

Async specs persist credential reference/binding hashes and count only. The
immutable spec hash is verified before secret resolution. Policy/profile/binding
and provider approval are revalidated at launch. Credential-bearing async jobs
do not persist stdout/stderr in v0.29.3.

## Windows file-secret

Windows `file-secret` process projection remains blocked pending a future ACL
attestation. POSIX chmod mode bits are not treated as a Windows security
primitive.

## Activated bounded claims

```text
sandbox_configuration_attested = true
credential_boundary_enabled = true
credential_boundary_attested = true
sync_credential_boundary_attested = true
async_credential_boundary_attested = true
scope = agentos_mediated_process_execution
```

The following remain false:

```text
credential_isolation_attested = false
restricted_token_attested = false
low_integrity_attested = false
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
same_user_host_bypass_resistance_claimed = false
```

A credential-bearing child process can read the credential projected to it.
Output redaction/suppression is defense-in-depth and is not a claim of semantic
noninterference or general credential-exfiltration prevention.

## Schema

Database schema remains **62**. v0.29.3 adds no migration.
