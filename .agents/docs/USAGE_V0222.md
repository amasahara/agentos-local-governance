# Usage v0.22.2

```bash
# schema
.agents/bin/agentos db-reconciliation-recovery-db-sync

# committed or uncertain insert reconciliation
.agents/bin/agentos db-reconciliation-create --insert-run-id 1 --created-by operator
.agents/bin/agentos db-reconciliation-spec --reconciliation-run-id 1
.agents/bin/agentos db-reconciliation-run --reconciliation-run-id 1
.agents/bin/agentos db-reconciliation-summary --reconciliation-run-id 1

# recovery discovery/readiness
.agents/bin/agentos db-recovery-scan
.agents/bin/agentos db-recovery-cases-list
.agents/bin/agentos db-recovery-readiness --insert-run-id 1
.agents/bin/agentos db-recovery-checkpoints-list --insert-run-id 1

# human decision for uncertain commit
.agents/bin/agentos db-recovery-commit-decide --recovery-case-id 1 \
  --decision committed_verified --decided-by owner --human-confirmed

# or prove no commit and enable manual retry
.agents/bin/agentos db-recovery-commit-decide --recovery-case-id 1 \
  --decision not_committed_verified --decided-by owner --human-confirmed

# known commit / pending local lineage
.agents/bin/agentos db-recovery-lineage-finalize --recovery-case-id 2 \
  --recovered-by owner --human-confirmed
```

Reconciliation execution and recovery decisions are intentionally not MCP tools.
