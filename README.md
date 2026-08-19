# AgentOS Local Governance

**Current release: v0.27.1 — Architecture-Aware Skill Selection & Evaluation**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **59**. Schema bootstrap baseline remains **46**.

v0.27.1 connects the existing **Governed Skill Contract v2** lifecycle to the active architecture-aware plan through deterministic, local, least-authority skill recommendation and observational evaluation. Selection is advisory only; it does not execute skills, change plans, grant capabilities, approve architecture, or choose a model/provider.

## Architecture governance progression

```text
v0.25.2  Architecture Contract + Human Clarification
   ↓
v0.25.3  Architecture Discovery & Evidence Binding
   ↓
v0.25.4  Architecture Drift & Compliance
   ↓
v0.25.5  Architecture Change Proposal & ADR
   ↓
v0.26.0  Architecture-Aware Task Planning
   ↓
v0.26.1  Structural Enforcement
   ↓
v0.26.2  Runtime/Data/API & Business Boundary Enforcement
   ↓
v0.26.3  Quality/Operational Enforcement
   ↓
v0.27.0  Governed Skill Contract v2
   ↓
v0.27.1  Architecture-Aware Skill Selection & Evaluation
```

## v0.27.1 selection flow

```text
Request + Requirement Ledger
        ↓
ACTIVE architecture-aware plan
        ↓
Graduated Contract-v2 skills
        ↓
Contract freshness / Architecture Baseline pin
        ↓
Architecture-section compatibility
        ↓
Write-scope / capability / tool / dependency / service / test gates
        ↓
Deterministic local lexical + architecture ranking
        ↓
ADVISORY RECOMMENDATION
```

Core invariants:

- Only graduated Contract-v2 skills can be recommended; `legacy_v1` skills are preserved but not selection-eligible.
- Stale or invalid skill contracts fail closed.
- Planned write targets must fit the skill's `allowed_write_scope`.
- Required capabilities cannot exceed AgentOS governed proxy capabilities.
- Required tools must be explicitly available to the selection run.
- Planned dependencies, external services, architecture sections, and required tests must fit the skill contract.
- Selection never modifies the active plan or grants execution authority.
- Evaluation reads existing task outcomes and never auto-graduates, auto-revokes, or changes future ranking weights.
- Model/provider selection authority remains outside AgentOS.
- MCP exposes selection/evaluation inspection only.

## Main commands

```bash
agentos skill-selection-run --task-id T-123
agentos skill-selection-run --task-id T-123 --available-tools '["pytest"]'
agentos skill-selection-status --task-id T-123
agentos skill-selection-candidates --run-id 1
agentos skill-evaluation-run --selection-run-id 1
```

Existing Skill Contract v2 commands remain available:

```bash
agentos skill-contract-show --skill-id 1
agentos skill-contract-set --skill-id 1 --drafted-by human:architect --contract '{...}'
agentos skill-contract-validate --skill-id 1
agentos skill-graduate --skill-id 1 --approved-by human:reviewer --note "reviewed exact contract"
```

## MCP read-only surface added in v0.27.1

```text
agentos.skill_selection_status_get
agentos.skill_selection_candidates_get
agentos.skill_evaluation_get
```

## Distribution model

Current AgentOS releases use the **Latest Full Release** model with **no updater script**. AgentOS-managed runtime is separate from project-owned user skills, workflows, source, architecture working copies, `governance.local.json`, `.agents/state/**`, and `.agents/runtime/**`.

See [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md).

## Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
git diff --check
```

## Current node documentation

- [Architecture-Aware Skill Selection & Evaluation v0.27.1](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Governed Skill Contract v2](.agents/docs/GOVERNED_SKILL_CONTRACT_V0270.md)
- [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md)

`AGENTS.md` remains the only coding-agent instruction authority. Architecture Authority remains human-owned.
