# AgentOS v0.27.0 Developer Guide

1. Promote procedural memory as before; each new candidate receives a least-authority Governed Skill Contract v2.
2. Use `skill-contract-show` and `skill-contract-set` to declare inputs/outputs, ARCH sections, capabilities, tools, read/write scopes, dependencies, external services, risk, and tests.
3. Run `skill-contract-validate`. Architecture-sensitive skills require an ACTIVE Architecture Baseline and pin its exact hash.
4. `skill-graduate` and `skill-revoke` remain human-only; MCP exposes no mutation authority.
5. Legacy v1 skills are preserved and never rewritten in place. Create a reviewed successor candidate/version to adopt v2.
6. Automatic architecture-aware selection is deferred to v0.27.1.
7. Starting with v0.27.0 there is no `apply_v*.py` chain. Download latest full release while preserving project-owned skills, workflows/workflow state, source, architecture working copies, `governance.local.json`, state, and runtime.
8. For AgentOS release development, rebuild/verify the manifest and run release/docs/instruction/regression checks.

Database schema: **58**; bootstrap baseline remains **46**.
