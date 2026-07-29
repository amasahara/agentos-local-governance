# AgentOS Local Governance

**Local-first governance for AI coding agents.**  
**Lớp quản trị local-first dành cho AI coding agent.**

AgentOS Local Governance helps developers keep AI coding agents aligned with one repository-local set of instructions, structured policies, approval gates, filesystem boundaries, evidence requirements, tests, and synchronized documentation.

AgentOS Local Governance giúp developer kiểm soát AI coding agent bằng một hệ thống quản trị nằm trực tiếp trong repository, gồm instruction thống nhất, policy có cấu trúc, approval gate, giới hạn filesystem, yêu cầu bằng chứng, kiểm thử và tài liệu đồng bộ.

> Repository slug: `agentos-local-governance`  
> Current version: `v0.9.0`  
> Database schema: `5`  
> Primary runtime: Python standard library  
> Test dependency: `pytest`

---

## English

### Why this project exists

AI coding agents can move quickly, but speed without project-local governance creates predictable risks. An agent may:

- infer missing requirements and implement the wrong behavior;
- modify files before approval or outside the agreed scope;
- create source, tests, scripts, or temporary artifacts in inconsistent locations;
- duplicate capabilities that already exist elsewhere in the repository;
- repeat failed tool calls without changing strategy;
- use network tools before exhausting local evidence;
- state conclusions about business logic, security, or data behavior without traceable evidence;
- apply different instructions depending on the model, IDE, or integration;
- update documentation without updating runtime enforcement, or update runtime without updating tests and documentation;
- allow rules, configuration, version identity, and actual behavior to drift apart.

AgentOS Local Governance provides a repository-local control layer for those risks. It is designed to work alongside different LLMs, coding agents, IDE integrations, CLI tools, local models, and remote models.

It is **not**:

- an LLM;
- a general-purpose autonomous agent framework;
- a hosted cloud service;
- an IDE extension;
- a replacement for source control, code review, or human approval.

Its role is to make project rules explicit, machine-readable where appropriate, enforceable at runtime, testable, and auditable.

### Design principles

#### 1. One instruction authority

`AGENTS.md` is the sole coding-agent instruction source.

`README.md`, `huong_dan.md`, and `.agents/docs/*` explain the system to developers, but they do not become competing instruction authorities.

Model-specific instruction files such as the following are rejected by `instruction-check`:

```text
CLAUDE.md
GEMINI.md
COPILOT.md
CODEX.md
CURSOR.md
```

#### 2. Local-first evidence

The agent should inspect local code, local indexes, recorded tool calls, and repository state before relying on network tools.

In v0.9.0, evidence-grounded claims accept successful `local` tool calls by default. Network evidence is disabled by the active policy.

#### 3. Fail-closed writes

A path is writable only when all required conditions are true:

- the task exists;
- the task has been approved;
- the path is project-relative or resolves inside the project root;
- the path is inside an approved scope;
- path traversal is absent;
- a symlink does not escape the project root.

#### 4. Structural governance

New files should be placed by responsibility, feature, layer, and lifecycle instead of being dropped into generic folders.

The system also exposes symbol indexing and duplicate-candidate detection so an agent can inspect reuse opportunities before creating a new implementation.

#### 5. Evidence-grounded conclusions

High-risk claims, and selected medium-risk claims, must reference successful tool calls from the same task.

This creates a traceable chain:

```text
claim
→ claim_evidence
→ tool_call
→ task
→ approval and execution context
```

#### 6. Governance synchronization

A governance change is incomplete when instruction text, structured policy, runtime enforcement, tests, developer documentation, changelog, or version identity materially disagree.

### Core capabilities in v0.9.0

- **Single instruction authority** through `AGENTS.md`
- **Task creation and bounded approval scopes**
- **Fail-closed project-root write containment**
- **Path traversal protection**
- **File and directory symlink-escape protection**
- **Composite change preparation** for create and modify operations
- **Feature/layer placement resolution** for new source files
- **Python symbol indexing** with qualified names and source locations
- **Similar-symbol discovery**
- **Duplicate-candidate reporting** using Python AST fingerprints
- **Recorded tool execution audit**
- **Evidence-grounded claims** with risk and claim-type validation
- **Atomic claim/evidence persistence**
- **Claim listing and evidence inspection**
- **SQLite schema migrations and status reporting**
- **Machine-readable policy validation**
- **Bilingual developer documentation**
- **Instruction and documentation synchronization checks**
- **Aggregated project status reporting**

### Standard workflow

The active default workflow is declared in `.agents/config/governance.json`:

```text
receive_request
→ assess_requirement_clarity
→ clarify_if_needed
→ approve_task
→ detect_environment
→ build_or_update_local_index
→ prepare_change
→ execute_guarded
→ documentation_check
→ tests
→ evidence_review
→ egress_review
→ structural_review
→ synchronize
→ report
```

The current v0.9.0 CLI directly implements the following runtime portions of that workflow:

```text
start-task
→ approve-task
→ index-build / index-query / duplicate-scan
→ prepare-change
→ record-tool
→ record-claim
→ list-claims / show-claim
→ docs-check / instruction-check / db-status / status
```

Some workflow stages remain governance responsibilities rather than standalone CLI commands. For example, environment detection, guarded execution, test execution, structural review, and final reporting may be performed by the calling agent or integration while following `AGENTS.md` and `governance.json`.

### Project structure

```text
project-root/
├── README.md
├── AGENTS.md
├── huong_dan.md
├── VERSION
├── src/
└── .agents/
    ├── agentos/
    │   ├── __init__.py
    │   ├── cli.py
    │   ├── core.py
    │   ├── db.py
    │   ├── indexing.py
    │   └── policy.py
    ├── bin/
    │   ├── agentos
    │   └── agentos.cmd
    ├── config/
    │   └── governance.json
    ├── docs/
    │   ├── USAGE.md
    │   ├── PROJECT_STRUCTURE.md
    │   └── RULES_WORKFLOW_CHANGELOG.md
    ├── tests/
    │   └── test_agentos.py
    ├── state/
    │   └── agentos.db
    └── runtime/
```

Generated cache folders such as `__pycache__` and `.pytest_cache` may appear after running Python or tests. They are runtime artifacts, not governance source files.

### Component responsibilities

| Component | Responsibility |
|---|---|
| `AGENTS.md` | Sole mandatory instruction source for coding agents |
| `README.md` | Public system overview, installation, workflows, examples, version history |
| `huong_dan.md` | Bilingual developer-oriented operating guide |
| `VERSION` | Release identity |
| `.agents/config/governance.json` | Machine-readable policy and workflow declarations |
| `.agents/agentos/core.py` | Task, approval, write checks, composite preparation, claims, checks, status |
| `.agents/agentos/cli.py` | Stable JSON command interface |
| `.agents/agentos/db.py` | SQLite connection, foreign-key enforcement, migrations |
| `.agents/agentos/indexing.py` | Python symbol index and duplicate candidates |
| `.agents/agentos/policy.py` | Structured policy loading and validation |
| `.agents/docs/USAGE.md` | Focused CLI usage examples |
| `.agents/docs/PROJECT_STRUCTURE.md` | Architectural responsibilities and reading paths |
| `.agents/docs/RULES_WORKFLOW_CHANGELOG.md` | Governance change history |
| `.agents/tests/test_agentos.py` | Executable guarantees |
| `.agents/state/agentos.db` | Local operational and audit state |
| `.agents/runtime/` | Temporary task artifacts when needed |

### Where to start

