# AgentOS Local Governance

**Lớp quản trị local-first đứng giữa project của bạn và AI coding agents.**

[English](README.en.md) · [Quickstart](.agents/docs/QUICKSTART.md) · [Changelog](CHANGELOG.md) · [Release notes](RELEASE_NOTES.md)

## AgentOS là gì?

AgentOS Local Governance không phải là một framework ứng dụng và cũng không thay thế coding agent. Nó là lớp kiểm soát nằm trong repository để AI có thể làm việc trên code của bạn với phạm vi, policy, architecture, approval và bằng chứng rõ ràng.

```text
Con người / yêu cầu
        ↓
AI coding agent hoặc LLM
        ↓
AgentOS: scope · policy · workflow · evidence · approval
        ↓
Source và cấu trúc project hiện có của người dùng
```

Mục tiêu là giữ quyền quyết định ở con người trong khi vẫn cho phép agent đọc ngữ cảnh, lập kế hoạch, dùng công cụ, sửa code và phối hợp công việc một cách có thể kiểm tra.

## AgentOS giải quyết vấn đề gì?

AgentOS cung cấp các primitive ở cấp project để:

- giữ nguyên yêu cầu và phạm vi đã được phê duyệt;
- chặn thao tác ghi hoặc tool call chưa đủ điều kiện;
- quản lý task, plan, human decision và architecture authority;
- bảo vệ thay đổi đồng thời bằng session, lease và expected hash;
- ghi lại evidence và audit cho kết luận quan trọng;
- kiểm tra drift, documentation, release identity và payload;
- tách metadata của bản phân phối khỏi metadata của project đã cài;
- giữ historical material ngoài current installed payload.

AgentOS fail closed khi workflow, scope, decision, drift hoặc approval chưa hợp lệ.

## Ranh giới với source của người dùng

Bản phân phối **không tạo một thư mục `src/` đại diện**. AgentOS không sở hữu layout source của ứng dụng.

Project của bạn có thể đang dùng `src/`, `app/`, `apps/`, `packages/`, `services/` hoặc một cấu trúc khác. AgentOS quản trị cấu trúc đó tại chỗ; implementation của chính AgentOS nằm dưới `.agents/agentos/`.

```text
<project-root>/
├── .agents/              AgentOS managed payload và local governance state
├── src/ hoặc app/...     Source do project của người dùng sở hữu
├── README.md             Tài liệu ứng dụng do người dùng sở hữu
└── VERSION               Phiên bản ứng dụng do người dùng sở hữu, nếu có
```

Khi cài vào project, AgentOS không copy README, VERSION hoặc hướng dẫn AgentOS vào application root.

## Cách hoạt động

Một task được quản trị đi qua các bước chính:

1. ghi nhận nguyên văn yêu cầu và tạo task;
2. xác định môi trường, index và bounded context;
3. làm rõ ambiguity cần quyết định của con người;
4. phê duyệt scope và plan;
5. kiểm tra quyền trước từng thay đổi hoặc tool call;
6. thực thi với evidence, expected hash và audit;
7. chạy documentation, test, structural và synchronization checks;
8. chỉ báo cáo hoàn thành khi các gate bắt buộc đều đạt.

## Bắt đầu

Project mới:

```powershell
.\.agents\bin\agentos.cmd project-init --target D:\path\to\project
```

Project hiện hữu, tạo adoption plan chỉ đọc trước:

```powershell
.\.agents\bin\agentos.cmd project-adopt --target D:\path\to\project
```

Sau khi con người review plan:

```powershell
.\.agents\bin\agentos.cmd project-adopt --target D:\path\to\project --apply --human-confirmed
```

Xem hướng dẫn theo hành trình:

- [NEW PROJECT](.agents/docs/NEW_PROJECT.md)
- [EXISTING PROJECT](.agents/docs/EXISTING_PROJECT.md)
- [WINDOWS](.agents/docs/WINDOWS.md)
- [REFERENCE](.agents/docs/REFERENCE.md)

## Cấu trúc repository phân phối

- `.agents/agentos/`: runtime implementation hiện hành;
- `.agents/config/policy/`: nguồn policy modular;
- `.agents/config/generated/governance.effective.json`: effective policy được sinh deterministic;
- `.agents/distribution/metadata.json`: metadata authoritative của distribution;
- `.agents/docs/`: tài liệu vận hành và reference;
- `.agents/tests/`: regression tests của distribution, không thuộc installed application payload;
- `tools/`: công cụ build/validation của distribution, không cài vào application project.

Lịch sử phiên bản thuộc [CHANGELOG.md](CHANGELOG.md), Git history, tags và relea