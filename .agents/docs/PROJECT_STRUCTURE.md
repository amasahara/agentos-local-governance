# CẤU TRÚC PROJECT / PROJECT STRUCTURE

Tài liệu này giải thích trách nhiệm của từng phần. Nó không thay thế `AGENTS.md`.

This document explains component responsibilities. It does not replace `AGENTS.md`.

## Root files

### `AGENTS.md`

- VI: Nguồn instruction duy nhất cho mọi coding agent.
- EN: Sole instruction authority for all coding agents.

### `huong_dan.md`

- VI: Điểm bắt đầu đọc project, mô tả song ngữ, workflow và checklist.
- EN: Project reading entry point with bilingual workflow and checklists.

### `VERSION`

- VI: Phiên bản governance hiện tại.
- EN: Current governance release version.

## `.agents/agentos/`

### `core.py`

- clarity assessment;
- task approval and write gate;
- environment profiling;
- tool budget and failure-signature control;
- placement, duplicate scan and context recommendation;
- documentation synchronization check.

### `cli.py`

- VI: Giao diện dòng lệnh ổn định cho developer, LLM và MCP wrapper.
- EN: Stable command-line interface for developers, LLMs, and MCP wrappers.

## `.agents/config/governance.json`

- VI: Các giá trị policy có cấu trúc và có thể kiểm tra tự động.
- EN: Structured, machine-checkable policy values.

Không đặt prose dài hoặc hướng dẫn sử dụng tại đây.

Do not put long prose or usage guidance here.

## `.agents/docs/`

### `USAGE.md`

Ví dụ command theo từng use case.

Command examples by use case.

### `PROJECT_STRUCTURE.md`

Tài liệu hiện tại: trách nhiệm thành phần và đường dẫn đọc.

This file: component ownership and reading paths.

### `RULES_WORKFLOW_CHANGELOG.md`

Audit trail cho thay đổi rules và workflow.

Audit trail for rules and workflow changes.

## `.agents/tests/`

- VI: Thể hiện các invariant mà hệ thống cam kết.
- EN: Encodes the invariants guaranteed by the system.

Governance change có enforcement mới phải có test tương ứng.

A governance change introducing new enforcement must include corresponding tests.

## `.agents/state/`

SQLite và state có thể tái tạo. Không commit database runtime.

Regenerable SQLite and state. Do not commit runtime databases.

## `.agents/cache/`

Cache file reads, searches, graph metadata hoặc dữ liệu có thể tái tạo.

Regenerable file-read, search, graph, or related caches.

## `.agents/runtime/`

Workspace, temporary scripts, tests, fixtures, downloads, exports và validation artifacts theo task.

Per-task workspaces, temporary scripts, tests, fixtures, downloads, exports, and validation artifacts.

## Luồng đọc theo mục tiêu / Goal-oriented reading paths

### Hiểu một rule / Understand a rule

```text
AGENTS.md
→ governance.json
→ core.py
→ tests
→ changelog
```

### Hiểu một workflow / Understand a workflow

```text
huong_dan.md
→ AGENTS.md workflow
→ USAGE.md
→ cli.py
→ tests
```

### Review governance change

```text
changelog entry
→ AGENTS.md diff
→ governance.json diff
→ implementation diff
→ test diff
→ docs-check result
```


## v0.7.0 modules

```text
.agents/agentos/
├── db.py
├── models.py
├── policy.py
├── tooling.py
├── cache.py
├── indexing.py
└── documentation.py
```

`documentation.py` validates file headers and input/output contracts. `indexing.py` incrementally indexes Python functions, async functions, classes, and methods. `tooling.py` implements tool classification, guards, redaction, and egress auditing.
