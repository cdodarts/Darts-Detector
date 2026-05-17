# Versioning Policy

The project has **four versioned surfaces**. Each follows semver. None of them are allowed to drift independently of the others.

This is the authoritative document for backwards compatibility. Every breaking change is governed by what's written here.

## The Four Versioned Surfaces

| Surface | Semver Tracked In | Authoritative File |
| --- | --- | --- |
| Application version | `pyproject.toml` `version` | `pyproject.toml` |
| WebSocket / JSON event schema | `version` field on every event | [schemas/dart-event.schema.json](../schemas/dart-event.schema.json) |
| Config file schema | `version` field at the top of every YAML config | `schemas/config.schema.json` (created in Phase 1) |
| Calibration profile schema | `version` field in the profile JSON | `schemas/calibration-profile.schema.json` (created in Phase 3) |

Plus the **Public Python API** which follows the *application version* but has additional deprecation rules below.

## Semver Definitions For Each Surface

### Application Version

The number a user sees. Stored in `pyproject.toml`.

- **Patch** (`1.0.0` → `1.0.1`): bug fixes. No schema, config, or public API change.
- **Minor** (`1.0.0` → `1.1.0`): additive features. Backward-compatible config and schema changes. New public API surfaces may be added.
- **Major** (`1.0.0` → `2.0.0`): breaking changes. Goes through the RFC process in [PROJECT_CHARTER.md](PROJECT_CHARTER.md).

The application version drives the release tag and the GitHub release notes.

### WebSocket / Event Schema Version

The wire format. Versioned independently of the app so the schema can stabilise faster than the app.

- **Patch**: clarifications only. No on-the-wire change.
- **Minor**: additive fields, additive enum values, new optional event types. Clients on the same major continue to work.
- **Major**: removed/renamed fields, changed field types, changed enum semantics. Requires:
  1. RFC.
  2. ADR in [DECISIONS.md](DECISIONS.md).
  3. Parallel emit period: the producer emits BOTH the old and new shapes for at least one full minor cycle of the application version.
  4. Client negotiation: `?clientVersion=` parameter.

### Config Schema Version

Config files declare their schema version at the top:

```yaml
version: 1
cameras:
  ...
```

- **Patch**: typo or comment fix. No file format change.
- **Minor**: additive fields, additive enum values. Older config files still load. Defaults applied for new fields.
- **Major**: removed fields, renamed fields, changed defaults that affect behaviour. Requires a migration tool (`darts-detector migrate-config`) that converts older format to newer. The app refuses to start with an unmigrated config and points to the migration tool.

### Calibration Profile Schema Version

Calibration profiles are JSON, validated against `schemas/calibration-profile.schema.json`, and declare their version.

- **Patch**: documentation only.
- **Minor**: additive fields. Older profiles still load.
- **Major**: structural change. Requires a migration tool. The app refuses to load an unmigrated profile and points to the migration tool. The user MUST run the calibration self-test ([CALIBRATION_SYSTEM.md](CALIBRATION_SYSTEM.md)) after migration before scoring resumes.

### Public Python API

The set of modules under `src/darts_detector/api_public/` and any module marked `@public-stable` in its docstring header.

- **Patch**: implementation changes that preserve behaviour. No signature change.
- **Minor**: new functions, classes, kwargs with defaults. Existing call sites continue to work.
- **Major**: removed/renamed/typed-differently functions, removed kwargs, changed default behaviour. Requires a full deprecation cycle (below).

## Deprecation Cycle

Anything in the public API or any stable schema that we want to remove follows this cycle:

1. **Deprecated in version `N.X`**: the symbol/field still works, but issuing a `DeprecationWarning` (Python) or a `deprecation` field in the event (wire) when used.
2. **Documented in the changelog**: every release that deprecates something lists it under "Deprecations" with the planned removal version.
3. **Removed in version `N+1.0`**: the next major bump, AND at least 6 months after deprecation, whichever is later.

Minimum deprecation period: **6 months OR one minor version cycle, whichever is longer**.

There is no shortcut. There is no "we'll do it in a hotfix".

## Backwards Compatibility Tests

Every release CI run includes:

1. **Replay regression test**: the labelled throw dataset is run through the current code. Scores must match the previous release within tolerance.
2. **Config compatibility test**: every config file from the previous N minor versions must load (with migration if needed) and produce a working runtime.
3. **Calibration profile compatibility test**: every calibration profile from the previous N minor versions must load (with migration if needed) and produce a valid self-test.
4. **Schema validation test**: every emitted event in the test corpus validates against the current schema. Old test corpora validate against their declared schema version.

A PR that breaks any of these is blocked from merging unless the PR description explicitly:

- Bumps the relevant major version.
- References the accepted RFC.
- Provides the migration tool.

## Migration Tooling

When a config or calibration profile major bump happens, a CLI migration tool ships in the same release:

```bash
darts-detector migrate-config /path/to/old.yaml --output /path/to/new.yaml
darts-detector migrate-calibration /path/to/old.json --output /path/to/new.json
```

The tool MUST:

- Be idempotent (running twice is safe).
- Refuse to overwrite without `--force`.
- Print a clear summary of what it changed.
- Exit non-zero on failure with a clear error message.

The application MUST refuse to load an unmigrated file and MUST point to this tool.

## Release Cadence

Target cadence once MVP ships:

- **Patch releases**: as needed for bugs.
- **Minor releases**: roughly every 8–12 weeks.
- **Major releases**: when the RFC backlog and migration plan warrant it. Not on a fixed schedule. Avoid breaking changes unless the maintainability gain is large.

Each release has:

- A tagged git commit.
- A changelog entry (added/changed/deprecated/removed/fixed sections — Keep A Changelog format).
- A GitHub release with binary or source artefacts as appropriate.

## Plugin Compatibility

Plugins declare the minimum and maximum core API version they support:

```toml
[darts-detector-plugin]
name = "my-plugin"
core-api-min = "1.2.0"
core-api-max = "1.x"
```

The plugin loader (Phase post-MVP) refuses to load plugins outside that range with a clear error.

Plugins are NOT bound by core's deprecation cycle. A plugin author may break their own users at any time. But core MUST NOT break plugins within a major version.

## Versioning Anti-Patterns We Will Not Do

- Silently changing field meanings without a version bump.
- "We renamed it but the old name still works forever" — accumulates technical debt. Use the deprecation cycle.
- Skipping the migration tool because "users can edit the file themselves".
- Backporting features to patch releases.
- Releasing without a changelog entry.

## What Future Agents Must Do

- Before changing any contract, calculate what version bump applies and whether it's allowed in the current phase.
- Before declaring work done, update the relevant version field and the changelog.
- Route any major-bump work through the RFC process. Refuse the request if no RFC exists.
- When in doubt, choose the more conservative (smaller) bump and ask the architecture owner.
