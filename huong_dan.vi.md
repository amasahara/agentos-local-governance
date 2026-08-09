# Hướng dẫn v0.22.6 — Secret Resolver & Lineage Key Lifecycle

1. Chỉ nâng từ baseline `VERSION=0.22.5`.
2. Chạy upgrader `tools/apply_v0226.py` và `agentos secret-lineage-db-sync` để schema lên 42.
3. Dùng `secret-provider-catalog` để xem provider pin; chỉ approve capability thực sự cần (`db.source.select`, `db.target.controlled_insert`, `db.target.reconciliation_select`).
4. Không đặt raw credential trong `governance.json`; `secret://alias` chỉ được trỏ tới URI resolver tin cậy.
5. Chạy `lineage-keyring-status`. Nếu chưa initialized, operator chạy privileged `lineage-keyring-initialize` trong task/session hợp lệ. MCP status không tự tạo/migrate key material.
6. Legacy `.agents/state/identity_lineage.key` được chuyển nguyên bytes vào keyring; kiểm tra file legacy không còn là nguồn authority và historical fingerprint/token không bị thay đổi.
7. Rotation phải theo create plan → review → approve → execute. Không bỏ qua bước hoặc mở rotation qua MCP.
8. Rekey phải dùng SOURCE `select_read` đã governance để đọc lại raw identifier; không re-HMAC từ hash/token cũ.
9. Chạy focused regression, registry collision checks, leakage checks, manifest/checksum và clean upgrade trước production.
