# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.27.0**. Database schema: **58**; schema bootstrap baseline remains **46**.

v0.27.0 adds Governed Skill Contract v2. New skill candidates receive deterministic least-authority contracts; architecture-sensitive skills require the ACTIVE human-approved baseline and pin its exact hash. Human graduation/revocation authority is unchanged and automatic architecture-aware skill selection is deferred to v0.27.1.

Distribution changed in v0.27.0: download latest full release; no updater script is required. User skills, workflows/workflow state, source, architecture working copies, local governance overrides, state, and runtime artifacts remain project-owned.
