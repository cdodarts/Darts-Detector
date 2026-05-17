# Project Charter

This charter sets the long-term identity, governance, and architectural philosophy of the darts detector project. **It overrides any conflicting guidance in any other document.** Future agents, contributors, and maintainers MUST read and respect it.

## Identity

The darts detector is an **open-source community project** intended to be maintained over many years by multiple contributors, modelled after the philosophy of **OBS Studio** and **Blender**:

- A stable, long-lived core maintained by a small group of architecture owners.
- A clear plugin/extension surface so the community can add features without forking.
- Stable contracts and long deprecation cycles.
- Documentation as a first-class deliverable, not an afterthought.
- Releases on a predictable cadence with clear backwards-compatibility guarantees.

This is **not** a throwaway prototype. This is **not** an internal tool to be archived later. This is intended to become **the official upstream project** for community-built steel-tip darts scoring.

## Mission

Build a deterministic, accurate, low-latency darts scoring application that:

- Runs on a Raspberry Pi 5 with three USB cameras.
- Scores throws in under 500 ms with measured accuracy.
- Is free and open-source under GPL-3.0.
- Can be extended by the community via documented plugin surfaces.
- Remains maintainable by independent contributors who have never met.

## Non-Negotiable Principles

These principles do not change without a unanimous maintainer vote AND a superseding ADR in [DECISIONS.md](DECISIONS.md). They apply to every code change, doc change, and agent action.

1. **Modular architecture.** Modules have clear boundaries from [REPO_LAYOUT.md](REPO_LAYOUT.md). Modules can be replaced without rewriting the system.
2. **Stable contracts.** The WebSocket schema, config schema, calibration profile schema, and public Python API are versioned and follow the rules in [VERSIONING.md](VERSIONING.md).
3. **Detection engine isolated from UI.** UI code MUST NOT import detection internals. Detection code MUST NOT depend on UI being present.
4. **Deterministic runtime.** No runtime ML. No randomness without a documented seed. Same inputs → same outputs.
5. **Replayable testing is mandatory.** Detection regressions are caught by replay-dataset CI, not by hand testing.
6. **Debug tooling is a core feature.** Not an afterthought, not a developer-only convenience.
7. **Performance on Raspberry Pi 5 is a hard requirement.** All optimisations validated on Pi 5 hardware.
8. **Backwards compatibility is enforced.** Breaking changes go through the deprecation cycle in [VERSIONING.md](VERSIONING.md). No "we'll fix it in v2" hand-waves.
9. **Experimental systems do not destabilise core.** Experimental code lives behind feature flags or in `plugins/experimental/`. It MUST NOT be on the default code path.
10. **Documentation is part of the implementation.** A change without doc updates is incomplete.

## Project Structure Philosophy

### Core vs Plugin

The codebase has two layers:

- **Core**: capture, calibration, detection, fusion, scoring, API/WebSocket, replay, debug overlays, config. Owned by maintainers. High stability bar. Changes require ADR for anything that affects a contract or a public API.
- **Plugins / Extensions**: optional features that load on top of core via the documented plugin surface (see [PLUGIN_ARCHITECTURE.md](PLUGIN_ARCHITECTURE.md)). Lower stability bar. Community-contributed plugins are encouraged.

Core does not depend on any plugin. Plugins depend on a frozen subset of core's public API.

### Public vs Internal API

The codebase has two API tiers:

- **Public API** (`src/darts_detector/api_public/`): The surface plugins and external consumers are allowed to import. Changes follow the deprecation cycle. Marked `@public` in docstrings.
- **Internal API** (everything else): Free to change at any time. Plugins MUST NOT import from internal modules.

The public API is the smallest possible surface that still lets useful plugins exist. We start with almost nothing public and expand only when a real use case demands it.

### Documentation Tiers

