# AgentOS Local Governance v0.27.0 — Governed Skill Contract v2

## Tiếng Việt

v0.27.0 nâng subsystem skill hiện hữu thành **Governed Skill Contract v2** mà không tạo skill framework mới.

### Thay đổi chính

- Schema **57 → 58**.
- New candidate skill mặc định dùng Contract v2 least-authority.
- Contract khai rõ input/output, required architecture sections, capabilities, tools, read/write scopes, dependencies, external services, pre/postconditions, risk tier, test contract và architecture constraints.
- Contract được canonicalize và SHA-256 hash deterministic.
- Skill architecture-sensitive cần ACTIVE human-approved Architecture Baseline; validation pin exact baseline hash.
- Existing v1 skills giữ nguyên `legacy_v1`; không rewrite approved artifact in-place.
- `skill-graduate` vẫn human-only và giờ yêu cầu v2 contract valid/current.
- `skill-revoke` vẫn human-only.
- `skill-match` vẫn lexical/deterministic; architecture-aware selection/evaluation dành cho v0.27.1.
- MCP thêm 3 read-only tools; không expose set/validate mutation, graduate, revoke hay approval authority.
- Distribution chuyển sang **download latest full release**, không còn yêu cầu version-specific `apply_v*.py` updater.
- User skills, workflows/workflow state, source, architecture working copy, local governance override, state/runtime là project-owned và không thuộc managed release payload.
- README VI/EN, developer guide và current-release docs được cập nhật cho v0.27.0.

### Schema 58

Bổ sung `skill_contracts`, `skill_contract_events` và contract metadata trên `promoted_skills`.

### CLI mới

```text
skill-contract-set
skill-contract-show
skill-contract-validate
skill-contract-status
```

### MCP mới

```text
agentos.skill_contract_get
agentos.skill_contract_status_get
agentos.skill_contracts_list
```

## English

v0.27.0 upgrades the existing skill subsystem into **Governed Skill Contract v2** without creating a second skill framework.

### Highlights

- Database schema **57 → 58**.
- New candidates receive a deterministic least-authority v2 contract.
- Contracts explicitly declare inputs/outputs, Architecture sections, capabilities, tools, read/write scopes, dependencies, external services, pre/postconditions, risk tier, tests, and architecture constraints.
- Architecture-sensitive contracts require an ACTIVE human-approved Architecture Baseline and pin its exact hash.
- Existing v1 skills remain `legacy_v1`; approved artifacts are not rewritten in place.
- Graduation/revocation remain human-controlled.
- Lexical skill matching remains unchanged; architecture-aware selection/evaluation is deferred to v0.27.1.
- Three read-only MCP tools expose contract inspection only.
- Distribution moves to **download latest full release** with no version-specific updater scripts.
- Project-owned skills, workflows/workflow state, source, architecture working copies, local governance overrides, state, and runtime are excluded from the managed release payload.
- README and developer documentation are synchronized for v0.27.0.
