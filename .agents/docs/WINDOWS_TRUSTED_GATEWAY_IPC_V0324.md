# AgentOS Local Governance v0.32.4 — Windows Trusted Gateway IPC & Capability Completion Stabilization

Database schema: **65**

## Scope

This cumulative release preserves the capability-session bootstrap and stable completion-subject semantics introduced operationally in v0.32.3, then adds a Windows-safe trusted gateway IPC transport.

## Windows gateway IPC

- Windows uses project-scoped `AF_PIPE` Named Pipes.
- POSIX keeps the existing `AF_UNIX` transport.
- The Windows auth-key file is created under `.agents/runtime/` and protected with a non-inherited DACL.
- Full access is limited to the current execution identity, `SYSTEM`, and `BUILTIN\Administrators`.
- The gateway opens no TCP listener.
- Gateway ACL setup uses direct Win32 APIs rather than `subprocess.run`, `subprocess.Popen`, or `os.system`.

## Capability/completion carry-forward

- Session issuance remains a privileged control-plane operation.
- Capability sets remain derived from approved task scope.
- Raw session tokens are not persisted.
- Workflow completion-subject hashing excludes task ownership/liveness state.

## Security boundaries

This release does not add new filesystem, process, network, database, or MCP mutation authority. It does not replace Human approval and makes no claim of general same-user host isolation.

## Verification

Required release gates include:

- Windows IPC focused tests.
- Enforcement attestation with no unexpected process primitive.
- Live Named Pipe health probe with zero TCP listeners.
- Restricted auth-key ACL verification.
- Release integrity, documentation, instruction, and full regression checks.
