# AgentOS v0.27.2 — Multi-Agent Worker Supervisor

## Mục tiêu

v0.27.2 bổ sung một **supervision plane** cho nhiều AI worker nhưng không tạo execution authority mới. Supervisor chỉ điều phối những primitive AgentOS đã có: approved tasks, active architecture-aware plans, capability sessions, collaboration roles, resource/task ownership, Governed Skill Contract v2 và v0.27.1 skill selection.

Nguyên tắc trung tâm:

> Supervisor decides **who may be ready next**. Existing AgentOS governance still decides **what may execute and write**.

## Baseline

- Release đầu vào: **v0.27.1 — Architecture-Aware Skill Selection & Evaluation**.
- Schema đầu vào: **59**.
- v0.27.1 selection vẫn advisory; supervisor không biến skill recommendation thành execution authority.
- `task_single_writer=true` tiếp tục là concurrency invariant.
- Workspace/worktree isolation và controlled integration **không** thuộc node này; chúng vẫn dành cho v0.27.3.

## Topology

```text
Human-approved parent task + ACTIVE plan
                │
                ▼
        Multi-Agent Supervisor
                │
       ┌────────┼─────────┐
       ▼        ▼         ▼
   Worker A  Worker B  Worker C
   task A    task B    task C
   plan A    plan B    plan C
   session A session B session C
       │        │         │
       └────────┴─────────┘
                │
        existing AgentOS gates
                │
      capability / lease / write
      architecture / tests / audit
```

Parent task là orchestration envelope. Mỗi write worker phải dùng **worker task riêng** và **session riêng**; nhiều worker không được cùng sở hữu một task để tránh phá `task_single_writer`.

## Authority invariants

v0.27.2 fail-closed với các authority sau:

1. Không tự tạo task.
2. Không tự approve task.
3. Không tự tạo/approve plan.
4. Không tự cấp capability session.
5. Không tự tạo collaboration role.
6. Không tự execute skill.
7. Không tự chọn model/provider.
8. Không tự launch subprocess/worker process.
9. Không mở rộng file/architecture envelope của parent plan.
10. Không cho hai executor đồng thời sở hữu cùng planned write target.
11. Không cho dependency graph có cycle.
12. Không thêm MCP mutation authority.
13. Không tạo worktree/workspace isolation hoặc merge authority trước v0.27.3.

## Worker binding

Một worker assignment hợp lệ phải pin:

```text
supervisor_id
worker_key
task_id
plan_id
plan_hash
architecture_baseline_hash
session_id
role
capability_set_hash
optional selection_run_id
optional skill_id
assignment_hash
```

Raw capability token không được lưu vào supervisor tables. MCP output chỉ trả `session_id_hash`, không trả session id thô.

### Existing task required

Worker task phải:

- tồn tại;
- đã `approved=1`;
- khác parent task;
- có ACTIVE plan;
- plan vẫn current với Architecture Baseline;
- nếu task đã có owner session thì owner phải đúng worker session.

### Parent plan envelope

Worker plan bắt buộc là subset của parent plan:

```text
worker.expected_files ⊆ parent.expected_files
worker.affected_architecture_sections ⊆ parent.affected_architecture_sections
```

Nếu worker cần file/section ngoài parent envelope, phải sửa/reapprove plan ở authority layer hiện hữu thay vì supervisor tự mở scope.

### Capability + role

Worker session phải là active capability session của đúng worker task. Role phải là active `task_role_assignments` role và thuộc role registry hiện tại:

```text
executor
reviewer
planner
observer
```

Capability set được hash tại lúc bind. Nếu capability session bị revoke hoặc capability set thay đổi, readiness trở thành stale.

### Optional skill binding

Supervisor có thể pin một skill đã được v0.27.1 selection đánh giá, nhưng chỉ khi:

- selection run thuộc đúng worker task/plan/hash;
- architecture baseline hash khớp;
- candidate `eligible=1` và `recommendable=1`;
- skill là `graduated` Contract v2;
- contract và validation đều `valid`;
- candidate contract hash vẫn khớp contract hiện tại.

