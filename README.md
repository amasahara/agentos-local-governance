# AgentOS Local Governance v0.13.0

**Phiên bản hiện hành:** 0.13.0  
Database schema: `12`  
**Ưu tiên tài liệu:** Tiếng Việt trước, English sau.

## Tiếng Việt — Coordination Enforcement Boundary

v0.13.0 đưa toàn bộ thao tác điều phối nhiều agent vào cùng MCP/tool-proxy boundary với filesystem, process và network. Agent không cần và không được dùng raw shell để acquire lease, claim task hoặc handoff. Mọi request coordination đều đi qua governance preflight, runtime transaction, internal hash-chain audit và external Ed25519 signed audit.

### MCP tools điều phối

`agentos.acquire_resource`, `agentos.heartbeat_resource`, `agentos.release_resource`, `agentos.list_resources`, `agentos.claim_task`, `agentos.handoff_task`, `agentos.task_heartbeat`, `agentos.task_status`, `agentos.force_reclaim_task`.

### Bảo đảm chính

- Handoff lấy danh tính caller từ session đã bind ở gateway; caller không thể tự khai `from_session`.
- Write lease phải nằm trong approved scope.
- Symbol lease bị từ chối khi policy tắt.
- Lease hết TTL được chuyển sang `expired`, không còn hiện là active.
- Directory/file overlap được phát hiện; exact/incompatible conflict bị block, overlap theo policy có warning có cấu trúc.
- Task mất heartbeat chuyển sang `stale`; force reclaim chỉ được phép với task stale và có signed audit.
- Mọi coordination action được liên kết trong bảng `coordination_events` với external event hash.

### Quy trình nhiều agent

1. Mỗi agent dùng session ID riêng.
2. Agent claim task qua MCP.
3. Đọc file và giữ `content_hash`.
4. Acquire resource khi cần work unit dài; `write_file` vẫn tự lấy exclusive lease.
5. Ghi file với `expected_hash`.
6. Heartbeat task/lease khi xử lý dài.
7. Release hoặc handoff qua MCP.
8. Chạy `audit-verify`, `doctor`, test và report.

### Migration từ v0.12.0

Chạy lệnh AgentOS bất kỳ để migration schema 12 được áp dụng. Cập nhật MCP client để lấy lại `tools/list`; bỏ tham số `--from-session` khỏi `handoff-task`. Review governance rồi xác nhận baseline mới.

---

## English — Coordination Enforcement Boundary

v0.13.0 places all multi-agent coordination actions inside the same MCP/tool-proxy enforcement and signed-audit boundary used by filesystem, process, and network capabilities. Caller identity is transport-bound, write leases are scope-checked, expired leases are materialized, stale owners can only be reclaimed through an audited stale-task path, and every coordination mutation is linked to an external signed event.

# AgentOS Local Governance v0.13.0

**Quản trị local-first, MCP proxy-only và điều phối nhiều agent cho dự án phần mềm.**  
**Local-first governance, proxy-only MCP enforcement, and concurrent-agent coordination.**

> Phiên bản hiện tại: `v0.13.0`  
> Current version: `v0.13.0`  
> Database schema: `12`  
> Trạng thái: active development; cần review trước khi dùng cho production hoặc môi trường bảo mật cao.

---

# Tiếng Việt

## 1. AgentOS là gì?

AgentOS Local Governance là lớp quản trị nằm trực tiếp trong repository, giúp coding agent và nhiều tiến trình CLI làm việc theo cùng một bộ quy tắc, workflow, approval gate, write gate, audit trail và cơ chế điều phối tài nguyên.

AgentOS không phải LLM, không phải IDE và không phải sandbox hệ điều hành. Từ v0.10+, AgentOS có thể làm enforcement point thực sự khi agent chỉ được kết nối tới AgentOS MCP gateway và không còn quyền truy cập trực tiếp filesystem, shell hoặc network backend.

v0.13.0 bổ sung lớp **Concurrent Work Coordination** để nhiều CLI hoặc agent có thể làm việc đồng thời mà không âm thầm ghi đè thay đổi của nhau.

## 2. Các mục tiêu cốt lõi

- Chỉ có một nguồn instruction dành cho coding agent: `AGENTS.md`.
- Yêu cầu phải đủ rõ và task phải được phê duyệt trước khi thay đổi project.
- File write phải nằm trong project root và approved scope.
- Tool execution phải đi qua MCP/tool proxy trong proxy-only mode.
- Evidence phải sinh từ execution thật, không từ lời khai tự do của agent.
- Governance drift phải được con người review và xác nhận.
- External audit được ký và có thể lưu ngoài repository.
- Nhiều session/task phải được nhận diện riêng.
- Hai tiến trình không được cùng sửa một tài nguyên khi lease không tương thích.
- Ghi file hiện hữu phải gửi `expected_hash` để phát hiện stale write.
- File phải được thay thế atomically để tránh trạng thái ghi dở.

