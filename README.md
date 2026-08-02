# AgentOS Local Governance v0.19.5

**Quản trị local-first, MCP proxy-only và điều phối nhiều agent cho dự án phần mềm.**  
**Local-first governance, proxy-only MCP enforcement, and concurrent-agent coordination.**

> Phiên bản hiện tại: `v0.19.5`  
> Current version: `v0.19.5`  
> Database schema: `31`
> Trạng thái: active development; cần review trước khi dùng cho production hoặc môi trường bảo mật cao.

---

# Tiếng Việt

## 1. AgentOS là gì?

AgentOS Local Governance là nền tảng quản trị và thực thi cục bộ cho coding agent. Phiên bản v0.19.5 hợp nhất Security Foundation, Knowledge Runtime, Execution Platform, Controlled Evolution, Multi-Agent Protocol, Transparent Context Compaction, Skill Promotion, Local Semantic Retrieval, Optional Local RAG và Evidence-Backed Relationship Graph trong cùng một enforcement boundary có audit ký ngoài.

AgentOS không phải LLM hay IDE. Hệ thống cung cấp gateway, capability session, isolated execution, context/memory có provenance, async jobs, planning/Git gates, evaluation harness, phối hợp nhiều agent theo role/context isolation, skill có human approval, truy hồi local thống nhất và graph quan hệ chỉ dựa trên evidence. Mức bảo đảm thực tế phụ thuộc security profile và quyền hệ điều hành được cấu hình.

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

## 3. Năng lực chính của v0.19.5

### v0.17.2–v0.19.5 — Knowledge Runtime fixes và Transparent Context Compaction

- `filesystem.read` dùng cache theo task/path/range và tự invalidation khi file thay đổi.
- Multi-agent disclosure thực sự lọc payload theo `metadata-only`, `summary`, `selected-artifacts`, `full-task-context`.
- Context pack xếp hạng file/symbol bằng tín hiệu cấu trúc cục bộ, nén theo symbol window, giới hạn ngân sách toàn cục/từng file và báo rõ `omitted_files`, `omitted_symbols`, `approx_tokens`.
- `context-compare` so sánh `flat_lines` và `symbol_window` mà không gọi LLM hoặc network.


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

- capability session được gateway cấp phát, hash, revoke và chống replay;
- task owner session và role `executor`, `reviewer`, `planner`, `observer`;
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
- structured messages có correlation/causation ID và disclosure level;
- collaboration readiness gate yêu cầu capability, role và context pack còn mới.


### v0.18.1–v0.19.5 — Skill Promotion và Local Semantic Retrieval

- Procedural memory có provenance có thể được promote thành skill candidate.
- Candidate không được tự động kích hoạt; graduation bắt buộc human approval và signed audit.
- Graduated skill được version, match, revoke và drift-track trong `.agents/skills/`.
- `knowledge-search` cung cấp abstraction thống nhất cho memory, findings, symbols và skills.
- Backend mặc định `lexical_structured` chạy hoàn toàn local, không dùng LLM/network; interface sẵn sàng cho local embeddings sau này.

Các lệnh chính:

```bash
agentos skill-promote --memory-id 42 --promoted-by AGENT-A
agentos skill-graduate --skill-id 7 --approved-by human_reviewer --note "Đã xác minh"
agentos skill-match "convert excel date"
agentos knowledge-search "convert excel date" --kinds '["memory","symbol","skill"]'
```

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
- symbol leases: mặc định tắt trong policy hiện hành; file-level locking vẫn là cơ chế ghi chính.

Symbol/line-range parallel editing chỉ nên bật khi có patch-range validation và conflict reconciliation phù hợp.

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

Policy hiện hành dùng một audit sink tuần tự cho multi-process. Daemon cấp sequence, nối previous hash, ký và append tuần tự; hardened deployments nên chạy daemon bằng identity riêng.

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

