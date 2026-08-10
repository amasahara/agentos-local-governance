# Upgrade v0.23.2 → v0.23.3

## 1. Dry-run

```bash
python3 tools/apply_v0233.py /path/to/agentos-v0.23.2 --dry-run
```

Upgrader yêu cầu:

- `VERSION = 0.23.2`;
- `CURRENT_SCHEMA_VERSION = 46`;
- unified CLI/MCP/release-integrity files của v0.23.2;
- governance version phải đúng `0.23.2`.

Mọi baseline khác bị từ chối.

## 2. Apply

```bash
python3 tools/apply_v0233.py /path/to/agentos-v0.23.2
```

Backup baseline được lưu dưới:

```text
.agents/runtime/upgrade-backups/v0.23.2-to-v0.23.3/
```

Schema không đổi: **46 → 46**.

## 3. Bắt buộc capture baseline thật

Overlay chứa một template fail-closed. Trước khi release gate có thể pass, chạy trên chính repository đã nâng cấp:

```bash
.agents/bin/agentos performance-baseline-run \
  --repeats 5 \
  --output PERFORMANCE_BASELINE_V0233.json

.agents/bin/agentos performance-baseline-check
```

Benchmark migration/index chỉ ghi vào temporary fixtures. Cockpit dùng DB thật nhưng mở read-only/query-only.

## 4. Kiểm tra cockpit và release

```bash
.agents/bin/agentos consolidation-status
.agents/bin/agentos runtime-health
.agents/bin/agentos release-integrity-check
.agents/bin/agentos docs-check
python3 tools/validate_v0233.py .
python3 -m pytest -q .agents/tests/test_consolidation_cockpit_v0233.py
```

## 5. Full regression trước khi publish

```bash
python3 -m pytest -q .agents/tests
```

v0.23.3 không sửa `index_build()`. Kết quả full-rebuild này là baseline cho v0.23.4 Incremental Symbol Index.
