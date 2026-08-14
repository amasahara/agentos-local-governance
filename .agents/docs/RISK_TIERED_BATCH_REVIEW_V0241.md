# v0.24.1 — Risk-Tiered Batch Review

## Mục tiêu

Giảm số lần human review cho **component mapping rủi ro thấp** mà không giảm authority, approval gate hoặc execution safety. Node này chỉ bổ sung review-plane cho consolidation; **không ngầm triển khai v0.24.0 orchestrator** và không parallelize TARGET mutation.

Schema AgentOS tăng **47 → 48**.

## Risk model deterministic

| Tier | Mapping | Review |
|---|---|---|
| `LOW` | `IGNORE`, `REUSE`, `MOVE` exact bytes vào target được pin `absent` | Có thể gom signed bundle |
| `MEDIUM` | `MOVE` thay thế target đã tồn tại | Human review riêng |
| `HIGH` | `ADAPT`, `REIMPLEMENT` | Human review riêng |
| `BLOCKED` | `CONFLICT`, action không được classifier nhận biết | Không được review |

Classifier là local deterministic code (`risk_tiered_mapping_v1`). LLM, MCP và model profile không có quyền override tier.

## Signed LOW-risk bundle

Một bundle pin đầy đủ:

- exact `consolidation_id`;
- exact `plan_hash`;
- classifier version;
- ordered mapping IDs;
- canonical mapping snapshot cho từng mapping;
- `mapping_hash` cho từng snapshot;
- aggregate `bundle_hash`.

`bundle_hash` và metadata tối thiểu được ghi vào **external Ed25519 signed audit chain**. Private signing key vẫn ở external audit home, không đưa vào repository/SQLite/MCP/context. Khi gọi qua Unified CLI, signed event nhận `task_id` và `session_id` từ governed CLI context.

Bundle core là immutable ở cấp SQLite: không DELETE, không sửa plan/mapping/hash/signature fields sau khi tạo. Chỉ cho transition review state `created → reviewed`. Mapping-review attestations cũng append-only.

## Review flow

```text
Draft consolidation
  ↓ deterministic classification
LOW ──→ immutable signed bundle ──→ one explicit human batch review
MEDIUM/HIGH ────────────────────→ individual explicit human review
BLOCKED ────────────────────────→ resolve/re-plan first
  ↓ all mapping attestations current for exact plan_hash
plan status = reviewed
  ↓
EXISTING whole-plan human approval
  ↓
EXISTING execution / target-precondition / rollback gates
```

Batch review **không phải batch approval**. `approve_consolidation()` vẫn là authority duy nhất để human-approve exact reviewed plan hash trước execution.

## Drift và idempotency

- Plan thay đổi → bundle/review cũ không được tính cho plan mới.
- Source manifest được re-verify trước create/review.
- Cùng exact LOW bundle tạo lại → trả bundle hiện có, không phát sinh signed event trùng.
- Cùng individual mapping review tạo lại với exact current snapshot → idempotent.
- Target drift vẫn bị execution precondition hiện hữu chặn fail-closed.

## CLI

Read-only:

```bash
agentos project-consolidation-risk-assess --consolidation-id 12
agentos project-consolidation-batch-bundle-show --bundle-id lrb_...
agentos project-consolidation-risk-review-show --consolidation-id 12
```

Mutation/review commands yêu cầu Unified CLI `--task-id` + `--session-id`:

```bash
agentos --task-id T-12 --session-id S-12 \
  project-consolidation-batch-bundle-create \
  --consolidation-id 12 --created-by operator

agentos --task-id T-12 --session-id S-12 \
  project-consolidation-batch-review \
  --bundle-id lrb_... --reviewed-by reviewer \
  --reason "Reviewed deterministic LOW-risk bundle" --human-confirmed

agentos --task-id T-12 --session-id S-12 \
  project-consolidation-mapping-review \
  --consolidation-id 12 --mapping-id 27 \
  --reviewed-by reviewer --reason "Reviewed existing-target replacement" \
  --human-confirmed
```

## MCP boundary

Chỉ expose read-only:

- `agentos.project_consolidation_risk_review_get`
- `agentos.project_consolidation_batch_bundle_get`

Không expose create/review/approve/execute mutation qua MCP.

## Safety invariants giữ nguyên

- Secondary/SOURCE project vẫn read-only.
- Governance paths vẫn bị loại khỏi consolidation.
- TARGET/database controlled insert authority không thay đổi.
- Identity decision, recovery decision và privacy lifecycle không được batch.
- Existing whole-plan human approval vẫn bắt buộc.
- Signed audit/key/secret/privacy boundaries giữ nguyên.
- Requirement-Preserving Context Control Plane vẫn lossless.
