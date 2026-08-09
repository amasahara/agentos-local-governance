# AgentOS Local Governance v0.23.1 — Adaptive Token Budget & Model Profiles

[README landing](README.md) | [English](README.en.md)

## Mục tiêu

v0.23.1 giữ nguyên toàn bộ guarantee của v0.23.0 và bổ sung lớp **Adaptive Token Budget & Model Profiles** để AgentOS chọn lượng token dành cho output/overhead/safety/evidence theo cách xác định, cục bộ và có thể audit.

Pipeline vẫn là:

```text
Canonical Context Pack
        ↓
Requirement Ledger + protected authority lock
        ↓
Control Plane — LOSSLESS
        ↓
Model Profile (hash-pinned)
        ↓
Adaptive Budget Decision
        ↓
Evidence Plane — deterministic/extractive
        ↓
Requirement Preservation Gate
        ↓
READY Transport Pack
```

## Model Profile Registry

Profile chỉ là dữ liệu cấu hình, không phải code/plugin. Mỗi profile được chuẩn hóa và pin bằng SHA-256 trên toàn bộ definition quan trọng:

- `context_capacity`;
- tokenizer policy (`auto`, `heuristic`, `tiktoken`);
- optional `model_name`/`encoding` dùng cho tokenizer local;
- `reserved_output_min/default/max`;
- `system_tool_overhead`;
- `safety_margin_min` + ratio;
- `minimum_evidence_tokens`.

Không cho network/provider API discovery, dynamic import, arbitrary code hoặc tokenizer auto-download. `tiktoken` nếu dùng chỉ được đọc asset đã có trong local cache; cache miss sẽ fallback heuristic hoặc fail nếu policy bắt buộc exact tokenizer. AgentOS **không tự đổi provider/model**; profile chỉ mô tả budget contract mà runtime/operator đã chọn.

## Adaptive Token Budget

Budget vẫn tuân theo công thức bất biến:

```text
input_budget = context_capacity
             - reserved_output
             - system_tool_overhead
             - safety_margin
```

Control Plane luôn được tính trước. Evidence chỉ nhận phần còn lại:

```text
evidence_budget = max(0, input_budget - control_tokens)
```

Adaptive mode dùng các tín hiệu deterministic từ Requirement Ledger/active plan để tăng output reserve khi task phức tạp. Safety margin lấy giá trị lớn nhất giữa floor của profile, tỷ lệ capacity và headroom calibration. Nếu Control Plane vượt input budget thì **fail-closed**, không cắt request/AGENTS/scope/plan/requirements.

`fixed` mode vẫn còn để tái tạo hành vi budgeting kiểu v0.23.0 khi operator cần.

## Calibration an toàn

CLI có thể ghi số token runtime thực tế sau một transport:

```text
predicted input tokens
observed input tokens
predicted output reserve
observed output tokens
profile hash
tokenizer id
```

Không lưu prompt, response, evidence, credential hoặc raw source text trong bảng calibration. `source` chỉ nhận enum allowlist (`runtime_report`, `provider_usage`, `tokenizer_probe`, `operator_verified`, `benchmark`, `local_runtime`) và mỗi transport/source chỉ được ghi một observation; replay khác số liệu sẽ bị chặn.

Calibration chỉ được dùng theo hướng bảo thủ:

- under-estimation input → tăng safety headroom;
- output thực tế cao → tăng reserved output cho lần sau;
- không được giảm `safety_margin_min`;
- không được giảm output floor;
- không làm thay đổi Control Plane hoặc Requirement Ledger.

## Schema 45

Bổ sung:

- `context_model_profile_snapshots`;
- `context_budget_decisions`;
- `context_token_observations`;
- provenance columns `model_profile_hash`, `budget_mode`, `budget_decision_id` trên `context_transport_packs`.

Migration vẫn qua `agentos.db.connect()` với `PRAGMA foreign_keys=ON`.

## CLI mới

```text
context-model-profiles-list
context-model-profile-get
context-budget-history
context-token-calibration-get
context-token-observation-record
```

`context-transport-compile` bổ sung `--budget-mode adaptive|fixed`.

## MCP read-only mới

```text
agentos.context_model_profiles_get
agentos.context_budget_history_get
agentos.context_token_calibration_get
```

MCP không expose observation recording, profile mutation, budget mutation, compile/evaluate mutation hay model switching authority.

## Safety invariants giữ nguyên

v0.23.1 không thay SOURCE/TARGET database safety, secret/key lifecycle, privacy erasure authority, signed-audit boundary hoặc v0.23.0 Requirement Preservation Gate. Original request, constraint, prohibition, authority, approved scope và plan vẫn phải được bảo toàn 100%.
