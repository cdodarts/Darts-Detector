# Agent Rules

These rules apply to future AI coding agents working on this repository.

The charter ([PROJECT_CHARTER.md](PROJECT_CHARTER.md)) and the locked decisions ([DECISIONS.md](DECISIONS.md)) override these rules where they conflict. The versioning policy ([VERSIONING.md](VERSIONING.md)) governs every change to a contract.

## Mandatory First Steps

- Always read [MASTER_PLAN.md](MASTER_PLAN.md) first.
- Read the phase-specific documentation before editing.
- Confirm the current phase.
- Check for existing user changes before editing files.
- Record assumptions clearly.

## Scope Rules

- Work only on the current phase unless explicitly instructed otherwise.
- Do not introduce runtime AI or ML detection into the MVP.
- Do not add unrelated product features.
- Do not build match management, cloud sync, accounts, or mobile app features during MVP.
- Do not create large rewrites without documenting why.

## Documentation Rules

- Update [MASTER_PLAN.md](MASTER_PLAN.md) after every meaningful change.
- Update relevant docs when architecture, contracts, config, calibration, detection, or testing behavior changes.
- Keep docs practical for future implementation.
- Do not let implementation drift away from documented contracts.

## Testing Rules

- Do not skip smoke tests.
- Add or update tests when behavior changes.
- Use replay tests for detection changes once replay tooling exists.
- Do not claim accuracy without labelled dataset evidence.
- Record known test gaps when work is incomplete.

## Runtime Detection Rules

- Runtime dart detection must be deterministic.
- Use computer vision, geometry, calibration, and measurable heuristics.
- Keep intermediate outputs inspectable.
- Prefer clear rejection over high-confidence wrong scoring.
- Preserve debug artifacts for failures where configured.

## Performance Rules

- Keep the Raspberry Pi 5 4GB target in mind.
- Avoid unnecessary frame copies.
- Avoid heavyweight dependencies unless justified.
- Measure latency for detection pipeline changes.
- Keep the 0.5 second post-landing target visible in design choices.

## Design Rules

- Prefer modular design.
- Keep capture, calibration, detection, fusion, scoring, API, and debug concerns separate.
- Keep contracts stable once implemented.
- Make config explicit and versioned.
- Keep code open-source friendly with clear dependency choices.

## Change Management Rules

- Do not overwrite user changes.
- Do not make broad formatting-only changes without reason.
- Document assumptions and decisions near the relevant docs or implementation notes.
- When blocked by missing hardware or unanswered product decisions, update [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) or clearly report the blocker.

## Phase Completion Rules

A phase is complete only when:

- Its acceptance criteria are met.
- Its smoke test passes.
- Relevant docs are updated.
- Known risks and gaps are recorded.
- The next phase remains aligned with [MASTER_PLAN.md](MASTER_PLAN.md).

## Backwards Compatibility Rules

- Before changing any contract (wire format, config schema, calibration profile, public API), calculate the version bump per [VERSIONING.md](VERSIONING.md).
- Additive changes within a major version are allowed in any phase (with doc + schema updates).
- Breaking changes require: an accepted RFC, an ADR, a migration tool where applicable, and a parallel-emit / deprecation period.
- Never remove a `@public-stable` symbol without going through the deprecation cycle.
- Never bypass the deprecation cycle by claiming "no one uses this yet" — by the time anyone notices, someone will.

## Public API And Plugin Awareness

- The public API lives under `src/darts_detector/api_public/`. Treat every export there as load-bearing.
- Never import from `api_public/` *into* internal modules — the dependency direction is the other way.
- Never add to `api_public/` without a documented use case and an RFC if the addition is non-trivial.
- The WebSocket schema IS the MVP plugin contract. Changes go through the same RFC + ADR process.

## Governance Rules

- Architecture-level changes (charter, decisions, plugin architecture, public API, JSON schema) require the RFC process described in [PROJECT_CHARTER.md](PROJECT_CHARTER.md).
- Agents do not have merge rights. Agents prepare changes for human review.
- The Doc Guardian agent reviews any change touching a contract doc or schema.
- The Project Manager agent updates `MASTER_PLAN.md` after every meaningful change.

## Drift Prevention

- Cite docs, do not paraphrase them. Paraphrasing creates a second source of truth that drifts.
- Update the docs when the code disagrees with them. Do not "leave it for later".
- When in doubt, the doc wins until an RFC says otherwise.
