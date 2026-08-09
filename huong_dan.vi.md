# Hướng dẫn AgentOS v0.23.1

## Luồng chuẩn

1. Duyệt task và approved scope.
2. Xây canonical Context Pack và bảo đảm không stale.
3. Kiểm tra model profile bằng `context-model-profile-get`.
4. Compile transport ở `adaptive` (mặc định) hoặc `fixed` mode.
5. Kiểm tra `context-token-report` và `context-budget-history`.
6. Chỉ gửi transport `READY` cho LLM.
7. Sau một call thật, operator/runtime có thể ghi **chỉ số token dạng số** bằng `context-token-observation-record` để tăng headroom bảo thủ cho lần sau.
8. Khi cần evidence đã omit, dùng `context-expand` read-only.

Ví dụ:

```bash
.agents/bin/agentos --task-id TASK-001 context-model-profile-get --model-profile generic-128k
.agents/bin/agentos --task-id TASK-001 context-transport-compile --model-profile generic-128k --budget-mode adaptive
.agents/bin/agentos --task-id TASK-001 context-token-report
.agents/bin/agentos --task-id TASK-001 context-budget-history

.agents/bin/agentos --task-id TASK-001 context-token-observation-record \
  --observed-input-tokens 42100 \
  --observed-output-tokens 6200
```

Không ghi prompt/response vào calibration. Không sửa profile qua MCP. Nếu profile không đủ cho Control Plane, chọn profile phù hợp hơn hoặc sửa budget contract qua governance workflow; **không cắt protected content**.
