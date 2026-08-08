[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.3

## Core Reintegration & Release Integrity

Phiên bản này sửa lỗi toàn vẹn release phát hiện ở v0.22.2: commit v0.22.2 vẫn chứa lõi cũ trên GitHub nhưng đã thay `db.py` bằng registry migration 32–40 và ghi đè `governance.json` bằng policy nhánh mới. v0.22.3 khôi phục một runtime thống nhất.

### Invariant

- Lõi governance v0.19.5 và nhánh v0.20–v0.22 phải cùng có mặt trong release.
- `db.py` khôi phục `connect()` và migration 1→31, sau đó nối additive migration 32→40.
- `CURRENT_SCHEMA_VERSION = 40` là nguồn chân lý duy nhất.
- `governance.json` là phép hợp của policy lõi và policy project/database mới.
- `agentos.v0195` và `agentos-mcp.v0195` phải gọi runtime thật; không silent success/echo stub.
- Historical core tests và feature tests đều là release gate.
- `MANIFEST.json`/`CHECKSUMS.sha256` được verify bằng tool chính thức.

### Phạm vi chưa làm

v0.22.3 không tuyên bố đã đưa mọi mutation database-domain qua `guard_tool`/signed audit. Việc đó thuộc v0.22.4 Unified Governance Enforcement & Signed Audit.

Database schema: **40**
