# Rules and Workflow Changelog

## 2026-07-29 — v0.7.1 — Governance synchronization and evidence-grounded claims

### Request

Upgrade the complete AgentOS system from v0.7.0 to v0.7.1 and provide a complete README.

### Decision

Implemented composite `prepare-change`; activated claim/evidence runtime and CLI; added `show-claim`; added `claim_policy`; enforced evidence type, risk, task ownership, success, and local classification; added schema indexes; locked symlink containment behavior; synchronized all documentation and version identities.

### Enforcement

- instruction: `AGENTS.md`;
- structured policy: `.agents/config/governance.json`;
- runtime: `.agents/agentos/core.py`, `policy.py`, `db.py`, `cli.py`, `indexing.py`;
- tests: `.agents/tests/test_agentos.py`;
- human documentation: `README.md`, `huong_dan.md`, `.agents/docs/*`.

### Migration note

Migration 4 adds indexes for tool-call and claim/evidence lookup. Existing v0.7.0 state is migrated automatically when AgentOS opens the database.

## 2026-07-28 — v0.7.0 — Local-first tools, cache, indexing, documentation contracts

Introduced local-first tool governance, file-read cache contracts, incremental Python symbol indexing, database migrations, documentation-code contracts, and aggregate status.
