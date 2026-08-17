# AgentOS Local Governance

**Current release: v0.26.2 — Runtime/Data/API & Business Boundary Enforcement**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **56**.

v0.26.1 turns the structural architecture sections of the human-approved Architecture Contract into deterministic pre-write, planning, and precommit enforcement. It builds on the architecture authority chain introduced in v0.25.2 and completed through discovery/evidence, compliance, ADR/change proposals, and architecture-aware task planning in v0.26.0.

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
```

## Structural hard-contract sections

v0.26.1 focuses only on structural architecture:

- `ARCH-02` Tech Stack
- `ARCH-03` Folder Structure
- `ARCH-04` System Architecture
- `ARCH-05` Module Breakdown
- `ARCH-12` Dependency Graph
- `ARCH-22` Coding Convention
- `ARCH-23` Design Pattern

Runtime/data/API/business boundaries remain reserved for v0.26.2. Quality/security/operational architecture remains reserved for v0.26.3.

## Core invariants

- `AGENTS.md` remains the only coding-agent instruction authority.
- Architecture Authority remains human-owned and hash-pinned.
- AI may inspect, plan, implement within the ACTIVE baseline, and propose an Architecture Change.
- AI may not approve/waive/activate Architecture Authority.
- No ACTIVE baseline means structural enforcement is `not_evaluable` and non-blocking.
- With an ACTIVE baseline, structural violations fail closed before write/plan approval/precommit.
- Structural enforcement is local, static, deterministic, and does not execute project code.
- A blocked structural change must use the v0.25.5 Proposal → ADR → Human Approval → successor baseline lifecycle.
- Project-owned source, rules, workflows, architecture working copies, skills, and runtime state remain protected from AgentOS updater overwrite.

## Structural contract examples

An ACTIVE contract may explicitly declare rules such as:

```json
{
  "ARCH-02": {
    "allowed_dependencies": ["requests"],
    "forbidden_dependencies": ["sqlalchemy"]
  },
  "ARCH-05": {
    "forbidden_module_names": ["utils.py"],
    "module_location_rules": [
      {
        "match": "utils.py",
        "allowed_paths": ["src/shared/date.py", "src/shared/validation.py"]
      }
    ]
  },
  "ARCH-22": {
    "require_file_header_path": true,
    "require_module_purpose": true,
    "require_public_symbol_docstrings": true
  }
}
```

Only explicit machine-readable keys become hard enforcement. AgentOS does not invent architecture rules from prose.

## Main commands

```bash
agentos architecture-structural-status
agentos architecture-structural-check --task-id TASK-1 --changed-file src/example.py
agentos architecture-structural-findings --task-id TASK-1

agentos architecture-plan-impact --task-id TASK-1 --plan '{...}'
agentos architecture-plan-status --task-id TASK-1
agentos precommit-check --task-id TASK-1
```

Architecture Proposal/ADR and Architecture Baseline approval/activation remain human-gated.

## Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests/test_architecture_structural_v0261.py
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
.agents/bin/agentos docs-check
.agents/bin/agentos runtime-health
.agents/bin/agentos manifest-verify
```

## Upgrade

See [.agents/docs/UPGRADE_FROM_0.26.0.md](.agents/docs/UPGRADE_FROM_0.26.0.md).

## Current node documentation

- [Structural Enforcement v0.26.1](.agents/docs/ARCHITECTURE_STRUCTURAL_ENFORCEMENT_V0261.md)
- [Architecture-Aware Task Planning v0.26.0](.agents/docs/ARCHITECTURE_AWARE_TASK_PLANNING_V0260.md)
- [Architecture Change Proposal & ADR v0.25.5](.agents/docs/ARCHITECTURE_CHANGE_PROPOSAL_ADR_V0255.md)
- [Architecture Drift & Compliance v0.25.4](.agents/docs/ARCHITECTURE_DRIFT_COMPLIANCE_V0254.md)
- [Architecture Discovery & Evidence v0.25.3](.agents/docs/ARCHITECTURE_DISCOVERY_EVIDENCE_V0253.md)
- [27-Section Architecture Contract v0.25.2](.agents/docs/ARCHITECTURE_CONTRACT_HUMAN_CLARIFICATION_V0252.md)
