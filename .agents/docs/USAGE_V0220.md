# Usage — v0.22.0 Controlled Target Insert

```bash
agentos db-target-insert-plan-create --extraction-batch-id <id> --created-by <operator>
agentos db-target-insert-plan-show --insert-run-id <id>
agentos db-target-insert-readiness --insert-run-id <id>
agentos db-target-insert-spec --insert-run-id <id>
agentos db-target-insert-plan-review --insert-run-id <id> --reviewed-by <name> --human-confirmed
agentos db-target-insert-plan-approve --insert-run-id <id> --approved-by <name> --human-confirmed
agentos db-target-insert-execute --insert-run-id <id>
agentos db-target-insert-receipt --insert-run-id <id>
```

Execution resolves the TARGET `credential_ref` locally. The default resolver supports `env://NAME` JSON only. Do not provide secrets as CLI arguments.
