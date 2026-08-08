# AgentOS v0.21.2 — Read-Only Extraction & Data Validation

## Mục tiêu / Purpose

v0.21.2 là node đầu tiên đọc **record nghiệp vụ thực** từ database SOURCE. Nó không thay đổi SOURCE và không ghi TARGET. Output duy nhất là staging local đã transform/validate để v0.22.0 có thể dùng cho controlled INSERT.

```text
SOURCE (verified read-only)
  ↓ generated SELECT, mapped columns only
Extraction Batch
  ↓ deterministic transforms
TARGET-shaped candidate row
  ↓ validation
valid → local staging JSONL
invalid → privacy-safe quarantine evidence
  ↓
TARGET DB write = DISABLED until v0.22.0
```

## Boundary bắt buộc

1. SOURCE phải active, role SOURCE, `readonly_verified=1`, `data_write_enabled=0`.
2. SOURCE phải thuộc cùng `db_consolidation` với TARGET contract.
3. Batch chỉ dùng mapping `confirmed` và current.
4. Batch bind vào `source_snapshot_hash`, `target_contract_hash`, `mapping_set_hash`, `extraction_plan_hash`.
5. Schema/mapping drift trước khi chạy làm batch `stale`.
6. Query do AgentOS sinh từ identifier đã validate; không nhận raw SQL.
7. Chỉ SELECT cột đã map; `SELECT *` bị cấm.
8. TARGET write tiếp tục bị deny bởi v0.21.0 boundary.

## Schema 37

- `db_extraction_batches`
- `db_extraction_batch_mappings`
- `db_validation_findings`
- `db_extraction_events`

SQLite chỉ chứa metadata, count, hash và finding đã redact. Business values không được persist trong SQLite/audit.

## Transform registry

v0.21.2 chỉ chạy các transform built-in đã allowlist:

`identity`, `datetime_to_date`, `date_to_datetime`, `integer_to_boolean`, `boolean_to_integer`, `stringify`, `uuid_to_string`, `string_to_uuid`, `json_to_text`, `text_to_json`, `trim_string`, `uppercase_string`, `lowercase_string`.

Không dùng `eval`, `exec`, import path động hay expression tự do.

## Validation rules

Mapping `validation_rule_json` có thể dùng các key allowlist:

- `not_null`
- `allow_blank`
- `min_length`, `max_length`
- `regex`
- `enum`
- `min`, `max`
- `date_min`, `date_max`

TARGET contract `required`/`nullable` luôn được enforce bổ sung.

## Staging & quarantine

Valid record được ghi dạng TARGET-shaped JSONL vào:

`.agents/runtime/data-staging/<batch_uuid>/valid.jsonl`

Quarantine nằm tại `quarantine.jsonl`, nhưng chỉ có row ordinal, locator hash, field/rule/message và value hash. Không lưu raw invalid values.

`manifest.json` bind counts + artifact hashes + source/target/mapping hashes. Files được tạo owner-only (0600 khi filesystem hỗ trợ) và staging path được Git-ignore.

## External DB adapters

CLI `db-extraction-run` dùng optional local DB-API drivers:

- PostgreSQL: `psycopg` / `psycopg2`
- MySQL: `pymysql` / `mysql.connector`
- SQL Server: `pyodbc`
- Oracle: `oracledb`

Default secret resolution chỉ hỗ trợ `env://NAME`, trong đó biến môi trường chứa JSON secret. `secret://`, keychain/vault/file-secret cần trusted resolver được tích hợp ngoài MCP. Secret không được log/return.

## MCP

Read-only only:

- `agentos.db_extraction_batch_get`
- `agentos.db_extraction_summary_get`
- `agentos.db_validation_findings_get`
- `agentos.db_staging_integrity_get`

Không expose extraction execution, generated SQL, secret resolution, staging contents hay TARGET INSERT.
