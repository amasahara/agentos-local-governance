# AgentOS Local Governance v0.27.2 — Multi-Agent Worker Supervisor

## 🇻🇳 Tiếng Việt

v0.27.2 bổ sung **Multi-Agent Worker Supervisor** để điều phối nhiều AI worker trên cùng project mà không tạo một execution authority thứ hai.

### Điểm chính

- Schema **59 → 60**.
- Parent task + ACTIVE architecture-aware plan trở thành orchestration envelope.
- Mỗi worker bind vào một **approved worker task riêng**, active plan, session, role và capability set hiện hữu.
- Worker plan phải nằm trong parent file/architecture envelope.
- Distinct worker sessions được enforcement; task owner đã tồn tại phải khớp worker session.
- Dependency graph là DAG; cycle fail-closed.
- Executor planned write targets trùng nhau block activation trước khi chạm write boundary.
- Worker freshness được re-check trên active plan, capability session, role và optional v0.27.1 skill-selection binding.
- Skill binding chỉ pin current `graduated` Contract-v2 candidate đã `eligible + recommendable`; supervisor không execute skill.
- `worker_start` chỉ chuyển state sang `running`; **không launch process**.
- Không tự tạo/approve task, plan, capability, architecture hay skill lifecycle.
- Không chọn model/provider.
- Không tạo worktree hoặc merge; workspace isolation/controlled integration vẫn thuộc v0.27.3.
- Signed audit được giữ cho supervisor mutation events.

### Schema 60

```text
multi_agent_supervisor_runs
multi_agent_workers
multi_agent_worker_dependencies
multi_agent_supervisor_events
```

### CLI mới

```text
multi-agent-supervisor-create
multi-agent-supervisor-worker-add
multi-agent-supervisor-dependency-add
multi-agent-supervisor-activate
multi-agent-supervisor-pause
multi-agent-supervisor-cancel
multi-agent-worker-start
multi-agent-worker-update
multi-agent-supervisor-status
multi-agent-supervisor-workers
```

Expected unified CLI count sau integration từ baseline v0.27.1: **310 → 320**.

### MCP read-only mới

```text
agentos.multi_agent_supervisor_status_get
agentos.multi_agent_supervisor_workers_get
agentos.multi_agent_supervisor_readiness_get
```

Không có MCP mutation authority cho supervisor. Expected MCP catalog từ baseline v0.27.1: **113 → 116**.

### Concurrency model

v0.27.2 không cho nhiều executor dùng chung một task để lách `task_single_writer`. Mô hình đúng là:

```text
Parent task / parent plan
          ↓
      Supervisor
   ┌──────┼──────┐
   ↓      ↓      ↓
Task A  Task B  Task C
Session A/B/C distinct
```

Runtime resource leases và stale-write protection hiện hữu tiếp tục là write authority.

### Validation của development patch

Development patch đã chạy focused supervisor tests trong representative SQLite runtime bám các schema contract v0.27.1 mà node sử dụng:

```text
11 passed
Python compile: PASS
```

Không tuyên bố full historical regression của repository đã chạy trong môi trường tạo patch, vì full v0.27.1 checkout không materialize được tại runtime này. Final release phải chạy toàn bộ tests + docs/release/manifest gates trên checkout thật.

### Distribution

Final v0.27.2 tiếp tục **Latest Full Release / no updater script**. File `apply_v0272_dev_patch.py` trong development bundle chỉ là helper ngoài release để materialize thay đổi lên checkout v0.27.1; **không được ship trong final release payload**.

---

## 🇬🇧 English

v0.27.2 adds a **Multi-Agent Worker Supervisor** that coordinates multiple AI workers without introducing a second execution authority.

### Highlights

- Schema **59 → 60**.
- The approved parent task and ACTIVE architecture-aware plan form the orchestration envelope.
- Every worker binds to a distinct existing approved worker task, active plan, session, role, and capability set.
- Worker plans must remain inside the parent file and architecture-section envelope.
- Worker sessions are distinct and existing task ownership must match the assigned session.
- Dependencies form an explicit DAG; cycles fail closed.
- Overlapping planned executor write targets block supervisor activation.
- Plan/session/role/optional v0.27.1 skill-selection freshness is revalidated.
- Optional skill binding only pins a current graduated Contract-v2 eligible/recommendable candidate; it never executes the skill.
- `worker_start` changes state only and **does not launch a process**.
- No automatic task/plan/capability/architecture approval, skill lifecycle mutation, or model/provider selection is introduced.
- Worktree isolation and controlled integration remain reserved for v0.27.3.
- Supervisor mutation events retain signed-audit linkage.

### Schema 60

```text
multi_agent_supervisor_runs
multi_agent_workers
multi_agent_worker_dependencies
multi_agent_supervisor_events
```

### New CLI

Ten commands are added, for an expected full registry count of **320** from the v0.27.1 baseline of 310.

### New read-only MCP

```text
agentos.multi_agent_supervisor_status_get
agentos.multi_agent_supervisor_workers_get
agentos.multi_agent_supervisor_readiness_get
```

No supervisor mutation is exposed over MCP. Expected catalog: **116** from the v0.27.1 baseline of 113.

### Development-patch validation

Focused supervisor tests passed in a representative SQLite runtime using the v0.27.1 contracts consumed by this node:

```text
11 passed
Python compile: PASS
```

This is not a claim that the complete historical repository regression suite was run. Final release materialization must rerun the full suite and all documentation, release-integrity, manifest, and runtime-health gates on a real v0.27.1 checkout.
