# AgentOS Local Governance v0.25.2 — 27-Section Architecture Contract & Human Clarification Gates

[README landing](README.md) | [Tiếng Việt](README.vi.md)

## Current release

- Version: **0.25.2**
- Database schema: **50**
- Schema bootstrap baseline: **46** (unchanged)

v0.25.2 introduces two human-authority boundaries. First, project architecture is
represented by exactly 27 fixed `ARCH-01`…`ARCH-27` sections. Files under
`.agents/architecture/` are only a working copy; AgentOS creates deterministic,
immutable DB baselines and only explicit human review → approval → activation can
make a baseline authoritative. `ARCH-26 Improvement Proposal` always remains
`proposal_only`.

Second, **Grill Me** becomes an enforcement gate. Before task approval, the agent
must record a structured clarity assessment. Material assumptions, ambiguities,
undefined acceptance behavior, business choices, and architectural choices must
be surfaced as human questions. During coding the agent may open a blocking human
decision and recommend an option, but it cannot resolve or waive the decision.
Dependent mutation stops while bounded read-only investigation remains available.
Human answer text is retained locally; signed external audit receives only hashes
and bounded authority metadata.

If a resolution changes requirements, scope, or architecture, AgentOS revokes the
current task approval and supersedes submitted/active plans so execution must be
revalidated.

Fresh DBs still bootstrap schema 46 and run only migrations **47→50**; existing
v0.25.1/schema-49 databases apply only migration **50**.

Architecture MCP is read-only. `agentos.human_decision_request` is the single
monotonic blocker signal: it may only make the system more restrictive and cannot
resolve, waive, approve, activate, or grant authority.

Architecture discovery/evidence binding remains v0.25.3, drift/compliance v0.25.4,
change proposals/ADR v0.25.5, and architecture-aware planning v0.26.0.

See the [node document](.agents/docs/ARCHITECTURE_CONTRACT_HUMAN_CLARIFICATION_V0252.md)
and [upgrade guide](UPGRADE_FROM_0.25.1.md).
