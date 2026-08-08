[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

# AgentOS v0.20.0 Developer Guide

## 1. After upgrading from v0.19.5

1. Run `project-identity-init` to establish the durable project UUID and local instance UUID.
2. A human confirms domain/purpose/capabilities/role with `project-purpose-set --human-confirmed`.
3. Run `project-identity-db-sync` if migration 32 has not already been applied through the normal runtime migration path.
4. Run `project-identity-verify`; do not proceed with cross-project work on `instance_clone_conflict` or `purpose_incomplete`.
5. Run tests, `docs-check`, `instruction-check`, `audit-verify`, and the v0.19.5 backup verification path.

## 2. Move, clone, and fork

- **Move:** retains project and instance identity; the host registry records relocation when the old path no longer exists.
- **Clean Git clone:** retains project identity but generates a new local instance UUID.
- **Full directory copy:** copying local state can duplicate the instance UUID; two live paths fail closed.
- **Fork:** `project-fork --human-confirmed` creates a new project UUID while preserving lineage.

## 3. Purpose

Purpose describes business identity rather than technology stack. Generic technical overlap is not evidence that two projects share the same purpose. v0.20.1 will consume this contract for domain compatibility.

## 4. MCP

Coding agents can read identity and purpose only. Identity/purpose mutation remains a human-operated CLI path.
