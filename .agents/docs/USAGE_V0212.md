# Usage — v0.21.2

## 1. Kiểm tra mapping readiness

Hoàn tất v0.21.1 với TARGET contract approved và mapping confirmed/current.

```bash
.agents/bin/agentos db-mapping-readiness --consolidation-id 1 --target-contract-id 1
```

## 2. Tạo extraction batch

```bash
.agents/bin/agentos db-extraction-batch-create \
  --consolidation-id 1 \
  --source-snapshot-id 1 \
  --target-contract-id 1 \
  --source-schema dbo --source-table BENH_NHAN \
  --target-schema public --target-table patient \
  --created-by data-operator \
  --max-rows 100000 --chunk-size 1000
```

Batch chỉ được tạo nếu mọi required TARGET field của target table có mapping confirmed/current từ SOURCE table được chọn.

## 3. Xem generated SELECT

```bash
.agents/bin/agentos db-extraction-select-spec --batch-id 1
```

Đây là generated SELECT, không phải raw SQL input. Chỉ mapped columns được chọn.

## 4. Credential local

Ví dụ connection dùng `credential_ref=env://FPT_HIS_READONLY`:

```bash
export FPT_HIS_READONLY='{"user":"readonly_user","password":"..."}'
```

Không commit biến/secret vào repository.

## 5. Chạy extraction + validation

```bash
.agents/bin/agentos db-extraction-run --batch-id 1
```

SOURCE chỉ SELECT; TARGET không được mở để ghi.

## 6. Xem summary/findings

```bash
.agents/bin/agentos db-extraction-summary --batch-id 1
.agents/bin/agentos db-validation-findings --batch-id 1 --limit 100
.agents/bin/agentos db-staging-verify --batch-id 1
```

MCP chỉ đọc các summary/hash tương ứng; không đọc content `valid.jsonl`.
