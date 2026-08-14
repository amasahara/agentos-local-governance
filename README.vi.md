# AgentOS Local Governance v0.25.0 — Schema Bootstrap Baseline

[README landing](README.md) | [English](README.en.md)

**Phiên bản hiện tại: v0.25.0 — Schema Bootstrap Baseline**  
Database schema: **49**.

Fresh DB không còn gọi migration functions 1→46. Runtime tạo trực tiếp snapshot
schema 46 đã pin trong release, kiểm tra fingerprint, ghi coverage 1..46 rồi chỉ
chạy migrations 47→49.

DB đã tồn tại vẫn nâng cấp tuần tự từ schema thực tế của nó; shortcut bootstrap
không được dùng cho existing database.

Các boundary SOURCE/TARGET, human approval, privacy, signed audit, context
preservation và MCP mutation authority không thay đổi.

Xem [Upgrade v0.24.3 → v0.25.0](UPGRADE_FROM_0.24.3.md) và
[Schema Bootstrap Baseline](.agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md).
