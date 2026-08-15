# AgentOS Local Governance v0.25.1 — Release Metadata Coherence

[README landing](README.md) | [English](README.en.md)

## Phiên bản hiện tại: v0.25.1 — Release Metadata Coherence

Database schema: **49**.

v0.25.1 khóa một release identity duy nhất cho toàn package. `VERSION` là nguồn
release-version chuẩn; `agentos.__version__`, MCP runtime, governance policy,
`MANIFEST.json`, `PACKAGE_COMPLETENESS.json` và tài liệu current-release phải
đồng thuận. Mismatch làm validation fail-closed thay vì được bỏ qua hoặc sửa
ngầm trong lúc kiểm tra.

Node này **không đổi database schema và không nới authority**. Cơ chế v0.25.0
Schema Bootstrap Baseline vẫn giữ nguyên: fresh DB materialize schema 46, xác
minh fingerprint, ghi coverage 1..46 rồi chỉ chạy migration 47→49; existing DB
vẫn migrate incremental từ version đã ghi nhận.

## Kiểm tra

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

## Nâng cấp

Xem [Upgrade v0.25.0 → v0.25.1](UPGRADE_FROM_0.25.0.md).

## Tài liệu node

- [Release Metadata Coherence](.agents/docs/RELEASE_METADATA_COHERENCE_V0251.md)
- [Schema Bootstrap Baseline](.agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md)
