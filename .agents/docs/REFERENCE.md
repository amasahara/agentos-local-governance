# Current Reference

## Repository roles

- `agentos_distribution`: distribution source, release metadata và managed payload.
- `governed_project`: application project đã cài AgentOS.

## Metadata ownership

- Distribution: `.agents/distribution/metadata.json`
- Installed AgentOS: `.agents/release/VERSION` và `.agents/release/install-manifest.json`
- Application: root `README.md` và root `VERSION`

## Current execution planes

Agent execution plane — `agentos`:

- `project-adopt` performs read-only adoption scanning;
- `repository-validate` validates repository contracts;
- `policy-compile` materializes deterministic effective policy;
- `runtime-health` reports execution-plane health;
- normal governed agent commands remain on this plane.

Privileged control plane — `agentos-admin`:

- `project-init`;
- `project-adopt --apply`;
- human/operator approval and activation commands;
- project identity and primary-project authority;
- privileged domain mutations.

Dual-plane commands are argument-gated:

- `project-adopt`;
- `architecture-init`.

MCP and Web Control Plane do not expose privileged mutation authority.

## Policy

Source fragments nằm tại `.agents/config/policy/`. Generated effective policy nằm tại `.agents/config/generated/governance.effective.json` và phải được pin bằng deterministic hash.
