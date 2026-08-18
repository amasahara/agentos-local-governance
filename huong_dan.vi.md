# Hướng dẫn AgentOS v0.27.0

1. Tạo/promote skill từ procedural memory như trước; candidate mới tự nhận Governed Skill Contract v2 ở trạng thái least-authority.
2. Dùng `skill-contract-show`, sau đó `skill-contract-set` để khai input/output, ARCH sections, capabilities, tools, read/write scopes, dependencies, external services, risk và test contract.
3. Chạy `skill-contract-validate`. Skill architecture-sensitive cần ACTIVE Architecture Baseline; validation sẽ pin exact baseline hash.
4. Chỉ con người được `skill-graduate` và `skill-revoke`; MCP không có mutation authority.
5. Skill v1 cũ được giữ nguyên, không rewrite in-place. Muốn lên v2 thì tạo successor candidate/version mới và review lại.
6. v0.27.0 chưa tự chọn skill theo architecture; chức năng đó thuộc v0.27.1.
7. Distribution từ v0.27.0 không dùng `apply_v*.py`. Tải latest full release và giữ nguyên project-owned user skills, workflows/workflow state, source, architecture working copy, `governance.local.json`, state và runtime.
8. Khi phát hành AgentOS repository, rebuild manifest, chạy validator/docs/instruction checks và toàn bộ pytest.

Database schema: **58**; bootstrap baseline vẫn **46**.
