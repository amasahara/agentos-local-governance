# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.24.3**. Database schema: **49**.

## MCP Feature Runtime Refactor

Active MCP code must follow:

```text
mcp_runtime            protocol/dispatch only
mcp_core_runtime       governed core tools
mcp_feature_runtime    read-only feature registry/dispatcher
mcp_feature_handlers   runtime-native migrated handlers
```

Do not add active imports from `mcp_*_gateway.py` or `mcp_server.py`.
Do not introduce subprocess/version forwarding into these modules.

Governed core tools keep the trusted `gateway_client → gatewayd` enforcement
boundary. Feature MCP remains read-only unless a future governance node explicitly
changes authority.

## Release gate

```text
build manifest → verify manifest → validate release → full regression → tag/release
```

Versioned updater/recovery scripts remain GitHub Release assets outside clean main.