## 3. Năng lực chính của v0.13.0

### Governance và workflow

- task lifecycle và approval scope;
- session-scoped current task;
- workflow checklist bền vững trong SQLite;
- automated-step provenance;
- final report gate;
- documentation synchronization;
- source documentation contract;
- governance drift detection;
- staged approval cho sensitive local override.

### MCP/tool proxy

- filesystem read/write;
- bounded process execution;
- network HTTP với domain/scheme/IP policy;
- proxy-only mode;
- canonical tool evidence;
- signed external audit;
- audit key registry và rotation;
- audit daemon append-only tối thiểu.

### Điều phối nhiều agent

- session identity riêng cho từng CLI/agent;
- task owner session;
- task claim và explicit handoff;
- resource lease với TTL;
- `shared_read`, `intent_write`, `exclusive_write`;
- heartbeat và auto-expiry;
- expected-content hash;
- stale-write conflict detection;
- atomic file replacement;
- file version history;
- SQLite WAL, busy timeout và immediate transactions;
- task workspace riêng;
- khuyến nghị audit daemon khi multi-process mode bật.

## 4. Kiến trúc thực thi

```text
Coding agents / CLI sessions
        │
        │ MCP hoặc proxy-execute
        ▼
AgentOS Enforcement Gateway
        ├─ resolve session + task owner
        ├─ workflow / approval / drift / override gates
        ├─ resource lease coordination
        ├─ compare expected_hash với file hiện tại
        ├─ filesystem/process/network policy
        ├─ canonical evidence
        └─ signed audit
        │
        ▼
Bounded backend adapters
        ├─ filesystem read/write
        ├─ process test/build/inspect
        └─ HTTP allowlisted egress
```

Để gateway thật sự là enforcement boundary, agent không được đồng thời có raw filesystem tool, raw shell, browser/network tool hoặc backend MCP khác.

## 5. Cấu trúc project

```text
project-root/
├── README.md
├── AGENTS.md
├── huong_dan.md
├── VERSION
└── .agents/
    ├── agentos/
    │   ├── core.py
    │   ├── cli.py
    │   ├── db.py
    │   ├── policy.py
    │   ├── workflow.py
    │   ├── concurrency.py
    │   ├── proxy.py
    │   ├── mcp_server.py
    │   ├── external_audit.py
    │   ├── audit_daemon.py
    │   ├── tooling.py
    │   ├── indexing.py
    │   ├── cache.py
    │   ├── drift.py
    │   └── documentation.py
    ├── bin/
    ├── config/governance.json
    ├── docs/
    ├── tests/
    ├── state/
    ├── cache/
    └── runtime/
```

## 6. Project mới cần làm gì?

1. Copy hoặc chạy safe installer vào repository mới.
2. Review `AGENTS.md`, `governance.json`, README và `huong_dan.md`.
3. Chọn `source_root` qua `governance.local.json` nếu không dùng `src/`.
4. Chạy migration và kiểm tra:

```bash
.agents/bin/agentos db-status
.agents/bin/agentos doctor --scope .agents/agentos
```

5. Xác nhận governance baseline bằng thao tác human review.
6. Cấu hình IDE/agent chỉ dùng AgentOS MCP gateway.
7. Cấu hình audit daemon nếu dùng nhiều process.
8. Mỗi CLI/agent phải có `session-id` riêng.
9. Tạo và approve task đầu tiên.

## 7. Project cũ cần làm gì?

1. Tạo branch/backup trước khi cài.
2. Dùng installer an toàn; không copy đè file root.
3. Merge thủ công các file `.agentos` nếu installer tạo ra.
4. Loại bỏ instruction source cạnh tranh hoặc hợp nhất về `AGENTS.md`.
5. Cấu hình `source_root`, test path và runtime path.
6. Chạy migration lên schema 12.
7. Build symbol index.
8. Rollout `docs-scan` theo module để tránh hàng nghìn finding cùng lúc.
9. Cấu hình MCP proxy-only; gỡ raw filesystem/shell/network tool khỏi agent.
10. Chọn audit sink: với nhiều process nên dùng daemon.
11. Chỉ tạo baseline sau khi merge và review hoàn chỉnh.
12. Tách task/scope để giảm xung đột file.

## 8. Quick start nhiều agent

### Agent A

```bash
export AGENTOS_SESSION_ID=AGENT-A
.agents/bin/agentos start-task --task-id TASK-A --request "Sửa order validation"
.agents/bin/agentos approve-task --task-id TASK-A --scope '["src/orders", "tests/orders"]'
.agents/bin/agentos claim-task --task-id TASK-A
```

