# AgentOS Local Governance v0.26.3 — Quality/Operational Enforcement

## Tiếng Việt

v0.26.3 hoàn thiện lớp Architecture Governance enforcement cho nhóm `ARCH-15..21`:
Logging, Error Handling, Security, Performance, Scalability, Deployment và Testing.

Release bổ sung schema 57, plan-time quality/operational declarations, static precommit
checks, write-target safeguards cho security/deployment paths, persisted findings và ba
MCP tool read-only. AgentOS chỉ enforce các rule machine-readable đã được human architect
đưa vào ACTIVE Architecture Contract; không tự biến best practice hoặc suy luận LLM thành authority.

Các kiểm tra tiêu biểu gồm sensitive logging, bare/broad exception policy, forbidden
security calls, `shell=True`, TLS `verify=False`, literal secret policy, async blocking
calls, Python file-size budget, scalability call boundaries, container base image/non-root/
privileged constraints, và source-change -> required-test-change rules.

Architecture Authority vẫn thuộc con người. Violation hợp lệ về mặt nhu cầu phải đi qua
Architecture Change Proposal + ADR + Human Approval + successor baseline + re-plan.

## English

v0.26.3 completes Architecture Governance enforcement for `ARCH-15..21`: Logging,
Error Handling, Security, Performance, Scalability, Deployment, and Testing.

The release adds schema 57, plan-time quality/operational declarations, deterministic
static precommit checks, security/deployment target safeguards, persisted findings, and
three read-only MCP tools. AgentOS enforces only machine-readable rules declared in the
human-approved ACTIVE Architecture Contract; generic best practices and LLM inference do
not become authority automatically.

Representative checks cover sensitive logging, bare/broad exception policies, forbidden
security calls, `shell=True`, TLS `verify=False`, literal-secret policy, blocking calls in
async code, Python file-size budgets, scalability call boundaries, container base-image/
non-root/privileged constraints, and source-change-to-test-change contracts.

Architecture Authority remains human-owned. Legitimate architecture changes must use an
Architecture Change Proposal, ADR, human approval, successor baseline, and re-planning.
