# Hướng dẫn AgentOS v0.25.1 — Release Metadata Coherence

1. Xác nhận `VERSION` là release version duy nhất cần dùng làm source of truth.
2. Đồng bộ current-release docs, `agentos.__version__`, MCP runtime và governance version.
3. Chạy `python tools/build_manifest.py .`; builder sẽ đồng bộ `PACKAGE_COMPLETENESS.json` trước khi hash.
4. Chạy `python tools/verify_manifest.py .`.
5. Chạy `python tools/validate_release.py .` và yêu cầu `release_metadata_coherence` pass.
6. Chạy toàn bộ docs/instruction/regression tests trước release.

Database schema vẫn là **49**; không có DB migration cho v0.25.1. Không commit
`VALIDATION_REPORT*.json` vào clean `main`. Cơ chế Schema Bootstrap v0.25.0 và
mọi SOURCE/TARGET, privacy, signed-audit, context và MCP authority vẫn giữ nguyên.
