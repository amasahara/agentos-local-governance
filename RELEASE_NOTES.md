# AgentOS Local Governance v0.27.3 — Isolated Workspace & Controlled Integration

## 🇻🇳 Tiếng Việt

v0.27.3 mở rộng **Multi-Agent Worker Supervisor** bằng isolated Git worktree cho executor worker và pipeline **Controlled Integration** có human review/approval.

### Điểm chính

- Schema **60 → 61**.
- Executor worker được bind vào detached Git worktree riêng theo đúng worker `task_id + session_id`.
- AgentOS state, policy, leases và signed audit vẫn dùng primary repository; không tạo state DB riêng trong worktree.
- Governed filesystem read/write và process/test execution được route vào worktree của đúng worker.
- Executor worker fail-closed nếu workspace bắt buộc nhưng chưa được provision.
- Worker write không chạm primary tree trước controlled integration.
- Diff collection pin path/change type/base SHA-256/workspace SHA-256; raw source không persist trong supervisor DB/audit.
- Changed files phải nằm trong worker plan; symlink change mặc định bị block.
- Workspace seal yêu cầu immutable diff + architecture PASS + security/quality PASS + governed test receipt PASS.
- Conflict analysis dùng Git semantic diff so với pinned `base_commit`, tránh false conflict do CRLF/LF hoặc clean/smudge normalization; raw SHA-256 vẫn là evidence/CAS metadata.
- Integration proposal có lifecycle `draft → reviewed → approved → applied/rejected/failed`.
- Human review + approval bắt buộc.
- Apply yêu cầu parent task/session authority, parent scope, file leases, hash/CAS check, backup manifest/bytes local dưới `.agents/runtime`, và rollback.
- Không gọi `git merge`, không auto-commit, không auto-push và không auto-resolve conflict.
- MCP chỉ thêm 4 read-only inspection tools; không có integration mutation authority.

### Schema 61

```text
multi_agent_workspaces
multi_agent_workspace_files
multi_agent_workspace_file_versions
multi_agent_integration_proposals
multi_agent_integration_events
```

### CLI mới

11 commands mới; expected unified count **320 → 331**.

### MCP read-only mới

4 tools mới; expected catalog **116 → 120**.

### Focused validation của development patch

```text
12 focused tests (run required on target checkout)
Python compile: PASS
real temporary Git worktree lifecycle: PASS
primary isolation before integration: PASS
plan containment: PASS
seal gates: PASS
conflict detection: PASS
human review/approval: PASS
controlled apply without git merge: PASS
local backup manifest/bytes: PASS
development helper dry-run/apply/rollback fixture: PASS
```

Đây chưa phải tuyên bố full historical regression. Checkout v0.27.2 thực tế phải chạy toàn bộ `.agents/tests`, docs/release/runtime/manifest gates trước khi materialize final v0.27.3 release.

---

## 🇬🇧 English

v0.27.3 extends the **Multi-Agent Worker Supervisor** with isolated detached Git worktrees and a human-gated **Controlled Integration** pipeline.

- Schema **60 → 61**.
- Exact worker task/session ownership routes filesystem/process execution into a dedicated worktree.
- Primary AgentOS remains the sole state/policy/lease/audit authority.
- Diffs are hash-only state, constrained to the worker plan.
- Sealing requires immutable diff, architecture/security gates, and a successful governed test receipt.
- Primary drift produces conflicts and never auto-resolves.
- Integration requires human review and approval plus parent-task scope, leases, CAS/hash checks, local backup manifest/bytes, and rollback.
- AgentOS never invokes `git merge`, auto-commit, auto-push, or automatic conflict resolution.
- 11 CLI commands are added (expected total **331**); 4 read-only MCP tools are added (expected total **120**).

The development bundle is not a full-release claim until the real v0.27.2 checkout passes the complete historical regression and release gates.
