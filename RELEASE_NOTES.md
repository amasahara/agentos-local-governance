# AgentOS Local Governance v0.29.2 — Windows Sandbox Workspace & Tool Runtime Profiles

v0.29.2 bổ sung lớp **sandbox workspace + tool runtime profile** cho phạm vi
**AgentOS-mediated process execution** trên Windows, kế thừa trực tiếp
process-tree containment của v0.29.1.

## Enforcement được activate

- deterministic tool runtime profiles;
- bounded sandbox workspace cho execution;
- sync runtime-profile enforcement;
- async profile snapshot/hash binding;
- async pre-launch revalidation;
- redirect mutable runtime state theo profile;
- terminal cleanup evidence;
- giữ nguyên v0.29.1 Windows process-tree containment;
- Windows CI có focused suite, v0.29.1 containment activation regression,
  v0.29.2 activation suite và full regression.

## Release attestation

```text
runtime_profile_sandbox_attested = true
scope = agentos_mediated_process_execution
```

Các claim sau **vẫn false**:

```text
credential_isolation_attested = false
restricted_token_attested = false
low_integrity_attested = false
host_filesystem_isolation_attested = false
os_write_confinement_attested = false
same_user_host_bypass_resistance_claimed = false
```

Do đó v0.29.2 không được mô tả như general Windows sandbox, Restricted Token
sandbox, Low Integrity sandbox hoặc same-user host-bypass resistant isolation.

## Schema

Database schema remains **62**. Không có schema migration trong v0.29.2.

## Finalization

Sau activation phải regenerate deterministic generated governance,
`MANIFEST.json`, `CHECKSUMS.sha256` và `PACKAGE_COMPLETENESS.json`, rồi mới chạy
docs/release-integrity/manifest/full release gates và stage/commit.
