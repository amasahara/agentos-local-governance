# Hướng dẫn sử dụng AgentOS v0.27.1

Phiên bản: **v0.27.1 — Architecture-Aware Skill Selection & Evaluation**
Database schema: **59**

## Chạy selection

Task phải có active architecture-aware plan trước:

```powershell
agentos skill-selection-run --task-id T-123
```

Nếu skill yêu cầu tools, truyền inventory rõ ràng:

```powershell
agentos skill-selection-run --task-id T-123 --available-tools '["pytest","ruff"]'
```

Xem kết quả:

```powershell
agentos skill-selection-status --task-id T-123
agentos skill-selection-candidates --run-id 1
```

Sau khi task có `task_outcome`, evaluation có thể chạy:

```powershell
agentos skill-evaluation-run --selection-run-id 1
```

Selection/evaluation không cấp authority và không tự sửa lifecycle skill.

## Cập nhật AgentOS

Dùng latest full release; **no updater script**. Không xóa project-owned user skills, workflows, source, architecture working copy, `governance.local.json`, `.agents/state/**`, `.agents/runtime/**`.

## Release gates

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python tools\build_manifest.py .
python tools\verify_manifest.py .
python -m pytest -q .agents\tests -rs
python tools\validate_release.py .
git diff --check
```
