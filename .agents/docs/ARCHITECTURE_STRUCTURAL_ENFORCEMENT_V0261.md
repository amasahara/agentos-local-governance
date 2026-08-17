# AgentOS v0.26.1 — Structural Enforcement

## Mục tiêu / Goal

v0.26.1 biến các phần kiến trúc có tính cấu trúc thành hard contract tại plan/write/precommit boundary. Node này chỉ bao phủ:

- `ARCH-02` Tech Stack
- `ARCH-03` Folder Structure
- `ARCH-04` System Architecture
- `ARCH-05` Module Breakdown
- `ARCH-12` Dependency Graph
- `ARCH-22` Coding Convention
- `ARCH-23` Design Pattern

Runtime/data/API/business boundaries không thuộc node này.

## Authority model

```text
Human-approved ACTIVE Architecture Baseline
                 ↓
       Explicit structural contract
                 ↓
 Plan analysis → write target → precommit
                 ↓
            PASS / BLOCK
```

AI không được approve, waive, rewrite hay activate Architecture Authority. Một `BLOCK` hợp lệ về mặt business/architecture phải chuyển sang v0.25.5 Change Proposal + ADR, sau đó tạo/approve/activate successor baseline rồi re-plan.

## Schema 55

Thêm:

- `architecture_structural_runs`
- `architecture_structural_findings`

State chỉ lưu rule/finding/path/provenance; không lưu raw source.

## Machine-readable vocabulary

AgentOS chỉ enforce field được khai rõ. Field không khai không tự trở thành authority.

### ARCH-02 Tech Stack

- `allowed_languages`
- `forbidden_languages`
- `allowed_dependencies`
- `forbidden_dependencies`

Plan thay dependency manifest phải khai `expected_dependencies`. Source language được suy ra deterministic từ extension và có thể bổ sung `expected_languages`.

### ARCH-03 Folder Structure

Kế thừa hard path contract:

- `allowed_write_roots`
- `forbidden_paths`

### ARCH-04 System Architecture

- `allowed_component_roots`
- `forbidden_component_paths`
- `forbidden_component_edges`

### ARCH-05 Module Breakdown

- `allowed_module_roots`
- `forbidden_module_paths`
- `forbidden_module_names`
- `module_location_rules`

Ví dụ chống module chung chung:

```json
{
  "forbidden_module_names": ["utils.py"],
  "module_location_rules": [
    {
      "match": "utils.py",
      "allowed_paths": ["src/shared/date.py", "src/shared/validation.py"]
    }
  ]
}
```

### ARCH-12 Dependency Graph

- `forbidden_imports`
- `forbidden_import_edges`
- `allowed_import_edges`

### ARCH-22 Coding Convention

- `forbidden_file_names`
- `require_file_header_path`
- `require_module_purpose`
- `require_public_symbol_docstrings`
- `forbid_wildcard_imports`
- `max_module_lines`

Các kiểm tra Python dùng AST/static text; project code không được execute.

### ARCH-23 Design Pattern

- `forbidden_artifacts`
- `required_artifacts`
- `forbidden_import_edges`

AgentOS không suy luận “pattern” bằng phỏng đoán semantic. Chỉ artifact/edge contract explicit mới block.

## Runtime integration

### Planning

v0.26.0 plan envelope được mở rộng bằng structural pre-plan analysis. Dependency manifest trong `expected_files` yêu cầu `expected_dependencies`; dependency/ngôn ngữ/target/import edge trái contract làm `plan-submit` fail trước persistence.

### Write gate

`check_write`/`prepare_change` dùng `architecture_structural_target_check`. Rule ARCH-03/04/05/22/23 có thể block target trước mutation.

### Precommit

`precommit_check` chạy cả:

1. architecture-aware plan freshness;
2. v0.25.4 repository architecture compliance;
3. v0.26.1 static structural enforcement.

Cả compliance và structural gate phải pass.

## MCP

Read-only only:

- `agentos.architecture_structural_status_get`
- `agentos.architecture_structural_findings_get`
- `agentos.architecture_structural_target_get`

Không có MCP check-run mutation, approve, waive, proposal approval hay baseline activation.

## No ACTIVE baseline

Nếu chưa có ACTIVE baseline:

```text
structural.enforced = false
status = not_evaluable
```

Đây là compatibility behavior có chủ ý.

## README coherence repair

Tag v0.26.0 có runtime `VERSION=0.26.0` nhưng `README.md`, `README.vi.md`, `README.en.md` vẫn mô tả v0.25.2/schema 50. v0.26.1 sửa ba file này khi chúng còn khớp chính xác SHA-256 của README AgentOS v0.26.0 chính thức. Release-integrity nhận diện exact official stale hashes; README project tùy biến được giữ nguyên và không bị AgentOS chiếm ownership.
