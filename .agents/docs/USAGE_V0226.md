# v0.22.6 Usage — Secret Resolver & Lineage Key Lifecycle

All mutation commands below use the unified v0.22.5+ Python CLI runtime and must run inside the existing governed task/session boundary. Read-only inspection commands do not initialize key material.

## 1. Inspect and approve trusted secret providers

```bash
agentos secret-provider-catalog
agentos --task-id TASK --session-id SESSION \
  secret-provider-approve \
  --scheme env \
  --capability db.source.select \
  --approved-by OPERATOR \
  --human-confirmed
```

Production capability allowlist:

```text
db.source.select
db.target.controlled_insert
db.target.reconciliation_select
```

Provider URI contracts:

```text
env://NAME
keychain://service/account
vault://mount/path#field
file-secret://relative.json
secret://alias
```

`secret://alias` is configured only as an alias to one of the trusted URI forms. Arbitrary `importlib`, `module:function`, executable, or callback resolver loading is forbidden for governed roots.

`file-secret://` is confined to `.agents/state/secrets/`. On POSIX the file must be owner-only. Keychain and Vault integrations require their optional trusted local dependencies; a missing dependency fails closed.

## 2. Inspect and initialize the lineage keyring

```bash
agentos lineage-keyring-status
agentos --task-id TASK --session-id SESSION lineage-keyring-initialize
```

Initialization migrates the old `.agents/state/identity_lineage.key` by moving the same bytes into `.agents/state/lineage-keys/<key_id>.key` and backfilling `key_id` metadata only. It never automatically re-HMACs historical fingerprints.

## 3. Rotate a lineage key

```bash
agentos --task-id TASK --session-id SESSION \
  lineage-key-rotation-plan-create --reason "scheduled rotation" --created-by OPERATOR

agentos --task-id TASK --session-id SESSION \
  lineage-key-rotation-review --plan-id PLAN --reviewed-by REVIEWER --human-confirmed

agentos --task-id TASK --session-id SESSION \
  lineage-key-rotation-approve --plan-id PLAN --approved-by APPROVER --human-confirmed

agentos --task-id TASK --session-id SESSION \
  lineage-key-rotation-execute --plan-id PLAN --executed-by OPERATOR
```

The predecessor becomes `retired`; the new key becomes the only `active` key. Retired keys remain available for historical lookup/verification until explicitly revoked.

## 4. Rekey workflow

Rekey is intentionally not a transformation from old HMAC → new HMAC. It requires a governed SOURCE `select_read` re-read of the raw identifier:

```text
create rekey plan
→ human review
→ human approval
→ re-check SOURCE SELECT authority
→ authorize source re-read
→ downstream rekey using raw identifier in operation memory
```

The rekey plan stores only connection/key IDs, hashes, status and approval metadata.

## 5. MCP

MCP exposes metadata-only inspection:

```text
agentos.secret_provider_catalog_get
agentos.secret_provider_approvals_get
agentos.lineage_keyring_get
agentos.lineage_rotation_plan_get
agentos.lineage_rekey_plan_get
```

MCP never resolves/returns credentials and does not expose provider approval/revocation, key initialization/rotation/revocation, rekey authorization, identity decisions, TARGET mutation, or recovery mutation.

## 6. Cross-platform entrypoints

POSIX wrappers and Windows `.cmd` wrappers continue to call the same unified Python runtime. Do not re-enable historical version forwarding or MCP subprocess gateways.
