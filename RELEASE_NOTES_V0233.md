# AgentOS Local Governance v0.23.3

## Consolidation Cockpit & Performance Baseline

- Thêm `consolidation-status` read-only cho toàn pipeline từ project candidate/Primary đến DB reconciliation/recovery.
- Scope identity/reconciliation theo đúng DB consolidation, tránh trộn status giữa nhiều pipeline đồng thời.
- Thêm benchmark non-destructive cho full migration 1→46, chính `index_build()` full-rebuild hiện tại và cockpit latency.
- Thêm `performance-baseline-check` vào release-integrity gate; template chưa đo phải fail cho đến khi benchmark thực tế được ghi lại.
- Thêm hai MCP read-only tools: `agentos.consolidation_status_get`, `agentos.performance_baseline_get`.
- Không tăng database schema; giữ schema **46**.
- Không thay đổi SOURCE/TARGET, identity, recovery, privacy, secret/key, signed-audit, human approval hoặc Context Control Plane authority.