| Goal | Read or run |
|---|---|
| Understand the project | `README.md` |
| Understand developer usage and architecture | `huong_dan.md` |
| Understand mandatory agent behavior | `AGENTS.md` |
| Inspect structured policies | `.agents/config/governance.json` |
| Learn CLI examples | `.agents/docs/USAGE.md` |
| Review module responsibilities | `.agents/docs/PROJECT_STRUCTURE.md` |
| Review governance history | `.agents/docs/RULES_WORKFLOW_CHANGELOG.md` |
| Verify enforced behavior | `.agents/tests/test_agentos.py` |
| Inspect current health | `.agents/bin/agentos status` |

### Requirements

- Python 3.10 or newer is recommended.
- Runtime code uses the Python standard library.
- Tests require `pytest`.
- Symlink tests may be skipped on systems where symlink creation is not permitted.

Install the test dependency:

```bash
python3 -m pip install pytest
```

No global AgentOS installation is required. The launcher is repository-local.

### Quick start

#### Linux or macOS

```bash
chmod +x .agents/bin/agentos

.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos db-status
.agents/bin/agentos status
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

#### Windows

```bat
.agents\bin\agentos.cmd instruction-check
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd db-status
.agents\bin\agentos.cmd status
set PYTHONPATH=.agents
python -m pytest .agents\tests -q
```

### End-to-end task example

#### 1. Create a task

```bash
.agents/bin/agentos start-task \
  --task-id TASK-001 \
  --request "Change order validation behavior"
```

The original request is preserved in local state.

#### 2. Approve bounded write scopes

```bash
.agents/bin/agentos approve-task \
  --task-id TASK-001 \
  --scope '["src", "tests", "README.md", "huong_dan.md", ".agents"]'
```

Approval does not grant unrestricted filesystem access. Every target is still normalized, resolved, checked against the project root, and compared with approved scopes.

#### 3. Build the Python symbol index

```bash
.agents/bin/agentos index-build src
```

Search it:

```bash
.agents/bin/agentos index-query "OrderService"
.agents/bin/agentos index-query "validate_order" --limit 5
```

Inspect identical AST fingerprints:

```bash
.agents/bin/agentos duplicate-scan
```

Duplicate reports are candidate signals. They identify structurally identical indexed Python symbols, but they do not by themselves prove that two capabilities should be merged.

#### 4. Prepare an existing-file modification

```bash
.agents/bin/agentos prepare-change \
  --task-id TASK-001 \
  --operation modify \
  --target src/orders/service.py \
  --intent "Require approved orders before processing" \
  --symbols '["OrderService", "validate_order"]'
```

The result includes:

- `requested_target`;
- `effective_target`;
- placement metadata;
- similar indexed symbols;
- duplicate candidates associated with the target;
- bounded recommended context;
- write decision;
- blockers;
- overall `ready` state.

#### 5. Prepare a new source file

```bash
.agents/bin/agentos prepare-change \
  --task-id TASK-001 \
  --operation create \
  --target date_converter.py \
  --intent "Convert Excel serial dates" \
  --feature reporting \
  --layer application \
  --file-kind source \
  --symbols '["convert_excel_date"]'
```

A typical resolved target is:

```text
src/reporting/application/date_converter.py
```

For temporary task material, add:

```bash
--temporary
```

Temporary placement is isolated under the AgentOS runtime workspace rather than permanent source locations.

#### 6. Record a tool execution

```bash
.agents/bin/agentos record-tool \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --input '{"path":"src/orders/service.py","lines":"1-180"}' \
  --success \
  --output "Read the validation branch and return behavior" \
  --classification local
```

The command returns a `tool_call_id`. Preserve that ID when the execution supports a later claim.

A failed call can also be recorded by omitting `--success`.

#### 7. Record an evidence-grounded claim

```bash
.agents/bin/agentos record-claim \
  --task-id TASK-001 \
  --claim "Order processing does not currently check the approved flag" \
  --claim-type business_logic \
  --risk high \
  --evidence-call-ids '[1]'
```

AgentOS rejects the claim when required evidence:

- is missing;
- does not exist;
- belongs to another task;
- represents a failed call;
- uses a classification disallowed by policy.

#### 8. Review recorded claims

```bash
.agents/bin/agentos list-claims --task-id TASK-001
.agents/bin/agentos show-claim --claim-id 1
```

`list-claims` shows claim summaries and evidence counts. `show-claim` returns the claim and its linked tool executions for audit and review.

#### 9. Run synchronization checks

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos db-status
.agents/bin/agentos status --task-id TASK-001
```

### Command reference

| Command | Purpose |
|---|---|
| `start-task` | Create or initialize a task from the original request |
| `approve-task` | Record project-relative approved write scopes |
| `index-build` | Build the Python symbol index for a source root |
| `index-query` | Search indexed symbols by name or qualified name |
| `duplicate-scan` | Report symbols with identical AST fingerprints |
| `record-tool` | Store a tool execution for audit and evidence |
| `prepare-change` | Combine placement, symbol search, duplicate signals, context, and write checks |
| `record-claim` | Validate and persist an evidence-grounded claim |
| `list-claims` | List claims and evidence counts for a task |
| `show-claim` | Inspect one claim and its supporting tool calls |
| `docs-check` | Check required docs, bilingual markers, versions, and changelog |
| `instruction-check` | Enforce `AGENTS.md` as the only instruction source |
| `db-status` | Show current and required migration versions |
| `status` | Aggregate instruction, docs, database, task, tool, and claim state |

All commands emit JSON. Runtime errors are returned in a stable error envelope:

```json
{
  "ok": false,
  "error": "RuntimeError",
  "message": "..."
}
```

### Language policy

The active language policy states that AgentOS-compatible agents should:

- understand the user's language directly;
- preserve the original request;
- not call an external translation tool merely to parse intent;
- respond in the user's language;
- keep technical identifiers in English.

Translation tools remain appropriate when translation itself is part of the requested work.

### Filesystem and write containment

AgentOS resolves the real target before comparing it with the project root.

Examples that must be rejected:

```text
../outside.py
../../secrets.txt
/home/user/outside.py
C:\Users\User\Desktop\outside.py
src/link-to-outside.py
src/link-directory/outside.py
```

A symlink is not rejected solely because it is a symlink. A symlink that resolves to a location still inside the project root may be allowed when approval and scope checks also pass.

This distinction guarantees `deny_symlink_escape`, not `deny_all_symlinks`.

### Placement policy

Permanent source should be grouped by feature, layer, and responsibility:

```text
src/<feature>/<layer>/<file>
tests/<feature>/<test-file>
scripts/<script>
```

Temporary task artifacts belong under:

```text
.agents/runtime/task-workspaces/<TASK-ID>/
├── scripts/
├── tests/
└── fixtures/
```

Avoid generic dumping grounds:

```text
misc/
other/
new_folder/
```

Avoid creating monolithic generic modules without a stable capability boundary:

```text
utils.py
helpers.py
common.py
```

Shared code is appropriate only when:

- at least two independent features use it;
- it is not tied to one domain-specific workflow;
- its public contract is stable enough to be shared.

### Python symbol index

The v0.9.0 index supports Python source and records information such as:

- symbol name;
- qualified name;
- symbol kind;
- file path;
- line range;
- signature where available;
- normalized AST fingerprint.

Examples of distinct qualified names:

```text
OrderService.save
ReportService.save
```

The index is used by `index-query`, `duplicate-scan`, and `prepare-change` recommended context.

Current limitations:

- JavaScript and TypeScript are not indexed;
- semantic equivalence is not proven;
- an identical AST fingerprint is a review signal, not an automatic merge decision.

### Evidence-grounded claims

Supported claim types:

```text
business_logic
security
data_behavior
destructive_effect
governance
other
```

Supported risk levels:

```text
low
medium
high
```

Evidence requirements in the default v0.9.0 policy:

