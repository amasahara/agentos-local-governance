# AgentOS v0.22.4 Developer Guide

[🇻🇳 Vietnamese](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Database schema: **41**

## Running a privileged database command

1. Create a task and complete its approval workflow.
2. Claim the task with the session that will execute the operation.
3. Acknowledge the governance baseline and resolve any drift.
4. Invoke the command with governance context:

```bash
.agents/bin/agentos --task-id TASK-001 --session-id AGENT-1 db-target-insert-execute --insert-run-id 12
```

AgentOS validates task/session, policy, workflow, and baseline/drift; issues one single-use guard token; runs the domain transaction; signs domain events; and completes the token.

If signed audit cannot be persisted, the mutation fails closed.
