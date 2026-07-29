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