v0.19.5 có isolated execution, capability sessions, bounded RAG và evidence-backed graph nhưng không thay thế hardening cấp hệ điều hành. Agent có raw shell, quyền sửa SQLite, truy cập gateway socket hoặc signing key vẫn có thể làm suy yếu enforcement. Để enforcement có ý nghĩa:

- agent chỉ được dùng MCP proxy;
- backend credential thuộc proxy/daemon;
- audit daemon chạy bằng account riêng;
- signing key nằm ngoài repository;
- production nên dùng container, read-only mount hoặc OS sandbox bổ sung.

## 22. Nâng cấp lên v0.19.5

1. Sao lưu `.agents/state`, audit store và public-key registry.
2. Thay hoặc merge `.agents/`, `AGENTS.md`, `README.md`, `huong_dan.md` và `VERSION`.
3. Chạy `db-migrate` rồi xác nhận schema `23`.
4. Khởi động gateway và kiểm tra capability-session/revocation.
5. Tạo context pack mới; validate project memory và stale sources.
6. Kiểm tra async jobs, active plan, pre-commit gate và evaluation baseline.
7. Chỉ bật controlled evolution sau evaluation; chỉ bật multi-agent messaging khi readiness gate đạt.
8. Chạy `doctor`, `docs-check`, `instruction-check`, `audit-verify` và toàn bộ test.

<!-- AGENTOS_VERSION_HISTORY_BEGIN -->
## 23. Lịch sử phiên bản rút gọn

- v0.17.0–v0.17.1: Controlled Evolution và Multi-Agent Protocol.
- v0.16.0–v0.16.2: Execution Platform.
- v0.15.0–v0.15.1: Knowledge Runtime.
- v0.14.0–v0.14.3: Security Foundation.
- v0.13.1: bản vá bảo mật tương thích.
- v0.13.0: coordination enforcement boundary.
- v0.11.0: process/domain hardening, key rotation, audit daemon.
- v0.10.1: MCP enforcement gateway và external signed audit.
- v0.9.0: trust-boundary hardening, guarded execution token, provenance.
- v0.8.1: workflow checklist, drift detection, safe installer.
- v0.7.x: documentation governance, index/cache, evidence claims.
<!-- AGENTOS_VERSION_HISTORY_END -->

---

# English

## 1. Overview

AgentOS Local Governance v0.19.5 is a repository-local governance and execution platform for coding agents. It combines a hardened gateway, capability sessions, isolated execution, verifiable state, context and project memory, asynchronous jobs, planning/Git gates, evaluation-driven controlled evolution, and role-authorized multi-agent collaboration with context isolation.

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

AgentOS includes isolated execution adapters but is not a substitute for a hardened operating-system security boundary. Deployments that give agents unrestricted shell, database, gateway-socket, or signing-key access remain outside the guaranteed trust boundary.

## Knowledge Runtime v0.15.0–v0.15.1

- `context-build`, `context-status`, `context-explain`: tạo context pack xác định, giới hạn dòng, có content hash và phát hiện stale source.
- `memory-record`, `memory-query`, `memory-validate`: quản lý semantic/episodic/procedural/evidence memory có provenance.
- `finding-record`: gom finding lặp lại bằng khóa ổn định và tăng `occurrences`.
- Schema at that milestone: `18`.

## Knowledge Runtime v0.15.0–v0.15.1 (English)

Deterministic context packs, stale-source detection, provenance-aware project memory, and recurring-finding deduplication are now available. Schema at that milestone: `18`.

## Lộ trình phát hành / Release programs

