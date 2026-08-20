# AgentOS v0.28.0 — Architecture & Agent Command Center

## Purpose

v0.28.0 adds a **read-only Architecture & Agent Command Center** after the architecture,
skill, supervisor, isolated-workspace and controlled-integration backends are already governed.

The Command Center answers one operator question:

> What is AgentOS doing now, under which architecture, and what needs human attention?

It does **not** create a second control plane.

## Architecture

```text
AgentOS state / architecture / supervisor / workspace
                    |
                    | strict read-only projection
                    v
          Command Center Snapshot v1
              /             \
             /               \
      CLI text TUI         MCP read-only
      CLI JSON             section/actions
             \               /
              \             /
               same snapshot
```

No dashboard table is introduced. Schema remains **61**.

## Snapshot

The snapshot aggregates:

### Architecture

- active/latest Architecture Baseline;
- active section coverage (27-section contract);
- Architecture Change Proposal counts;
- pending ADR count.

### Execution

- tasks and task states;
- supervisor states;
- worker states;
- active resource leases;
- workspace states;
- controlled-integration proposal states;
- unresolved primary conflicts.

### Compliance

The latest status of:

- Architecture Contract compliance;
- Structural enforcement;
- Runtime/data/API/business boundary enforcement;
- Quality/security/operational enforcement.

Overall precedence is:

```text
BLOCK > WARN > PASS > NOT_EVALUABLE
```

### Human actions

Privacy-safe metadata for pending:

- human clarification/decision requests;
- Architecture Baseline review/approval/activation;
- Architecture Change Proposal review/approval;
- proposed ADR decisions;
- supervisor activation;
- controlled-integration review/approval/apply.

The Command Center does not include raw task requests, human questions, source bodies,
capability tokens, secrets, or physical workspace paths.

## CLI

```text
command-center
command-center-snapshot
command-center-actions
command-center-section
```

`command-center` renders a deterministic terminal dashboard by default.

Use:

```bash
agentos command-center --format json
```

for the same machine-readable snapshot.

## MCP

Read-only tools:

```text
agentos.command_center_snapshot_get
agentos.command_center_human_actions_get
agentos.command_center_section_get
```

No MCP mutation tool is added.

## Authority invariants

v0.28.0 enforces:

- projection only;
- strict read-only SQLite access;
- no architecture approval authority;
- no integration approval authority;
- no worker launch authority;
- no model/provider selection authority;
- no raw source-content exposure;
- no physical workspace-path exposure;
- no web server.

The optional local Web Control Plane remains **v0.28.1** and must consume the same
Command Center snapshot/read model rather than inventing a new backend authority.
