# AgentOS Usage

## Initialize task state

```bash
.agents/bin/agentos start-task --task-id T1 --request "Update behavior"
.agents/bin/agentos approve-task --task-id T1 --scope '["src","tests",".agents","README.md"]'
```

## Build and query the local index

```bash
.agents/bin/agentos index-build src
.agents/bin/agentos index-query OrderService
.agents/bin/agentos duplicate-scan
```

## Composite change preparation

Modify:

```bash
.agents/bin/agentos prepare-change \
  --task-id T1 \
  --operation modify \
  --target src/a.py \
  --intent "Change return value" \
  --symbols '["a"]'
```

Create:

```bash
.agents/bin/agentos prepare-change \
  --task-id T1 \
  --operation create \
  --target date_converter.py \
  --intent "Convert Excel date values" \
  --feature reporting \
  --layer application \
  --file-kind source \
  --symbols '["convert_excel_date"]'
```

## Evidence-grounded claims

```bash
.agents/bin/agentos record-tool \
  --task-id T1 \
  --tool bounded_file_read \
  --input '{"path":"src/a.py"}' \
  --success \
  --output "Read implementation" \
  --classification local

.agents/bin/agentos record-claim \
  --task-id T1 \
  --claim "Function a returns a constant" \
  --claim-type business_logic \
  --risk high \
  --evidence-call-ids '[1]'

.agents/bin/agentos list-claims --task-id T1
.agents/bin/agentos show-claim --claim-id 1
```

## Synchronization checks

```bash
.agents/bin/agentos db-status
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
.agents/bin/agentos status --task-id T1
```


## v0.8.1 repaired runtime commands

### Documentation scan

```bash
.agents/bin/agentos docs-scan --scope src
.agents/bin/agentos docs-scan --scope .agents/agentos
```

### Tool guard and egress audit

```bash
.agents/bin/agentos tool-guard --task-id TASK-001 --tool bounded_file_read --args '{"path":"src/a.py"}'
.agents/bin/agentos tool-guard --task-id TASK-001 --tool web --args '{"query":"..."}' --reason-code research --justification "Need current evidence" --target example.org
.agents/bin/agentos record-tool-result --task-id TASK-001 --tool web --args '{"query":"..."}' --success
.agents/bin/agentos egress-report --task-id TASK-001
```

### File-read cache

```bash
.agents/bin/agentos cache-store --task-id TASK-001 --path src/a.py --range-key 1:160 --summary "Relevant functions"
.agents/bin/agentos cache-lookup --task-id TASK-001 --path src/a.py --range-key 1:160
```

## v0.8.1 task heartbeat and workflow

```bash
agentos start-task --task-id TASK-042 --request "..."
agentos use-task --task-id TASK-042
agentos whoami
agentos next-step
agentos workflow-status
agentos mark-step --step structural_review --status done --note "Reviewed."
agentos run-tests
agentos sync-check
agentos report
```

Commands that accept `--task-id` may omit it after a current task has been selected.

## Governance drift

```bash
agentos ack-baseline --acknowledged-by human
agentos drift-check
agentos drift-diff --file AGENTS.md
```

Only the user should acknowledge a governance baseline.

## Safe installation

```bash
.agents/bin/install.sh /path/to/project
.agents/bin/install-git-hooks.sh
```

Use `.agents/bin/install.cmd` on Windows. Existing root files are preserved.
