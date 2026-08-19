# AgentOS Local Governance v0.27.1 — Architecture-Aware Skill Selection & Evaluation

## 🇻🇳 Tiếng Việt

v0.27.1 nối **Governed Skill Contract v2** với active architecture-aware task plan và bổ sung một bộ chọn skill deterministic, local, least-authority cùng lớp evaluation observational.

### Điểm chính

- Schema **58 → 59**.
- Chỉ `graduated` Contract v2 đang `valid` mới được selection xem xét.
- `legacy_v1`, stale/invalid contracts và architecture mismatch bị loại fail-closed.
- Selection kiểm tra:
  - affected architecture sections;
  - `allowed_write_scope` với toàn bộ planned write targets;
  - required capabilities;
  - required tools;
  - allowed dependencies;
  - allowed external services;
  - required test suites.
- Caller capability inventory chỉ có thể thu hẹp governed proxy capability policy, không thể tạo authority mới.
- Ranking deterministic/local; không dùng LLM, embedding, network hoặc model/provider discovery.
- Raw user request không được copy vào selection state; chỉ hash/counts/evidence metadata được lưu.
- Selection là **advisory only**: không sửa plan, không execute skill, không cấp capability, không approve architecture.
- Evaluation dùng existing `task_outcomes` và phân loại `positive / mixed / negative / stale_context`.
- Evaluation không auto-graduate, auto-revoke, sửa contract hoặc tự thay future ranking weights.
- Model/provider selection authority vẫn ở external runtime.

### Schema 59

```text
skill_selection_runs
skill_selection_candidates
skill_evaluation_runs
```

### CLI mới

```text
skill-selection-run
skill-selection-status
skill-selection-candidates
skill-evaluation-run
```

### MCP read-only mới

```text
agentos.skill_selection_status_get
agentos.skill_selection_candidates_get
agentos.skill_evaluation_get
```

Không có MCP tool để chạy selection/evaluation, execute skill, mutate contract, approve, graduate hoặc revoke.

### Distribution

v0.27.1 tiếp tục **Latest Full Release** model với **no updater script**. Project-owned user skills, workflows, source, architecture working copy, `governance.local.json`, `.agents/state/**` và `.agents/runtime/**` được giữ ngoài managed release partition.

---

## 🇬🇧 English

v0.27.1 connects **Governed Skill Contract v2** to the active architecture-aware task plan and introduces deterministic local least-authority skill recommendation plus observational evaluation.

### Highlights

- Schema **58 → 59**.
- Only current `graduated` Contract-v2 skills are considered.
- Legacy-v1, stale/invalid contracts, and architecture mismatches fail closed.
- Selection validates architecture sections, write scope, capabilities, tools, dependencies, external services, and required test suites.
- Caller capability inventory can only narrow governed proxy capabilities; it cannot create authority.
- Ranking is deterministic/local and uses no LLM, embedding, network, or model/provider discovery.
- Raw user requests are not duplicated into selection state; only hashes, counts, blocker codes, and integrity pins are persisted.
- Selection is advisory only and cannot mutate the active plan, execute a skill, grant a capability, or approve architecture.
- Evaluation observes existing task outcomes and classifies results as `positive`, `mixed`, `negative`, or `stale_context`.
- Evaluation cannot graduate/revoke skills, mutate contracts, or automatically alter future ranking weights.
- Model/provider selection authority remains external to AgentOS.

### Schema 59

```text
skill_selection_runs
skill_selection_candidates
skill_evaluation_runs
```

### New CLI

```text
skill-selection-run
skill-selection-status
skill-selection-candidates
skill-evaluation-run
```

### New read-only MCP tools

```text
agentos.skill_selection_status_get
agentos.skill_selection_candidates_get
agentos.skill_evaluation_get
```

No MCP mutation, selection execution, evaluation persistence, skill execution, approval, graduation, or revocation authority is added.

### Distribution

v0.27.1 continues the **Latest Full Release** model with **no updater script**. Project-owned skills, workflows, source, architecture working copies, local governance overrides, state, and runtime data remain outside the managed release partition.
