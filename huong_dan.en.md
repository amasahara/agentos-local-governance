# AgentOS v0.27.1 Guide

Release: **v0.27.1 — Architecture-Aware Skill Selection & Evaluation**
Database schema: **59**

Run explicit advisory selection only after the task has an active architecture-aware plan:

```bash
agentos skill-selection-run --task-id T-123
agentos skill-selection-status --task-id T-123
agentos skill-selection-candidates --run-id 1
```

Provide an explicit tool inventory when a contract requires tools:

```bash
agentos skill-selection-run --task-id T-123 --available-tools '["pytest","ruff"]'
```

After a task outcome exists:

```bash
agentos skill-evaluation-run --selection-run-id 1
```

Selection/evaluation never grants authority or mutates skill lifecycle automatically.

Distribution uses the latest full release with **no updater script**. Preserve project-owned user skills, workflows, source, architecture working copies, `governance.local.json`, `.agents/state/**`, and `.agents/runtime/**`.