### Agent B

```bash
export AGENTOS_SESSION_ID=AGENT-B
.agents/bin/agentos start-task --task-id TASK-B --request "Sửa report export"
.agents/bin/agentos approve-task --task-id TASK-B --scope '["src/reports", "tests/reports"]'
.agents/bin/agentos claim-task --task-id TASK-B
```

Mỗi agent phải dùng session ID khác nhau. Không tái sử dụng một session ID cho hai tiến trình chạy song song.

## 9. Resource lease

### Lấy exclusive lease

```bash
.agents/bin/agentos --session-id AGENT-A acquire-resource \
  --task-id TASK-A \
  --type file \
  --resource src/orders/service.py \
  --mode exclusive_write \
  --ttl 300
```

### Gia hạn

```bash
.agents/bin/agentos --session-id AGENT-A heartbeat-resource \
  --task-id TASK-A \
  --lease-id 42
```

### Giải phóng

```bash
.agents/bin/agentos --session-id AGENT-A release-resource \
  --task-id TASK-A \
  --lease-id 42
```

### Xem lease

```bash
.agents/bin/agentos --session-id AGENT-A list-resources --task-id TASK-A
```

Proxy tự lấy và giải phóng file lease cho một lần `write_file`; lệnh lease thủ công phù hợp khi một work unit cần giữ quyền sở hữu lâu hơn một thao tác ghi.

## 10. Optimistic concurrency và expected hash

Khi đọc file qua proxy:

```json
{
  "tool": "agentos.read_file",
  "args": {"path": "src/orders/service.py"}
}
```

kết quả có:

```json
{
  "content_hash": "H1",
  "version": 7
}
```

Khi ghi file hiện hữu, phải gửi:

```json
{
  "tool": "agentos.write_file",
  "args": {
    "path": "src/orders/service.py",
    "content": "...",
    "expected_hash": "H1"
  }
}
```

Nếu tiến trình khác đã đổi file thành `H2`, write bị chặn:

```json
{
  "allowed": false,
  "reason": "stale_write_conflict",
  "expected_hash": "H1",
  "current_hash": "H2"
}
```

Agent phải đọc lại file và merge/rebase thay đổi. AgentOS không tự ghi đè.

## 11. Atomic write

File không được ghi trực tiếp. Runtime:

```text
create temp file cùng filesystem
→ write + flush + fsync
→ verify expected hash
→ os.replace
→ fsync parent directory
→ record file version
```

Nếu process chết giữa lúc ghi, target cũ vẫn nguyên vẹn hoặc target mới đã được thay thế hoàn chỉnh.

## 12. Task ownership và handoff

Một task có một writer owner mặc định.

```bash
agentos --session-id AGENT-A claim-task --task-id TASK-A
```

Chuyển task:

```bash
agentos --session-id ADMIN handoff-task \
  --task-id TASK-A \
  --from-session AGENT-A \
  --to-session AGENT-C \
  --note "Agent A dừng; Agent C tiếp quản sau checkpoint."
```

Handoff chuyển cả active leases và ghi audit trong database.

## 13. Scope và conflict policy

Policy mặc định:

- exact file conflict: block;
- directory scope overlap: warn;
- file write: yêu cầu lease;
- existing file write: yêu cầu expected hash;
- task: single writer session;
- symbol leases: tắt trong v0.13.0.

v0.13.0 ưu tiên file-level locking. Symbol/line-range parallel editing được để cho bản sau vì cần patch-range validation mạnh hơn.

## 14. SQLite multi-process hardening

Mọi connection được cấu hình:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

Lease acquisition và handoff dùng `BEGIN IMMEDIATE` để tránh hai process cùng nhìn thấy tài nguyên rảnh rồi cùng lấy lease.

SQLite vẫn không phải distributed lock manager. Không dùng cùng database trên network filesystem không bảo đảm POSIX locking.

## 15. Audit trong multi-process mode

Nhiều proxy không nên append trực tiếp cùng JSONL. Khuyến nghị:

```text
all proxy processes → one AgentOS audit daemon
```

Policy v0.13.0 đánh dấu `daemon` là sink bắt buộc được khuyến nghị cho multi-process. Daemon cấp sequence, nối previous hash, ký và append tuần tự.

## 16. MCP gateway

```bash
.agents/bin/agentos-mcp --task-id TASK-A --session-id AGENT-A
```

Tool công bố:

```text
agentos.read_file
agentos.write_file
agentos.run_command
agentos.http_request
```

Không expose raw backend tool song song.

## 17. Process và network policy

`process.exec` chỉ dành cho test/build/inspect profile được allowlist. Không dùng process để sửa source hoặc gọi mạng.

