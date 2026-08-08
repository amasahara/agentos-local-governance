[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.20.0

## Project Identity & Purpose Model

v0.20.0 là node đầu tiên sau baseline v0.19.5. Phiên bản này chưa gộp project; nó tạo nền móng để v0.20.1 có thể chọn Primary Project và kiểm tra Domain Compatibility an toàn.

### Bảo đảm mới

- `project_uuid` bền vững, không phụ thuộc absolute path.
- `instance_uuid` riêng cho từng working copy.
- Phát hiện bản copy nguyên thư mục bị trùng instance khi hai path cùng tồn tại.
- Fork project phải do con người xác nhận, tạo UUID mới và giữ `origin_project_uuid`.
- Purpose gồm domain, purpose family, capabilities, role và human confirmation.
- External audit phải dùng `project_uuid` thay cho SHA-256 của path.
- Schema 32 namespace hóa `symbol_index`, `project_findings`, `promoted_skills`, `resource_leases` khi các bảng tồn tại.
- MCP chỉ được đọc identity/purpose; không được tự đổi UUID hoặc xác nhận purpose.

### Local-first nhưng không thay thế LLM

AgentOS giữ governance, state, evidence, audit và identity ở local. LLM vẫn đảm nhiệm reasoning, planning và semantic suggestions. Identity/purpose có ảnh hưởng tới consolidation không được LLM tự phê duyệt.

### Cấu trúc

```text
.agents/config/project.id               stable project UUID
.agents/config/project.purpose.json     human-confirmed business purpose
.agents/state/project.instance.json     local working-copy UUID
~/.agentos/projects/registry.json       host-local clone/relocation registry
```

### Khởi tạo purpose

```bash
.agents/bin/agentos project-identity-init
.agents/bin/agentos project-purpose-set \
  --name "AgentOS Local Governance" \
  --domain-id software_engineering_governance \
  --domain-name "Software Engineering Governance" \
  --purpose-id local_agent_governance \
  --description "Govern local LLM-assisted software engineering with evidence, policy, audit and recovery." \
  --role governance_platform \
  --capability project_governance \
  --capability tool_proxy \
  --capability audit \
  --capability knowledge_runtime \
  --confirmed-by "human-owner" \
  --human-confirmed
```

### Kiểm tra

```bash
.agents/bin/agentos project-identity-verify
.agents/bin/agentos project-identity-db-sync
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

### Giới hạn có chủ đích

v0.20.0 không chọn Primary Project và không thực thi project merge. Hai năng lực đó thuộc v0.20.1 và v0.20.2.

### Nâng cấp từ v0.19.5

Upgrade phải giữ nguyên toàn bộ guarantee v0.19.5: context/knowledge, outcome evaluation, memory privacy, embedding storage, retention, audit archive và backup verification. Migration 32 chỉ thêm identity/purpose/namespace state.

Xem chi tiết: [.agents/docs/PROJECT_IDENTITY.md](.agents/docs/PROJECT_IDENTITY.md)
