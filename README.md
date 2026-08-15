# AgentOS Local Governance

**Current release: v0.25.2 — 27-Section Architecture Contract & Human Clarification Gates**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **50**.

v0.25.2 establishes a human-owned Architecture Authority and turns requirement
clarification into a fail-closed execution gate. A project has exactly 27 fixed
architecture sections (`ARCH-01`…`ARCH-27`), represented as a human-readable
working copy plus machine-readable contracts. Working-copy files are never
approval authority: AgentOS snapshots deterministic immutable baselines in
SQLite, and only explicit human review, approval, and activation can make a
baseline ACTIVE.

The same release upgrades the existing `assess_requirement_clarity` /
`clarify_if_needed` workflow into **Grill Me** enforcement. Material assumptions,
ambiguities, undefined acceptance behavior, or decisions discovered while coding
become first-class human-decision blockers. Read-only investigation may continue;
dependent writes and governed mutations fail closed until the human resolves the
question and the task is revalidated.

The v0.25.0 Schema Bootstrap Baseline remains unchanged: fresh databases
materialize schema 46 and apply only migrations **47→50**. Existing v0.25.1
schema-49 databases apply only migration **50**.

## Core invariants

- `AGENTS.md` remains the only coding-agent instruction authority.
- Architecture working-copy Markdown/JSON is **not** Architecture Authority.
- Exactly 27 section IDs are recognized; free-form architecture sections do not
  become active authority.
- `ARCH-26 Improvement Proposal` is permanently `proposal_only`; proposals do
  not silently become current architecture.
- AI may draft, inspect, validate, recommend, and open a blocking human decision.
- AI may not review/approve/activate architecture, resolve/waive a human decision,
  or silently convert a material assumption into an implementation choice.
- Human architecture lifecycle actions pin the exact deterministic baseline hash.
- Editing the working copy after activation does not mutate the ACTIVE baseline.
- An unresolved clarity/decision gate blocks task approval, plan approval,
  project writes, mutating local tools, pre-commit readiness, and privileged
  governed operations.
- While waiting for a human, bounded read-only inspection remains available.
- Human question/answer text is retained locally; signed external audit receives
  only hashes and bounded authority metadata.
- MCP architecture operations are read-only. `agentos.human_decision_request` is
  the sole v0.25.2 monotonic blocker signal: it can only make execution more
  restrictive and cannot grant authority.
- v0.25.2 does **not** perform architecture discovery, source-evidence binding,
  architecture drift enforcement, or architecture-aware planning; those remain
  subsequent roadmap nodes.

## Main commands

```bash
# Working copy only; does not infer architecture from source.
agentos architecture-init --created-by human
agentos architecture-validate

# Grill Me before approval.
agentos --task-id TASK-1 clarity-assess \
  --assessed-by agent \
  --objective-understood --scope-understood \
  --constraints-understood --acceptance-understood
agentos --task-id TASK-1 grill-me

# Human-owned architecture baseline lifecycle.
agentos architecture-baseline-create --created-by architect
agentos --task-id GOV-TASK --session-id HUMAN-SESSION architecture-baseline-review ... --human-confirmed
agentos --task-id GOV-TASK --session-id HUMAN-SESSION architecture-baseline-approve ... --human-confirmed
agentos --task-id GOV-TASK --session-id HUMAN-SESSION architecture-baseline-activate ... --human-confirmed

# During execution, an agent may only open the blocker.
agentos --task-id TASK-1 decision-request --phase execution \
  --type architecture_choice --severity high \
  --question "Which approved behavior should be used?"

# Only human/operator boundary resolves it.
agentos --task-id TASK-1 --session-id HUMAN-SESSION decision-resolve ... --human-confirmed
```

## Validation

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

## Upgrade

See [Upgrade v0.25.1 → v0.25.2](UPGRADE_FROM_0.25.1.md).

## Current node documentation

- [Architecture Contract & Human Clarification Gates](.agents/docs/ARCHITECTURE_CONTRACT_HUMAN_CLARIFICATION_V0252.md)
- [Release Metadata Coherence](.agents/docs/RELEASE_METADATA_COHERENCE_V0251.md)
- [Schema Bootstrap Baseline](.agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md)
