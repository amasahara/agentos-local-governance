# Hướng dẫn AgentOS v0.22.7

Phiên bản hiện tại: **0.22.7**, schema **43**.

Quy trình erasure bắt buộc: `request-create → plan-create → plan-review → plan-approve → execute`. Request/plan là immutable; review/approval/execution được lưu riêng. Không nhập raw identifier vào lifecycle; dùng canonical `entity_uuid`. Trước khi execute phải xử lý xong operation active/in-doubt. Sau execute, kiểm tra `local_erasure_completed` và nếu có `external_target_erasure_required`, chuyển yêu cầu tới authority của TARGET bên ngoài AgentOS.

MCP chỉ dùng để inspection, không dùng để duyệt/xóa.
