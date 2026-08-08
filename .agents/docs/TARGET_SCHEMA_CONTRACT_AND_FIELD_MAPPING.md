# AgentOS v0.21.1 — Target Schema Contract & Cross-DB Field Mapping

## Mục tiêu / Purpose

Node này xác định cấu trúc TARGET trước khi di chuyển dữ liệu và ánh xạ metadata từ nhiều SOURCE khác engine về cùng TARGET contract.

```text
SOURCE schema snapshots (metadata only)
        ↓
SOURCE → TARGET field mappings
        ↓
approved TARGET schema contract
```

Không extraction record, không chạy SQL tùy ý và không INSERT trong v0.21.1.

## Schema snapshot

`db_schema_snapshots` lưu metadata catalog đã được operator thu thập. Manifest chỉ gồm table, column, native type, canonical type, nullability và keys. Không chứa row/sample value.

- SOURCE snapshot chỉ được đăng ký khi connection đã `readonly_verified`.
- TARGET snapshot được dùng để chứng minh contract phản ánh cấu trúc TARGET thật.
- Snapshot mới supersede snapshot cũ của cùng connection.

## Target Schema Contract

Contract là subset/contract có chủ đích của TARGET snapshot, không được suy ra tự động từ SOURCE.

Lifecycle:

```text
draft → reviewed → approved
              ↓
       superseded on TARGET drift/new approved contract
```

Contract phải:

- thuộc đúng TARGET của consolidation;
- tham chiếu TARGET snapshot active;
- chỉ chứa bảng/cột tồn tại trong snapshot;
- có canonical type khớp snapshot;
- được con người review và approve.

## Canonical types

`string`, `integer`, `decimal`, `float`, `boolean`, `date`, `datetime`, `time`, `uuid`, `json`, `binary`, `text`, `code`, `other`.

Mỗi snapshot giữ cả `native_type` và `canonical_type`, cho phép so sánh MySQL / MSSQL / PostgreSQL / Oracle mà không làm mất metadata gốc.

## Field Mapping

Mapping luôn có hướng:

```text
SOURCE schema.table.column
        ↓
TARGET schema.table.column
```

Không có SOURCE↔SOURCE mapping.

Mỗi mapping lưu:

- source connection/snapshot/hash;
- target contract/hash;
- source/target canonical type;
- `type_compatibility`: `exact`, `coercible`, `incompatible`;
- transform rule + declared output type khi cần;
- validation rule metadata;
- confidence;
- match method;
- evidence;
- mapping hash;
- human confirmation.

### Type rules

- `exact`: không bắt buộc transform.
- `coercible`: bắt buộc explicit `transform_rule`.
- `incompatible`: bắt buộc transform và `transform_output_type` phải bằng TARGET canonical type.

Transform trong v0.21.1 chỉ là contract metadata; chưa được thực thi.

## Drift / stale

- SOURCE snapshot mới → mappings gắn snapshot cũ thành `stale`.
- TARGET snapshot mới → contracts gắn snapshot cũ thành `superseded`; mappings phụ thuộc thành `stale`.
- Contract mới được approve → contract approved cũ `superseded`; mappings cũ `stale`.

v0.21.2 chỉ được dùng mapping `confirmed` còn current.

## LLM/MCP boundary

LLM được đọc snapshot/contract/mapping và dùng lexical/type suggestion local. Suggestion không ghi DB, không xác nhận mapping và không tự approve contract.

Mutation chỉ qua operator CLI/human boundary.
