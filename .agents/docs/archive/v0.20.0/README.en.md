[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.20.0

## Project Identity & Purpose Model

v0.20.0 is the first node after the v0.19.5 baseline. It does not merge projects yet; it establishes the identity foundation required for v0.20.1 Primary Project Selection & Domain Compatibility.

### New guarantees

- Durable `project_uuid`, independent of absolute repository path.
- Local `instance_uuid` for each working copy.
- Fail-closed detection when a full directory copy duplicates a live instance UUID.
- Human-confirmed project fork creates a new UUID and preserves `origin_project_uuid`.
- Purpose captures business domain, purpose family, capabilities, role, and human confirmation.
- External audit uses `project_uuid` instead of a path hash.
- Schema 32 namespaces `symbol_index`, `project_findings`, `promoted_skills`, and `resource_leases` when present.
- MCP exposes identity/purpose reads only; UUID mutation and purpose confirmation are not agent-callable.

### Local-first without replacing the LLM

AgentOS keeps governance, state, evidence, audit, and identity local. The LLM still provides reasoning, planning, and semantic suggestions. Identity/purpose decisions that affect future consolidation remain human-controlled.

### Layout

```text
.agents/config/project.id               stable project UUID
.agents/config/project.purpose.json     human-confirmed business purpose
.agents/state/project.instance.json     local working-copy UUID
~/.agentos/projects/registry.json       host-local clone/relocation registry
```

### Verification

```bash
.agents/bin/agentos project-identity-verify
.agents/bin/agentos project-identity-db-sync
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

### Deliberate scope boundary

v0.20.0 does not select a primary project or execute project consolidation. Those capabilities belong to v0.20.1 and v0.20.2.

### Upgrade from v0.19.5

The upgrade must preserve all v0.19.5 guarantees: unified context/knowledge, outcome evaluation, memory privacy, embedding storage, retention, audit archival, and backup verification. Migration 32 is additive.

See [.agents/docs/PROJECT_IDENTITY.md](.agents/docs/PROJECT_IDENTITY.md) for the complete contract.
