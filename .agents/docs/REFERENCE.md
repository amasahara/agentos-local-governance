# Current Reference

## Repository roles

- `agentos_distribution`: distribution source, release metadata và managed payload.
- `governed_project`: application project đã cài AgentOS.

## Metadata ownership

- Distribution: `.agents/distribution/metadata.json`
- Installed AgentOS: `.agents/release/VERSION` và `.agents/release/install-manifest.json`
- Application: root `README.md` và root `VERSION`

## Current commands

- `project-init`
- `project-adopt`
- `repository-validate --role agentos_distribution`
- `repository-validate --role governed_project`
- `policy-compile`
- `runtime-health`
- `release-integrity-check`
- `manifest-verify`

## Policy

Source fragments nằm tại `.agents/config/policy/`. Generated effective policy nằm tại `.agents/config/generated/governance.effective.json` và phải được pin bằng deterministic hash.