- **v0.13.1 — Immediate Security Fixes:** bản vá nhỏ, nhanh và tương thích.
- **v0.14.0–v0.14.3 — Security Foundation Program:** gateway boundary, capability sessions, isolated execution, verifiable state và recovery.
- **v0.15.0–v0.15.1 — Knowledge Runtime:** deterministic context packs và project memory có provenance.
- **v0.16.0–v0.16.2 — Execution Platform:** async jobs, workflow-aware tool discovery, versioned planning, Git pre-commit gate và evaluation harness.
- **v0.17.0–v0.17.1 — Controlled Evolution & Multi-Agent Protocol:** evolution dựa trên evaluation baseline; collaboration bị ràng buộc bởi capability, role và context isolation.
- **v0.17.2–v0.18.0 — Knowledge Runtime Fixes & Transparent Context:** read cache, disclosure filtering, symbol-window compaction, budgets và omission reporting.
- **v0.18.1–v0.18.2 — Skill Promotion & Local Retrieval:** skill graduation có human approval và retrieval abstraction thống nhất.
- **v0.19.0–v0.19.5 — Optional Local RAG & Relationship Graph:** semantic retrieval/RAG cục bộ tùy chọn và graph quan hệ có bằng chứng cho use case cụ thể.

### v0.16.0 — Async Tool Runtime

- Job specification bất biến, trạng thái `queued/running/succeeded/failed/cancelled/orphaned`.
- `job-submit`, `job-status`, `job-cancel`, `job-recover`.
- `tools-discover` phân nhóm tool đang dùng được, tool cần bước tiếp theo và human-only tool.
- MCP bổ sung `agentos.run_command_async`.

### v0.16.1 — Planning and Git Integration

- Task plan có revision và lifecycle `submitted → active → superseded`.
- `plan-submit`, `plan-approve`, `plan-show`.
- `precommit-check` đối chiếu Git diff với approved scope, active plan và workflow provenance.

### v0.16.2 — Evaluation Harness

- Metrics versioned cho task, workflow, write blocks, evidence và async jobs.
- Xuất JSON/CSV bằng `evaluation-report`.
- Dimension so sánh gồm agent, model, policy version và repository version.

**Schema at the v0.16.2 milestone: `21`.**

### English summary

v0.16.0–v0.16.2 delivers the Execution Platform: governed asynchronous jobs, workflow-aware tool discovery, revisioned task plans, Git-aware pre-commit enforcement, and a versioned evaluation harness with JSON/CSV export.

## v0.17.0–v0.17.1 — Adaptive Multi-Agent Platform

### Tiếng Việt

**v0.17.0 — Controlled Evolution** chỉ hoạt động khi đã có kết quả từ Evaluation Harness. Mọi đề xuất policy phải đi qua chuỗi `draft → simulated → reviewed → shadow → canary → active`; hệ thống không tự kích hoạt và luôn lưu rollback plan cùng signed audit.

**v0.17.1 — Multi-Agent Protocol** chỉ bật khi capability session, task role và context isolation đều ổn định. Message có schema, correlation/causation ID, quyền theo role và mức disclosure `metadata-only`, `summary`, `selected-artifacts`, hoặc `full-task-context`.

```bash
agentos evaluation-report
agentos evolution-propose --title "..." --patch '{}' --benefit "..." --rollback '{}' --created-by operator
agentos evolution-simulate --proposal-id 1
agentos evolution-transition --proposal-id 1 --status reviewed --actor operator --note "Reviewed"
agentos role-assign --task-id T1 --target-session REVIEWER --role reviewer --assigned-by operator
agentos collaboration-readiness --task-id T1
agentos message-send --task-id T1 --to-session EXECUTOR --kind review_request --payload '{}'
```

### English

**v0.17.0 — Controlled Evolution** requires an Evaluation Harness baseline. Every policy proposal follows `draft → simulated → reviewed → shadow → canary → active`; automatic activation is forbidden, and rollback plus signed audit provenance are mandatory.

**v0.17.1 — Multi-Agent Protocol** is enabled only after capability sessions, task roles, and context isolation are stable. Messages are schema-versioned, correlated, role-authorized, and disclosure-bounded.

### Release program history

