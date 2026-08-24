# AgentOS Local Governance

**Local-first governance runtime cho AI coding agents.**

[English](README.en.md) · [Quickstart](.agents/docs/QUICKSTART.md) · [Changelog](CHANGELOG.md) · [Release notes](RELEASE_NOTES.md)

## Current release

**v0.28.2 — Project Bootstrap & Repository Normalization**

Release này không thêm security feature. Nó làm sạch nền móng phân phối và cài đặt:

- tách `agentos_distribution` khỏi `governed_project`;
- tách distribution metadata khỏi installed-project metadata;
- thay installer bằng `project-init` và `project-adopt`;
- không ship project UUID, business domain hoặc purpose mẫu;
- không ghi AgentOS README hoặc VERSION vào application root;
- không cài tests, historical launchers, historical docs hoặc release-maintenance tools;
- tổ chức current docs theo NEW PROJECT / EXISTING PROJECT / WINDOWS / REFERENCE;
- compile modular policy thành một deterministic effective policy;
- kiểm tra release identity và repository role coherence.

Current schema: **61**.

## Bắt đầu

Project mới:

```text
agentos project-init --target <project-root>
```

Project hiện hữu, read-only plan trước:

```text
agentos project-adopt --target <project-root>
```

Sau human review:

```text
agentos project-adopt --target <project-root> --apply --human-confirmed
```

## Ownership

```text
AgentOS distribution metadata
→ .agents/distribution/metadata.json

Installed AgentOS metadata
→ .agents/release/VERSION
→ .agents/release/install-manifest.json

Application metadata
→ ./README.md
→ ./VERSION
```

AgentOS chỉ sở hữu managed payload dưới `.agents/` trong application project.

## Tài liệu hiện hành

- [Quickstart](.agents/docs/QUICKSTART.md)
- [New Project](.agents/docs/NEW_PROJECT.md)
- [Existing Project](.agents/docs/EXISTING_PROJECT.md)
- [Windows](.agents/docs/WINDOWS.md)
- [Reference](.agents/docs/REFERENCE.md)

Version history nằm trong [CHANGELOG.md](CHANGELOG.md), Git tags và GitHub Releases; nó không còn là onboarding path hay instruction authority.

## Authority

Human sở hữu requirement, approval và architecture authority. AgentOS thực thi policy và fail closed khi scope, decision, drift, audit hoặc workflow gate chưa hợp lệ.
