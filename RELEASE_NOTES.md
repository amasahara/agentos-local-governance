# AgentOS Local Governance v0.28.4 — Tool Exclusivity & Enforcement Attestation

AgentOS v0.28.4 establishes machine-verifiable tool exclusivity for AgentOS-mediated agent execution surfaces.

Database schema remains **61**.

## Highlights

### Canonical execution boundary

Supported agent-side process execution now uses the canonical AgentOS enforcement lifecycle:

```text
request
→ proxy preflight
→ guard
→ governed adapter execution
→ completion
→ tool_call_id
→ signed audit evidence
```

Synchronous process execution remains owned by the canonical process proxy. Asynchronous job execution is reintegrated into the same governed lifecycle.

### Guarded asynchronous process execution

`job-submit` and MCP `agentos.run_command_async` now route through the canonical async proxy boundary. The actual `subprocess.Popen()` side effect revalidates its execution token immediately before process creation and verifies task/session ownership, guarded command, working directory, timeout, filtered environment hash, immutable job specification hash, and `auto_start` authority.

Deferred queued jobs cannot use an already completed execution authority to start a process.

### Governed `run-tests`

`agentos run-tests` no longer owns a separate raw pytest subprocess path. It executes project tests through governed `process.exec` using `agentos.run_command`. The default project test surface is `tests/` rather than AgentOS internal tests.

### Legacy MCP gateways remain inactive

Historical `mcp_*_gateway.py` compatibility modules may remain in the repository, but they are not part of the active MCP runtime. The active runtime attests `subprocess_forwarding=false`, `legacy_gateway_active=false`, `legacy_gateway_handler_count=0`, and `trusted_enforcement_gateway=true`.

### Enforcement attestation

A new read-only command is available:

```text
agentos enforcement-attest
```

It deterministically verifies proxy-only execution, canonical guarded lifecycle, registry separation, backend-access restrictions, legacy path blocking, MCP trusted-gateway binding, sync/async signed lifecycle, guarded async `Popen`, process-primitive classification, and canonical process adapter presence.

Runtime now contains:

```text
341 canonical commands
245 agent-plane commands
98 privileged-control-plane commands
2 intentional dual-plane commands
0 unexpected agent/privileged overlap
```

### Fail-closed integration

Enforcement attestation is integrated into `runtime-health`, `doctor`, release integrity validation, and release policy validation.

v0.28.4+ requires:

```text
tool_exclusivity_attested = true
hard_anti_bypass_reserved_for_v0284 = false
tool_exclusivity_scope = agentos_mediated_agent_execution
enforcement_attestation_version = 1
```

### Explicit security scope

The v0.28.4 attestation scope is `agentos_mediated_agent_execution`.

The release intentionally does **not** claim same-user host bypass resistance, OS-level process isolation, or arbitrary host-process containment.

## Compatibility

No database migration is required.

```text
v0.28.3 schema: 61
v0.28.4 schema: 61
```

The Privileged Control Plane introduced in v0.28.3 remains intact.

## Next

The next planned roadmap node is:

**v0.29.0 — Independent Completion Verification**
