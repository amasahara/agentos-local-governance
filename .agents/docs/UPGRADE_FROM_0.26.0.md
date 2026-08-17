# Upgrade AgentOS v0.26.0 → v0.26.1

## Distribution model

Bộ nâng cấp v0.26.1 được phát hành như một **GitHub Release asset** bên ngoài repository project. Updater không phải là file mà project phải commit hoặc duy trì trong source tree.

Tải `agentos-local-governance-v0.26.1-upgrade-overlay-r2.zip` từ **GitHub Release** tương ứng, xác minh checksum nếu release cung cấp, rồi giải nén vào một thư mục updater riêng, ví dụ:

```text
D:\agentos-updaters\agentos-v0.26.1-upgrade-overlay-r2
```

Không giải nén overlay trực tiếp đè lên repository project.

## Preflight

Updater yêu cầu:

- `VERSION=0.26.0`;
- distribution lock release `0.26.0`, schema `54`;
- mọi AgentOS-managed replacement file vẫn khớp SHA-256 trong distribution lock;
- root README khớp chính xác tài liệu AgentOS chính thức v0.26.0 sẽ được reconcile; README project tùy biến được giữ nguyên;
- project-owned source/rules/workflows/architecture working copy không bị overwrite.

Từ thư mục overlay đã giải nén, chạy:

```powershell
python .\tools\apply_v0261.py D:\agentos-local-governance --dry-run
```

Chỉ tiếp tục khi `ok=true` và `findings=[]`.

## Apply

Vẫn từ thư mục overlay bên ngoài repository:

```powershell
python .\tools\apply_v0261.py D:\agentos-local-governance
```

Updater backup managed files, snapshot SQLite, migrate schema `54→55`, rebuild package/distribution-lock/manifest và rollback nếu post-validation fail.

## Validation

```powershell
cd D:\agentos-local-governance
$env:PYTHONPATH = (Resolve-Path .\.agents).Path

python -m pytest -q .agents\tests\test_architecture_structural_v0261.py
python -m pytest -q .agents\tests --basetemp=.agents\runtime\pytest-release-v0261 -rs

.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd manifest-verify
.agents\bin\agentos.cmd architecture-structural-status
```

Không tạo/activate Architecture Baseline giả chỉ để làm `enforced=true`.
