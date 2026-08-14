# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.25.0**. Database schema: **49**.

## Schema Bootstrap Baseline

For a new empty state DB, `db.migrate()` selects the schema-46 bootstrap artifact
and then applies only 47→49. For an existing versioned DB it remains incremental.

The baseline is immutable release data under `.agents/schema/` and must pass
schema fingerprint equivalence against historical replay.

Never bootstrap an unversioned non-empty database; fail closed instead.

Versioned updater/recovery files remain GitHub Release assets, not clean-main files.
