# AgentOS v0.22.3 — Release Integrity Usage

## Vietnamese

Sau khi nâng cấp từ v0.22.2, chạy theo thứ tự:

```bash
.agents/bin/agentos release-integrity-check
.agents/bin/agentos db-status
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
python3 -m pytest -q .agents/tests
python3 tools/build_manifest.py . --kind full
python3 tools/verify_manifest.py .
python3 tools/validate_release.py .
```

`release-integrity-check` yêu cầu cả lõi governance lịch sử và các module v0.20–v0.22 cùng tồn tại, migration 1→40 có authority trung tâm, và launcher lõi không phải stub.

## English

Run the same sequence after upgrading. A release is invalid if the historical core or the v0.20–v0.22 extension branch is missing, the schema chain is discontinuous, or release hashes do not verify.
