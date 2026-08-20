# AgentOS — Cài đặt / làm mới từ Latest Full Release

Current release: **v0.28.0 — Architecture & Agent Command Center**
Database schema: **61**

> Release model invariant: **no updater script**.

AgentOS current releases are distributed as a **GitHub Release / source archive**. Không cần chạy chuỗi updater theo từng version lịch sử.

## Ownership boundary

### AgentOS-managed distribution

```text
.agents/agentos/**
release-owned policy
AgentOS docs/tests/runtime launchers
release metadata
```

### Project-owned partition — phải được giữ nguyên

```text
user skills
project workflows / workflow state
project source
architecture working copy
governance.local.json
.agents/state/**
.agents/runtime/**
```

Không xóa toàn bộ `.agents` của project và không overwrite project-owned partition khi refresh AgentOS.

## Fresh install / clean release repository

1. Download latest **GitHub Release** or source archive.
2. Extract the complete release.
3. Preserve/create project-owned data separately from the managed distribution.
4. Set `PYTHONPATH=.agents` when invoking Python modules directly.
5. Run release validation.

## Refresh an existing project

Khi cập nhật AgentOS trong một project đã có dữ liệu:

```text
backup project-owned partition
        ↓
replace/refesh AgentOS-managed distribution
        ↓
restore/preserve project-owned partition
        ↓
run schema migration through normal AgentOS startup/connect
        ↓
validate release/runtime
```

Không xóa user skill, workflow state, source, architecture working copy, local governance override hoặc AgentOS state/runtime chỉ để cập nhật runtime distribution.

## Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
git diff --check
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python tools\build_manifest.py .
python tools\verify_manifest.py .
python -m pytest -q .agents\tests -rs
python tools\validate_release.py .
git diff --check
```

## v0.28.0 runtime note

The Architecture & Agent Command Center is a strict read-only projection over the existing AgentOS state database. It does not persist dashboard state or add mutation/approval/worker-launch authority.

See [Architecture & Agent Command Center](ARCHITECTURE_AGENT_COMMAND_CENTER_V0280.md).

### v0.27.3 workspace/integration note

Executor workspace routing and controlled integration preserve primary AgentOS state/policy/lease/audit authority. Integration remains human-reviewed/approved and never performs automatic Git merge, commit or push.

See [Isolated Workspace & Controlled Integration](ISOLATED_WORKSPACE_CONTROLLED_INTEGRATION_V0273.md).
