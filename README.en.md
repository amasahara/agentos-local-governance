# AgentOS Local Governance v0.27.0 — Governed Skill Contract v2

[README landing](README.md) | [Tiếng Việt](README.vi.md)

## Current release

- Version: **0.27.0**
- Database schema: **58**
- Schema bootstrap baseline: **46** (unchanged)

v0.27.0 upgrades the existing procedural-skill subsystem into **Governed Skill Contract v2**. It does not create a second skill framework: the existing candidate → human graduation → revoke lifecycle remains authoritative and gains a deterministic machine-readable contract, architecture binding, hashes, and explicit authority boundaries.

## Contract v2

Each new candidate declares inputs/outputs, required Architecture sections, capabilities, tools, read/write scopes, dependencies, external services, preconditions/postconditions, risk tier, test contract, and architecture constraints.

A skill contract cannot grant itself authority beyond task, plan, architecture, capability, filesystem, network, database, or tool governance.

Legacy v1 skills remain readable and are never rewritten in place. Moving a legacy skill to v2 requires a reviewed successor candidate/version rather than silent mutation of an approved artifact.

Architecture-sensitive contracts require an ACTIVE human-approved Architecture Baseline and pin its exact baseline hash when validation succeeds. Automatic architecture-aware skill selection is intentionally deferred to v0.27.1.

## Distribution model — no updater scripts

Starting with v0.27.0, AgentOS no longer requires version-specific `apply_v*.py` updater scripts.

User skills, project workflows/workflow state, project source, architecture working copies, `governance.local.json`, `.agents/state/**`, and `.agents/runtime/**` are project-owned partitions and are excluded from the release-managed payload.

Download the latest GitHub Release/source to obtain the newest AgentOS-managed distribution. See [.agents/docs/INSTALL_LATEST_RELEASE.md](.agents/docs/INSTALL_LATEST_RELEASE.md).

## Commands

```bash
agentos skill-contract-show --skill-id 1
agentos skill-contract-set --skill-id 1 --drafted-by human:architect --contract '{...}'
agentos skill-contract-validate --skill-id 1
agentos skill-contract-status
```

Skill graduation/revocation remain human-gated. MCP exposes read-only contract inspection only.
