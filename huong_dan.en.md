[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

# Developer Guide — v0.22.2

## Operating sequence

1. Complete extraction, identity resolution, and Controlled Target Insert under v0.21.2–v0.22.1 rules.
2. Reconcile committed runs to prove the expected TARGET row set.
3. For `committing/in_doubt`, scan recovery cases and perform a read-only TARGET reconciliation.
4. A human may select `committed_verified` only after `matched`.
5. A human may select `not_committed_verified` only after `observed_none`; this enables manual retry, never automatic retry.
6. `observed_partial/mismatch` stays manual intervention; AgentOS does not UPDATE/DELETE/UPSERT/MERGE the TARGET to repair it.
7. If external commit is known but local lineage is pending, rebuild lineage locally/idempotently without retrying INSERT.
8. Review reconciliation summary, recovery cases, and checkpoint hashes before closing the incident.

```bash
.agents/bin/agentos db-reconciliation-recovery-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests
```
