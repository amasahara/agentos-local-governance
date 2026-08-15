# Upgrade v0.25.0 → v0.25.1 — Release Metadata Coherence

v0.25.1 là hardening node không đổi database schema. Nó sửa drift giữa release/package metadata và thêm fail-closed coherence validation.

## Upgrade asset

Tải `agentos-local-governance-v0.25.1-upgrade-overlay.zip` từ **GitHub Release** `v0.25.1` và giải nén ra một thư mục nằm ngoài repository AgentOS.

Upgrader `apply_v0251.py` là release asset bên ngoài repository, không được giả định tồn tại trong source tree của AgentOS.

## Windows

```powershell
python D:\agentos-updaters\agentos-v0.25.1-upgrade-overlay\tools\apply_v0251.py D:\agentos-local-governance --dry-run
python D:\agentos-updaters\agentos-v0.25.1-upgrade-overlay\tools\apply_v0251.py D:\agentos-local-governance

## Linux / macOS
python3 /path/to/agentos-v0.25.1-upgrade-overlay/tools/apply_v0251.py /path/to/agentos-local-governance --dry-run
python3 /path/to/agentos-v0.25.1-upgrade-overlay/tools/apply_v0251.py /path/to/agentos-local-governance

## Trước khi nâng cấp

Repository phải là baseline `VERSION=0.25.0`. Upgrader xác minh các file được sửa bằng SHA-256 lấy từ `MANIFEST.json`; local drift trên các file đó sẽ chặn upgrade.

```bash
python3 tools/apply_v0251.py /path/to/agentos-v0.25.0 --dry-run
python3 tools/apply_v0251.py /path/to/agentos-v0.25.0
```

Upgrader tạo backup trước khi ghi, sau đó rebuild `PACKAGE_COMPLETENESS.json`, `MANIFEST.json` và `CHECKSUMS.sha256`.

## Sau khi nâng cấp

```bash
python3 tools/validate_release.py .
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
python3 -m pytest -q .agents/tests/test_release_metadata_coherence_v0251.py
```

Expected state:

- `VERSION = 0.25.1`
- database schema `49`
- `PACKAGE_COMPLETENESS.release = 0.25.1`
- `PACKAGE_COMPLETENESS.schema = 49`
- package file count bằng `MANIFEST.file_count`
- clean-main package completeness không yêu cầu `VALIDATION_REPORT.json`
- release metadata coherence gate pass.

Không cần database migration hoặc DB sync cho node này.
