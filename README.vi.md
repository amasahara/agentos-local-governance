# AgentOS Local Governance v0.23.4 — Incremental Symbol Index

[README landing](README.md) | [English](README.en.md)

## v0.23.4

v0.23.4 chuyển `index-build` sang incremental mặc định: file không đổi vẫn được SHA-256 để bảo đảm correctness nhưng không AST-parse; file mới/đổi chỉ thay symbol rows của chính file đó; file xóa loại stale rows. Lần đầu sau migration 47 bootstrap full rebuild để seed metadata.

## v0.23.3

v0.23.3 bổ sung `consolidation-status` read-only cho toàn chuỗi project/database consolidation và baseline hiệu năng non-destructive cho migration 1→46, full symbol-index rebuild hiện tại và cockpit latency. Schema vẫn là **46**; MCP chỉ đọc status/baseline, không chạy benchmark và không có quyền mutation.

## Nền v0.23.2

v0.23.2 hoàn thiện vòng lặp **nén → mở rộng có kiểm soát → đánh giá → so sánh shadow** trên nền Requirement-Preserving Context Compression. Control Plane vẫn giữ nguyên 100% original request, Requirement Ledger, AGENTS authority, approved scope và active plan; node này không nới quyền nén protected content.

```text
Canonical Context Pack
        ↓
Requirement-Preserving Transport
        ↓
Deterministic Evidence Compression
        ↓
Hash-pinned omission handles
        ↓
Bounded read-only expansion
        ↓
Compression Evaluation v2
        ↓
PASS / WARN / FAIL + shadow comparison
```

## Context Expansion v2

- mở rộng chỉ từ omission handle đã hash-pin;
- kiểm tra transport hash, canonical revision và source hash trước khi đọc;
- hỗ trợ `line_start`, `max_lines`, `max_tokens`, reason code allowlist và Requirement Ledger IDs;
- batch expansion có giới hạn số handle và tổng token;
- nội dung mở rộng chỉ trả về memory/caller, **không persist vào SQLite/audit**;
- telemetry chỉ giữ request hash, handle, line range, token count, reason code và requirement IDs;
- MCP expansion chạy `record_event=false`, không tạo mutation telemetry từ LLM.

## Compression Evaluation v2

Hard gate:

- requirement preservation rate = **100%**;
- mọi canonical evidence candidate phải được included hoặc có expansion handle;
- expansion-handle integrity = **100%**;
- transport không vượt input budget;
- transport integrity và source freshness phải được xác minh.

Mục tiêu compression **2–4x** vẫn là stability target advisory: dưới 2x hoặc trên 4x tạo warning để review, không được đổi thành lý do cắt Control Plane.

Evaluation giữ metric contract cũ (`raw_tokens`, `transport_tokens`, `compression_ratio`, requirement preservation, context miss, expansion request, task/test success, rework, tool calls) và bổ sung candidate accountability, handle integrity, expansion success/failure, budget utilization, hard failures và warnings.

## Shadow comparison

Có thể so sánh hai transport revision, kể cả revision `SUPERSEDED`, theo read-only historical verification. Regression flags gồm requirement preservation giảm, context miss tăng, expansion failure tăng, budget vượt, hard gate fail, task/test success giảm hoặc rework tăng.

## Schema 46

Bổ sung:

- `context_expansion_sessions`;
- metadata mới trong `context_expansion_events`;
- `context_compression_evaluation_runs`;
- `context_compression_comparisons`.

Migration tiếp tục qua `agentos.db.connect()` với `foreign_keys=ON`.

## MCP read-only mới

```text
agentos.context_expansion_explain
agentos.context_expand_batch
agentos.context_expansion_history_get
agentos.context_compression_evaluation_get
agentos.context_compression_compare
```

Không expose evaluation persistence, comparison persistence, transport compile/mutation, authority mutation hoặc model/provider switching cho LLM.

## Bản full GitHub-ready

Bản phát hành đầy đủ v0.23.2 được materialize từ toàn bộ repository, không phải overlay. Khi dùng gói full, bạn chỉ cần giải nén, upload/replace nội dung repository và commit/push; không cần chạy `apply_v0232.py`. GitHub Actions trong `.github/workflows/agentos-release-validation.yml` sẽ tự chạy compile, validator, release-integrity, manifest/checksum, docs/instruction và toàn bộ test suite.

Chi tiết: [Full GitHub-Ready Materialization](.agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md).
