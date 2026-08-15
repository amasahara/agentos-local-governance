# AgentOS Local Governance v0.25.2

**27-Section Architecture Contract & Human Clarification Gates**

This release adds schema 50, a fixed human-owned 27-section Architecture Contract,
deterministic immutable architecture baselines, explicit review/approve/activate
lifecycle, a structured Grill Me gate, and runtime human-decision blockers. It also
removes stale CLI/MCP release literals by deriving runtime version from
`agentos.__version__`.

No architecture discovery/drift enforcement is introduced yet. SOURCE/TARGET,
privacy, secret, signed-audit and existing authority boundaries remain in place.
