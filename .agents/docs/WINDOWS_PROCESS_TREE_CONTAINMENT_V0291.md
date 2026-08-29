# Windows Process-Tree Containment — v0.29.1

## Scope

This contract applies only to `agentos_mediated_process_execution`. It does not establish a general Windows sandbox.

## Synchronous execution

```text
AgentOS process.exec
        ↓
CreateProcessW(CREATE_SUSPENDED)
        ↓
Create Job Object
        ↓
AssignProcessToJobObject
        ↓
ResumeThread
        ↓
governed execution
        ↓
timeout / teardown
        ↓
TerminateJobObject or kill-on-close
```

The root process is assigned before user-mode execution resumes.

## Asynchronous execution

```text
AgentOS start_job
        ↓
dedicated Windows Job broker
        ↓
named Job Object + KILL_ON_JOB_CLOSE
        ↓
worker CreateProcessW(CREATE_SUSPENDED)
        ↓
AssignProcessToJobObject
        ↓
ResumeThread
        ↓
READY evidence
        ↓
broker remains durable Job-handle owner
```

The broker is not assigned to the Job it manages.

## Liveness and terminal state

Windows async liveness is derived from Job membership rather than only root-PID presence. Normal terminal completion requires a broker drain receipt carrying the worker root exit code.

```text
root exit 0     → succeeded
root exit != 0  → failed
timeout         → timed_out / exit 124
broker missing without terminal evidence → orphaned / containment loss
```

## Cancellation, timeout, and broker failure

Cancellation and timeout use whole-Job termination, not root-only `os.kill(pid, ...)`. Unexpected broker termination closes the durable `KILL_ON_JOB_CLOSE` owner handle and fails closed on the associated worker process tree.

## CI and release attestation

v0.29.1 requires structural process-tree attestation, policy-declared containment attestation, `windows-latest` CI, focused Windows containment/activation tests, and the full Windows regression suite.

## Nonclaims

v0.29.1 does not claim same-user host bypass resistance, general OS process isolation, arbitrary host-process containment, or containment of processes not launched through AgentOS-mediated execution.
