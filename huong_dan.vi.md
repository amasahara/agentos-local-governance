# Hướng dẫn AgentOS v0.24.2 — DB-Aware Context Projection

## v0.24.2 — DB-Aware Context Projection

1. Chỉ projection Evidence Plane dạng schema/mapping/manifest có strong signal.
2. Codec phải deterministic, reversible và pin source hash.
3. Chỉ dùng projection khi representation thực tế nhỏ hơn source.
4. Không persist raw schema/mapping/manifest hoặc projected text.
5. Original request, Requirement Ledger, `AGENTS.md`, approved scope, active plan
   và governance authority luôn giữ lossless.
6. `agentos.context_db_projection_get` chỉ đọc state DB bằng SQLite `mode=ro`;
   không tạo DB và không chạy migration.

## v0.24.1 — Risk-Tiered Batch Review

1. Chạy `project-consolidation-risk-assess`.
2. Batch chỉ mapping `LOW` vào signed bundle.
3. Review `MEDIUM/HIGH` riêng; `BLOCKED` phải re-plan.
4. Exact-plan whole-plan approval vẫn bắt buộc trước execution.

## Kiểm tra release

```powershell
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

Updater theo version là GitHub Release asset và không được commit vào clean `main`.
