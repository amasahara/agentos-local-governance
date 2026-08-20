# AgentOS v0.27.3 — Isolated Workspace & Controlled Integration

## Mục tiêu

v0.27.3 mở rộng Multi-Agent Worker Supervisor bằng workspace/worktree tách biệt cho executor worker và một pipeline integration có kiểm soát. Release này không cấp merge authority cho AI và không tạo execution authority thứ hai.

```text
PRIMARY REPOSITORY / AgentOS state
          │
          ├── Supervisor / leases / audit / policy
          │
          ├── Worker A task/session ──> detached worktree A
          ├── Worker B task/session ──> detached worktree B
          └── Worker C task/session ──> detached worktree C
                                      │
                                      ↓
                              diff/hash collection
                                      ↓
                         architecture + security gate
                                      ↓
                          governed test receipt gate
                                      ↓
                             conflict analysis
                                      ↓
                         integration proposal (draft)
                                      ↓
                            HUMAN REVIEW + APPROVAL
                                      ↓
                         parent-task controlled apply
```

## Invariant bắt buộc

1. Executor worker của supervisor không được ghi trực tiếp vào primary tree khi policy v0.27.3 đang bật.
2. Workspace được bind theo đúng `task_id + session_id`; workspace của worker khác không thể được route nhầm.
3. Git worktree nằm ngoài primary repository; `.agents/state` và governance database vẫn chỉ thuộc primary AgentOS.
4. Worker changes phải là subset của worker plan; worker plan vẫn là subset của parent plan theo v0.27.2.
5. Diff persistence chỉ giữ path, change type, size và SHA-256; không persist raw source content vào supervisor state/audit.
6. Workspace sau khi `sealed` là read-only.
7. Seal yêu cầu diff hiện tại không đổi, architecture gate PASS, security/quality gate PASS và governed test receipt PASS.
8. Integration proposal chỉ được tạo từ worker `completed` + workspace `sealed`.
9. Conflict được re-check so với primary ngay trước review/approval/apply và sau khi giữ toàn bộ file leases.
10. Apply sử dụng parent task/session authority, parent scope gate, file leases, CAS/hash verification, backup và rollback.
11. AgentOS không chạy `git merge`, không auto-commit và không tự approve integration.
12. MCP chỉ expose trạng thái/readiness; create/review/approve/reject/apply không được expose qua MCP.

## Schema 61

Bổ sung additive state:

```text
multi_agent_workspaces
multi_agent_workspace_files
multi_agent_workspace_file_versions
multi_agent_integration_proposals
multi_agent_integration_events
```

`multi_agent_workspaces` pin worker, task/session, base commit và trạng thái workspace. `multi_agent_workspace_files` pin base/workspace SHA-256 cho từng changed path. Proposal pin exact `diff_manifest_hash` và gate states.

## Workspace routing boundary

v0.27.3 nối trực tiếp vào governed proxy:

```text
agentos.read_file
agentos.write_file
agentos.run_command
        │
        ↓
exact task/session workspace lookup
        │
   ┌────┴─────┐
   │          │
worker     non-worker
executor      task
   │          │
worktree   primary root
```

Khi task/session thuộc executor worker và policy v0.27.3 bật nhưng chưa có workspace, filesystem/process route fail-closed với `executor_workspace_binding_required`.

Workspace write vẫn dùng resource lease/CAS authority trong primary AgentOS; chỉ physical file target được chuyển sang worktree.

## Diff collection

Collection dùng Git metadata từ detached worktree:

```text
git diff --name-status --no-renames -z <base_commit>
git ls-files --others --exclude-standard -z
```

Các path ngoài worker plan bị block. Symlink change mặc định bị block. Raw source không được ghi vào SQLite/audit; chỉ hash/metadata được giữ.

## Candidate gates trước integration

Trước seal, AgentOS chạy lại deterministic candidate checks trên chính workspace candidate:

- Structural Architecture checks.
- Quality/Security/Operational static checks.
- Governed test receipt từ `process_exec_events`, yêu cầu profile `test`, `decision=allowed`, `success=1` và receipt không cũ hơn diff collection.

Không có LLM heuristic trở thành architecture/security authority.

## Conflict analysis

Mỗi workspace pin `base_commit`; mỗi changed file vẫn giữ SHA-256 làm evidence/CAS metadata. Trước integration, conflict authority dùng Git semantics:

```text
ADD           → primary target phải absent
MODIFY/DELETE → git diff --quiet --no-ext-diff --no-textconv <base_commit> -- <path> phải clean
```

Cách này tôn trọng Git clean/smudge và EOL normalization, nên một Windows worktree CRLF không bị coi là drift giả khi canonical Git blob là LF. Raw SHA-256 vẫn được giữ làm evidence nhưng không còn là cross-platform conflict authority. Git semantic mismatch trả conflict và block review/approval/apply; AgentOS không tự resolve conflict.

## Controlled Integration lifecycle

```text
sealed workspace
      ↓
DRAFT proposal
      ↓
HUMAN REVIEW
      ↓
HUMAN APPROVAL
      ↓
parent task/session scope validation
      ↓
acquire all file leases
      ↓
conflict recheck
      ↓
backup current primary files
      ↓
atomic replace/delete
      ↓
APPLIED
```

Lỗi giữa apply sẽ rollback từ backup local. AgentOS không gọi Git merge và không tự tạo commit.

## CLI v0.27.3

```text
multi-agent-workspace-provision
multi-agent-workspace-collect
multi-agent-workspace-seal
multi-agent-workspace-release
multi-agent-workspace-status
multi-agent-integration-proposal-create
multi-agent-integration-proposal-review
multi-agent-integration-proposal-approve
multi-agent-integration-proposal-reject
multi-agent-integration-apply
multi-agent-integration-status
```

Expected unified registry: **331 commands** sau khi tích hợp trên v0.27.2.

## MCP read-only v0.27.3

```text
agentos.multi_agent_workspace_status_get
agentos.multi_agent_workspace_diff_summary_get
agentos.multi_agent_integration_proposal_get
agentos.multi_agent_integration_readiness_get
```

Expected MCP catalog: **120 tools**. Không expose workspace/integration mutation qua MCP.

## Human authority

AI/worker không được:

- provision/release workspace ngoài governed operator flow;
- bypass worker task/session binding;
- sửa workspace sau seal;
- tự approve/reject proposal;
- tự resolve conflict;
- tự `git merge`, auto-commit hoặc auto-push;
- thay Architecture Contract để làm gate pass.

## Distribution

Final v0.27.3 tiếp tục mô hình **Latest Full Release / no updater script**. Development helper chỉ dùng để materialize node trên checkout v0.27.2 trong quá trình phát triển và không được ship trong final release payload.

## Local integration backup

Before primary mutation, controlled integration writes a local backup manifest plus pre-change bytes under `.agents/runtime/integration-v0273/proposal-<id>/`. These runtime artifacts are not persisted in AgentOS SQLite/audit payloads and are excluded from release distribution. Runtime rollback still executes fail-closed in the same apply path.
