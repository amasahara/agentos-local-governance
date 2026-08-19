# AgentOS Local Governance — English

**Current release: v0.27.1 — Architecture-Aware Skill Selection & Evaluation**

Database schema: **59**. Schema bootstrap baseline remains **46**.

v0.27.1 connects **Governed Skill Contract v2** to the active architecture-aware task plan through deterministic, local, least-authority skill recommendation and observational evaluation.

## Selection flow

```text
User Request
    ↓
Requirement Ledger + ACTIVE plan
    ↓
Architecture Baseline
    ↓
Graduated Skill Contract v2
    ↓
Contract freshness
    ↓
Architecture / scope / capability / tool / dependency / service / test gates
    ↓
Deterministic ranking
    ↓
ADVISORY RECOMMENDATION
```

Selection does not grant execution authority. It cannot alter the active plan, grant capabilities, execute a skill, approve architecture, or choose a model/provider.

Core invariants:

- Only current graduated Contract-v2 skills are eligible.
- Legacy-v1 skills remain preserved but are not architecture-aware selection candidates.
- Stale/invalid contracts fail closed.
- Planned write targets must fit `allowed_write_scope`.
- Required capabilities remain bounded by governed proxy capabilities.
- Required tools must be explicitly available.
- Dependencies, external services, architecture sections, and required tests must fit the skill contract.
- Evaluation observes task outcomes only and cannot change lifecycle or future ranking weights automatically.
- MCP is read-only for selection/evaluation inspection.

## CLI

```bash
agentos skill-selection-run --task-id T-123
agentos skill-selection-status --task-id T-123
agentos skill-selection-candidates --run-id 1
agentos skill-evaluation-run --selection-run-id 1
```

## Distribution

AgentOS uses the **Latest Full Release** model with **no updater script**. Project-owned user skills, workflows, source, architecture working copies, local governance overrides, state, and runtime data remain outside the managed release partition.

- [v0.27.1 documentation](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [Tiếng Việt](README.vi.md)
