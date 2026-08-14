# Hướng dẫn AgentOS v0.25.0 — Schema Bootstrap Baseline

- Fresh DB: bootstrap trực tiếp schema 46, verify fingerprint, rồi chạy 47→49.
- Existing DB: migrate tuần tự từ version đang ghi trong `schema_migrations`.
- Không replay migration functions 1→46 trên fresh path.
- Unversioned DB có object lạ phải fail-closed.
- Schema hiện tại vẫn là 49.
- Không thay đổi SOURCE/TARGET authority, approval, privacy, audit hoặc MCP mutation.

Kiểm tra release:

```powershell
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```
