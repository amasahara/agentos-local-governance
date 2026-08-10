# Hướng dẫn AgentOS v0.23.3

1. Dùng `consolidation-status` để đọc snapshot toàn pipeline mà không mutate state.
2. Chạy `performance-baseline-run --repeats 5` trên repository đã materialize và xác nhận `performance-baseline-check`.
3. Duyệt task/scope và xây canonical Context Pack không stale.
4. Compile transport bằng model profile/adaptive budget v0.23.1.
5. Dùng `context-expansion-explain` để xem evidence đã omit.
6. Dùng `context-expand` hoặc `context-expand-batch` với giới hạn dòng/token và reason code allowlist.
7. Chạy `context-compression-evaluate`; mọi hard gate phải đạt.
8. Dùng `context-compression-compare` để shadow-compare revision mà không tự kích hoạt revision mới.

Expanded content chỉ được trả ở output hiện thời và không persist vào expansion/evaluation telemetry. Mục tiêu 2–4x là advisory; không được cắt original request, AGENTS, scope, plan hoặc requirement để đạt ratio.
