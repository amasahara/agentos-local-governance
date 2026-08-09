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


## v0.9.0 repaired runtime commands

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

## v0.9.0 task heartbeat and workflow

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

## Hardened tool lifecycle (v0.9.0)

```bash
agentos --session-id S1 guard-tool --task-id T1 \
  --tool bounded_file_read --args '{"path":"src/a.py"}'
agentos --session-id S1 complete-tool --execution-token TOKEN \
  --input '{"path":"src/a.py"}' --success --output "Read source contract"
```

`record-tool` is retained only to return a migration error. It cannot write evidence.

## Sensitive local overrides

```bash
agentos local-override-status
agentos approve-local-override --reviewed-by USER --note "Reviewed"
```

## Session isolation

Pass global `--session-id NAME` or set `AGENTOS_SESSION_ID`.


## v0.10.1 MCP enforcement gateway

```bash
python3 -m pip install -r .agents/requirements.txt
.agents/bin/agentos-mcp --task-id TASK-001 --session-id IDE-1
.agents/bin/agentos audit-verify
```

CLI smoke call:

```bash
.agents/bin/agentos --session-id IDE-1 proxy-execute --task-id TASK-001 --tool agentos.read_file --args '{"path":"src/a.py"}'
```

Set `AGENTOS_AUDIT_HOME` to a directory outside the repository and outside the coding agent's write scope.


## Concurrent work coordination

```bash
agentos --session-id A claim-task --task-id T1
agentos --session-id A acquire-resource --task-id T1 --type file --resource src/a.py --mode exclusive_write
agentos --session-id A list-resources --task-id T1
agentos --session-id A handoff-task --task-id T1 --from-session A --to-session B --note "Reviewed"
```

Existing-file proxy writes must include the latest `expected_hash` returned by `agentos.read_file`.

## Knowledge runtime

```bash
agentos context-build --task-id TASK-001 --max-lines 500
agentos context-status --task-id TASK-001
agentos context-explain --task-id TASK-001
agentos finding-record --task-id TASK-001 --kind duplicate --message "Repeated implementation"
agentos memory-record --task-id TASK-001 --kind semantic --statement "Stable project convention"
agentos memory-query "project convention"
agentos memory-validate
```

## Controlled evolution and multi-agent commands (v0.17.1)

```bash
agentos evaluation-report
agentos evolution-propose --title "Policy proposal" --findings '[]' --patch '{}' --benefit "Expected benefit" --risks '[]' --rollback '{}' --created-by operator
agentos evolution-simulate --proposal-id 1
agentos evolution-transition --proposal-id 1 --status reviewed --actor operator --note "Reviewed"
agentos evolution-status --proposal-id 1
agentos role-assign --task-id T1 --target-session REVIEWER --role reviewer --assigned-by operator
agentos collaboration-readiness --task-id T1
agentos message-send --task-id T1 --to-session EXECUTOR --kind review_request --payload '{}' --disclosure metadata-only
agentos message-list --task-id T1
```


## v0.22.3 integrity commands

```bash
.agents/bin/agentos release-integrity-check
.agents/bin/agentos docs-check
python3 tools/verify_manifest.py .
```

The current release must preserve both the historical governance core and the v0.20-v0.22 extension branch.

## v0.22.4 privileged database operations

Use task/session context before privileged database commands:

```bash
.agents/bin/agentos --task-id TASK-001 --session-id AGENT-1 db-target-insert-execute --insert-run-id 12
```

The task must be approved, owned by the session, workflow-approved, and free of unacknowledged governance drift. Signed-audit failure blocks the mutation.

## v0.22.5 unified runtime commands

```bash
.agents/bin/agentos runtime-health
.agents/bin/agentos commands-list
.agents/bin/agentos release-integrity-check
```

Windows:

```bat
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd commands-list
```

MCP clients should launch `.agents/bin/agentos-mcp` on POSIX or `.agents\bin\agentos-mcp.cmd` on Windows. Governed core proxy tools require `--task-id`, `--session-id`, and `AGENTOS_SESSION_TOKEN`; extension read-only tools and discovery/health remain non-mutating.
