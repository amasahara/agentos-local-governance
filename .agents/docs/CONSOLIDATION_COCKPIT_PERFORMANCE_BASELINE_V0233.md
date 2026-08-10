# AgentOS v0.23.3 — Consolidation Cockpit & Performance Baseline

## Mục tiêu

v0.23.3 tạo một mặt quan sát **read-only** cho toàn pipeline consolidation và khóa một baseline hiệu năng trước khi tối ưu index/concurrency ở các node sau. Node này không tăng quyền mutation và không thay đổi schema SQLite.

## Consolidation Cockpit

`agentos consolidation-status` tổng hợp một snapshot từ:

```text
Candidate set / compatibility / Primary selection
                    ↓
Primary-project consolidation
                    ↓
SOURCE/TARGET database boundary
                    ↓
Target contract + field mapping
                    ↓
Read-only extraction + validation
                    ↓
Identity resolution / human candidates
                    ↓
Controlled Target INSERT
                    ↓
Reconciliation / recovery
```

Cockpit:

- mở `.agents/state/agentos.db` bằng SQLite URI `mode=ro`;
- bật `PRAGMA query_only=ON`;
- chỉ trả status/count và blocker code;
- không trả business row, staging content, credential, secret/key material, identity token hay raw PII/PHI;
- scope identity/reconciliation thông qua quan hệ batch/insert để không trộn số liệu giữa nhiều `db_consolidations`;
- hỗ trợ chọn rõ `candidate_set_id`, `project_consolidation_id`, `consolidation_id`; nếu không truyền sẽ dùng record mới nhất của từng tầng.

CLI:

```bash
.agents/bin/agentos consolidation-status
.agents/bin/agentos consolidation-status \
  --candidate-set-id 3 \
  --project-consolidation-id 4 \
  --consolidation-id 7
```

MCP read-only:

```text
agentos.consolidation_status_get
```

## Performance Baseline

`agentos performance-baseline-run` đo ba workload hiện trạng:

1. **Fresh migration 1→46**: tạo project root tạm và chạy full migration vào SQLite tạm.
2. **Current symbol index**: copy Python runtime/tests sang fixture tạm, pre-initialize schema rồi chạy chính `index_build()` hiện tại. v0.23.3 chỉ đo hành vi full rebuild; không sửa nó.
3. **Cockpit latency**: đọc database thật bằng connection read-only/query-only.

Ngoài timing, artifact ghi:

- migration chain length;
- số file/byte Python;
- manifest file count nếu có;
- Python/platform/CPU metadata không nhạy cảm;
- inventory của benchmark context v0.23.x;
- lỗi benchmark nếu runtime không load được.

Mọi write-heavy measurement diễn ra trong `TemporaryDirectory`; benchmark không được ghi vào state database của project. Kết quả duy nhất được ghi vào repository là file output do operator yêu cầu.

```bash
.agents/bin/agentos performance-baseline-run \
  --repeats 5 \
  --output PERFORMANCE_BASELINE_V0233.json

.agents/bin/agentos performance-baseline-check
```

## Release gate

`PERFORMANCE_BASELINE_V0233.json` trong overlay ban đầu là **fail-closed template**. `release-integrity-check` phải báo lỗi cho tới khi operator chạy benchmark trên repository v0.23.3 materialized và thay template bằng measurement thật.

v0.23.3 chưa áp threshold tuyệt đối cho millisecond vì wall-clock phụ thuộc runner. Gate hiện kiểm tra:

- baseline version = 0.23.3;
- schema = 46;
- migration chain nếu load được phải = 46;
- có measurement thật cho fresh migration, full index rebuild và cockpit;
- benchmark contract cấm mutate project state;
- symbol-index baseline mode vẫn là `full_rebuild`.

Threshold so sánh thời gian chỉ nên bật sau khi CI runner/environment fingerprint được pin.

## Bất biến không đổi

- SOURCE luôn read-only.
- TARGET chỉ ghi qua Controlled Target INSERT đã được duyệt.
- `in_doubt` không auto-retry/auto-resolve.
- identity decision nhạy cảm vẫn thuộc human authority.
- MCP không có cockpit mutation và không được chạy benchmark.
- secret/key/PII/PHI không được đưa vào cockpit/baseline.
- lossless Context Control Plane v0.23.x vẫn nguyên vẹn.
- SQLite schema giữ **46 → 46**.

## Phạm vi node kế tiếp

v0.23.3 chỉ tạo measurement surface. **Incremental Symbol Index** được để riêng cho v0.23.4 để có thể so before/after trên cùng baseline.
