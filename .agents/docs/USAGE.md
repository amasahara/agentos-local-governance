# AgentOS v0.7.0 usage

## Initialize the project state

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos detect-environment --session-id SESSION-1
```

On Windows:

```bat
.agents\bin\agentos.cmd instruction-check
.agents\bin\agentos.cmd detect-environment --session-id SESSION-1
```

## Clarification gate

```bash
.agents/bin/agentos clarity-check \
  --task-id TASK-001 \
  --request "Sửa phần in lịch" \
  --payload '{
    "intent": "modify_existing_feature",
    "target": null,
    "expected_behavior": null,
    "current_behavior": null,
    "acceptance_criteria": [],
    "scope": null,
    "risk": "medium"
  }'
```

A task with `needs_clarification` cannot be approved and cannot write files.

After the user clarifies, run the check again using the same task ID. When the result is `ready`:

```bash
.agents/bin/agentos approve-task TASK-001
```

## Tool loop guard

Before every tool call:

```bash
.agents/bin/agentos tool-guard \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --args '{"path":"schedules/views/printing.py","start":1,"end":160}'
```

After the tool finishes:

```bash
.agents/bin/agentos record-tool \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --args '{"path":"schedules/views/printing.py","start":1,"end":160}' \
  --success \
  --summary "Read print_schedule and helper functions."
```

A repeated identical call, repeated failure signature, exhausted call budget, or too many consecutive failures is denied.

## Composite change preparation

```bash
.agents/bin/agentos prepare-change \
  --task-id TASK-001 \
  --operation modify \
  --target schedules/views/printing.py \
  --intent "Chỉ in các lịch đã được duyệt" \
  --symbols '["print_schedule"]'
```

This combines:

- placement resolution for new files;
- similar-symbol lookup;
- duplicate-risk scan;
- write permission;
- recommended context selection.

## Runtime files

```bash
.agents/bin/agentos runtime-path \
  TASK-001 temporary_script inspect_schedule.py
```


## Developer documentation check

```bash
.agents/bin/agentos docs-check
```

This verifies:

- required bilingual documentation exists;
- `VERSION`, `governance.json`, and `__version__` agree;
- the current version is recorded in the rules/workflow changelog;
- the developer entry point contains Vietnamese and English markers.

## Rules and workflow change procedure

When a user asks to add, remove, or change a rule or workflow:

1. classify the task as `governance_change`;
2. clarify desired behavior and enforcement level;
3. update authoritative instruction and structured policy;
4. update runtime code and tests when enforcement changes;
5. update bilingual documentation and changelog;
6. bump `VERSION`;
7. run `docs-check` and tests;
8. include a synchronization matrix in the final report.


## v0.7.0 commands

```bash
.agents/bin/agentos db-migrate
.agents/bin/agentos index-build src
.agents/bin/agentos index-query "OrderService.create_order"
.agents/bin/agentos duplicate-scan
.agents/bin/agentos docs-code-check src
.agents/bin/agentos status
```