| Risk and type | Evidence requirement |
|---|---|
| High, any claim type | At least one valid tool call |
| Medium business logic | At least one valid tool call |
| Medium security | At least one valid tool call |
| Medium data behavior | At least one valid tool call |
| Medium destructive effect | At least one valid tool call |
| Medium governance or other | Optional |
| Low | Optional |

Evidence must be:

- linked to the same task;
- recorded before the claim;
- successful when policy requires success;
- classified as allowed by policy.

The active v0.9.0 policy uses `local` evidence and keeps network evidence disabled.

Claim insertion and claim-evidence insertion occur in one transaction. If any referenced evidence is invalid, the claim is not partially stored.

### Structured policy

The machine-readable policy is stored at:

```text
.agents/config/governance.json
```

Major sections:

```text
version
language_policy
instruction_policy
filesystem_policy
claim_policy
workflows
```

`policy.py` validates required structures and allowed values. Core runtime validation remains necessary even when CLI argument choices already restrict values, because runtime functions may be called directly.

### SQLite state and migrations

Database location:

```text
.agents/state/agentos.db
```

Current schema version:

```text
4
```

Core tables include:

- `schema_migrations`;
- `tasks`;
- `write_audit`;
- `tool_calls`;
- `symbol_index`;
- `claims`;
- `claim_evidence`.

Foreign keys are enabled for every connection. Migration 4 adds or confirms indexes required for efficient claim and evidence lookup.

Check migration state:

```bash
.agents/bin/agentos db-status
```

### Documentation and governance synchronization

A rules or workflow change must evaluate these authoritative layers:

```text
AGENTS.md
.agents/config/governance.json
.agents/agentos/
.agents/tests/
README.md
huong_dan.md
.agents/docs/PROJECT_STRUCTURE.md
.agents/docs/USAGE.md
.agents/docs/RULES_WORKFLOW_CHANGELOG.md
VERSION
```

Each component should be reported as:

```text
updated
unchanged
not_applicable
```

with a reason.

Run:

```bash
.agents/bin/agentos docs-check
```

`docs-check` verifies:

- required documents exist;
- the developer guide contains Vietnamese and English markers;
- `VERSION`, `governance.json`, and package `__version__` agree;
- the changelog contains the current version.

Run:

```bash
.agents/bin/agentos instruction-check
```

`instruction-check` verifies that `AGENTS.md` is present and model-specific instruction files are absent.

### Code documentation contract

AgentOS v0.7.x follows this source-documentation convention:

At file header, declare the path once and describe the module:

```python
"""
File: src/orders/services/order_service.py

Purpose:
    Coordinate order creation and validation.

Responsibilities:
    - Validate application input.
    - Coordinate repositories and domain services.
"""
```

At a public class or function, describe the symbol's contract in its own docstring, including meaningful inputs, outputs, raised errors, and side effects where applicable.

The path is not repeated in every function or class.

### Governance change workflow

For changes to rules or workflow, the declared workflow is:

```text
classify_governance_change
→ identify_authoritative_files
→ assess_compatibility
→ update_instruction
→ update_structured_policy
→ update_runtime
→ update_tests
→ update_bilingual_docs
→ append_changelog
→ bump_version
→ run_checks
→ report_matrix
```

A governance change must not be considered complete merely because prose documentation was updated.

### Version history and evolution

#### v0.5.1 — Documentation and synchronization foundation

The v0.5.1 line established the documentation-oriented foundation reflected in the reference README:

- one instruction authority through `AGENTS.md`;
- bilingual `README.md` and `huong_dan.md`;
- `PROJECT_STRUCTURE.md` and `RULES_WORKFLOW_CHANGELOG.md`;
- documentation synchronization checks;
- governance-change synchronization matrix;
- repository-local CLI and SQLite state.

#### v0.7.0 — Local-first runtime governance

v0.7.0 expanded the system toward runtime-enforced local governance:

- local-first tool policy concepts;
- Python symbol indexing and AST fingerprints;
- duplicate-candidate discovery;
- project-root filesystem containment;
- feature/layer placement rules;
- runtime workspaces for temporary artifacts;
- database migrations;
- source documentation contracts;
- workflow declaration including `prepare_change` and evidence review.

#### v0.7.1 — Governance synchronization and evidence-grounded claims

v0.7.1 closed gaps between documented behavior and runtime implementation:

- implements composite `prepare-change` for create and modify;
- uses a consistent `effective_target` across placement, context, and write checks;
- exposes `record-tool`, `record-claim`, `list-claims`, and `show-claim`;
- validates claim type, risk, task ownership, tool success, and evidence classification;
- requires evidence for high-risk and selected medium-risk claims;
- stores claims and evidence atomically;
- adds machine-readable `claim_policy`;
- adds direct file and directory symlink-escape regression coverage;
- advances the database schema to migration 4;
- synchronizes runtime, policy, tests, bilingual documentation, changelog, and version identity.

#### v0.9.0 — Runtime repair and documentation enforcement patch

v0.9.0 is a focused compatibility patch based on the post-v0.7.1 audit. It does not introduce the heartbeat, persistent workflow checklist, governance drift baseline, installer, or git-hook design reserved for v0.8.x. It repairs the runtime contracts already promised by v0.7.0/v0.7.1:

- restores `tooling.py`, `cache.py`, and `documentation.py` as importable runtime modules;
- keeps `core.record_tool_execution()` as the single canonical writer to `tool_calls`;
- adds migration 5 for `tool_events`, `egress_events`, and `file_read_cache`;
- adds fail-closed `tool-guard`, result audit, and task-scoped `egress-report`;
- adds content-validated `cache-store` and `cache-lookup`;
- exposes `docs-scan --scope ...` through the CLI;
- enforces module `File`, `Purpose`, and `Responsibilities` headers plus public-symbol docstrings;
- adds regression tests for migration 5, tool audit, egress policy, cache invalidation, and documentation scanning;
- advances the release database schema to migration 5.

Pre-merge validation for v0.9.0:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos docs-scan --scope .agents/agentos
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

### Tests

Run:

