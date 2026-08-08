# Primary Project Selection & Domain Compatibility — v0.20.1

## Goal

v0.20.1 decides **which project is the consolidation target** and whether each intended source is business-compatible with that target. It deliberately does not merge code yet.

## Invariants

```text
N candidate projects
        ↓ read-only scan
business identity/purpose
        ↓
compatibility matrix
        ↓
advisory recommendation
        ↓
HUMAN SELECTS EXACTLY ONE PRIMARY
```

The selection may be persisted only in the active project when the selected `project_uuid` equals that active root. This prevents AgentOS from writing governance state into a project that is about to become a secondary/source project.

## Compatibility rules

| Domain | Purpose | Result |
|---|---|---|
| Same | Same | `compatible` |
| Same | Different | `conditionally_compatible` |
| Different | Any | `incompatible` |

For `conditionally_compatible`, a human must provide `confirmed_by` and a business reason. Domain mismatch cannot be overridden.

Capabilities, module names, shared libraries, language, framework, authentication, reporting, Excel helpers, or other technical similarities are evidence only; they never override business-domain mismatch.

## Directed compatibility

After a primary is chosen, AgentOS requires:

```text
Primary ↔ Source A  compatible
Primary ↔ Source B  compatible
Primary ↔ Source C  compatible
```

Source A and Source B are not required to interact with each other. The model is directed consolidation into one primary, not an all-to-all project federation.

## Source immutability

Candidate scanning reads only:

- `.agents/config/project.id`
- `.agents/config/project.purpose.json`
- `.agents/state/project.instance.json` when present
- `.agents/config/governance.json`
- `VERSION`

It does not initialize identity, update registries, open source AgentOS databases for write, or change source files.

## MCP boundary

MCP exposes only read operations:

- `agentos.project_candidate_set_get`
- `agentos.project_domain_compatibility_get`
- `agentos.project_primary_recommend`
- `agentos.project_primary_selection_get`

MCP does **not** expose compatibility confirmation or primary selection.

## Next node

v0.20.2 consumes a human-selected primary and performs governed Primary-Project Consolidation. Source projects remain read-only; only the primary receives controlled writes.
