# AgentOS Governance

This is the only instruction source for all coding agents in this repository.

## Core principles

1. Understand the user's language directly. Do not call a translation tool merely to interpret intent.
2. Preserve the user's original request in the task brief.
3. Do not infer missing business requirements.
4. Do not modify files until the request is sufficiently clear and the task is approved.
5. Prefer repository-local evidence, indexed symbols, targeted search, and bounded reads.
6. Do not repeat a failed tool call without new evidence that specifically addresses the failure.
7. Keep source, tests, scripts, generated artifacts, and temporary files in their designated locations.
8. Reuse stable shared capabilities rather than introducing duplicate implementations.
9. Treat `AGENTS.md` as the sole instruction file. Model-specific instruction files are forbidden.

## Requirement clarification gate

Before planning or modifying files, determine whether the request provides:

- intended outcome;
- affected feature, module, file, or observable behavior;
- current behavior or problem, when applicable;
- expected behavior;
- relevant constraints;
- sufficient acceptance criteria;
- acceptable scope and risk.

When a missing detail could materially change the implementation, stop and ask a concise clarification question.

Do not choose one interpretation merely because it appears likely.

A short request may still be clear. Judge semantic completeness, not word count.

### Clarification levels

- Low risk: proceed only with reversible, convention-preserving technical assumptions and record them.
- Medium risk: ask before execution.
- High risk: require explicit scope, acceptance criteria, and approval.

Business behavior, permissions, calculations, destructive changes, migrations, security rules, and data visibility must never be inferred.

## Tool execution policy

- Detect operating system, shell, project root, Python executable, path conventions, encoding, and virtual environment once per session.
- Maximum tool calls per work unit: 12.
- Maximum identical tool calls: 1.
- Maximum retries for the same normalized failure signature: 1.
- Maximum consecutive failures: 3.
- Retry only after obtaining new evidence or applying a change that directly addresses the error.
- Cache file reads by path, modification time, and content hash.
- Cache searches by query, scope, and graph generation.
- Prefer composite governance operations over multiple small calls.
- Return summaries and bounded excerpts rather than full command output.
- On budget exhaustion, stop and report the intended action, failed command, normalized error, attempted fixes, and required user input.

## Source inspection policy

### Python and Django

Preferred order:

1. symbol or route lookup;
2. targeted text search;
3. bounded file read;
4. AST analysis;
5. execution only when static analysis is insufficient.

For Django, inspect in this order when relevant:

1. `urls.py`;
2. the relevant view;
3. form or serializer;
4. template;
5. model only when required.

Do not import the Django project merely to inspect source. Do not run the server for static analysis. Do not scan all apps before identifying the relevant route. Do not inspect migrations unless schema changes are in scope.

### JavaScript and TypeScript

Prefer symbol index, targeted search, and bounded reads. Avoid running builds merely to locate code.

### Generated and binary files

Skip by default unless the task explicitly concerns them.

## File placement

Resolve placement before creating a persistent file.

Persistent source belongs under the project's existing source roots and feature/layer structure.

Persistent tests belong under:

- `tests/`
- `test/`
- `__tests__/`

Persistent scripts belong under:

- `scripts/`
- `tools/`
- `devtools/`

Temporary task files belong under:

`.agents/runtime/task-workspaces/<TASK-ID>/`

Do not create source files at repository root. Avoid ambiguous folders such as `misc`, `other`, and `new_folder`.

## Shared capability policy

Move code into shared infrastructure only when:

- at least two independent features use it;
- it has no domain-specific dependency;
- its contract is stable.

Avoid monolithic `utils.py`, `helpers.py`, and `common.py`. Prefer focused packages such as:

- `shared/datetime/`
- `shared/excel/`
- `shared/files/`
- `shared/presentation/`

## Workflow

receive_request
→ analyze_intent
→ assess_requirement_clarity
→ clarify_if_needed
→ create_task_brief
→ governance_check
→ plan
→ await_approval
→ prepare_change
→ execute
→ validate
→ review
→ synchronize
→ report

`prepare_change` combines placement, similar-symbol search, duplicate risk, write permission, and recommended context.

No modifying tool may run unless the task status is `ready`, approval is recorded, and write scope is allowed.


## Developer documentation and governance synchronization

`huong_dan.md` is the bilingual developer entry point. It explains the project but does not replace this instruction source.

When a user request changes project rules or workflow, classify the task as `governance_change`.

Before reporting completion, evaluate and synchronize:

- `AGENTS.md`;
- `.agents/config/governance.json`;
- `huong_dan.md`;
- `.agents/docs/PROJECT_STRUCTURE.md`;
- `.agents/docs/USAGE.md`;
- `.agents/docs/RULES_WORKFLOW_CHANGELOG.md`;
- implementation under `.agents/agentos/`, when enforcement changes;
- tests under `.agents/tests/`, when behavior changes;
- `VERSION`.

Not every file must be modified, but every item must be evaluated. The final report must include a synchronization matrix with `updated`, `unchanged`, or `not_applicable` and a reason.

A governance change is incomplete when instruction text, structured configuration, runtime enforcement, tests, human documentation, changelog, or version identity materially disagree.

Run `agentos docs-check` and the relevant tests before reporting completion.


## Local-first guarded execution

All tool access must pass through AgentOS guard. Unknown tools fail closed. Network calls require structured justification and a successful prior local evidence attempt.

## Code documentation governance

Every owned source file must declare its project-relative path exactly once in the file header. The header must contain `File:`, `Purpose:`, and `Responsibilities:`. Do not repeat the path inside each class or function.

Every public class, public function, public method, and business-logic symbol must document its own contract. Function and method documentation must describe purpose, every meaningful input, returned output, relevant errors, and side effects. Private trivial functions may omit long documentation.

After changing source, run `agentos docs-code-check` before final validation. A stale path header, missing input contract, or missing output contract fails enforcement mode.
