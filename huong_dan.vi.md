# Hướng dẫn AgentOS v0.24.2

## v0.24.2 — Risk-Tiered Batch Review

1. Chạy `project-consolidation-risk-assess` để phân tier deterministic.
2. Gom mapping `LOW` vào signed bundle; review bundle với human confirmation.
3. Review `MEDIUM/HIGH` riêng; `BLOCKED` phải re-plan.
4. Chỉ khi mọi mapping review current cho exact `plan_hash` thì plan thành `reviewed`; approval toàn plan vẫn bắt buộc.


1. Dùng `consolidation-status` để đọc snapshot toàn pipeline mà không mutate state.
2. Chạy `performance-baseline-run --repeats 5` trên repository đã materialize và xác nhận `performance-baseline-check`.
3. Duyệt task/scope và xây canonical Context Pack không stale.
4. Compile transport bằng model profile/adaptive budget v0.23.1.
5. Dùng `context-expansion-explain` để xem evidence đã omit.
6. Dùng `context-expand` hoặc `context-expand-batch` với giới hạn dòng/token và reason code allowlist.
7. Chạy `context-compression-evaluate`; mọi hard gate phải đạt.
8. Dùng `context-compression-compare` để shadow-compare revision mà không tự kích hoạt revision mới.

Expanded content chỉ được trả ở output hiện thời và không persist vào expansion/evaluation telemetry. Mục tiêu 2–4x là advisory; không được cắt original request, AGENTS, scope, plan hoặc requirement để đạt ratio.


## v0.24.2 — DB-Aware Context Projection

Deterministic reversible schema/mapping/manifest projection is limited to the Context Evidence Plane. Control Plane authority remains lossless.
