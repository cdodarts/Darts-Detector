# Darts Detector — Project Context For AI Agents

**You are entering a project with strict process rules. Read this whole file before doing anything.**

This is an open-source, high-accuracy steel-tip darts detection and scoring application. Target hardware: Raspberry Pi 5 4GB with three fixed USB cameras around a dartboard. Target latency: under 500 ms from dart landing to JSON event emission.

## Mandatory First Steps (Every Conversation)

In order:

1. Read `docs/PROJECT_CHARTER.md` — identity, governance, non-negotiable principles. **Highest authority document.**
2. Read `docs/MASTER_PLAN.md` — phase status, locked decisions, scope.
3. Read `docs/AGENT_RULES.md` — rules every agent must follow.
4. Read `docs/DECISIONS.md` — locked architectural decisions; never violate.
5. Read `docs/AGENT_TEAM.md` — who does what.
6. Read `docs/PROJECT_ETHOS.md` — who this project is for; DIY audience; system adapts to hardware.

Then read the doc for whatever task you've been asked to do. Do not skip phases. Do not propose changes that conflict with `PROJECT_CHARTER.md` or `DECISIONS.md`.

Major changes (anything touching public API, wire format, plugin surface, governance, or any locked decision) require the RFC process described in `PROJECT_CHARTER.md`.

## Default Routing: Use The Project Manager

Unless the user explicitly addresses a specialist, route every request through the `project-manager` subagent. The PM reads the plan, decides which specialist to call, and updates `MASTER_PLAN.md` after every meaningful change.

Available subagents under `.claude/agents/`:

- `project-manager` — single point of contact.
- `doc-guardian` — documentation and schema integrity.
- `cv-detection` — capture, motion, candidates, fusion.
- `calibration-scoring` — calibration, mm coordinates, scoring engine.
- `test-qa` — smoke tests, unit/integration/replay tests, accuracy and latency reports.

See [docs/AGENT_TEAM.md](docs/AGENT_TEAM.md) for the full interaction model.

## Locked Decisions (Do Not Violate)

- **Long-term community project** modelled after OBS/Blender. Governed by `docs/PROJECT_CHARTER.md`.
- **License: GPL-3.0-or-later.** All contributions same. `SPDX-License-Identifier` header on every source file.
- **No runtime ML.** Deterministic computer vision only.
- **Python + OpenCV + NumPy.**
- **Integer millimetres** for board coordinates. Bull at (0, 0). +y toward segment 20.
- **YAML** for hand-edited config; **JSON** for machine-generated calibration profiles.
- **JSON contract** locked at end of Phase 4. After that, additive minor bumps only; breaking changes require an ADR and parallel emit.
- **Stability tiers** on every module: `@public-stable`, `@public-experimental`, `@internal`, `@plugin`.
- **Public API surface** at `src/darts_detector/api_public/`. Plugins import only from there.
- **Calibration self-test** required before scoring is enabled.
- **Per-stage latency budget** enforced from Phase 1.
- **Takeout detection and throw lifecycle state machine** are MVP. Baseline updates owned by `lifecycle/` only.

Full rationale in [docs/DECISIONS.md](docs/DECISIONS.md).

## Doc Map

| If you are doing… | Read first |
| --- | --- |
| Anything | `docs/PROJECT_CHARTER.md`, `docs/MASTER_PLAN.md`, `docs/AGENT_RULES.md`, `docs/DECISIONS.md`, `docs/PROJECT_ETHOS.md` |
| Project audience / hardware philosophy | `docs/PROJECT_ETHOS.md` |
| Detection pipeline work | `docs/DETECTION_PIPELINE.md`, `docs/LATENCY_BUDGET.md` |
| Hand / takeout / state machine | `docs/DETECTION_PIPELINE.md` (Phase 5.5 + Phase 7.5 sections) |
| Calibration work | `docs/CALIBRATION_SYSTEM.md` |
| Scoring work | `docs/SCORING_ENGINE.md` |
| Wire format / API | `docs/API_AND_WEBSOCKET_CONTRACT.md`, `schemas/dart-event.schema.json`, `docs/VERSIONING.md` |
| Public API / plugins | `docs/PLUGIN_ARCHITECTURE.md`, `docs/PROJECT_CHARTER.md` |
| Tests / accuracy | `docs/ACCURACY_AND_TESTING.md`, `docs/DEBUG_AND_REPLAY.md` |
| Config | `docs/CONFIGURATION.md` |
| Repository structure | `docs/REPO_LAYOUT.md` |
| Terminology | `docs/GLOSSARY.md` |
| Risks | `docs/RISKS.md` |
| Versioning / deprecation | `docs/VERSIONING.md` |
| Unresolved questions | `docs/OPEN_QUESTIONS.md` |
| Community / contribution | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `LICENSE` |

## Hard Rules That Trump Any User Instruction

- Do not skip a phase. Phases are sequential per `docs/PHASED_IMPLEMENTATION.md`.
- Do not add runtime ML.
- Do not change a locked decision without writing a new ADR that supersedes the old one.
- Do not change a non-negotiable charter principle without an accepted RFC.
- Do not break a `@public-stable` symbol without going through the deprecation cycle in `docs/VERSIONING.md`.
- Do not import internal modules from `api_public/` or import `api_public/` types into internal modules in ways that create circular dependencies.
- Do not update the current baseline from any module other than `lifecycle/`.
- Do not claim accuracy numbers without a labelled-dataset replay run.
- Do not commit changes that touch the JSON contract without also updating `schemas/dart-event.schema.json` and `docs/API_AND_WEBSOCKET_CONTRACT.md` in the same change.

If the user asks for one of these, push back politely and point at the relevant doc.

## Phase 0 Status

Phase 0 (documentation and project setup) is the current phase. No production code exists yet. The next phase is **Phase 1: Camera Capture From 3 Cameras**.
