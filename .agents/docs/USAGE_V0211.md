# Usage — v0.21.1

## 1. Chuẩn bị boundary v0.21.0

Có sẵn 1 TARGET, 1..N SOURCE, SOURCE đã read-only verified và đã add vào consolidation.

## 2. Đăng ký schema snapshots

```bash
.agents/bin/agentos db-schema-snapshot-register \
  --connection-id 1 \
  --manifest-file source-fpt-schema.json \
  --captured-by dba

.agents/bin/agentos db-schema-snapshot-register \
  --connection-id 2 \
  --manifest-file target-unified-schema.json \
  --captured-by dba
```

## 3. Tạo TARGET contract

```bash
.agents/bin/agentos db-target-contract-create \
  --consolidation-id 1 \
  --target-snapshot-id 2 \
  --contract-file target-contract.json \
  --created-by architect
```

Review và approve:

```bash
.agents/bin/agentos db-target-contract-review --contract-id 1 --reviewed-by reviewer --human-confirmed
.agents/bin/agentos db-target-contract-approve --contract-id 1 --approved-by owner --human-confirmed
```

## 4. Gợi ý mapping local

```bash
.agents/bin/agentos db-field-mapping-suggest \
  --consolidation-id 1 \
  --source-snapshot-id 1 \
  --target-contract-id 1
```

Suggestion là read-only/advisory.

## 5. Ghi mapping có evidence

```bash
.agents/bin/agentos db-field-mapping-add \
  --consolidation-id 1 \
  --source-snapshot-id 1 \
  --target-contract-id 1 \
  --source-schema dbo --source-table BENH_NHAN --source-column MA_BN \
  --target-schema public --target-table patient --target-column patient_code \
  --confidence 1.0 --match-method manual \
  --evidence-file mapping-evidence.json \
  --created-by data-architect
```

Confirm:

```bash
.agents/bin/agentos db-field-mapping-confirm --mapping-id 1 --confirmed-by data-owner --human-confirmed
```

## 6. Kiểm tra readiness cho v0.21.2

```bash
.agents/bin/agentos db-mapping-readiness --consolidation-id 1 --target-contract-id 1
```

`ready_for_v0.21.2=true` yêu cầu contract approved, mọi SOURCE có mapping confirmed hiện hành, không có mapping stale và mọi TARGET field đánh dấu `required` đã được map.