Supervisor **không** execute skill.

## DAG scheduling

Dependency graph được lưu explicit:

```text
worker-b depends_on worker-a
worker-c depends_on worker-a
```

Cycle bị chặn ngay khi add dependency.

Một worker chỉ được trả về trong `runnable_workers` khi:

- supervisor đang ACTIVE;
- worker status là `ready`;
- worker plan/session/role/skill binding vẫn fresh;
- mọi dependency đã `completed`.

`worker_start` chỉ đổi state sang `running`; nó **không tạo process**.

## Planned write overlap

Trước activation, supervisor so sánh planned file targets giữa các worker role `executor` còn non-terminal.

```text
Executor A → src/orders.py
Executor B → src/orders.py
```

Kết quả:

```text
overlapping_executor_write_targets
→ BLOCK activation
```

Đây là preflight. Runtime resource leases và stale-write protection hiện hữu vẫn là enforcement authority ở lúc write thật.

## Lifecycle

```text
draft
  │ add workers / dependencies
  ▼
ACTIVE ───────────────► completed
  │                       ▲
  │ pause                 │ all workers completed
  ▼                       │
paused ───── activate ────┘
  │
  └────────► cancelled
```

Worker lifecycle:

```text
registered
   ↓ supervisor activation
ready
   ↓ owner task/session starts assignment
running
   ├── completed
   ├── failed
   └── blocked
```

`failed`/`blocked` đưa effective supervisor state về `blocked`. Supervisor không tự repair/retry worker.

## Schema 60

Migration additive:

```text
multi_agent_supervisor_runs
multi_agent_workers
multi_agent_worker_dependencies
multi_agent_supervisor_events
```

Signed external audit được nối với mutation events; local event state giữ hash/provenance, không lưu raw user request.

## CLI v0.27.2

Mười command mới:

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

Tám mutation commands phải được thêm vào unified `PRIVILEGED_COMMANDS` để giữ task/session context boundary. Hai status commands là read-only.

## MCP v0.27.2

Chỉ thêm ba tool read-only:

```text
agentos.multi_agent_supervisor_status_get
agentos.multi_agent_supervisor_workers_get
agentos.multi_agent_supervisor_readiness_get
```

Không expose:

```text
create
worker-add
dependency-add
activate
pause
cancel
worker-start
worker-update
process launch
skill execution
model/provider selection
```

Nếu baseline MCP catalog là 113 tools, integration dự kiến thành **116** tools.

## CLI/MCP expected counts

Baseline v0.27.1 có 310 CLI commands. Node này thêm 10 unique commands nên expected registry sau integration là **320**.

Baseline v0.27.1 có 113 MCP tools. Node này thêm 3 read-only tools nên expected catalog là **116**.

Các số này phải được xác minh lại bằng runtime-health/mcp-health trên full checkout; không được hard-code như release proof.

## Boundary với v0.27.3

v0.27.2 cố ý **không** giải quyết:

- Git worktree per worker;
- isolated source workspace;
- diff collection;
- integration queue;
- cross-worker merge/conflict resolution;
- controlled merge into primary tree.

Những phần này thuộc **v0.27.3 — Isolated Workspace & Controlled Integration**.

## Validation contract

Node-level tests phải kiểm tra tối thiểu:

- schema 60 additive tables;
- human activation requirement;
- approved/current parent + worker plans;
- parent file/architecture envelope;
- task owner/session binding;
- distinct worker sessions;
- active capability session and role;
- optional current v0.27.1 skill selection binding;
- overlap block;
- cycle block;
- DAG runnable ordering;
- revoked session → stale;
- zero subprocess/model-provider authority;
- exactly 10 CLI commands;
- exactly 3 read-only MCP tools.

Final release chỉ được tuyên bố hoàn tất sau khi full v0.27.1 checkout chạy lại toàn bộ regression, docs-check, release-integrity, manifest build/verify và runtime health.
