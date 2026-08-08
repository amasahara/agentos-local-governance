# AgentOS v0.20.2 Usage

```bash
# Sau khi v0.20.1 đã select Primary
.agents/bin/agentos project-consolidation-create \
  --candidate-set-id 1 --created-by operator

# Lập mapping
.agents/bin/agentos project-consolidation-add \
  --consolidation-id 1 \
  --source-project-uuid <UUID> \
  --source-path src/patient/mapper.py \
  --target-path integrations/fpt/patient_mapper.py \
  --action MOVE \
  --reason "Import adapter into primary integration boundary" \
  --created-by operator

# Review + approval phải là người thật
.agents/bin/agentos project-consolidation-review \
  --consolidation-id 1 --reviewed-by reviewer \
  --reason "Reviewed paths, hashes and architecture mapping" --human-confirmed

.agents/bin/agentos project-consolidation-approve \
  --consolidation-id 1 --approved-by owner \
  --reason "Approved exact plan hash for primary project" --human-confirmed

# Thực thi từng component
.agents/bin/agentos project-consolidation-execute \
  --consolidation-id 1 --mapping-id 1 --executed-by operator

# ADAPT/REIMPLEMENT cần content đã chuẩn bị bên trong Primary
.agents/bin/agentos project-consolidation-execute \
  --consolidation-id 1 --mapping-id 2 --executed-by operator \
  --prepared-content-file .agents/runtime/task-workspaces/TASK/adapted.py

.agents/bin/agentos project-consolidation-complete \
  --consolidation-id 1 --completed-by operator
```
