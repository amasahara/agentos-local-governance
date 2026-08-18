# Hướng dẫn AgentOS v0.25.2

1. Chạy `architecture-init` để tạo đúng 27 template; lệnh này không scan source và không tự suy luận kiến trúc.
2. Điền Markdown + JSON contract. Section `applicable` phải có payload và không còn marker UNRESOLVED.
3. Chạy `architecture-validate`, tạo baseline, sau đó con người review → approve → activate với exact baseline hash.
4. Trước `approve-task`, chạy `clarity-assess`. Nếu còn assumption/ambiguity/decision, dùng `grill-me` và chờ human resolution.
5. Trong lúc code, nếu phát sinh lựa chọn có ảnh hưởng behavior/architecture/data/API/security/scope, mở `decision-request`; không tự chọn.
6. Khi decision đang open, chỉ tiếp tục bounded read-only investigation. Project mutation phải dừng.
7. Human dùng `decision-resolve --human-confirmed`. Nếu impact khác `none`, task approval bị thu hồi và plan active/submitted bị supersede.
8. Sau upgrade chạy manifest, release validator, docs/instruction checks và toàn bộ pytest.

Database schema: **57**; bootstrap baseline vẫn **46**.
