# Usage — v0.20.1

Create a candidate set from the project you expect may become primary:

```bash
.agents/bin/agentos project-candidate-set-create \
  --source-root /path/to/project-b \
  --source-root /path/to/project-c \
  --created-by "human-owner"
```

Review compatibility and advisory ranking:

```bash
.agents/bin/agentos project-compatibility-show --candidate-set-id 1
.agents/bin/agentos project-primary-recommend --candidate-set-id 1
```

If two projects share the same domain but have different purpose IDs, confirm the business relationship explicitly:

```bash
.agents/bin/agentos project-compatibility-confirm \
  --candidate-set-id 1 \
  --project-a <UUID-A> \
  --project-b <UUID-B> \
  --confirmed-by "human-owner" \
  --reason "Both projects serve the same hospital-management platform" \
  --human-confirmed
```

Commit the primary from that primary project's own root:

```bash
.agents/bin/agentos project-primary-select \
  --candidate-set-id 1 \
  --project-uuid <ACTIVE-ROOT-UUID> \
  --confirmed-by "human-owner" \
  --reason "This is the production core application and consolidation target" \
  --human-confirmed
```

If the project you want as primary is not the active root, do not select it remotely. Run the candidate workflow again from that project.
