# AgentOS Instruction Authority

`AGENTS.md` is the only coding-agent instruction source in this repository.

## Core principles

- Understand the user's language directly; do not call a translation tool merely to parse intent.
- Preserve the original request and reply in the user's language.
- Keep technical identifiers in English unless the project explicitly requires otherwise.
- Work local-first. Unknown tools and writes outside approved scope fail closed.
- New files must be placed by responsibility, feature, layer, and lifecycle.
- Reuse stable shared capabilities; do not create generic monolithic `utils.py`, `helpers.py`, or `common.py` files.
- Keep temporary scripts, tests, fixtures, downloads, and validation artifacts under `.agents/runtime/`.

## Source documentation contract

Each source file must contain one header declaring:

- `File:` project-relative path;
- `Purpose:` module purpose;
- `Responsibilities:` bounded responsibilities.

Public classes, functions, and methods must document their contract at the symbol itself, including inputs, outputs, raised errors, and material side effects. Do not repeat the file path in every symbol.

## Guarded change workflow

Before creating or modifying code:

1. create and approve a task;
2. build or update the local symbol index;
3. run `prepare-change`;
4. read the recommended bounded context;
5. review similar symbols and duplicate candidates;
6. verify write permission;
7. execute the change;
8. run `docs-scan` for the affected source scope;
9. run tests, structural review, and synchronization checks.

A failed write check blocks execution.

## Evidence-grounded claims

Conclusions about business logic, security behavior, data visibility, destructive effects, or governance enforcement must be traceable to recorded tool evidence when required by `claim_policy`.

A high-risk claim must not be recorded or reported without at least one successful supporting tool call from the same task. Sensitive medium-risk claims also require evidence.

Evidence is local by default. Network evidence is rejected unless the active structured policy explicitly permits it and the relevant egress has been authorized and audited.

Use:

- `record-tool` to preserve a bounded execution record;
- `record-claim` to link a conclusion to evidence;
- `list-claims` to review task claims;
- `show-claim` to inspect the supporting tool calls.

## Governance changes

A governance change is incomplete when instruction text, structured configuration, runtime enforcement, tests, human documentation, changelog, or version identity materially disagree.

For every governance change, evaluate and report the status of:

- `AGENTS.md`;
- `.agents/config/governance.json`;
- `.agents/agentos/` runtime;
- `.agents/tests/`;
- `README.md` and `huong_dan.md`;
- `.agents/docs/`;
- `VERSION` and package version.


## v0.9.0 runtime repair gates

- Run `agentos docs-scan --scope <source-root-or-affected-path>` before reporting a source change complete. A failed source documentation scan blocks completion.
- Use `tool-guard` before governed tool execution. Unknown tools fail closed; network tools require reason, justification, and prior successful local evidence.
- Keep `record-tool` as the canonical evidence writer. `record-tool-result` records guard/audit outcomes and must not replace evidence records.
- Use `cache-lookup` before repeating an identical bounded file read and `cache-store` only for bounded, non-sensitive summaries. A stale cache entry must not be reused.

## Persistent task heartbeat and workflow gates (v0.9.0)

AgentOS workflow state is persisted outside the conversation context. Starting a task sets `.agents/runtime/current_task.json` and seeds `workflow_steps` from the configured workflow. Commands may resolve the current task when `--task-id` is omitted.

Before continuing a resumed task, inspect `whoami` or `next-step`. Do not bypass a pending required workflow step because a conversation is long or because a user asks to skip governance. A skipped step must be recorded with `mark-step --status skipped --note ...`; the reason is mandatory.

The final `report` command is fail-closed and must return a non-zero exit code while any required step other than `report` remains pending.

## Governance drift acknowledgement

Governance files are compared against a human-acknowledged hash baseline. Use `drift-check` and `drift-diff` to review changes. A coding agent must not call `ack-baseline` on behalf of the user. Human acknowledgement is required after reviewing intentional governance changes.

## Safe installation and local policy

Installers must preserve existing root files. Conflicting files are written with an `.agentos` suffix for manual merge. Project-specific overrides belong in `.agents/config/governance.local.json`; the canonical `.agents/config/governance.json` remains the distributed baseline.

## v0.9.0 trust-boundary rules

- Never use direct `record-tool`; obtain a guard token and complete that token.
- Never supply or override tool classification. Runtime classification is authoritative.
- Do not mark automated-only workflow steps done manually.
- Use a distinct session ID for each concurrent agent or IDE session.
- Do not approve sensitive local overrides or acknowledge baselines on behalf of a human.
- Do not report completion while baseline, drift, provenance, or override gates are blocked.
