# AgentOS Local Governance v0.25.2 — 27-Section Architecture Contract & Human Clarification Gates

[README landing](README.md) | [English](README.en.md)

## Phiên bản hiện tại

- Version: **0.25.2**
- Database schema: **50**
- Schema bootstrap baseline: **46** (không đổi)

v0.25.2 đưa hai quyền quan trọng về phía con người.

Thứ nhất, kiến trúc project được biểu diễn bằng đúng **27 section cố định
`ARCH-01`…`ARCH-27`**. Markdown/JSON trong `.agents/architecture/` chỉ là working
copy. AgentOS snapshot nội dung thành baseline bất biến, hash xác định; chỉ con
người mới được review → approve → activate. AI không thể sửa tài liệu rồi tự làm
vi phạm kiến trúc trở thành hợp lệ. `ARCH-26 Improvement Proposal` luôn là
`proposal_only`, không phải kiến trúc hiện hành.

Thứ hai, `Grill Me` trở thành gate thật. Trước khi task được approve, AI phải ghi
structured clarity assessment. Mọi giả định vật chất, mơ hồ, business choice,
acceptance chưa xác định hoặc lựa chọn kiến trúc phải trở thành câu hỏi cho người
dùng. Khi đang code, AI có thể mở `human decision` blocker; phần công việc phụ
thuộc dừng lại, nhưng read-only investigation vẫn được phép. AI được nêu phương
án và recommendation nhưng **không được tự resolve/waive**. Câu trả lời của con
người được lưu nguyên văn ở local state; external signed audit chỉ giữ hash và
metadata giới hạn.

### Nguyên tắc No Silent Assumption

```text
Requirement/Architecture đã quyết định → làm theo
Pure implementation detail            → AI có thể tự chọn
Material behavior/architecture choice → phải hỏi con người
Không chắc thuộc nhóm nào              → fail closed → hỏi
```

Nếu human resolution thay đổi requirement/scope/architecture, AgentOS thu hồi
approval hiện tại và supersede active/submitted plan để buộc revalidation.

Fresh DB vẫn bootstrap schema 46 rồi chỉ chạy migration **47→50**. Existing DB
v0.25.1 schema 49 chỉ chạy migration **50**.

## MCP

Read-only architecture tools:

- `agentos.architecture_get`
- `agentos.architecture_section_get`
- `agentos.architecture_status_get`

Human-decision inspection:

- `agentos.human_decision_status`
- `agentos.human_decision_get`

`agentos.human_decision_request` là ngoại lệ monotonic duy nhất: nó chỉ **mở
blocker**, không thể resolve/waive/approve/activate hay cấp quyền.

## Chưa thuộc v0.25.2

Source discovery/evidence binding → v0.25.3; architecture drift/compliance →
v0.25.4; ADR/change proposal → v0.25.5; architecture-aware task planning →
v0.26.0.

Xem [tài liệu node](.agents/docs/ARCHITECTURE_CONTRACT_HUMAN_CLARIFICATION_V0252.md)
và [hướng dẫn nâng cấp](UPGRADE_FROM_0.25.1.md).
