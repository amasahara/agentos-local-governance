# AgentOS Local Governance v0.26.2 — Runtime/Data/API & Business Boundary Enforcement

[README landing](README.md) | [Tiếng Việt](README.vi.md)

## Current release

- Version: **0.26.2**
- Database schema: **56**
- Schema bootstrap baseline: **46** (unchanged)

v0.26.1 adds deterministic **Structural Enforcement** to the existing planning, write, and precommit boundaries. The release focuses on `ARCH-02/03/04/05/12/22/23`: tech stack, folder structure, system/component structure, module placement, dependency graph, coding convention, and structural design-pattern artifacts.

No ACTIVE Architecture Baseline keeps the engine non-blocking and `not_evaluable`. Once a human-approved baseline is ACTIVE, explicit machine-readable structural rules may fail closed before a prohibited structure is committed.

## Authority

- Architecture remains human-owned and hash-pinned.
- AI may inspect, plan, and propose architecture changes.
- AI may not approve, waive, rewrite, or activate architecture authority.
- MCP structural operations are read-only.
- A legitimate blocked structural change must go through the v0.25.5 Proposal → ADR → Human Approval → successor baseline lifecycle, then be re-planned under v0.26.0 planning.

## Structural enforcement examples

Explicit contracts may restrict dependencies, file/module names and locations, component roots, import edges, coding-convention requirements, and required/forbidden design artifacts.

For example, a contract can forbid `utils.py`, require date and validation utilities to live in specific shared modules, or reject a dependency not listed in `ARCH-02.allowed_dependencies`.

## Commands

```bash
agentos architecture-structural-status
agentos architecture-structural-check --task-id TASK-1 --changed-file src/example.py
agentos architecture-structural-findings --task-id TASK-1
agentos architecture-plan-status --task-id TASK-1
agentos precommit-check --task-id TASK-1
```

See [Structural Enforcement v0.26.1](.agents/docs/ARCHITECTURE_STRUCTURAL_ENFORCEMENT_V0261.md) and the [v0.26.0 → v0.26.1 upgrade guide](.agents/docs/UPGRADE_FROM_0.26.0.md).
