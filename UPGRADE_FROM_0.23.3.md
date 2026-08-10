# Upgrade v0.23.3 → v0.23.4

AgentOS v0.23.4 introduces **Incremental Symbol Index** and upgrades the local AgentOS database schema from **46 → 47**.

## Standard upgrade

For a clean and coherent v0.23.3 repository, Windows, Linux, and macOS use the same Python updater:

```bash
python tools/apply_v0234.py .
```

The updater is fail-closed and performs the v0.23.4 upgrade as one governed operation:

```text
verify v0.23.3 / schema 46
→ back up files affected by the upgrade
→ install Incremental Symbol Index
→ migrate schema 46 → 47
→ capture INDEX_INCREMENTAL_BENCHMARK_V0234.json
→ rebuild release manifest/checksums
→ run v0.23.4 targeted regression tests
→ validate release integrity
→ finalize VERSION 0.23.4
```

Do not manually change `VERSION` or the AgentOS schema before running the updater.

## Recovery from a partially applied v0.23.4 upgrade

If an earlier v0.23.4 updater stopped after modifying `indexing.py` but before completing the release, the repository may remain in a recoverable partial state such as:

```text
VERSION = 0.23.3
schema = 46
indexing.py = incremental/partial v0.23.4 implementation
```

Typical preflight errors from this state include:

```text
indexing.py is not the expected v0.23.3 full-rebuild baseline
```

or:

```text
indexing.py semantic baseline is unsupported for v0.23.4
mode = incremental_or_partial_v0234
```

Do not manually restore or edit `indexing.py`.

Use the recovery updater instead:

```bash
python tools/apply_v0234_recover.py .
```

The recovery updater:

```text
detects the known partial v0.23.4 indexing state
→ backs up the partial file
→ restores the canonical v0.23.3 indexing baseline
→ re-runs the complete v0.23.4 upgrade
→ migrates schema 46 → 47
→ captures the v0.23.4 benchmark
→ rebuilds manifest/checksums
→ runs targeted tests
→ validates release integrity
→ finalizes VERSION 0.23.4
```

The recovery path is intended only for a recognized, deterministic partial-upgrade state. Unknown source modifications remain fail-closed.

## Verify the resulting release

After a successful upgrade, verify:

```bash
cat VERSION
```

Expected:

```text
0.23.4
```

On Windows PowerShell:

```powershell
Get-Content .\VERSION
```

The AgentOS database schema should be:

```text
47
```

The upgrade should also produce:

```text
INDEX_INCREMENTAL_BENCHMARK_V0234.json
```

This benchmark records the v0.23.4 incremental-index behavior and retains the measured v0.23.3 full-rebuild baseline as the historical comparison point.

## Run the full regression suite

The updater runs the targeted v0.23.4 regression suite automatically. Before publishing the release, also run the full repository test suite.

### Linux / macOS

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests
```

### Windows PowerShell

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests
```

Platform/capability-dependent tests may be skipped when the host does not provide the required operating-system capability, for example Windows symbolic-link privileges. A skipped test is not a failure; release validation requires **zero failed tests**.

For skip details:

```bash
python -m pytest -q .agents/tests -rs
```

## Incremental index verification

After upgrade, the first index build bootstraps schema-47 index state:

```bash
agentos index-build src
```

Subsequent builds are incremental.

With no source changes:

```text
files_parsed = 0
```

After modifying one Python source file:

```text
files_parsed = 1
```

Deleted source files remove their stale symbol-index records without requiring a complete rebuild.

A full rebuild remains available explicitly:

```bash
agentos index-build src --full
```

Inspect current index metadata with:

```bash
agentos index-status
```

## Safety invariants

v0.23.4 changes symbol-index maintenance only. It does not relax existing AgentOS governance boundaries.

The following remain unchanged:

* SOURCE databases remain read-only.
* TARGET database mutations remain controlled and approval-gated.
* Identity and lineage decisions retain their existing authority boundaries.
* Recovery does not introduce automatic unsafe TARGET repair.
* MCP receives no new privileged index mutation authority.
* Secret, privacy, signed-audit, and Requirement-Preserving Context Compression guarantees remain in force.
