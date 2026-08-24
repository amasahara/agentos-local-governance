# AgentOS Local Governance v0.28.2 — Project Bootstrap & Repository Normalization

v0.28.2 cleans and normalizes the repository and project bootstrap foundation. It adds no new security feature.

## Release identity

- AgentOS version: **0.28.2**
- Database schema: **61**
- Distribution role: `agentos_distribution`
- Installed project role: `governed_project`
- Distribution metadata authority: `.agents/distribution/metadata.json`
- Installed metadata root: `.agents/release/`

Release coherence is checked against the current distribution metadata, package version, schema source, current README files, release notes, manifest, and checksums.

## Project lifecycle

The legacy installer flow is replaced by two explicit commands:

- `project-init` initializes a new governed project.
- `project-adopt` produces a read-only plan for an existing project and mutates only with `--apply --human-confirmed`.

Every installed project receives a newly generated project UUID. Business domain and purpose begin as `UNCONFIRMED`; the distribution contains no representative Hospital Core purpose.

## Ownership boundary

AgentOS writes only its managed payload under the application `.agents/` directory. It does not copy or overwrite application-root:

- `README.md` or `README.en.md`;
- `VERSION`;
- `huong_dan.md`;
- application source or tests.

Distribution metadata and installed-project metadata are separate documents with separate roles.

## Installed payload

The current installed payload contains:

- unified runtime modules;
- current cross-platform launchers;
- current schema;
- current governance baseline and modular policy sources;
- deterministic generated effective policy;
- current user-journey documentation.

It excludes repository tests, historical launchers, historical documentation, update utilities, release-maintenance tools, runtime caches, and representative application identity.

## Documentation

Current documentation is organized as:

- `.agents/docs/QUICKSTART.md`
- `.agents/docs/NEW_PROJECT.md`
- `.agents/docs/EXISTING_PROJECT.md`
- `.agents/docs/WINDOWS.md`
- `.agents/docs/REFERENCE.md`

Historical release details remain in `CHANGELOG.md`, Git tags, and archived release artifacts.

## Policy compilation

The effective policy is generated deterministically from:

1. the current governance baseline;
2. sorted modular fragments under `.agents/config/policy/`;
3. the optional project-owned `governance.local.json`.

The generated output is `.agents/config/generated/governance.effective.json`. Source paths and SHA-256 hashes are recorded with the compilation result.

## Validation

`repository-validate --role agentos_distribution` validates distribution identity and metadata.

`repository-validate --role governed_project` validates installed metadata, generated identity, effective policy, and application-root ownership boundaries.
