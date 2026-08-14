# v0.24.2 — DB-Aware Context Projection

## Mục tiêu

Nén **Evidence Plane** dạng cấu trúc DB trước khi gửi context cho LLM, tập trung vào ba loại artifact:

- schema / target contract;
- field mapping;
- manifest.

Node này không cho phép LLM tóm tắt hoặc tự sửa cấu trúc. Codec là deterministic và reversible ở cấp canonical JSON.

## Schema

AgentOS schema tăng **48 → 49**.

Bảng `context_db_projection_events` chỉ lưu:

- task/context/transport revision;
- candidate ID;
- loại `schema|mapping|manifest`;
- codec;
- source/projection hash;
- byte/token counters;
- reversible flag.

Không lưu raw schema, raw mapping, raw manifest hoặc projected text.

## Codec

Ba codec:

- `db_schema_keydict_v1`
- `db_mapping_keydict_v1`
- `db_manifest_keydict_v1`

Cùng sử dụng deterministic key dictionary: key object lặp lại được đưa vào một dictionary và object body chỉ giữ key index + value tree. Decoder phục hồi cùng canonical JSON structure.

Projection chỉ được dùng nếu kích thước thực sự nhỏ hơn source evidence. Nếu không, context transport fallback về codec hiện có.

## Context boundary

DB-aware projection chỉ chạy trong **Evidence Plane**.

Không được projection:

- original user request;
- Requirement Ledger;
- `AGENTS.md`;
- governance authority;
- approved scope;
- active plan.

Các authority hash và preservation gate v0.23.x giữ nguyên.

## Expansion/freshness

Mọi candidate vẫn giữ `source_hash` và canonical revision. Existing expansion/freshness mechanisms vẫn là authority cho source evidence.

## CLI

Read-only:

```bash
agentos context-db-projection-preview --path path/to/schema.json
agentos context-db-projection-status --task-id T-123
```

## MCP

Chỉ expose:

`agentos.context_db_projection_get`

MCP chỉ trả telemetry/hash/count; không expose projected raw content và không có mutation.
