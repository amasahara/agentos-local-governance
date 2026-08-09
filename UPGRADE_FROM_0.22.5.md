# Upgrade v0.22.5 → v0.22.6

## Preconditions

- Exact baseline `VERSION=0.22.5`.
- Existing AgentOS database must be on or migratable through schema 41.
- Preserve `.agents/state/identity_lineage.key` if present until the governed keyring initialization succeeds.

## Apply

```bash
python3 tools/apply_v0226.py /path/to/agentos-v0.22.5 --dry-run
python3 tools/apply_v0226.py /path/to/agentos-v0.22.5
```

The upgrader refuses any other VERSION, backs up replaced files, merges only v0.22.6 policy nodes into the existing governance policy, and installs the new runtime/docs/tests.

## Migrate and initialize

```bash
.agents/bin/agentos secret-lineage-db-sync
.agents/bin/agentos runtime-health
```

Schema migration is 41 → 42 and remains part of the continuous migration chain through `agentos.db.connect()` with `foreign_keys=ON`.

Inspect keyring state first:

```bash
.agents/bin/agentos lineage-keyring-status
```

If uninitialized, run `lineage-keyring-initialize` as a privileged command inside an approved task/session. This migrates the legacy key with identical bytes and backfills `key_id` only; it does not recompute historical HMACs.

## Resolver approval

Inspect the shipped pins and approve only the minimum required capabilities:

```bash
.agents/bin/agentos secret-provider-catalog
.agents/bin/agentos secret-provider-approve --scheme env --capability db.source.select --approved-by OPERATOR --human-confirmed
```

Production DB operations no longer use arbitrary resolver callback injection. Existing non-governed tests/adapters may keep the compatibility callback.

## Validate

```bash
python3 tools/validate_v0226.py /path/to/upgraded/root
python3 -m pytest -q .agents/tests/test_secret_lineage_v0226.py
.agents/bin/agentos docs-check
.agents/bin/agentos release-integrity-check
```

Also run the repository's full historical/feature suite in an environment where the complete test tree is available.
