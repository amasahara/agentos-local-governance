[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

# Hướng dẫn AgentOS v0.20.0

## 1. Sau khi nâng từ v0.19.5

1. Chạy `project-identity-init` để tạo `project_uuid` bền vững và local `instance_uuid`.
2. Con người xác nhận domain/purpose/capabilities/role bằng `project-purpose-set --human-confirmed`.
3. Chạy `project-identity-db-sync` để đồng bộ migration 32 nếu migration runtime chưa được kích hoạt qua command khác.
4. Chạy `project-identity-verify`; không tiếp tục cross-project work nếu có `instance_clone_conflict` hoặc `purpose_incomplete`.
5. Chạy test, `docs-check`, `instruction-check`, `audit-verify` và backup verification của baseline v0.19.5.

## 2. Move, clone và fork

- **Move:** giữ `project.id` và local instance state; registry thấy path cũ biến mất và ghi nhận relocation.
- **Git clone sạch:** `project.id` giữ nguyên, local instance state không đi theo → instance UUID mới.
- **Copy nguyên thư mục:** nếu cả hai path tồn tại và copy cả local state → conflict fail-closed.
- **Fork:** dùng `project-fork --human-confirmed`; project UUID mới, `origin_project_uuid` trỏ về project gốc.

## 3. Purpose

Purpose mô tả business identity, không phải technology stack. Các capability kỹ thuật generic không đủ để chứng minh hai project cùng mục đích. Đây là dữ liệu đầu vào cho v0.20.1.

## 4. MCP

Coding agent chỉ được đọc identity và purpose. Mọi mutation identity/purpose vẫn thuộc CLI do người dùng/human operator kiểm soát.
