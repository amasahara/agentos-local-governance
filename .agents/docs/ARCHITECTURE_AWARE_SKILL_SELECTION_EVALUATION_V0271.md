# AgentOS v0.27.1 — Architecture-Aware Skill Selection & Evaluation

**Release:** v0.27.1 — Architecture-Aware Skill Selection & Evaluation
**Database schema:** **59**

## Mục tiêu / Goal

v0.27.1 nối Governed Skill Contract v2 vào active architecture-aware task plan bằng một bộ chọn deterministic và advisory. AgentOS có thể đề xuất skill phù hợp, nhưng recommendation không tạo execution authority.

v0.27.1 connects Governed Skill Contract v2 to the active architecture-aware task plan through deterministic advisory matching. A recommendation never grants execution authority.

```text
User Request
    ↓
Requirement Ledger / Active Plan
    ↓
Architecture Baseline + affected sections
    ↓
Governed Skill Contract v2 candidates
    ↓
Least-authority compatibility gates
    ↓
Deterministic local ranking
    ↓
ADVISORY RECOMMENDATION
    ↓
Existing AgentOS capability / tool / write / test gates
    ↓
AI Worker
```

## Selection eligibility

Chỉ skill thỏa toàn bộ điều kiện sau mới eligible:

- lifecycle `graduated`;
- Contract v2, không phải `legacy_v1`;
- contract validation status `valid` và không stale;
- active task plan hiện hành;
- architecture baseline pin hiện hành;
- `required_architecture_sections` nằm trong affected sections của plan;
- tất cả planned write targets nằm trong `allowed_write_scope`;
- required capabilities nằm trong effective governed capability inventory;
- required tools có trong explicit available-tool inventory;
- planned dependencies/external services không vượt contract allowlist;
- required test suites được plan khai báo.

Only graduated, current Contract-v2 skills that fit the active plan and least-authority boundaries can be eligible.

## Ranking

Ranking là local/deterministic, không dùng LLM, embedding, network hay provider discovery. Score hiện dùng evidence có thể tái tạo:

```text
lexical relevance
+ architecture overlap
+ write-scope coverage
+ required-test overlap
```

Raw user request không được copy vào selection tables. Selection state chỉ lưu hash, counts, blocker codes, contract hash và architecture/plan pins.

## Capability boundary

Caller-provided capability inventory chỉ được **thu hẹp** capability policy của AgentOS:

```text
Effective capabilities
=
Governed proxy capabilities
∩
Caller availability inventory (if supplied)
```

Caller input không thể tạo capability authority mới.

Required tools được coi là availability evidence cho selection; actual execution vẫn phải đi qua AgentOS tool/capability gates.

## Explicit, not automatic

`skill-selection-run` là explicit analysis command. v0.27.1 không tự attach skill vào plan và không tự execute skill.

```text
selection result
≠ plan approval
≠ capability grant
≠ skill execution
≠ architecture approval
```

## Evaluation

Evaluation dùng outcome đã tồn tại của task:

- task outcome;
- test pass rate;
- rework count;
- current plan/baseline pin;
- current skill contract status.

Classification:

```text
positive
mixed
negative
stale_context
```

Evaluation là observational. Nó không:

- mutate skill lifecycle;
- auto-graduate hoặc auto-revoke;
- đổi contract;
- đổi future ranking weights;
- sửa Architecture Contract;
- chọn model/provider.

## Schema 59

Bổ sung:

```text
skill_selection_runs
skill_selection_candidates
skill_evaluation_runs
```

State không lưu raw request hoặc raw outcome note.

## CLI

```bash
agentos skill-selection-run --task-id T-123
agentos skill-selection-run --task-id T-123 --available-tools '["pytest"]'
agentos skill-selection-status --task-id T-123
agentos skill-selection-candidates --run-id 1
agentos skill-evaluation-run --selection-run-id 1
```

## MCP read-only

```text
agentos.skill_selection_status_get
agentos.skill_selection_candidates_get
agentos.skill_evaluation_get
```

MCP không có selection-run, evaluation-run, execution, approval, graduation, revocation hoặc mutation tool.

## Human authority invariants

```text
AI cannot approve architecture.
AI cannot approve or graduate a skill.
Selection cannot grant capabilities.
Selection cannot expand write scope.
Selection cannot alter the active plan.
Evaluation cannot change skill lifecycle.
Evaluation cannot tune future rankings automatically.
Model/provider selection authority remains external to AgentOS.
```

## Distribution

v0.27.1 tiếp tục **Latest Full Release** model. Project-owned user skills, workflows, source, architecture working copy, `governance.local.json`, `.agents/state/**` và `.agents/runtime/**` không thuộc managed release payload.

See [Install Latest Release](INSTALL_LATEST_RELEASE.md).