```bash
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

The v0.9.0 test suite covers:

- task creation and approval;
- approved write scopes;
- path traversal rejection;
- file symlink escape;
- directory symlink escape;
- internal symlink behavior;
- create and modify preparation;
- effective target consistency;
- symbol context and duplicate candidates;
- unknown and cross-task evidence rejection;
- failed and non-local evidence rejection;
- high-risk and sensitive medium-risk evidence requirements;
- low-risk claims without evidence;
- claim type and risk validation;
- evidence deduplication;
- atomic claim insertion;
- claim listing and evidence inspection;
- structured policy validation;
- documentation and version synchronization;
- instruction-source enforcement;
- database migration status.

### Current scope and limitations

Version `v0.9.0` focuses on:

- repository-local Python governance utilities;
- CLI integration;
- SQLite audit state;
- Python source indexing;
- local evidence and claim traceability;
- filesystem and documentation synchronization guarantees.

Not included in this release:

- packaged installer;
- hosted service;
- IDE extension;
- complete MCP server distribution;
- JavaScript or TypeScript symbol indexing;
- semantic duplicate proof;
- automatic snapshot and rollback;
- secret scanning of recorded output summaries;
- network evidence enabled by default;
- distributed or multi-repository state.

### Contributing

Contributions should preserve these principles:

1. `AGENTS.md` remains the sole coding-agent instruction source.
2. New enforced behavior must be reflected in policy, runtime, and tests.
3. Rules and workflow changes must update bilingual documentation and changelog.
4. Version identity must remain synchronized.
5. Temporary artifacts must stay outside persistent source locations.
6. High-risk conclusions must remain traceable to valid evidence.
7. Filesystem operations must remain project-contained and fail closed.

Before merging, run:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos db-status
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

### Security and production note

AgentOS reduces several classes of coding-agent governance risk, but it does not replace:

- operating-system sandboxing;
- source-control protections;
- code review;
- dependency scanning;
- secret management;
- production access controls;
- human approval for high-impact changes.

Review the implementation and policy before using it in security-critical or production automation.

### License

No `LICENSE` file is included in this release. Add an explicit license before public distribution or broad external contribution.

---

## Tiếng Việt

### Vì sao project này được xây dựng?

AI coding agent có thể làm việc rất nhanh, nhưng tốc độ không đi kèm governance local sẽ tạo ra nhiều rủi ro có thể dự đoán. Agent có thể:

- tự suy diễn khi yêu cầu chưa đầy đủ và triển khai sai hành vi;
- sửa file trước khi được phê duyệt hoặc vượt quá phạm vi đã thống nhất;
- tạo source, test, script hoặc artifact tạm ở vị trí thiếu nhất quán;
- tạo lại chức năng đã tồn tại ở nơi khác trong repository;
- lặp lại tool call thất bại mà không thay đổi chiến lược;
- dùng network tool trước khi khai thác hết bằng chứng local;
- kết luận về business logic, bảo mật hoặc dữ liệu nhưng không có bằng chứng truy nguyên được;
- áp dụng instruction khác nhau giữa các model, IDE hoặc integration;
- cập nhật tài liệu nhưng không cập nhật runtime, hoặc cập nhật runtime nhưng bỏ quên test và tài liệu;
- làm instruction, config, version và hành vi thực tế bị drift.

AgentOS Local Governance cung cấp một lớp kiểm soát nằm trực tiếp trong repository để giảm các rủi ro đó. Hệ thống được thiết kế để hoạt động cùng nhiều LLM, coding agent, IDE integration, CLI, local model và remote model.

AgentOS **không phải** là:

- một LLM;
- một autonomous agent framework đa mục đích;
- một cloud service;
- một IDE extension;
- công cụ thay thế source control, code review hoặc phê duyệt của con người.

Vai trò của AgentOS là biến quy tắc project thành nội dung rõ ràng, có cấu trúc khi phù hợp, có runtime enforcement, có test và có audit trail.

### Nguyên tắc thiết kế

#### 1. Một nguồn instruction duy nhất

`AGENTS.md` là nguồn instruction bắt buộc duy nhất dành cho coding agent.

`README.md`, `huong_dan.md` và `.agents/docs/*` dùng để giải thích cho developer, không trở thành nguồn instruction cạnh tranh.

`instruction-check` từ chối các file instruction riêng theo model như:

```text
CLAUDE.md
GEMINI.md
COPILOT.md
CODEX.md
CURSOR.md
```

#### 2. Local-first evidence

Agent nên kiểm tra code local, symbol index local, tool call đã ghi và trạng thái repository trước khi dựa vào network tool.

Trong v0.9.0, evidence-grounded claim mặc định chỉ chấp nhận tool call thành công có classification `local`. Network evidence đang bị tắt trong policy hiện hành.

#### 3. Write fail-closed

Một đường dẫn chỉ được phép ghi khi toàn bộ điều kiện bắt buộc đều đúng:

- task tồn tại;
- task đã được phê duyệt;
- đường dẫn là project-relative hoặc resolve vào trong project root;
- đường dẫn thuộc approved scope;
- không có path traversal;
- symlink không thoát khỏi project root.

#### 4. Structural governance

File mới phải được đặt theo trách nhiệm, feature, layer và lifecycle thay vì đưa vào các thư mục chung chung.

Hệ thống cung cấp symbol index và duplicate candidate để agent kiểm tra khả năng reuse trước khi tạo implementation mới.

#### 5. Kết luận dựa trên bằng chứng

Claim rủi ro cao và một số claim rủi ro trung bình phải tham chiếu tới tool call thành công của cùng task.

Chuỗi truy nguyên:

```text
claim
→ claim_evidence
→ tool_call
→ task
→ approval và execution context
```

#### 6. Đồng bộ governance

Một governance change chưa hoàn chỉnh khi instruction, structured policy, runtime enforcement, test, tài liệu developer, changelog hoặc version identity còn bất đồng đáng kể.

### Chức năng chính trong v0.9.0

- **Một nguồn instruction duy nhất** qua `AGENTS.md`
- **Tạo task và phê duyệt phạm vi ghi có giới hạn**
- **Write containment fail-closed trong project root**
- **Chống path traversal**
- **Chặn symlink file và directory thoát khỏi project**
- **Composite change preparation** cho thao tác create và modify
- **Placement theo feature/layer** cho file source mới
- **Python symbol index** với qualified name và vị trí source
- **Tìm symbol tương tự**
- **Duplicate candidate** bằng Python AST fingerprint
- **Audit tool execution**
- **Evidence-grounded claims** với kiểm tra risk và claim type
- **Ghi claim/evidence trong một transaction**
- **Liệt kê claim và xem evidence chi tiết**
- **SQLite migration và trạng thái schema**
- **Validate policy machine-readable**
- **Tài liệu developer song ngữ**
- **Kiểm tra đồng bộ instruction và documentation**
- **Báo cáo trạng thái tổng hợp**

### Workflow chuẩn

Workflow mặc định đang được khai báo trong `.agents/config/governance.json`:

```text
receive_request
→ assess_requirement_clarity
→ clarify_if_needed
→ approve_task
→ detect_environment
→ build_or_update_local_index
→ prepare_change
→ execute_guarded
→ documentation_check
→ tests
→ evidence_review
→ egress_review
→ structural_review
→ synchronize
→ report
```

CLI v0.9.0 hiện triển khai trực tiếp các phần runtime sau:

```text
start-task
→ approve-task
→ index-build / index-query / duplicate-scan
→ prepare-change
→ record-tool
→ record-claim
→ list-claims / show-claim
→ docs-check / instruction-check / db-status / status
```

Một số stage vẫn là trách nhiệm governance của agent hoặc integration, chưa phải command CLI riêng. Ví dụ: detect environment, execute guarded, chạy test, structural review và report cuối.

### Cấu trúc project

```text
project-root/
├── README.md
├── AGENTS.md
├── huong_dan.md
├── VERSION
├── src/
└── .agents/
    ├── agentos/
    │   ├── __init__.py
    │   ├── cli.py
    │   ├── core.py
    │   ├── db.py
    │   ├── indexing.py
    │   └── policy.py
    ├── bin/
    │   ├── agentos
    │   └── agentos.cmd
    ├── config/
    │   └── governance.json
    ├── docs/
    │   ├── USAGE.md
    │   ├── PROJECT_STRUCTURE.md
    │   └── RULES_WORKFLOW_CHANGELOG.md
    ├── tests/
    │   └── test_agentos.py
    ├── state/
    │   └── agentos.db
    └── runtime/
```

Các folder sinh ra như `__pycache__` và `.pytest_cache` có thể xuất hiện sau khi chạy Python hoặc test. Đây là runtime artifact, không phải governance source.

### Trách nhiệm từng thành phần

| Thành phần | Trách nhiệm |
|---|---|
| `AGENTS.md` | Nguồn instruction bắt buộc duy nhất cho coding agent |
| `README.md` | Tổng quan hệ thống, cài đặt, workflow, ví dụ và lịch sử phiên bản |
| `huong_dan.md` | Hướng dẫn vận hành dành cho developer bằng hai ngôn ngữ |
| `VERSION` | Nhận diện phiên bản phát hành |
| `.agents/config/governance.json` | Policy và workflow machine-readable |
| `.agents/agentos/core.py` | Task, approval, write check, prepare-change, claim, check và status |
| `.agents/agentos/cli.py` | Giao diện command JSON ổn định |
| `.agents/agentos/db.py` | SQLite, foreign key và migrations |
| `.agents/agentos/indexing.py` | Python symbol index và duplicate candidates |
| `.agents/agentos/policy.py` | Load và validate structured policy |
| `.agents/docs/USAGE.md` | Ví dụ CLI tập trung |
| `.agents/docs/PROJECT_STRUCTURE.md` | Kiến trúc, trách nhiệm và đường dẫn đọc |
| `.agents/docs/RULES_WORKFLOW_CHANGELOG.md` | Lịch sử thay đổi governance |
| `.agents/tests/test_agentos.py` | Các guarantee có thể thực thi |
| `.agents/state/agentos.db` | Trạng thái vận hành và audit local |
| `.agents/runtime/` | Artifact tạm theo task khi cần |

### Nên bắt đầu đọc từ đâu?

| Mục tiêu | File hoặc lệnh |
|---|---|
| Hiểu tổng quan project | `README.md` |
| Hiểu cách vận hành và kiến trúc | `huong_dan.md` |
| Hiểu hành vi bắt buộc của agent | `AGENTS.md` |
| Xem policy có cấu trúc | `.agents/config/governance.json` |
| Xem ví dụ CLI | `.agents/docs/USAGE.md` |
| Hiểu trách nhiệm module | `.agents/docs/PROJECT_STRUCTURE.md` |
| Xem lịch sử governance | `.agents/docs/RULES_WORKFLOW_CHANGELOG.md` |
| Kiểm chứng hành vi | `.agents/tests/test_agentos.py` |
| Xem sức khỏe hiện tại | `.agents/bin/agentos status` |

### Yêu cầu môi trường

- Khuyến nghị Python 3.10 trở lên.
- Runtime chỉ dùng Python standard library.
- Test cần `pytest`.
- Symlink test có thể được skip nếu hệ điều hành không cho phép tạo symlink.

Cài test dependency:

```bash
python3 -m pip install pytest
```

Không cần cài AgentOS global. Launcher nằm trực tiếp trong repository.

### Khởi động nhanh

#### Linux hoặc macOS

```bash
chmod +x .agents/bin/agentos

.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos db-status
.agents/bin/agentos status
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

#### Windows

```bat
.agents\bin\agentos.cmd instruction-check
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd db-status
.agents\bin\agentos.cmd status
set PYTHONPATH=.agents
python -m pytest .agents\tests -q
```

### Ví dụ workflow đầy đủ

#### 1. Tạo task

```bash
.agents/bin/agentos start-task \
  --task-id TASK-001 \
  --request "Thay đổi hành vi kiểm tra đơn hàng"
```

Yêu cầu gốc được giữ lại trong state local.

#### 2. Phê duyệt phạm vi ghi

```bash
.agents/bin/agentos approve-task \
  --task-id TASK-001 \
  --scope '["src", "tests", "README.md", "huong_dan.md", ".agents"]'
```

Approval không cấp quyền ghi filesystem không giới hạn. Mọi target vẫn phải normalize, resolve, nằm trong project root và thuộc approved scope.

#### 3. Xây dựng Python symbol index

```bash
.agents/bin/agentos index-build src
```

Tìm kiếm:

```bash
.agents/bin/agentos index-query "OrderService"
.agents/bin/agentos index-query "validate_order" --limit 5
```

Kiểm tra AST fingerprint trùng:

```bash
.agents/bin/agentos duplicate-scan
```

Duplicate report chỉ là candidate signal. Kết quả cho biết các Python symbol có cấu trúc AST giống nhau, nhưng không tự chứng minh rằng chúng phải được merge.

#### 4. Chuẩn bị sửa file hiện có

```bash
.agents/bin/agentos prepare-change \
  --task-id TASK-001 \
  --operation modify \
  --target src/orders/service.py \
  --intent "Yêu cầu đơn hàng phải được duyệt trước khi xử lý" \
  --symbols '["OrderService", "validate_order"]'
```

Kết quả bao gồm:

- `requested_target`;
- `effective_target`;
- metadata placement;
- symbol tương tự;
- duplicate candidate liên quan tới target;
- recommended context có giới hạn;
- write decision;
- blockers;
- trạng thái `ready` tổng hợp.

#### 5. Chuẩn bị tạo file source mới

```bash
.agents/bin/agentos prepare-change \
  --task-id TASK-001 \
  --operation create \
  --target date_converter.py \
  --intent "Chuyển Excel serial date" \
  --feature reporting \
  --layer application \
  --file-kind source \
  --symbols '["convert_excel_date"]'
```

Target điển hình sau resolve:

```text
src/reporting/application/date_converter.py
```

Với artifact tạm theo task, thêm:

```bash
--temporary
```

Artifact tạm được cô lập trong runtime workspace thay vì source location lâu dài.

#### 6. Ghi nhận tool execution

```bash
.agents/bin/agentos record-tool \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --input '{"path":"src/orders/service.py","lines":"1-180"}' \
  --success \
  --output "Đã đọc validation branch và return behavior" \
  --classification local
```

Command trả về `tool_call_id`. Cần giữ ID này khi tool call là bằng chứng cho claim sau đó.

Muốn ghi tool call thất bại, bỏ cờ `--success`.

#### 7. Ghi evidence-grounded claim

```bash
.agents/bin/agentos record-claim \
  --task-id TASK-001 \
  --claim "Order processing hiện chưa kiểm tra approved flag" \
  --claim-type business_logic \
  --risk high \
  --evidence-call-ids '[1]'
```

AgentOS từ chối claim khi evidence bắt buộc:

- bị thiếu;
- không tồn tại;
- thuộc task khác;
- là tool call thất bại;
- có classification không được policy cho phép.

#### 8. Review claim

```bash
.agents/bin/agentos list-claims --task-id TASK-001
.agents/bin/agentos show-claim --claim-id 1
```

`list-claims` hiển thị claim và số evidence. `show-claim` trả về claim cùng các tool execution đã liên kết để audit.

#### 9. Chạy kiểm tra đồng bộ

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos db-status
.agents/bin/agentos status --task-id TASK-001
```

### Tham chiếu command

| Command | Mục đích |
|---|---|
| `start-task` | Tạo hoặc khởi tạo task từ yêu cầu gốc |
| `approve-task` | Ghi approved write scopes dạng project-relative |
| `index-build` | Xây Python symbol index cho source root |
| `index-query` | Tìm symbol theo tên hoặc qualified name |
| `duplicate-scan` | Báo các symbol có AST fingerprint giống nhau |
| `record-tool` | Lưu tool execution để audit và làm evidence |
| `prepare-change` | Gộp placement, symbol search, duplicate signal, context và write check |
| `record-claim` | Validate và lưu evidence-grounded claim |
| `list-claims` | Liệt kê claim và số evidence của task |
| `show-claim` | Xem một claim và tool call hỗ trợ |
| `docs-check` | Kiểm tra tài liệu, song ngữ, version và changelog |
| `instruction-check` | Đảm bảo `AGENTS.md` là instruction source duy nhất |
| `db-status` | Hiển thị migration hiện tại và migration yêu cầu |
| `status` | Tổng hợp trạng thái instruction, docs, database, task, tool và claim |

Mọi command trả JSON. Runtime error sử dụng envelope ổn định:

```json
{
  "ok": false,
  "error": "RuntimeError",
  "message": "..."
}
```

### Chính sách ngôn ngữ

Language policy hiện hành quy định agent tương thích AgentOS phải:

- hiểu trực tiếp ngôn ngữ của người dùng;
- giữ nguyên yêu cầu gốc;
- không gọi tool dịch bên ngoài chỉ để parse intent;
- phản hồi bằng ngôn ngữ của người dùng;
- giữ technical identifier bằng tiếng Anh.

Tool dịch vẫn phù hợp khi dịch thuật chính là nội dung task.

### Filesystem và write containment

AgentOS resolve target thực trước khi so sánh với project root.

Ví dụ phải bị từ chối:

```text
../outside.py
../../secrets.txt
/home/user/outside.py
C:\Users\User\Desktop\outside.py
src/link-to-outside.py
src/link-directory/outside.py
```

Symlink không bị từ chối chỉ vì nó là symlink. Symlink resolve tới vị trí vẫn nằm trong project root có thể được cho phép khi approval và scope đều hợp lệ.

Điều này đảm bảo `deny_symlink_escape`, không phải `deny_all_symlinks`.

### Chính sách placement

Source lâu dài nên được tổ chức theo feature, layer và responsibility:

```text
src/<feature>/<layer>/<file>
tests/<feature>/<test-file>
scripts/<script>
```

Artifact tạm theo task thuộc:

```text
.agents/runtime/task-workspaces/<TASK-ID>/
├── scripts/
├── tests/
└── fixtures/
```

Tránh các dumping ground chung chung:

```text
misc/
other/
new_folder/
```

Tránh tạo module generic đơn khối khi chưa có capability boundary ổn định:

```text
utils.py
helpers.py
common.py
```

Chỉ đưa code vào shared khi:

- có ít nhất hai feature độc lập sử dụng;
- không gắn chặt với một domain workflow;
- public contract đủ ổn định để dùng chung.

### Python symbol index

Index v0.9.0 hỗ trợ Python và ghi nhận:

- symbol name;
- qualified name;
- symbol kind;
- file path;
- line range;
- signature khi có;
- normalized AST fingerprint.

Ví dụ qualified name không collision:

```text
OrderService.save
ReportService.save
```

Index được dùng bởi `index-query`, `duplicate-scan` và recommended context của `prepare-change`.

Giới hạn hiện tại:

- chưa index JavaScript và TypeScript;
- chưa chứng minh semantic equivalence;
- AST fingerprint giống nhau chỉ là tín hiệu review, không phải quyết định merge tự động.

### Evidence-grounded claims

Claim type được hỗ trợ:

```text
business_logic
security
data_behavior
destructive_effect
governance
other
```

Risk level:

```text
low
medium
high
```

Yêu cầu evidence mặc định trong v0.9.0:

| Risk và loại claim | Yêu cầu evidence |
|---|---|
| High, mọi claim type | Ít nhất một tool call hợp lệ |
| Medium business logic | Ít nhất một tool call hợp lệ |
| Medium security | Ít nhất một tool call hợp lệ |
| Medium data behavior | Ít nhất một tool call hợp lệ |
| Medium destructive effect | Ít nhất một tool call hợp lệ |
| Medium governance hoặc other | Không bắt buộc |
| Low | Không bắt buộc |

Evidence phải:

- thuộc cùng task;
- được ghi trước claim;
- thành công khi policy yêu cầu;
- có classification được policy cho phép.

Policy v0.9.0 chỉ dùng evidence `local` và chưa cho phép network evidence.

Claim và claim evidence được insert trong cùng transaction. Nếu bất kỳ evidence nào không hợp lệ, claim không bị lưu dang dở.

### Structured policy

Policy machine-readable nằm tại:

```text
.agents/config/governance.json
```

Các phần chính:

```text
version
language_policy
instruction_policy
filesystem_policy
claim_policy
workflows
```

`policy.py` kiểm tra cấu trúc bắt buộc và allowed values. Runtime core vẫn phải validate độc lập dù CLI đã giới hạn choices, vì các hàm core có thể được gọi trực tiếp.

### SQLite state và migrations

Database:

```text
.agents/state/agentos.db
```

Schema version hiện tại:

```text
4
```

Các bảng chính:

- `schema_migrations`;
- `tasks`;
- `write_audit`;
- `tool_calls`;
- `symbol_index`;
- `claims`;
- `claim_evidence`.

Foreign key được bật cho mọi connection. Migration 4 thêm hoặc xác nhận index cần thiết cho claim/evidence lookup.

Kiểm tra migration:

```bash
.agents/bin/agentos db-status
```

### Đồng bộ tài liệu và governance

Một thay đổi rule hoặc workflow phải đánh giá các layer sau:

```text
AGENTS.md
.agents/config/governance.json
.agents/agentos/
.agents/tests/
README.md
huong_dan.md
.agents/docs/PROJECT_STRUCTURE.md
.agents/docs/USAGE.md
.agents/docs/RULES_WORKFLOW_CHANGELOG.md
VERSION
```

Mỗi thành phần cần được báo là:

```text
updated
unchanged
not_applicable
```

kèm lý do.

Chạy:

```bash
.agents/bin/agentos docs-check
```

`docs-check` kiểm tra:

- tài liệu bắt buộc có tồn tại;
- hướng dẫn developer có marker tiếng Việt và tiếng Anh;
- `VERSION`, `governance.json` và package `__version__` đồng nhất;
- changelog có entry cho version hiện tại.

Chạy:

```bash
.agents/bin/agentos instruction-check
```

`instruction-check` kiểm tra `AGENTS.md` tồn tại và không có model-specific instruction file.

### Contract comment và docstring

AgentOS v0.7.x dùng quy ước documentation source sau:

Tại file header, khai báo path một lần và mô tả module:

```python
"""
File: src/orders/services/order_service.py

Purpose:
    Coordinate order creation and validation.

Responsibilities:
    - Validate application input.
    - Coordinate repositories and domain services.
"""
```

Tại public class hoặc function, mô tả contract của chính symbol trong docstring, gồm input, output, error và side effect có ý nghĩa khi phù hợp.

Không lặp lại đường dẫn file trong từng function hoặc class.

### Workflow governance change

Workflow khai báo cho thay đổi rule hoặc workflow:

```text
classify_governance_change
→ identify_authoritative_files
→ assess_compatibility
→ update_instruction
→ update_structured_policy
→ update_runtime
→ update_tests
→ update_bilingual_docs
→ append_changelog
→ bump_version
→ run_checks
→ report_matrix
```

Không được xem governance change là hoàn thành chỉ vì prose documentation đã được sửa.

### Lịch sử và quá trình nâng cấp

#### v0.5.1 — Nền tảng tài liệu và synchronization

Dòng v0.5.1 thiết lập nền tảng documentation được phản ánh trong README mẫu:

- một instruction authority qua `AGENTS.md`;
- `README.md` và `huong_dan.md` song ngữ;
- `PROJECT_STRUCTURE.md` và `RULES_WORKFLOW_CHANGELOG.md`;
- documentation synchronization checks;
- synchronization matrix cho governance change;
- CLI và SQLite state nằm trong repository.

#### v0.7.0 — Local-first runtime governance

v0.7.0 mở rộng hệ thống theo hướng runtime-enforced local governance:

- khái niệm local-first tool policy;
- Python symbol index và AST fingerprint;
- duplicate candidate discovery;
- project-root filesystem containment;
- placement theo feature/layer;
- runtime workspace cho artifact tạm;
- database migrations;
- contract documentation cho source;
- workflow có `prepare_change` và evidence review.

#### v0.7.1 — Governance synchronization và evidence-grounded claims

v0.7.1 đóng khoảng trống giữa hành vi đã tài liệu hóa và implementation runtime:

- triển khai composite `prepare-change` cho create và modify;
- dùng `effective_target` nhất quán cho placement, context và write check;
- expose `record-tool`, `record-claim`, `list-claims` và `show-claim`;
- validate claim type, risk, task ownership, tool success và evidence classification;
- bắt buộc evidence cho high-risk và một số medium-risk claim;
- ghi claim/evidence atomically;
- thêm `claim_policy` machine-readable;
- thêm regression coverage trực tiếp cho symlink file và directory thoát root;
- nâng database schema lên migration 4;
- đồng bộ runtime, policy, tests, tài liệu song ngữ, changelog và version identity.

#### v0.9.0 — Bản vá runtime và enforcement tài liệu source

v0.9.0 là patch tương thích tập trung theo báo cáo audit sau v0.7.1. Phiên bản này chưa đưa heartbeat, workflow checklist bền vững, governance drift baseline, installer hoặc git hook của lộ trình v0.8.x vào runtime. Bản vá sửa các contract đã được công bố từ v0.7.0/v0.7.1:

- phục hồi `tooling.py`, `cache.py` và `documentation.py` thành các runtime module có thể import;
- giữ `core.record_tool_execution()` là nơi duy nhất ghi vào `tool_calls`;
- thêm migration 5 cho `tool_events`, `egress_events` và `file_read_cache`;
- thêm `tool-guard` fail-closed, audit kết quả và `egress-report` theo task;
- thêm `cache-store` và `cache-lookup` có kiểm tra content identity;
- expose `docs-scan --scope ...` qua CLI;
- enforce header `File`, `Purpose`, `Responsibilities` và docstring cho public symbol;
- thêm regression test cho migration 5, tool audit, egress policy, cache invalidation và documentation scan;
- nâng schema phát hành lên migration 5.

Kiểm tra pre-merge cho v0.9.0:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos docs-scan --scope .agents/agentos
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

### Kiểm thử

Chạy:

```bash
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

Test suite v0.9.0 bao phủ:

- tạo task và approval;
- approved write scope;
- từ chối path traversal;
- symlink file escape;
- symlink directory escape;
- hành vi symlink nội bộ;
- prepare create và modify;
- effective target nhất quán;
- symbol context và duplicate candidates;
- từ chối unknown evidence và cross-task evidence;
- từ chối failed/non-local evidence;
- yêu cầu evidence cho high-risk và sensitive medium-risk;
- low-risk claim không evidence;
- validate claim type và risk;
- deduplicate evidence ID;
- atomic claim insertion;
- list claim và inspect evidence;
- validate structured policy;
- đồng bộ documentation và version;
- single instruction source;
- database migration status.

### Phạm vi và giới hạn hiện tại

Phiên bản `v0.9.0` tập trung vào:

- governance utility Python nằm trong repository;
- tích hợp qua CLI;
- SQLite audit state;
- Python source index;
- local evidence và claim traceability;
- filesystem containment;
- documentation synchronization.

Chưa có trong phiên bản này:

- packaged installer;
- hosted service;
- IDE extension;
- complete MCP server distribution;
- JavaScript/TypeScript symbol index;
- semantic duplicate proof;
- snapshot và rollback tự động;
- secret scanning cho output summary đã ghi;
- network evidence bật mặc định;
- distributed hoặc multi-repository state.

### Đóng góp

Contribution cần giữ các nguyên tắc:

1. `AGENTS.md` tiếp tục là coding-agent instruction source duy nhất.
2. Enforcement mới phải được phản ánh trong policy, runtime và tests.
3. Thay đổi rule hoặc workflow phải cập nhật tài liệu song ngữ và changelog.
4. Version identity phải đồng nhất.
5. Artifact tạm không được đưa vào source location lâu dài.
6. Kết luận rủi ro cao phải truy nguyên được về evidence hợp lệ.
7. Filesystem operation phải nằm trong project và fail closed.

Trước khi merge, chạy:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos db-status
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

### Lưu ý bảo mật và production

AgentOS giảm một số nhóm rủi ro governance khi coding agent làm việc, nhưng không thay thế:

- OS sandbox;
- source-control protection;
- code review;
- dependency scanning;
- secret management;
- production access control;
- phê duyệt của con người cho thay đổi tác động cao.

Cần review implementation và policy trước khi dùng cho automation production hoặc môi trường yêu cầu bảo mật cao.

### Giấy phép

Phiên bản này chưa có file `LICENSE`. Cần bổ sung giấy phép rõ ràng trước khi public distribution hoặc mời đóng góp rộng rãi.

---

## Project status

AgentOS Local Governance is under active development. Version `v0.9.0` is suitable for evaluation, experimentation, and repository-local integration. Review the policy and implementation before security-critical or production use.

AgentOS Local Governance đang được phát triển tích cực. Phiên bản `v0.9.0` phù hợp để đánh giá, thử nghiệm và tích hợp local trong repository. Cần review policy và implementation trước khi dùng trong production hoặc môi trường bảo mật cao.


---

## v0.9.0 runtime repair command reference / Tham chiếu lệnh sửa runtime v0.9.0

### Source documentation enforcement

```bash
.agents/bin/agentos docs-scan --scope src
.agents/bin/agentos docs-scan --scope .agents/agentos
```

A failed scan returns `status: failed`, `ok: false`, and deterministic findings such as `missing_file_header`, `invalid_file_path_header`, `missing_module_purpose`, `missing_module_responsibilities`, and `missing_symbol_docstring`.

Scan thất bại trả `status: failed`, `ok: false` và danh sách finding xác định như `missing_file_header`, `invalid_file_path_header`, `missing_module_purpose`, `missing_module_responsibilities`, `missing_symbol_docstring`.

### Local-first tool guard and egress audit

```bash
.agents/bin/agentos tool-guard --task-id TASK-001 --tool bounded_file_read --args '{"path":"src/a.py"}'
.agents/bin/agentos tool-guard --task-id TASK-001 --tool web --args '{"query":"..."}' --reason-code research --justification "Current external evidence is required" --target example.org
.agents/bin/agentos record-tool-result --task-id TASK-001 --tool web --args '{"query":"..."}' --success
.agents/bin/agentos egress-report --task-id TASK-001
```

Unknown tools fail closed. Network tools require a reason, justification, and at least one prior successful local tool call for the same task. `tooling.py` only records guard/audit events; canonical evidence records remain in `core.record_tool_execution()` through `record-tool`.

Tool không đăng ký bị chặn fail-closed. Network tool cần reason, justification và ít nhất một local tool call thành công trước đó trong cùng task. `tooling.py` chỉ ghi guard/audit event; evidence chuẩn trong `tool_calls` vẫn do `core.record_tool_execution()` qua lệnh `record-tool` quản lý.

### File-read cache

```bash
.agents/bin/agentos cache-store --task-id TASK-001 --path src/a.py --range-key 1:160 --summary "Relevant implementation summary"
.agents/bin/agentos cache-lookup --task-id TASK-001 --path src/a.py --range-key 1:160
```

A cache hit requires matching task ID, normalized project-relative path, range key, modification time, size, and SHA-256 content hash. Changed files invalidate and remove stale entries.

Cache chỉ hit khi task ID, path chuẩn hóa, range key, thời gian sửa, kích thước và SHA-256 content hash còn khớp. File thay đổi làm entry cũ bị vô hiệu và xóa.

---

# v0.9.0 — Persistent workflow, drift awareness, and safe installation

Version 0.9.0 completes the v0.8 proposal on top of the v0.7.2 runtime repair. Its central change is that workflow state no longer depends on an LLM remembering the conversation. Required progress is persisted in SQLite and the current task is stored under `.agents/runtime/current_task.json`.

## New persistent task commands

```bash
.agents/bin/agentos start-task --task-id TASK-042 --request "Change order validation"
.agents/bin/agentos use-task --task-id TASK-042
.agents/bin/agentos whoami
.agents/bin/agentos next-step
```

`start-task` now performs three actions atomically from the user's perspective:

1. creates the task record;
2. seeds all configured workflow steps;
3. selects the task as the current local task.

Commands accepting a task can omit `--task-id`; AgentOS resolves the current task. Every normal CLI response is wrapped with a `context_reminder` containing the active task, original request, approval scope, workflow progress, next pending step, and governance drift count.

## Persistent workflow checklist

Migration 6 adds `workflow_steps`. Existing commands automatically mark their corresponding steps after successful execution. Manual steps can be recorded explicitly:

```bash
.agents/bin/agentos mark-step \
  --step structural_review \
  --status done \
  --note "Reviewed placement and duplicate candidates."

.agents/bin/agentos mark-step \
  --step egress_review \
  --status skipped \
  --note "No network calls were made."
```

A skipped step without a note is rejected. Inspect progress with:

```bash
.agents/bin/agentos workflow-status
```

Run tests through the governance wrapper so the `tests` step can be recorded:

```bash
.agents/bin/agentos run-tests --path .agents/tests
```

Run instruction and documentation synchronization together:

```bash
.agents/bin/agentos sync-check
```

The final gate is:

```bash
.agents/bin/agentos report
```

It exits with code `2` and lists pending steps until the workflow is complete.

## Governance drift detection

Migration 7 adds `governance_baseline` and `governance_change_log`. AgentOS tracks:

- `AGENTS.md`;
- `.agents/config/governance.json`;
- `.agents/config/governance.local.json` when present;
- `VERSION`;
- every Python module under `.agents/agentos/`.

Create the first reviewed baseline manually:

```bash
.agents/bin/agentos ack-baseline --acknowledged-by human
```

A coding agent must not run this command on behalf of the user. Review changes with:

```bash
.agents/bin/agentos drift-check
.agents/bin/agentos drift-diff --file AGENTS.md
```

`status`, `whoami`, and normal CLI responses expose the number of unacknowledged governance changes. Drift detection reports that content changed; it does not decide whether the change is correct.

## Safe installation

Linux and macOS:

```bash
/path/to/agentos/.agents/bin/install.sh /path/to/existing-project
```

Windows:

```bat
C:\path\to\agentos\.agents\bin\install.cmd
```

The installer copies the private `.agents/` namespace and never overwrites existing root files. When `AGENTS.md`, `README.md`, `huong_dan.md`, or `VERSION` already exists, the AgentOS version is written using an `.agentos` suffix for manual merge. The first installation runs instruction, documentation, and database checks, then creates an installer baseline.

For a non-standard source root:

```bash
SOURCE_ROOT=app .agents/bin/install.sh /path/to/project
```

This creates `.agents/config/governance.local.json` rather than editing the distributed policy.

## Local policy override

`governance.local.json` overlays project-specific values. Nested policy sections are merged one level so a small override does not remove unrelated mandatory fields:

```json
{
  "source_root": "app",
  "claim_policy": {
    "allow_network_evidence": true
  }
}
```

Local overrides are tracked by drift detection.

## Optional git gate

Install the supplied pre-commit hook:

```bash
.agents/bin/install-git-hooks.sh
```

The hook runs:

```text
instruction-check
→ docs-check
→ docs-scan
→ drift-check
→ AgentOS tests
```

The hook is an additional defense layer, not an operating-system sandbox. Direct writes outside AgentOS remain possible; review, drift detection, Git policy, and human approval remain necessary.

## Database schema v7

| Migration | Tables | Purpose |
|---|---|---|
| 5 | `tool_events`, `egress_events`, `file_read_cache` | Tool governance and cache repair |
| 6 | `workflow_steps` | Persistent workflow checklist |
| 7 | `governance_baseline`, `governance_change_log` | Human-visible governance drift |

## v0.9.0 validation checklist

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos docs-scan --scope .agents/agentos
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
.agents/bin/agentos db-status
```

Expected release state:

```text
version: 0.9.0
schema: 7
38 tests passed
instruction-check: ok

docs-check: ok

docs-scan: passed
```

---

# v0.9.0 — Workflow bền vững, cảnh báo drift và cài đặt an toàn

Phiên bản 0.9.0 hoàn thiện đề xuất v0.8 trên nền bản vá v0.7.2. Thay đổi trọng tâm là trạng thái workflow không còn phụ thuộc vào việc LLM nhớ nội dung hội thoại. Tiến trình bắt buộc được lưu trong SQLite và task hiện tại được lưu tại `.agents/runtime/current_task.json`.

## Lệnh task mới

```bash
.agents/bin/agentos start-task --task-id TASK-042 --request "Thay đổi validation đơn hàng"
.agents/bin/agentos use-task --task-id TASK-042
.agents/bin/agentos whoami
.agents/bin/agentos next-step
```

Mỗi phản hồi CLI thông thường có `context_reminder`, gồm task hiện tại, yêu cầu gốc, trạng thái approval, phạm vi được duyệt, tiến độ workflow, bước tiếp theo và số thay đổi governance chưa được xác nhận.

## Checklist workflow bắt buộc

Migration 6 bổ sung bảng `workflow_steps`. Các lệnh thành công tự đánh dấu step tương ứng. Step thủ công dùng `mark-step`. Khi bỏ qua, `--note` là bắt buộc. Lệnh `report` chặn fail-closed và trả exit code `2` nếu còn step bắt buộc chưa hoàn thành.

## Phát hiện thay đổi governance

Migration 7 bổ sung baseline hash và change log. Người dùng tạo mốc đã review bằng `ack-baseline`; agent không được tự gọi lệnh này thay người dùng. `drift-check` phát hiện thay đổi chưa xác nhận, còn `drift-diff` hỗ trợ review nội dung cụ thể.

## Cài đặt không ghi đè

`install.sh` và `install.cmd` không ghi đè các file root đã có. File AgentOS xung đột được ghi với hậu tố `.agentos` để merge thủ công. Source root hoặc policy riêng của project được lưu trong `governance.local.json`.

## Git hook tùy chọn

`install-git-hooks.sh` cài pre-commit gate để chạy instruction check, docs check, source documentation scan, drift check và test. Đây là lớp phòng thủ bổ sung; AgentOS không phải sandbox hệ điều hành.

---

## v0.9.0 — Trust Boundary Hardening

Version 0.9.0 changes AgentOS from a purely self-attested audit flow toward a
linked execution lifecycle. Tool evidence can no longer be created by choosing a
classification in `record-tool`. The canonical flow is now:

```text
guard-tool → single-use execution token → actual execution → complete-tool → tool_calls evidence
```

The token is bound to task, session, tool name, derived classification, normalized
argument hash, expiry, and one-time use. Unknown and dynamic tools fail closed.
Audit inputs and summaries are redacted before persistence.

Automated workflow steps such as `tests`, `documentation_check`, `synchronize`,
`prepare_change`, and `execute_guarded` cannot be marked done manually. Their
rows contain command provenance, result hash, evidence type, evidence ID, and exit
code. The final `report` gate verifies workflow provenance, baseline state,
unacknowledged drift, and sensitive local-override approval.

Current task state is now session-scoped under:

```text
.agents/runtime/sessions/<session-id>/current_task.json
```

Set `AGENTOS_SESSION_ID` or pass global `--session-id` when multiple agents or IDE
sessions operate in one repository.

Sensitive `governance.local.json` sections are staged until explicitly approved.
Safe project settings such as `source_root` may apply immediately; policy sections
such as `claim_policy`, `filesystem_policy`, and `workflow_policy` do not.

```bash
agentos local-override-status
agentos approve-local-override --reviewed-by USER --note "Reviewed project policy"
```

The installer no longer acknowledges the governance baseline. After installation,
a human reviews the governance files and runs `ack-baseline` interactively.
Non-interactive acknowledgement is labeled `ci_machine`, never `interactive_human`.
