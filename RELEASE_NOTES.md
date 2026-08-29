# AgentOS Local Governance v0.29.1 — Windows Process-Tree Containment

AgentOS v0.29.1 adds native Windows process-tree containment for AgentOS-mediated execution while keeping database schema **62**.

## Highlights

### Assign-before-resume Windows containment

On Windows, governed synchronous execution creates the root process suspended, creates a Job Object, assigns the root process to that Job, and only then resumes user-mode execution. This closes the spawn/assign race for the AgentOS-mediated root.

### Whole-tree synchronous teardown

The synchronous Windows runner owns Job Object containment. Governed timeout and teardown terminate or close the Job as a tree, including descendants that remain after the root exits. POSIX execution remains on its existing process-group path.

### Durable async Job broker

Windows asynchronous jobs use a dedicated AgentOS broker process. The broker creates a unique named Job Object with `KILL_ON_JOB_CLOSE`, creates the worker root suspended, assigns the worker before resume, emits READY evidence, remains alive as the durable Job-handle owner, tracks Job membership, and writes a completion receipt with the worker root exit code.

The broker itself is not assigned to the worker Job.

### Fail-closed async lifecycle

- cancellation terminates the named Job tree;
- timeout terminates the named Job tree and persists `timed_out` / exit code **124**;
- broker failure closes the durable Job handle and kills the associated worker tree;
- missing broker evidence before deadline is containment loss/orphaning rather than success;
- normal completion requires a broker drain receipt;
- root exit code `0` materializes `succeeded`;
- non-zero root exit materializes `failed`.

### Machine-verifiable attestation

`agentos enforcement-attest` verifies the bounded Windows containment contract: synchronous routing, create-suspended / assign-before-resume, synchronous tree teardown, async broker kill-on-close ownership, guarded broker launch, Job-membership liveness, whole-tree cancellation, whole-tree timeout, broker completion evidence, and preserved broad nonclaims.

Attested scope:

```text
agentos_mediated_process_execution
```

### Windows CI release gate

The release-validation workflow contains a separate `windows-latest` job. It runs release validation, manifest verification, runtime/documentation checks, the focused Windows containment/activation tests, and the full regression suite. Release integrity requires this CI contract for v0.29.1+.

## Explicit claim boundary

> AgentOS-mediated Windows process trees are Job Object contained before root execution resumes, with whole-tree termination on governed timeout, cancellation, broker failure, and synchronous teardown.

This claim is limited to execution launched through AgentOS-mediated process surfaces.

v0.29.1 does **not** claim same-user host bypass resistance, general OS process isolation, arbitrary host-process containment, containment of unrelated same-user processes that bypass AgentOS, or replacement of stronger OS/container sandboxing.

The v0.29.0 Independent Completion Verification contract remains intact.

## Compatibility

- AgentOS version: **0.29.1**
- database schema: **62**
- no new database migration;
- existing schema-62 state remains current;
- distribution model remains **Latest Full Release**;
- project-owned source, skills/workflows, state, runtime data, and local governance overrides remain outside the managed replacement boundary.
