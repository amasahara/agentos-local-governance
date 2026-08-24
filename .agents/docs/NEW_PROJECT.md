# New Project

Khởi tạo AgentOS trong một application project mới:

```text
agentos project-init --target <project-root>
```

Kết quả:

- cài current managed payload dưới `.agents/`;
- sinh project UUID mới;
- đặt purpose thành `UNCONFIRMED`;
- ghi AgentOS version tại `.agents/release/VERSION`;
- không ghi README hoặc VERSION vào application root;
- không cài tests hay historical release payload.

Sau bootstrap, xác nhận purpose bằng workflow human-authorized trước khi dùng domain compatibility.
