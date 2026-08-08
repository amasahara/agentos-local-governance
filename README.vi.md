[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.2

## Reconciliation & Recovery

v0.22.2 là node cuối của roadmap consolidation. Release này không mở thêm quyền ghi dữ liệu; nó bổ sung lớp **đối soát read-only và phục hồi fail-closed** sau Controlled Target Insert/Identity Resolution.

```text
SOURCE SELECT-only
      ↓
validated + identity-resolved staging
      ↓
Controlled Target Insert
      ↓
TARGET
      ↓ SELECT-only reconciliation
expected whole-row fingerprints ↔ observed TARGET fingerprints
      ↓
matched / observed_none / observed_partial / mismatch
      ↓
Human recovery decision khi commit còn in_doubt
```

### Invariant bắt buộc

- Reconciliation chỉ đọc TARGET và chỉ truy vấn các business key đã nằm trong identity policy/TARGET contract.
- Không lưu business-key value, query parameter, record value, PHI/PII hoặc credential trong SQLite/audit/recovery checkpoint.
- Đối soát so sánh **HMAC whole-row fingerprints** của toàn bộ cột đã INSERT, không chỉ so count.
- `in_doubt`/`committing` không bao giờ tự chuyển thành committed/failed.
- `committed_verified` chỉ hợp lệ sau kết quả reconciliation `matched` + human confirmation.
- `not_committed_verified` chỉ hợp lệ sau `observed_none` + human confirmation; sau đó chỉ **manual retry** được mở.
- `observed_partial`/`mismatch` không được AgentOS tự UPDATE/DELETE/UPSERT/MERGE để sửa TARGET; trạng thái phải `manual_intervention`.
- SOURCE luôn read-only; recovery không bao giờ sửa SOURCE.
- Lineage local bị pending có thể rebuild idempotent sau khi đã biết chắc external commit thành công; không được retry INSERT chỉ để sửa lineage.
- Mọi recovery stage tạo checkpoint/hash để resume và audit mà không lưu dữ liệu nghiệp vụ.

### Schema 40

Bổ sung:

- `db_reconciliation_runs`
- `db_reconciliation_findings`
- `db_recovery_cases`
- `db_recovery_checkpoints`
- `db_recovery_events`

### Recovery semantics

```text
insert status = committed
    ↓ reconciliation
matched       → reconciliation complete
mismatch      → discrepancy / manual investigation

insert status = in_doubt | committing
    ↓ reconciliation
matched       → HUMAN may mark committed_verified
observed_none → HUMAN may mark not_committed_verified
                → manual retry allowed, automatic retry still forbidden
partial       → manual_intervention only
mismatch      → manual_intervention only
```

### CLI

```bash
# Đồng bộ schema 40
.agents/bin/agentos db-reconciliation-recovery-db-sync

# Tạo và chạy đối soát read-only
.agents/bin/agentos db-reconciliation-create \
  --insert-run-id 1 --created-by operator
.agents/bin/agentos db-reconciliation-run \
  --reconciliation-run-id 1
.agents/bin/agentos db-reconciliation-summary \
  --reconciliation-run-id 1

# Phát hiện recovery case
.agents/bin/agentos db-recovery-scan
.agents/bin/agentos db-recovery-cases-list
.agents/bin/agentos db-recovery-readiness --insert-run-id 1

# Human xử lý commit uncertainty
.agents/bin/agentos db-recovery-commit-decide \
  --recovery-case-id 1 \
  --decision committed_verified \
  --decided-by owner --human-confirmed

# Hoặc xác nhận external commit không xảy ra
.agents/bin/agentos db-recovery-commit-decide \
  --recovery-case-id 1 \
  --decision not_committed_verified \
  --decided-by owner --human-confirmed

# Rebuild lineage local sau known commit
.agents/bin/agentos db-recovery-lineage-finalize \
  --recovery-case-id 2 --recovered-by owner --human-confirmed
```

### MCP read-only

v0.22.2 thêm 6 tool đọc:

- `agentos.db_reconciliation_get`
- `agentos.db_reconciliation_summary_get`
- `agentos.db_reconciliation_spec_get`
- `agentos.db_recovery_cases_get`
- `agentos.db_recovery_readiness_get`
- `agentos.db_recovery_checkpoints_get`

MCP không expose reconciliation execution, recovery decision, lineage finalization, TARGET mutation, raw values hoặc credentials.

Chi tiết: [.agents/docs/RECONCILIATION_AND_RECOVERY.md](.agents/docs/RECONCILIATION_AND_RECOVERY.md)

## Roadmap hoàn tất

```text
v0.20.0 Project Identity & Purpose Model
→ v0.20.1 Primary Project Selection & Domain Compatibility
→ v0.20.2 Primary-Project Consolidation
→ v0.21.0 Source/Target Database Boundary
→ v0.21.1 Target Schema Contract & Cross-DB Field Mapping
→ v0.21.2 Read-Only Extraction & Data Validation
→ v0.22.0 Controlled Target Insert
→ v0.22.1 Identity Resolution, Deduplication & Lineage
→ v0.22.2 Reconciliation & Recovery                     ← hiện tại
```

## Validation release

```text
v0.22.2 node tests:              18 passed
available full regression:       159 passed
schema:                          40
MCP read-only catalog:            37 tools
SOURCE write:                    forbidden
in_doubt automatic retry:        forbidden
partial TARGET automatic repair: forbidden
raw values in recovery state:    forbidden
```
