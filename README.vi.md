# AgentOS Local Governance v0.27.0 — Governed Skill Contract v2

[README landing](README.md) | [English](README.en.md)

## Phiên bản hiện tại

- Version: **0.27.0**
- Database schema: **58**
- Schema bootstrap baseline: **46** (không đổi)

v0.27.0 nâng subsystem skill hiện hữu từ procedural skill đơn giản thành **Governed Skill Contract v2**. AgentOS không tạo một skill framework thứ hai; lifecycle candidate → human graduation → revoke hiện tại được giữ lại và bổ sung contract machine-readable, hash, architecture binding và authority boundaries.

## Contract v2

Mỗi candidate mới khai rõ:

- input/output;
- Architecture sections bắt buộc;
- capability/tool cần thiết;
- read/write scope cho phép;
- dependency và external service cho phép;
- precondition/postcondition;
- risk tier;
- test contract;
- architecture constraints;
- deterministic contract hash.

Skill không thể dùng contract để tự cấp thêm quyền. Mọi quyền thực thi vẫn phải đi qua task/plan/architecture/capability/tool governance hiện hữu.

## Legacy skill

Skill v1 đã tồn tại được giữ nguyên:

```text
legacy v1 skill
      ↓
readable / usable theo lifecycle hiện hữu
      ↓
KHÔNG rewrite artifact đã được duyệt
```

Nếu muốn đưa một skill cũ sang v2, hướng đúng là tạo successor candidate/version mới để con người review lại, không sửa âm thầm artifact cũ.

## Architecture binding

Skill trung lập kiến trúc có thể validate mà không cần ACTIVE Architecture Baseline.

Skill khai `required_architecture_sections`, dependency/external service hoặc architecture constraint thì cần ACTIVE human-approved baseline. Validation thành công sẽ pin `architecture_baseline_id` và `architecture_baseline_hash`.

v0.27.0 chưa tự chọn skill theo kiến trúc; phần **Architecture-Aware Skill Selection & Evaluation** thuộc v0.27.1.

## Distribution mới — không dùng updater script

Từ v0.27.0, không còn yêu cầu chạy `apply_v0270.py` hay updater theo từng version.

AgentOS-managed distribution được tách khỏi dữ liệu project-owned. Release mới **không sở hữu và không overwrite**:

- user skills;
- project workflows / workflow state;
- project source;
- architecture working copy;
- `governance.local.json`;
- `.agents/state/**`;
- `.agents/runtime/**`.

Do đó chỉ cần tải **latest GitHub Release/source** để lấy AgentOS runtime mới nhất. Xem `.agents/docs/INSTALL_LATEST_RELEASE.md`.

## Command

```bash
agentos skill-contract-show --skill-id 1
agentos skill-contract-set --skill-id 1 --drafted-by human:architect --contract '{...}'
agentos skill-contract-validate --skill-id 1
agentos skill-contract-status
```

`skill-graduate` và `skill-revoke` vẫn human-gated. MCP chỉ đọc contract/status/list và không expose mutation authority.

## Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
git diff --check
```

Xem [Governed Skill Contract v2](.agents/docs/GOVERNED_SKILL_CONTRACT_V0270.md).
