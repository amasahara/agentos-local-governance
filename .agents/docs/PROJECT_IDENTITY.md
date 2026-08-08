# Project Identity & Purpose Model — v0.20.0

[🇻🇳 Tiếng Việt](#tiếng-việt) | [🇬🇧 English](#english)

## Tiếng Việt

### Ba lớp định danh

- `.agents/config/project.id`: `project_uuid` bền vững và lineage `origin_project_uuid`. File này đi cùng project.
- `.agents/state/project.instance.json`: `instance_uuid` cục bộ cho một working copy. Clone sạch tạo instance mới.
- `.agents/config/project.purpose.json`: domain, purpose family, capability và role do con người xác nhận.

Không dùng absolute path làm `project_uuid`. `audit_project_id` là namespace audit ổn định; khi nâng từ v0.19.5 nó giữ lại ID SHA-256(path) hiện tại một lần để chain cũ không đổi namespace. Di chuyển thư mục sau đó không làm đổi `project_uuid` hoặc `audit_project_id`.

Copy nguyên thư mục có cả local state có thể làm trùng `instance_uuid`; local registry dưới `AGENTOS_HOME` sẽ fail-closed khi cả hai path còn tồn tại. Nếu bản sao trở thành project độc lập, chạy `project-fork` với human confirmation để tạo `project_uuid` mới và giữ `origin_project_uuid`.

### Purpose là business identity

Purpose không được suy ra chỉ từ framework hoặc utility trùng nhau. Hai project cùng dùng Django, logging hoặc Excel không có nghĩa cùng mục đích. Domain/purpose là nền móng cho compatibility gate ở v0.20.1.

### MCP

v0.20.0 chỉ expose các tool đọc:

- `agentos.project_identity_get`
- `agentos.project_identity_verify`
- `agentos.project_purpose_get`

Không expose tool MCP để đổi UUID, xác nhận purpose hoặc fork project.

## English

### Three identity layers

- `.agents/config/project.id`: durable `project_uuid` plus `origin_project_uuid` lineage; travels with the project.
- `.agents/state/project.instance.json`: local `instance_uuid` for one working copy; a clean clone creates a new instance.
- `.agents/config/project.purpose.json`: human-confirmed business domain, purpose family, capabilities, and project role.

Absolute paths are not project UUIDs. A stable `audit_project_id` preserves the current v0.19.5 SHA-256(path) namespace once during upgrade so the existing signed-audit namespace is not switched. Later relocation changes neither `project_uuid` nor `audit_project_id`.

Copying the whole directory including local state can duplicate an instance UUID. The host-local registry under `AGENTOS_HOME` fails closed when both paths still exist. A copy becoming an independent project must use a human-confirmed `project-fork`, which creates a new project UUID while preserving `origin_project_uuid`.

### Purpose is business identity

Purpose cannot be inferred from shared frameworks or generic utilities. Two projects using the same technology are not automatically compatible. The v0.20.0 purpose contract is the foundation for the v0.20.1 domain compatibility gate.

### MCP

Only read-only tools are exposed in v0.20.0. UUID mutation, purpose confirmation, and forking remain human-controlled CLI operations.
