<!-- Path: .agents/docs/RELEASE_METADATA_COHERENCE_V0251.md -->
<!-- Purpose: Define the v0.25.1 fail-closed release metadata coherence contract. -->

# Release Metadata Coherence — v0.25.1

## Mục tiêu

v0.25.1 khóa một release identity duy nhất cho toàn bộ AgentOS package. Node này không thay đổi database schema, MCP authority, migration semantics hay execution behavior của v0.25.0.

Nguồn release version duy nhất là `VERSION`. Schema runtime tiếp tục lấy từ `CURRENT_SCHEMA_VERSION` và giữ ở schema `49`.

## Invariant

Các nguồn sau phải đồng thuận:

- `VERSION`;
- `.agents/agentos/mcp_runtime.py`;
- `.agents/config/governance.json`;
- `MANIFEST.json`;
- `PACKAGE_COMPLETENESS.json`;
- các current-release identity documents do `documentation_policy.current_release_identity_files` khai báo.

Bất kỳ mismatch nào đều làm release validation fail-closed.

## PACKAGE_COMPLETENESS

`PACKAGE_COMPLETENESS.json` được đồng bộ bởi `tools/build_manifest.py` trước khi tính hash manifest:

- `release` lấy từ `VERSION`;
- `schema` lấy từ `CURRENT_SCHEMA_VERSION`;
- `authoritative_file_count` lấy từ candidate set của release manifest;
- `VALIDATION_REPORT.json` không còn là required clean-main file vì đó là generated validation artifact và bị clean-main release policy loại trừ;
- `PACKAGE_COMPLETENESS.json` phải tự xuất hiện trong `required_top_level`.

## Validation boundary

`release_coherence.check_release_metadata_coherence()` là read-only. Hàm chỉ quan sát và báo finding; nó không sửa metadata trong quá trình validation.

`tools/validate_release.py` và `release_integrity.py` đều gọi coherence gate để lỗi không thể bị bỏ qua bởi một validation path khác.

## Compatibility

- Release: `0.25.1`
- Database schema: `49` — không đổi
- Schema bootstrap baseline: `46` — không đổi
- Fresh migration suffix: mọi migration sau baseline đến current schema, hiện là `47..49`
- MCP tool surface: không đổi
- Governance authority: không đổi

## Rule cho release tương lai

Release validator không được hard-code `0.25.1` làm expected runtime version. `VERSION` là source of truth, để release bump tiếp theo không yêu cầu sửa logic validator chỉ để đổi một literal version.
