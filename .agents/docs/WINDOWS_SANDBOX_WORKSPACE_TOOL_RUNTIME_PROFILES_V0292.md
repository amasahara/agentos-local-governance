# Windows Sandbox Workspace & Tool Runtime Profiles — v0.29.2

## Scope

v0.29.2 enforce sandbox workspace và tool runtime profiles chỉ trong
`agentos_mediated_process_execution`.

Nó không attest general Windows host isolation.

## Relationship to v0.29.1

v0.29.1 cung cấp Windows process-tree containment. v0.29.2 đặt deterministic
runtime-profile/workspace resolution phía trước execution path đó, không thay thế
Job Object containment.

## Async binding

Queued async job bind runtime-profile snapshot/hash và revalidate ngay trước
launch. Snapshot stale hoặc thay đổi phải fail closed.

## Bounded claims

```text
runtime_profile_sandbox_attested = true
scope = agentos_mediated_process_execution

credential_isolation_attested = false
restricted_token_attested = false
low_integrity_attested = false
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
same_user_host_bypass_resistance_claimed = false
```
