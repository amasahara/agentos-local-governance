# AgentOS Local Governance v0.28.0 — Architecture & Agent Command Center

## Development patch scope

v0.28.0 adds a privacy-safe, read-only Command Center on top of the existing
Architecture Governance, skill selection, multi-agent supervisor, isolated workspace,
and controlled-integration backends.

### Core changes

- Database schema remains **61**.
- Adds a single shared Command Center Snapshot v1 read model.
- Adds deterministic terminal dashboard rendering.
- Aggregates:
  - active Architecture Baseline and section coverage;
  - Architecture Change Proposal / ADR lifecycle counts;
  - task/supervisor/worker/workspace state;
  - active resource leases and integration conflicts;
  - latest architecture compliance/structural/runtime/quality status;
  - privacy-safe pending human/operator actions.
- Does not persist dashboard state.
- Uses strict `connect_read_only()` access.
- Does not expose raw task requests, human questions, source bodies, secrets,
  capability tokens, or physical workspace paths.

### CLI

Adds four read-only commands:

```text
command-center
command-center-snapshot
command-center-actions
command-center-section
```

Expected unified CLI count after integration: **331 → 335**.

### MCP

Adds three read-only tools:

```text
agentos.command_center_snapshot_get
agentos.command_center_human_actions_get
agentos.command_center_section_get
```

Expected MCP catalog after integration: **120 → 123**.

No MCP mutation authority is added.

### Authority invariants

The Command Center cannot:

- approve/activate Architecture Baselines;
- approve ADRs;
- approve or apply controlled integration;
- create/approve tasks or plans;
- launch workers/processes;
- select a model/provider;
- mutate AgentOS state;
- expose workspace physical paths.

The optional local Web Control Plane remains reserved for **v0.28.1** and must use
the same Command Center read model.

### Validation of development patch

Focused Command Center tests in a representative SQLite read-model fixture:

```text
10 passed
```

The final v0.28.0 release must still run the full repository regression and all
docs/release/manifest gates on the real v0.27.3 checkout.
