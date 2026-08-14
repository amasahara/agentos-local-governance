# AgentOS Local Governance v0.24.2 — DB-Aware Context Projection

[README landing](README.md) | [English](README.en.md)

**Phiên bản hiện tại: v0.24.2 — DB-Aware Context Projection**  
Database schema: **49**.

## v0.24.2 — DB-Aware Context Projection

v0.24.2 bổ sung codec cấu trúc deterministic và reversible cho ba nhóm Evidence
Plane: DB schema, field mapping và manifest. Codec chỉ được chọn khi representation
mới nhỏ hơn source và decoder phải phục hồi cùng canonical JSON structure.

Control Plane vẫn giữ nguyên 100%:

- original user request;
- Requirement Ledger;
- `AGENTS.md` authority;
- approved scope;
- active plan;
- governance authority.

Schema 49 chỉ lưu projection hash, source hash, codec và byte/token counters;
không lưu raw schema/mapping/manifest hoặc projected text.

## v0.24.1 — Risk-Tiered Batch Review

Mapping `LOW` có thể được gom vào signed review bundle pin exact `plan_hash`.
`MEDIUM/HIGH` vẫn phải review riêng, `BLOCKED` không được review, và approval
toàn plan vẫn bắt buộc trước execution.

## MCP read-only

`agentos.context_db_projection_get` chỉ đọc telemetry/hash/count. v0.24.2
Release Hardening mở state DB bằng SQLite `mode=ro`, không tạo database và
không chạy migration từ MCP GET.

## Kiểm tra release

```powershell
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

## Nâng cấp

Xem [Upgrade v0.24.1 → v0.24.2](UPGRADE_FROM_0.24.1.md). Updater theo version
được phát hành dưới dạng GitHub Release asset, không được lưu trên clean `main`.

## Tài liệu

- [DB-Aware Context Projection](.agents/docs/DB_AWARE_CONTEXT_PROJECTION_V0242.md)
- [Risk-Tiered Batch Review](.agents/docs/RISK_TIERED_BATCH_REVIEW_V0241.md)
- [Repository Release Policy](.agents/docs/REPOSITORY_RELEASE_POLICY.md)
