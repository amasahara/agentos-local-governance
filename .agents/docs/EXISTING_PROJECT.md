# Existing Project

Bắt đầu bằng read-only adoption plan:

```text
agentos project-adopt --target <project-root>
```

Plan kiểm tra Git, README, VERSION, tests và source roots mà không sửa project.

Chỉ apply sau khi human review:

```text
agentos project-adopt --target <project-root> --apply --human-confirmed
```

Apply chỉ sở hữu `.agents/`; source, tests, README và VERSION của application được giữ nguyên.
