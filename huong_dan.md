# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.22.7**. Database schema: **43**.

Use the immutable data-subject erasure request/plan lifecycle and keep review/approval/execution in the governed operator boundary. Local erasure may complete without TARGET mutation; `external_target_erasure_required` is the explicit handoff signal when external TARGET data remains.