- v0.13.1: small, fast, backward-compatible security patch.
- v0.14.0–v0.14.3: unified Security Foundation program.
- v0.15.0–v0.15.1: Knowledge Runtime.
- v0.16.0–v0.16.2: Execution Platform.
- v0.17.0–v0.17.1: Controlled Evolution and Multi-Agent Protocol.
- v0.17.2–v0.18.0: Knowledge Runtime fixes and Transparent Context Compaction.
- v0.18.1–v0.18.2: Skill Promotion Runtime and Local Semantic Retrieval Abstraction.
- v0.19.0–v0.19.5: Optional Local Embeddings/RAG and Evidence-Backed Relationship Graph.

Current database schema: `31`.


## v0.17.2–v0.18.0 — Knowledge Runtime fixes and Transparent Context Compaction

v0.17.2–v0.18.0 added validated file-read caching, enforced collaboration disclosure filtering, deterministic symbol-window context compaction, global/per-file budgets, omission reasons, approximate token reporting, and context mode comparison. v0.18.1–v0.18.2 added skill promotion and unified local retrieval. v0.19.0–v0.19.5 adds optional local RAG and an evidence-backed relationship graph. Database schema is now 27.

## v0.19.0–v0.19.5 — Optional Local RAG and Relationship Graph

### Tiếng Việt

`v0.19.0` bổ sung embeddings/RAG cục bộ **tùy chọn**. Backend mặc định vẫn là `lexical_structured`; backend `local_feature_hash_v1` dùng feature hashing xác định, không tải model, không gọi mạng và không gọi LLM.

```bash
agentos embedding-index
agentos knowledge-search "excel date conversion" --backend local_feature_hash_v1
agentos rag-query "how to validate release" --top-k 8
```

`v0.19.5` chỉ xây relationship graph cho các use case đã xác định: impact analysis, finding-to-symbol và skill provenance. Hệ thống không cố tạo knowledge graph tổng quát hoặc suy diễn quan hệ không có bằng chứng.

```bash
agentos graph-build
agentos graph-neighbors --node-id "skill:1"
agentos graph-path --from-node "skill:1" --to-node "memory:42"
```

Schema hiện hành: `31`.

### English

`v0.19.0` adds optional local embeddings and RAG. `lexical_structured` remains the default; `local_feature_hash_v1` is deterministic and dependency-free, with no model download, network call, LLM call, or API key.

`v0.19.5` materializes only evidence-backed relationships for concrete use cases: impact analysis, finding-to-symbol navigation, and skill provenance. It intentionally does not create a speculative general-purpose knowledge graph.

## v0.19.2–v0.19.5 — Unified Context, Evaluation, Privacy, Storage

- **v0.19.2 Unified Context Knowledge:** context pack hợp nhất graduated skills, verified project memory và findings vào cùng ngân sách; lexical-first, semantic fallback theo ngưỡng; báo cáo `omitted_knowledge`, fallback và merge errors.
- **v0.19.3 Context/Outcome Evaluation:** ghi outcome nhẹ theo task, cohort metadata, Wilson confidence interval và two-proportion comparison có cảnh báo mẫu nhỏ.
- **v0.19.4 Memory Scope and Privacy:** project/user scope, explicit consent, sensitivity, TTL/decay và right-to-forget xóa derived embeddings.
- **v0.19.5 Storage and Recovery Hardening:** embedding BLOB versioned, retention cho observability, verified audit segment archive không phá hash chain, backup manifest và verification.

### English

- **v0.19.2 Unified Context Knowledge:** merges graduated skills, verified memory, and findings into the bounded transparent context budget.
- **v0.19.3 Context/Outcome Evaluation:** adds lightweight outcomes, cohort metadata, confidence intervals, and small-sample warnings.
- **v0.19.4 Memory Scope and Privacy:** adds scoped memory, explicit consent, decay, and right-to-forget with derived embedding invalidation.
- **v0.19.5 Storage and Recovery Hardening:** adds versioned BLOB embeddings, retention, verified audit segment archives, and backup verification.