`network.http` mặc định deny và kiểm tra:

- scheme;
- domain allowlist;
- redirect destination;
- private/loopback/link-local IP;
- response size.

## 18. External signed audit

Audit sử dụng Ed25519, hash chain và key registry. Các mode:

```text
jsonl
daemon
remote_http
```

Lệnh:

```bash
agentos audit-verify
agentos rotate-audit-key --identity reviewer --reason "Scheduled rotation"
```

## 19. Documentation và governance checks

```bash
agentos instruction-check
agentos docs-check
agentos docs-scan --scope .agents/agentos
agentos doctor --scope .agents/agentos
```

`docs-check` kiểm tra current version, schema, changelog, marker song ngữ và stale current-release references.

## 20. Checklist trước merge

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos docs-scan --scope .agents/agentos
.agents/bin/agentos drift-check
.agents/bin/agentos audit-verify
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

Đối với task code, phải hoàn tất workflow và chạy `report`.

## 21. Giới hạn bảo mật

v0.13.0 không phải OS sandbox. Agent có raw shell hoặc quyền sửa trực tiếp SQLite vẫn có thể bypass governance. Để enforcement có ý nghĩa:

- agent chỉ được dùng MCP proxy;
- backend credential thuộc proxy/daemon;
- audit daemon chạy bằng account riêng;
- signing key nằm ngoài repository;
- production nên dùng container, read-only mount hoặc OS sandbox bổ sung.

## 22. Nâng cấp từ v0.11.0

1. Thay `.agents/` bằng bản v0.13.0 hoặc merge source.
2. Chạy `db-status`; migration 11 tự áp dụng.
3. Cập nhật `governance.json` với `concurrency_policy`.
4. Cấp session ID riêng cho mỗi CLI/agent.
5. Sửa client write để luôn gửi `expected_hash` cho file hiện hữu.
6. Chọn audit daemon cho multi-process.
7. Review và xác nhận baseline mới.
8. Chạy toàn bộ checks và test.

<!-- AGENTOS_VERSION_HISTORY_BEGIN -->
## 23. Lịch sử phiên bản rút gọn

- v0.11.0: process/domain hardening, key rotation, audit daemon.
- v0.10.1: MCP enforcement gateway và external signed audit.
- v0.9.0: trust-boundary hardening, guarded execution token, provenance.
- v0.8.1: workflow checklist, drift detection, safe installer.
- v0.7.x: documentation governance, index/cache, evidence claims.
<!-- AGENTOS_VERSION_HISTORY_END -->

---

# English

## 1. Overview

AgentOS Local Governance is a repository-local governance and enforcement layer for coding agents. Version 0.13.0 adds concurrent work coordination so multiple CLI processes and agents can operate at the same time without silently overwriting one another.

## 2. Concurrent coordination model

The model combines:

- session-scoped task context;
- single-writer task ownership;
- expiring resource leases;
- optimistic concurrency through expected hashes;
- crash-safe atomic replacement;
- file version history;
- explicit task handoff;
- SQLite WAL and immediate write transactions;
- serialized external audit through one daemon in multi-process deployments.

## 3. Required write flow

```text
read file → receive content_hash
→ request write with expected_hash
→ proxy acquires exclusive lease
→ compare current hash
→ write temporary file + fsync
→ atomic replace
→ record version
→ release lease
```

A stale expected hash produces a structured conflict instead of an overwrite.

## 4. Session isolation

Every concurrent CLI or agent must use a unique session identifier:

```bash
export AGENTOS_SESSION_ID=AGENT-A
```

Do not share one session ID between simultaneous processes.

## 5. Resource lease commands

```bash
agentos acquire-resource --task-id TASK-A --type file --resource src/a.py --mode exclusive_write
agentos heartbeat-resource --task-id TASK-A --lease-id 42
agentos release-resource --task-id TASK-A --lease-id 42
agentos list-resources --task-id TASK-A
```

## 6. Task ownership and handoff

```bash
agentos claim-task --task-id TASK-A
agentos handoff-task --task-id TASK-A --from-session AGENT-A --to-session AGENT-B --note "Reviewed handoff"
```

## 7. Deployment requirements

For a real enforcement boundary:

- expose only the AgentOS MCP gateway to the agent;
- do not expose raw filesystem, shell, or network tools;
- use a unique session ID per process;
- require expected hashes for existing-file writes;
- use the audit daemon when multiple proxies run concurrently;
- keep signing keys and audit storage outside the agent's write permissions.

## 8. Validation

```bash
agentos doctor --scope .agents/agentos
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

## 9. Limitations

AgentOS is not an operating-system sandbox or a distributed lock service. Network filesystems and agents with unrestricted shell/database access remain outside the guaranteed trust boundary.
