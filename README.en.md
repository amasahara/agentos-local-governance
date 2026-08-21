# AgentOS Local Governance

**A local-first governance layer for AI coding agents inside a software project.**

[README landing](README.md) · [🇻🇳 Tiếng Việt](README.vi.md) · [Latest Release](https://github.com/amasahara/agentos-local-governance/releases/latest) · [Changelog](CHANGELOG.md)

---

## 1. What is AgentOS Local Governance?

AgentOS Local Governance is a **project-local governance layer** that controls how AI coding agents consume context, plan work, use tools, modify files, coordinate multiple workers, and integrate changes.

The project is not intended to be another LLM or coding agent. AgentOS acts as an **operating/governance layer around existing agents**.

A governed execution path can look like:

```text
User request
    ↓
Policy / capability / project scope
    ↓
Provenance-aware context and knowledge
    ↓
Governed task / plan
    ↓
Architecture contract
    ↓
Eligible skill / capability
    ↓
Authorized worker / workspace
    ↓
Compliance checks
    ↓
Human approval where required
    ↓
Controlled integration
    ↓
Audit / Command Center
```

AgentOS is intended for projects that need stronger AI automation while preserving:

- human-owned authority;
- explicit permission boundaries;
- traceable decisions and changes;
- multi-agent coordination without uncontrolled file collisions;
- architecture and policy compliance;
- privacy, secret and state boundaries;
- controlled integration into the primary project.

---

## 2. Problems the project addresses

Direct use of coding agents can create recurring governance problems:

- an agent edits outside the requested scope;
- multiple agents write to the same files/resources;
- compression or truncation loses important requirements;
- knowledge is stale or lacks provenance;
- architecture drifts over repeated changes;
- work is executed without an approval/decision trail;
- tools or skills are invoked without a governed contract;
- worker changes are integrated too early;
- sensitive data crosses a context/tool boundary;
- operators cannot see the current governed system state.

AgentOS implements reusable project-level primitives for those problems rather than depending on one prompt per agent.

---

## 3. Major capability layers

### Governance & Authority

- policy enforcement;
- capability/session boundaries;
- human clarification and approval gates;
- auditable state;
- fail-closed validation;
- separation between human authority and agent execution.

### Context, Knowledge & Privacy

- context transport;
- requirement-preserving compression;
- adaptive token budgets;
- context expansion/evaluation;
- provenance-aware knowledge;
- stale detection;
- memory scope;
- privacy lifecycle and data-subject rights.

### Architecture Governance

- Architecture Contract;
- discovery and evidence binding;
- drift and compliance;
- Architecture Change Proposals;
- ADR lifecycle;
- architecture-aware task planning;
- structural enforcement;
- runtime/data/API/business-boundary enforcement;
- quality/security/operational enforcement.

### Governed Skills

- Governed Skill Contract v2;
- architecture-aware skill selection;
- skill evaluation and eligibility;
- provenance/freshness-aware skill binding.

### Multi-Agent Governance

- Multi-Agent Worker Supervisor;
- dependency DAGs;
- role/session/lease validation;
- file/write-overlap protection;
- isolated worker workspaces;
- controlled integration;
- conflict detection;
- human-reviewed integration.

### Operator Interfaces

- unified CLI;
- governed/read-only MCP surfaces;
- Architecture & Agent Command Center;
- Optional Local Web Control Plane.

---

## 4. High-level architecture

```text
                    Human / Project Owner
                           │
                           ▼
                  Governance & Policy
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
         Context       Architecture      Privacy
        /Knowledge      Governance       /Security
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                    Governed Task/Plan
                           │
                           ▼
                    Governed Skills
                           │
                           ▼
                Multi-Agent Supervisor
                           │
                           ▼
                  Isolated Workspaces
                           │
                           ▼
                 Controlled Integration
                           │
                           ▼
              State / Audit / Compliance
                           │
               ┌───────────┼───────────┐
               ▼           ▼           ▼
              CLI         MCP     Command Center
                                      │
                                      ▼
                            Optional Local Web UI
```

CLI, MCP and the Web UI do **not** create separate authority systems. They use the same AgentOS core and governed state.

---

## 5. What AgentOS is not

AgentOS Local Governance is not:

- an LLM provider;
- an IDE;
- a Git replacement;
- a mandatory cloud service;
- an autonomous authority that can approve itself;
- an automatic merge/commit/push system;
- a historical updater chain users must execute one version at a time.

Model/provider selection remains outside AgentOS authority. Human/project authority remains authoritative.

---

## 6. Distribution model: download a full release and run it

Current releases use the **Latest Full Release** model.

A new user does **not** need to run a historical updater chain.

```text
GitHub Release / source archive
            ↓
       obtain full source
            ↓
        extract or clone
            ↓
          run AgentOS
```

Development patch/hotfix scripts are release-development tools, not required end-user artifacts.

### Clone a tagged release

```bash
git clone https://github.com/amasahara/agentos-local-governance.git
cd agentos-local-governance
git checkout v0.28.1
```

Or download a source archive from:

- [GitHub Releases](https://github.com/amasahara/agentos-local-governance/releases)
- [GitHub Tags](https://github.com/amasahara/agentos-local-governance/tags)

Full instructions:

[Install / Refresh from Latest Full Release](.agents/docs/INSTALL_LATEST_RELEASE.md)

---

## 7. Quick start

### Windows PowerShell

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path

.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd command-center
```

Optional Local Web Control Plane:

```powershell
.agents\bin\agentos.cmd web-control-plane
```

Default bind:

```text
127.0.0.1:8765
```

Non-loopback binds fail closed.

### POSIX

```bash
export PYTHONPATH="$(pwd)/.agents"

.agents/bin/agentos runtime-health
.agents/bin/agentos command-center
```

---

## 8. Latest release — v0.28.1

### Optional Local Web Control Plane

v0.28.1 adds an optional local browser interface on top of the read-only v0.28.0 Command Center model.

```text
Architecture
Tasks / Agents
Workspaces
Compliance
Human Actions
      │
      ▼
Command Center Snapshot
   │      │      │
   ▼      ▼      ▼
  CLI    MCP   Web UI
```

Important invariants:

- loopback-only by default;
- one-time browser bootstrap;
- ephemeral in-memory sessions;
- Host/Origin validation;
- no CORS;
- no external assets;
- no direct database mutation;
- no architecture approval authority;
- no worker-launch authority;
- no integration approval authority;
- no model/provider authority.

| Component | v0.28.1 |
|---|---:|
| Database schema | 61 |
| CLI commands | 336 |
| MCP tools | 123 |
| Manifest files | 300 |
| Focused Web tests | 16 passed |
| Full regression | 565 passed, 1 expected Windows skip |

Documentation:

- [v0.28.1 Release Notes](RELEASE_NOTES.md)
- [Optional Local Web Control Plane v0.28.1](.agents/docs/OPTIONAL_LOCAL_WEB_CONTROL_PLANE_V0281.md)
- [Install Latest Full Release](.agents/docs/INSTALL_LATEST_RELEASE.md)

---

## 9. Recent releases

| Version | Main change |
|---|---|
| [v0.28.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.28.1) | Optional Local Web Control Plane |
| [v0.28.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.28.0) | Architecture & Agent Command Center |
| [v0.27.3](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.3) | Isolated Workspace & Controlled Integration |
| [v0.27.2](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.2) | Multi-Agent Worker Supervisor |
| [v0.27.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.1) | Architecture-Aware Skill Selection & Evaluation |
| [v0.27.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.0) | Governed Skill Contract v2 |
| [v0.26.3](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.3) | Quality / Security / Operational Enforcement |
| [v0.26.2](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.2) | Runtime / Data / API / Business Boundary Enforcement |
| [v0.26.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.1) | Structural Enforcement |
| [v0.26.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.0) | Architecture-Aware Task Planning |
| [v0.25.5](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.5) | Architecture Change Proposal & ADR |
| [v0.25.4](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.4) | Architecture Drift & Compliance |
| [v0.25.3](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.3) | Architecture Discovery & Evidence Binding |
| [v0.25.2](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.2) | Architecture Contract & Human Clarification |
| [v0.25.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.1) | Release Metadata Coherence |
| [v0.25.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.0) | Schema Bootstrap Baseline |

Complete history:

- [CHANGELOG.md](CHANGELOG.md)
- [GitHub Releases](https://github.com/amasahara/agentos-local-governance/releases)
- [GitHub Tags](https://github.com/amasahara/agentos-local-governance/tags)

---

## 10. Ownership boundary when refreshing AgentOS

### AgentOS-managed distribution

```text
.agents/agentos/**
release-owned policy
AgentOS docs/tests/runtime launchers
release metadata
```

### Project-owned data

```text
user skills
project workflows / workflow state
project source
architecture working copy
governance.local.json
.agents/state/**
.agents/runtime/**
```

When refreshing AgentOS in an existing project, do not delete the project-owned partition just to replace the runtime distribution.

See [Install / Refresh from Latest Full Release](.agents/docs/INSTALL_LATEST_RELEASE.md).

---

## 11. Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
git diff --check
```

v0.28.1 final validation:

```text
565 passed
1 expected Windows skip
0 failed
```

---

## 12. Authority principle

```text
Human Architect / Project Owner
             │
             ▼
        defines authority
             │
             ▼
   AgentOS validates/enforces
             │
             ▼
 Agents execute inside boundaries
             │
             ▼
 Audit / Compliance / Visibility
```

> **Human defines authority. AgentOS governs execution. Agents do not grant themselves authority.**
