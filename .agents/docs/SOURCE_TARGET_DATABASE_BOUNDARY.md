# Source/Target Database Boundary — v0.21.0

[🇻🇳 Tiếng Việt](#tiếng-việt) | [🇬🇧 English](#english)

## Tiếng Việt

### Mục tiêu

v0.21.0 tạo ranh giới database có hướng:

```text
SOURCE A ─┐
SOURCE B ─┼── SELECT/catalog only ──→ AgentOS boundary ──→ TARGET
SOURCE C ─┘                                     (data write disabled)
```

Mỗi kế hoạch có đúng một TARGET. SOURCE không bao giờ bị sửa để “chuẩn hóa” dữ liệu.

### Quyền v0.21.0

| Role | Catalog | SELECT | INSERT | UPDATE | DELETE | DDL |
|---|---:|---:|---:|---:|---:|---:|
| SOURCE | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| TARGET | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |

TARGET được đăng ký ở v0.21.0 nhưng write vẫn khóa. v0.21.1 sẽ định nghĩa schema contract, v0.21.2 extraction/validation, và v0.22.0 mới mở controlled INSERT.

### Credential

Chỉ lưu `credential_ref`, ví dụ `secret://hospital/fpt/prod-readonly`. Không lưu password, connection string hoặc URI có userinfo.

### Read-only verification

Không thử `INSERT` để xem nó có fail hay không. Các phương thức được chấp nhận:

- `grant_review`
- `account_policy`
- `session_readonly`
- `external_attestation`

## English

### Goal

v0.21.0 introduces a directional database boundary with one TARGET and one or more immutable SOURCE connections.

SOURCE permits catalog/SELECT-style reads only. TARGET is registered but data writes remain disabled until the later roadmap nodes establish a schema contract, validated extraction, and controlled INSERT.

### Credentials and verification

Only a credential reference may be stored. Read-only posture must be verified by grants/account/session policy or external attestation; never by attempting a write against production.
