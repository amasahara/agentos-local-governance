# AgentOS — Cài đặt / làm mới từ Latest Full Release

Current release: **v0.27.0 — Governed Skill Contract v2**
Database schema: **58**

## 🇻🇳 Tiếng Việt

### Mô hình phân phối từ v0.27.0

Từ v0.27.0, AgentOS dùng mô hình **download latest full release** và **không còn dùng updater script theo từng version**.

Không cần chạy updater riêng cho từng phiên bản hoặc đi qua chuỗi updater lịch sử.

### Ranh giới ownership

AgentOS-managed distribution và dữ liệu riêng của từng project được tách biệt. Latest release không sở hữu hoặc ghi đè các partition project-owned:

- user skills / approved project skills;
- project workflows và workflow state;
- project source;
- Architecture working copy của project;
- `governance.local.json`;
- `.agents/state/**`;
- `.agents/runtime/**`.

Release-managed content gồm AgentOS runtime modules, canonical/release-owned governance policy, current release documentation, release tests và các distribution artifacts của AgentOS.

### Cách sử dụng latest release

1. Tải **latest GitHub Release/source** của AgentOS.
2. Dùng phần AgentOS-managed distribution mới nhất.
3. Giữ nguyên toàn bộ project-owned partition nêu trên.
4. Khởi động AgentOS bình thường. Runtime hiện tại tự thực hiện additive database schema migration khi state được mở bằng governed runtime; không cần chương trình updater bên ngoài.
5. Nếu đang phát triển/chốt release cho chính repository AgentOS, rebuild manifest rồi chạy toàn bộ validation/tests trước khi publish.

```text
latest GitHub Release
        ↓
AgentOS-managed distribution
        ↓
project-owned partition preserved
        ↓
current AgentOS runtime
        ↓
normal additive schema migration
```

### Release validation cho repository AgentOS

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/validate_release.py .
git diff --check
```

---

## 🇬🇧 English

### Distribution model from v0.27.0

Starting with v0.27.0, AgentOS uses a **download latest full release** model with **no version-specific updater script**.

Release model invariant: **no updater script**.

No version-specific updater is required, and users do not need to execute a historical updater chain.

### Ownership boundary

The AgentOS-managed distribution is separate from project-owned data. A current release does not own or overwrite:

- user skills / approved project skills;
- project workflows and workflow state;
- project source;
- project Architecture working copies;
- `governance.local.json`;
- `.agents/state/**`;
- `.agents/runtime/**`.

Release-managed content consists of AgentOS runtime modules, canonical/release-owned governance policy, current release documentation, release tests, and AgentOS distribution artifacts.

### Using the latest release

1. Download the **latest GitHub Release/source** for AgentOS.
2. Use the newest AgentOS-managed distribution.
3. Preserve the project-owned partition unchanged.
4. Start AgentOS normally. The current runtime applies additive database schema migrations when governed state is opened; no external updater program is required.
5. When developing or publishing the AgentOS repository itself, rebuild the manifest and run the full validation/test gates before publishing.

```text
latest GitHub Release
        ↓
AgentOS-managed distribution
        ↓
project-owned partition preserved
        ↓
current AgentOS runtime
        ↓
normal additive schema migration
```

### Release validation for the AgentOS repository

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/validate_release.py .
git diff --check
```

This document replaces the version-specific updater-guide model for current releases.
