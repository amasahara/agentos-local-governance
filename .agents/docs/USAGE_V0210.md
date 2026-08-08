# AgentOS v0.21.0 Usage

```bash
# Apply schema 35
.agents/bin/agentos db-boundary-db-sync

# Register a SOURCE (metadata only; no connection is opened here)
.agents/bin/agentos db-connection-register \
  --alias fpt_his_prod_ro \
  --role SOURCE \
  --engine mssql \
  --host fpt-db.internal \
  --database FPT_HIS \
  --domain healthcare \
  --credential-ref secret://hospital/fpt/prod-readonly \
  --created-by operator

# Human/operator verification; no write probe
.agents/bin/agentos db-source-verify-readonly \
  --connection-id 1 \
  --verified-by dba \
  --method grant_review \
  --evidence "DBA grant review ticket DB-1024: SELECT/catalog only" \
  --human-confirmed

# Register one TARGET
.agents/bin/agentos db-connection-register \
  --alias unified_his \
  --role TARGET \
  --engine postgresql \
  --host unified-db.internal \
  --database unified_his \
  --domain healthcare \
  --credential-ref secret://hospital/unified/target \
  --created-by operator

# Create plan and attach verified sources
.agents/bin/agentos db-consolidation-create --target-connection-id 2 --created-by operator
.agents/bin/agentos db-consolidation-add-source --consolidation-id 1 --source-connection-id 1 --registered-by operator

# Boundary checks only; no SQL execution
.agents/bin/agentos db-boundary-authorize --connection-id 1 --operation select_read
.agents/bin/agentos db-boundary-authorize --connection-id 1 --operation update
.agents/bin/agentos db-boundary-authorize --connection-id 2 --operation insert
```
