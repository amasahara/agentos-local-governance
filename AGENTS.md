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
8. run documentation, tests, structural review, and synchronization checks.

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