- **Charter, Decisions, Versioning, Architecture, Plugin Architecture**: contributor-facing. Changes require maintainer approval.
- **Subsystem docs** (detection, calibration, scoring, etc.): implementation-facing. Updated by the agent or contributor making the change.
- **OPEN_QUESTIONS.md, RISKS.md**: working docs. Updated freely as questions are answered and risks surface.

## Governance

### Roles

- **Architecture Owner**: the person or small group who controls the architectural direction. Veto right on changes to charter, decisions, versioning policy, plugin architecture, public API, and the JSON schema.
- **Maintainer**: a contributor with merge rights. Approves PRs that don't touch architecture-level surfaces.
- **Contributor**: anyone who submits a PR or issue. Submissions are reviewed, not auto-merged.
- **AI Agent**: a subagent in `.claude/agents/`. Bound by [AGENT_RULES.md](AGENT_RULES.md). Agents do not have merge rights; they prepare changes for human review.

### Decision Rights

| Decision | Who Decides |
| --- | --- |
| Architecture direction, charter, public API, JSON schema | Architecture Owner |
| New plugin surfaces | Architecture Owner |
| Breaking changes (any major version bump) | Architecture Owner + RFC process |
| Subsystem implementation details | Maintainer who reviews the PR |
| Test additions | Maintainer who reviews the PR |
| Doc updates not touching contracts | Any maintainer |
| Risk register additions | Anyone |

### RFC Process (For Big Changes)

A change is "big" if it:

- Adds a new public API surface.
- Removes or breaks an existing public API.
- Adds a new top-level module.
- Bumps the major version of any contract.
- Changes a locked decision in [DECISIONS.md](DECISIONS.md).

Big changes follow the RFC process:

1. Open an issue with the `rfc` label describing the proposal, motivation, alternatives, and migration plan.
2. Discussion period: minimum 14 days.
3. Architecture Owner accepts, rejects, or asks for revisions.
4. On acceptance: an ADR is added to [DECISIONS.md](DECISIONS.md) and the implementation PR references it.

### Contribution Flow

1. Read [CONTRIBUTING.md](../CONTRIBUTING.md).
2. Open an issue describing the work (unless it's a tiny fix).
3. Fork, branch, implement, write tests, update docs.
4. Open a PR. CI runs unit tests, integration tests, replay regression tests, and schema validation.
5. Maintainer reviews. Architecture Owner reviews if architecture-level surfaces are touched.
6. Merge after approval.

## Stability Tiers

The codebase marks every module with a stability tier in its docstring header:

| Tier | Meaning | Change Policy |
| --- | --- | --- |
| `@public-stable` | Part of the public API. | Breaking changes follow the deprecation cycle in [VERSIONING.md](VERSIONING.md). |
| `@public-experimental` | Part of the public API but marked unstable. | May change between minor versions. Documented in release notes. |
| `@internal` | Core internal implementation. | May change at any time. Plugins MUST NOT import. |
| `@plugin` | Lives in `plugins/` directory. | Per-plugin stability policy; not bound by core's stability rules. |

If a module has no tier marker, treat it as `@internal`.

## Why OBS And Blender As Models

OBS Studio and Blender are the two most successful long-lived FOSS apps in their respective domains. Both share traits we explicitly want to copy:

- A small core team controls architecture; a large community contributes features via plugins/add-ons.
- Public APIs are documented and stable; internal APIs change freely.
- Releases are time-boxed with clear changelogs and migration notes.
- Backwards compatibility is enforced; deprecations have a long grace period.
- The project has survived many maintainer generations.

What we explicitly do **not** copy:

- Their UI frameworks (we are headless-first with optional browser UI).
- Their build systems (we are pure Python; they have C/C++ build matrices).
- Their licensing exemptions for plugins (we are GPL-3.0 throughout; plugins must be GPL-3.0-compatible).

## What Future Agents Must Do With This Charter

- Read it before any architecture-level change.
- Cite it when refusing a request that violates a non-negotiable principle.
- Update it only via the RFC process.
- Never paraphrase it into other docs; link to it.

This charter is the highest-authority document in the repo after the LICENSE.
