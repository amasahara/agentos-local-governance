# v0.24.2 — Repository Release Cleanup Policy

## Mục tiêu

`main` chỉ đại diện cho trạng thái AgentOS mới nhất có thể clone, test và phát hành trực tiếp.

Lịch sử phát hành không bị mất: Git commit/tag giữ snapshot source; GitHub Release giữ release notes, updater và checksum theo phiên bản.

## Main phải giữ

- Source runtime hiện tại trong `.agents/agentos/`.
- Toàn bộ regression tests trong `.agents/tests/`.
- Launcher hiện tại: `agentos`, `agentos.cmd`, `agentos-mcp`, `agentos-mcp.cmd` và hooks.
- Governance/config và tài liệu kiến trúc còn hiệu lực.
- `README*`, `huong_dan*`, `CHANGELOG.md`, `RELEASE_NOTES.md`.
- `UPGRADE_FROM_0.24.2.md` cho bước nâng cấp hiện tại.
- `MANIFEST.json`, `CHECKSUMS.sha256`.
- Benchmark/evaluation artifacts vẫn được runtime checker hoặc regression test tham chiếu.
- Tool generic: `build_manifest.py`, `verify_manifest.py`, `validate_release.py`,
  `repository_release_cleanup.py`.

## Main không giữ

- `tools/apply_v*.py`, `tools/validate_v*.py`.
- Recovery/finalizer/hotfix updater theo phiên bản.
- `RELEASE_NOTES_V*.md`, `USAGE_V*.md`, `GITHUB_READY_FULL_RELEASE_V*.md`.
- Upgrade guide cũ hơn bước trực tiếp đến current release.
- Versioned compatibility launchers `.agents/bin/agentos.v*`,
  `.agents/bin/agentos-mcp.v*`.
- `VALIDATION_REPORT*.json`, `CHECKSUMS_V*.sha256`, `HOTFIX_INFO.txt`.
- ZIP/release asset trong repository.
- `.agents/runtime`, `.agents/state`, `.agents/cache`, test/editor caches.

## GitHub Release

Mỗi tag/release nên chứa:

- release notes;
- updater của chính release (nếu cần);
- updater checksum;
- optional validation report;
- GitHub tự cung cấp source zip/tar.gz.

Không commit release ZIP vào `main`.

## Regression policy

Historical regression tests được giữ trên `main` vì chúng là contract bảo vệ backward compatibility.
Historical release packaging scripts không phải runtime contract và được archive ngoài repository.

## Local archive

Cleanup mặc định lưu file được loại khỏi `main` tại sibling directory:

`.agentos-release-archive/<project-name>/v0.24.3-<timestamp>/`

Có thể override bằng `AGENTOS_RELEASE_ARCHIVE_HOME`.

Không có file nào thuộc nhóm cleanup bị xóa vĩnh viễn trong quá trình này.
