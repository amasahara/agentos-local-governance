# AgentOS Local Governance v0.26.2 — Runtime/Data/API & Business Boundary Enforcement

v0.26.2 extends Architecture Authority enforcement from structural constraints into the project's runtime-facing boundaries for `ARCH-06/07/08/09/10/11/13/14`.

## Main changes

- Adds schema **56** with `architecture_runtime_runs` and `architecture_runtime_findings`.
- Adds a deterministic, non-executing runtime boundary engine.
- Adds plan-time declarations and fail-closed validation for runtime calls, data operations, API routes, business calls, external services, and configuration keys.
- Adds post-change static extraction for Python calls, SQL literals, route decorators, URL literals, and environment-variable access.
- Integrates the runtime boundary gate into `precommit_check`.
- Extends `check_write` with target-only ARCH-09/14 path restrictions.
- Adds read-only CLI inspection/run commands and three read-only MCP inspection tools.
- Keeps Architecture review/approval/activation and waiver authority human-only.

## Security and authority invariants

- Project code is never executed by the v0.26.2 analyzer.
- No network access is required by the analyzer.
- LLM output is not runtime/business authority.
- MCP does not expose scan execution, approval, waiver, contract mutation, or architecture activation.
- A blocked boundary requires an Architecture Change Proposal/ADR or a code/plan change; the engine cannot self-waive.

## Upgrade

Apply the overlay with `tools/apply_v0262.py`, then rebuild release metadata and run the full regression suite.
