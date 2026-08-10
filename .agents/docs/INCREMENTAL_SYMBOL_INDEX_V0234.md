# AgentOS v0.23.4 — Incremental Symbol Index

## Mục tiêu

v0.23.4 thay full symbol-index rebuild bằng cập nhật tăng dần có content-hash, nhưng không đánh đổi correctness để lấy tốc độ.

## Invariant

- Schema tăng **46 → 47** để lưu `symbol_index_state` và `symbol_index_files`.
- Lần đầu sau upgrade chạy `bootstrap_full_rebuild`; không tin symbol rows cũ khi chưa có file hash.
- Mỗi lần scan vẫn SHA-256 bytes của file để phát hiện thay đổi chính xác; file không đổi **không AST parse**.
- File mới/đổi được parse từ đúng bytes dùng để hash rồi thay thế riêng symbol rows của file đó.
- File bị xóa làm xóa symbol rows tương ứng mà không parse lại file khác.
- Parse/decode error fail-closed và rollback toàn transaction; index cũ vẫn nguyên vẹn.
- Đổi source root hoặc `index-build --full` sẽ full rebuild có chủ đích.
- Symlink file bị bỏ qua; source path không được thoát khỏi project root.
- Không thay đổi SOURCE/TARGET database authority, privacy, secret, signed-audit hoặc Context Control Plane.

## CLI

```bash
agentos index-build src
agentos index-build src --full
agentos index-status
agentos index-benchmark-run --repeats 3 --output INDEX_INCREMENTAL_BENCHMARK_V0234.json
agentos index-benchmark-check
```

`index-build` giữ tương thích các field `files` và `symbols`, đồng thời thêm telemetry incremental.

## Benchmark contract

Benchmark chạy hoàn toàn trong temporary fixture và bắt buộc xác nhận:

1. bootstrap parse toàn bộ file;
2. no-change incremental parse 0 file;
3. đổi một file parse đúng 1 file;
4. xóa một file xóa đúng state/symbol của file đó.

Timing so với `PERFORMANCE_BASELINE_V0233.json` chỉ advisory vì wall-clock chưa environment-pinned.
