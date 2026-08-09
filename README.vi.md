# AgentOS Local Governance v0.22.6

**Node:** Secret Resolver & Lineage Key Lifecycle  
**Schema:** 42  
**Baseline:** v0.22.5 — Unified CLI/MCP & Cross-Platform Runtime

## Secret Resolver production-grade

AgentOS không còn dùng `env://` như resolver mặc định riêng lẻ cho production DB pipeline. Extraction, Controlled Target Insert và reconciliation đi qua **trusted resolver registry** dùng chung.

Hỗ trợ:

- `env://NAME`
- `keychain://service/account`
- `vault://mount/path#field`
- `secret://alias`
- `file-secret://relative.json` trong `.agents/state/secrets/`

Mỗi provider có `provider_id`, version và implementation SHA-256 pin. Provider phải được operator approve theo đúng capability trước khi resolve. Provider thiếu, hash/version không khớp, capability không được approve hoặc dependency không tồn tại đều fail-closed.

`governance.json` chỉ được ánh xạ alias sang URI resolver tin cậy; không được chỉ định `importlib`, `module:function`, executable hay plugin code tùy ý. Callback resolver cũ chỉ còn compatibility cho test/library root không được governance; production AgentOS root từ chối callback injection.

Credential đã resolve chỉ tồn tại trong memory của operation đang dùng. SQLite, audit, MCP, context/LLM và cache không nhận raw credential.

## Versioned lineage keyring

`identity_lineage.key` đơn lẻ được thay bằng keyring tại `.agents/state/lineage-keys/` với metadata schema 42:

- `key_id`
- `active`
- `retired`
- `revoked`
- created/activated/retired/revoked timestamps
- predecessor + rotation-plan provenance

Khởi tạo keyring là **privileged mutation** (`lineage-keyring-initialize`), không xảy ra khi MCP chỉ đọc status. Nếu legacy key tồn tại, AgentOS chuyển **nguyên bytes** vào keyring và chỉ backfill `key_id`; không re-HMAC lịch sử.

Token/fingerprint mới dùng active key. Lookup identity hiện tính fingerprint bằng active + retired keys để vẫn tìm dữ liệu cũ. Revoked key bị loại khỏi lookup/verification.

Rotation:

```text
immutable plan
→ human review
→ human approval
→ governed execution
→ old active = retired
→ new key = active
→ signed audit
```

Rekey không được tính HMAC mới từ HMAC cũ. Workflow phải xác nhận SOURCE còn quyền `select_read`, sau đó đọc lại raw identifier qua boundary đã governance.

## Invariant giữ nguyên

- Migration liên tục schema 1 → 42 qua `agentos.db.connect()` và `foreign_keys=ON`.
- Unified CLI/MCP vẫn in-process, không quay lại version/subprocess forwarding.
- Privileged mutation vẫn nằm trong task/session/capability/baseline-drift/one-time-token/hash-chain/Ed25519 signed-audit boundary.
- MCP không expose approval, credential resolution, identity decision, key mutation, TARGET mutation hoặc recovery mutation.
- SOURCE vẫn read-only; TARGET chỉ ghi qua Controlled Target Insert.

## Lệnh operator chính

```bash
agentos secret-lineage-db-sync
agentos secret-provider-catalog
agentos secret-provider-approve --scheme env --capability db.source.select --approved-by OPERATOR --human-confirmed
agentos lineage-keyring-status
agentos lineage-keyring-initialize
agentos lineage-key-rotation-plan-create --reason "scheduled rotation" --created-by OPERATOR
```

Các lệnh mutation phải chạy với task/session hợp lệ theo enforcement v0.22.4+.
