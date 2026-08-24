# Hướng dẫn sử dụng AgentOS v0.28.2

[Tiếng Việt](huong_dan.vi.md) · [English guide](huong_dan.en.md) · [README](README.md)

Phiên bản hiện hành: **v0.28.2 — Project Bootstrap & Repository Normalization**  
Database schema: **61**

AgentOS là lớp quản trị local-first đứng giữa repository của người dùng và coding agent/LLM. AgentOS không thay thế cấu trúc source của ứng dụng: mã nguồn vẫn nằm ở vị trí do project lựa chọn (`src/`, `app/`, `packages/` hoặc cấu trúc sẵn có), còn runtime quản trị nằm trong `.agents/`.

## Bắt đầu project mới

Tại distribution AgentOS, chạy:

```powershell
.\.agents\bin\agentos.cmd project-init --project-root D:\path\to\new-project
```

Lệnh khởi tạo metadata riêng của governed project và chỉ cài installed payload cần thiết. README, VERSION và hướng dẫn của distribution không được sao chép vào application root.

## Áp dụng cho project hiện có

Tạo kế hoạch adoption chỉ đọc trước:

```powershell
.\.agents\bin\agentos.cmd project-adopt --project-root D:\path\to\existing-project
```

Đọc kế hoạch, xử lý xung đột rồi mới áp dụng bằng xác nhận của con người:

```powershell
.\.agents\bin\agentos.cmd project-adopt --project-root D:\path\to\existing-project --apply --human-confirmed
```

AgentOS quản trị source layout hiện có tại chỗ; không yêu cầu distribution phải có thư mục `src/` đại diện.

## Metadata và policy

- Distribution metadata: `.agents/distribution/metadata.json`
- Installed-project identity: `.agents/project/identity.json`
- Installed release metadata: `.agents/release/`
- Policy baseline và module: `.agents/config/governance.json` cùng `.agents/config/policy/`
- Effective policy được sinh deterministic: `.agents/config/generated/governance.effective.json`

Không chỉnh trực tiếp effective policy. Hãy sửa nguồn policy phù hợp rồi sinh lại artifact.

## Tài liệu theo hành trình

- Bắt đầu nhanh: `.agents/docs/QUICKSTART.md`
- Project mới: `.agents/docs/NEW_PROJECT.md`
- Project hiện có: `.agents/docs/EXISTING_PROJECT.md`
- Windows: `.agents/docs/WINDOWS.md`
- Tham chiếu: `.agents/docs/REFERENCE.md`

## Kiểm tra distribution

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python tools\build_manifest.py .
python tools\verify_manifest.py .
python -m pytest -q .agents\tests -rs
python tools\validate_release.py .
git diff --check
```

`tools/build_manifest.py` phải chạy sau thay đổi release payload; kết quả `tools/verify_manifest.py` phải có `ok: true` trước khi phát hành.

## Phạm vi v0.28.2

v0.28.2 chỉ chuẩn hóa bootstrap, repository, metadata, policy và tài liệu. Phiên bản này không thêm security feature mới. Lịch sử thay đổi nằm trong `CHANGELOG.md`, còn `README.md` mô tả mục tiêu và cách AgentOS hoạt động.