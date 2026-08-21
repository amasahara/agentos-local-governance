# AgentOS Local Governance

**Local-first governance runtime for AI coding agents.**
**Hệ thống quản trị cục bộ cho AI coding agents: policy, approval, architecture, multi-agent coordination, controlled integration và audit.**

[🇻🇳 Tiếng Việt](README.vi.md) · [🇬🇧 English](README.en.md) · [Latest Release](https://github.com/amasahara/agentos-local-governance/releases/latest) · [Changelog](CHANGELOG.md)

---

## What is AgentOS Local Governance?

AgentOS Local Governance is a **project-local control and governance layer for AI coding agents**.

It is designed for projects where one or more AI agents can inspect, plan, modify, review, or coordinate work, but those agents must remain inside explicit project rules and human-owned authority.

AgentOS adds reusable governance primitives around an existing project:

- policy and capability boundaries;
- human approval and clarification gates;
- governed task / plan lifecycle;
- architecture contracts and compliance;
- context, knowledge and privacy controls;
- governed skills;
- multi-agent worker supervision;
- isolated workspaces and controlled integration;
- auditable state;
- CLI, MCP, Command Center and an optional local Web Control Plane.

> AgentOS does not replace the LLM, coding agent, IDE, Git, or human architect. It governs how those components are allowed to act inside a project.

For the full explanation:

- [README tiếng Việt](README.vi.md)
- [English README](README.en.md)

---

## Download once, run the full release

Current releases follow a **Latest Full Release** model.

You do **not** need to install every historical updater in sequence.

```text
GitHub Release / source archive
            ↓
      extract or clone
            ↓
       run AgentOS
```

For an existing governed project, preserve project-owned state and local overrides when refreshing the AgentOS-managed distribution.

See [Install / Refresh from Latest Full Release](.agents/docs/INSTALL_LATEST_RELEASE.md).

---

## Current release

### v0.28.1 — Optional Local Web Control Plane

v0.28.1 adds an optional, loopback-only browser interface on top of the existing read-only Command Center snapshot.

```text
Architecture / Tasks / Agents / Workspaces / Compliance / Human Actions
                              ↓
                    Command Center Snapshot
                       ↓       ↓       ↓
                      CLI     MCP    Web UI
```

The Web Control Plane does **not** add a second governance backend or new mutation authority.

- Database schema: **61**
- CLI commands: **336**
- MCP tools: **123**
- Full regression: **565 passed, 1 expected Windows skip**
- [Release notes](RELEASE_NOTES.md)
- [v0.28.1 technical documentation](.agents/docs/OPTIONAL_LOCAL_WEB_CONTROL_PLANE_V0281.md)

---

## Quick links

- [Vietnamese documentation](README.vi.md)
- [English documentation](README.en.md)
- [Installation / latest full release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [Current release notes](RELEASE_NOTES.md)
- [Changelog](CHANGELOG.md)
- [GitHub Releases](https://github.com/amasahara/agentos-local-governance/releases)
- [GitHub Tags](https://github.com/amasahara/agentos-local-governance/tags)

---

## Authority principle

```text
Human defines authority
        ↓
AgentOS enforces governance
        ↓
Agents execute only inside granted boundaries
        ↓
Command Center / Web UI provide visibility
```

**Human authority remains authoritative. AgentOS governs execution; it does not grant itself authority.**
