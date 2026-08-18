# AgentOS Local Governance

**Current release: v0.27.0 — Governed Skill Contract v2**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **58**. Schema bootstrap baseline remains **46**.

v0.27.0 upgrades the existing procedural-skill lifecycle into a **Governed Skill Contract v2**. New skill candidates now carry deterministic contracts for architecture sections, capabilities, tools, read/write scopes, dependencies, external services, risk, tests, preconditions, and postconditions. Human graduation/revocation authority remains unchanged; MCP remains read-only.

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
```

## Governed Skill Contract v2

A new candidate uses a closed deterministic contract:

```json
{
  "contract_version": 2,
  "skill_key": "example",
  "skill_version": 1,
  "inputs": [],
  "outputs": [],
  "required_architecture_sections": [],
  "required_capabilities": [],
  "required_tools": [],
  "allowed_read_scope": [],
  "allowed_write_scope": [],
  "allowed_dependencies": [],
  "allowed_external_services": [],
  "preconditions": [],
  "postconditions": [],
  "risk_tier": "medium",
  "test_contract": {"required": true, "suites": []},
  "architecture_constraints": {}
}
```

Core invariants:

- New candidates use Contract v2; existing v1 skills remain readable and are **not rewritten in place**.
- Skill contracts cannot grant architecture, task, tool, capability, filesystem, network, database, or approval authority beyond existing AgentOS gates.
- Architecture-sensitive contracts require an ACTIVE human-approved Architecture Baseline and pin its exact hash when validation succeeds.
- Human approval is still required to graduate a candidate; human authority is also required to revoke a skill.
- v0.27.0 does **not** perform automatic architecture-aware skill selection. Selection/evaluation is reserved for v0.27.1.
- MCP exposes contract inspection only; it cannot set, validate-as-authority, graduate, revoke, approve, or mutate skills.

## Distribution model from v0.27.0

AgentOS no longer requires version-specific `apply_v*.py` updater scripts.

The release is divided into two ownership planes:

```text
AGENTOS-MANAGED DISTRIBUTION
  .agents/agentos/**
  release-owned policy/docs/tests/runtime launchers

PROJECT-OWNED PARTITION
  user skills
  project workflows / workflow state
  project source
  architecture working copies
  governance.local.json
  .agents/state/**
  .agents/runtime/**
```

Project-owned content is not part of the managed release payload. Download the latest GitHub Release/source and use the newest AgentOS-managed distribution; no version-specific updater script is required.

See [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md).

## Main skill commands

```bash
agentos skill-promote --memory-id 12 --promoted-by human:author
agentos skill-contract-show --skill-id 1
agentos skill-contract-set --skill-id 1 --drafted-by human:architect --contract '{...}'
agentos skill-contract-validate --skill-id 1
agentos skill-contract-status
agentos skill-graduate --skill-id 1 --approved-by human:reviewer --note "reviewed exact v2 contract"
```

## Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
git diff --check
```

## Current node documentation

- [Governed Skill Contract v2](.agents/docs/GOVERNED_SKILL_CONTRACT_V0270.md)
- [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [Quality/Operational Enforcement v0.26.3](.agents/docs/QUALITY_OPERATIONAL_ENFORCEMENT_V0263.md)
- [Runtime/Data/API Enforcement v0.26.2](.agents/docs/RUNTIME_DATA_API_BUSINESS_ENFORCEMENT_V0262.md)
- [Structural Enforcement v0.26.1](.agents/docs/ARCHITECTURE_STRUCTURAL_ENFORCEMENT_V0261.md)

`AGENTS.md` remains the only coding-agent instruction authority. Architecture Authority remains human-owned.
