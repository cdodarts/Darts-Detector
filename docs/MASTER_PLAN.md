# Master Plan

This document is the single source of truth for the darts detector project. Future planning, implementation, testing, and documentation updates must stay aligned with this file.

This project is a **long-lived open-source community project** modelled after OBS Studio and Blender. The [Project Charter](PROJECT_CHARTER.md) is the highest-authority document in this repo and overrides anything in this file that conflicts with it.

## Project Vision

Build an open-source, high-accuracy, automatic steel-tip darts detection and scoring application for a DIY camera setup.

The target hardware is a Raspberry Pi 5 4GB with three fixed USB cameras mounted around a dartboard at roughly 120-degree angles and stable illumination from a light ring.

The runtime detection system must be deterministic, fast, explainable, and based on computer vision and geometry. Runtime dart detection must not use AI or machine learning. AI tools may be used only to help write, review, test, and document the software.

## Core Runtime Objective

After a dart lands, the system should:

1. Detect that a new dart is present.
2. Identify the dart tip landing position.
3. Map the tip to calibrated board coordinates.
4. Calculate the score.
5. Emit a structured JSON event over WebSocket.

Target latency: under 0.5 seconds after the dart lands, measured on the target Raspberry Pi 5 4GB hardware.

## Current MVP Target

The MVP is a deterministic three-camera scorer with:

- Three USB camera capture.
- Manual camera and board calibration.
- Board geometry and scoring.
- Frame differencing based dart detection.
- Dart tip candidate estimation.
- Multi-camera fusion.
- JSON dart events over WebSocket.
- Debug overlays and replay tooling sufficient to diagnose errors.

## In Scope

- Steel-tip dartboard scoring.
- Fixed camera setup with roughly known mounting geometry.
- Stable controlled lighting.
- Manual MVP calibration.
- Configurable camera settings.
- Deterministic computer vision pipeline.
- Per-camera confidence and multi-camera confidence fusion.
- JSON event contracts.
- Saved frames and replay datasets for testing.
- Accuracy and latency measurement.
- Open-source friendly design and dependencies.

## Out Of Scope For MVP

- AI or ML based runtime dart detection.
- Cloud processing.
- Mobile app development.
- Online match platform features.
- Player accounts, profiles, or league management.
- Voice control.
- Automatic camera discovery beyond basic device enumeration.
- Fully automatic calibration.
- Advanced dart removal detection beyond what is needed for reliable throw sequencing.
- Claims of 99%+ accuracy before measured labelled dataset results exist.

## Locked Decisions

These decisions are locked. Full rationale lives in [DECISIONS.md](DECISIONS.md). They must not be changed without superseding the relevant ADR.

- **Language:** Python 3.11+ with OpenCV and NumPy (`D-003`).
- **Coordinate unit:** integer millimetres, bull `(0, 0)`, `+y` toward segment 20 (`D-004`).
- **Config format:** YAML for hand-edited config, JSON for machine-generated calibration profiles (`D-005`).
- **Detection:** deterministic CV only, no runtime ML (`D-001`).
- **JSON contract:** locked at end of Phase 4 (`D-006`).
- **Replay tooling:** lands before detection phases (`D-007`).
- **Calibration self-test:** required before scoring is enabled (`D-008`).
- **Latency budget:** per-stage, enforced from Phase 1 (`D-009`, [LATENCY_BUDGET.md](LATENCY_BUDGET.md)).
- **Semi-/fully-automatic calibration:** post-MVP (`D-010`).

## Development Phases

| Phase | Name | Status | Required Smoke Test |
| --- | --- | --- | --- |
| 0 | Documentation and project setup only | **Complete** (2026-05-17) | Required docs exist, agree on MVP boundaries, and no production app code has been created. |
| 1 | Camera capture from 3 cameras | **In progress** (2026-05-17) | Three configured cameras stream frames concurrently at the selected resolution and FPS. Per-stage timing instrumentation in place. |
| 2 | Camera settings and performance profiles | Not started | Exposure, gain, brightness, contrast, white balance, resolution, and FPS can be applied and verified. Manual exposure/WB confirmed effective. |
| 3 | Manual board calibration | Not started | User can mark required board points for all cameras and save/load a calibration profile. |
| 3.5 | Calibration self-test | Not started | After calibration, projected board rings align with the real board in all three views; scoring is gated on user confirmation. |
| 4 | Board geometry and scoring engine | Not started | Known board coordinates produce correct segment, multiplier, and score outputs using the mm coordinate system. JSON contract locked. |
| 4.5 | Frame recorder and minimal replay runner | Not started | A throw can be recorded to disk and re-run through the (future) detection pipeline without live cameras. |
| 5 | Frame differencing and motion detection | Not started | A thrown dart causes a stable post-throw change mask without firing on normal noise. Validated on replay dataset. |
| 5.5 | Hand and takeout detection | Not started | Hand-in-board area is detected via percentage-coverage heuristic; "board clear of darts" state is detected against the empty-board baseline. |
| 6 | Dart silhouette and tip candidate detection | Not started | Each usable camera produces a tip candidate and confidence from saved test frames. |
| 7 | Multi-camera fusion | Not started | Two or three camera candidates fuse into one board coordinate with confidence. |
| 7.5 | Throw lifecycle state machine | Not started | Coordinates motion, fusion, dart count, hand detection, and takeout into a deterministic state machine that drives baseline updates and emits `TurnState` events. |
| 8 | WebSocket dart event output | Not started | A detected dart emits a valid versioned JSON Dart event that validates against `schemas/dart-event.schema.json`. `TurnState` events emit on every state transition. |
| 9 | Debug UI and replay tooling (full) | Not started | Saved throws can be replayed and visual overlays inspected without live cameras. |
| 10 | Semi-automatic calibration (post-MVP) | Not started | Calibration assists the user while still allowing manual correction. |
| 11 | Fully automated calibration research (post-MVP) | Not started | Prototype research is documented and measured separately from MVP reliability. |
| 12 | Accuracy testing and optimisation | Not started | Labelled replay dataset reports accuracy, false positives, false negatives, and latency percentiles on Pi 5 hardware. |

### Parallelisable Work

To shorten the critical path without compromising quality:

- **Phases 2 and 3 may run in parallel** once Phase 1 is complete. Camera settings and manual calibration share no runtime code path.
- **Phase 11 (research)** may run as a separate research track from the start. It does not block MVP.
- **Phase 4.5** is sized as a half-phase and may be built alongside Phase 4 if capacity allows.

## Current Phase Status

Current phase: **Phase 1 — Camera Capture From 3 Cameras** (started 2026-05-17).

### Phase 0 — Complete (2026-05-17)

All required documentation files exist, scope is constrained, agent rules are in place, no production code existed at close.

### Phase 1 — In Progress (2026-05-17)

**Dev environment constraints:**
- Windows 11 dev machine; Raspberry Pi 5 is the eventual target but is NOT in scope for Phase 1.
- Camera capture uses `cv2.CAP_DSHOW` (DirectShow) as the default Windows backend.
- Three OV2710-based UVC cameras sold as "Autodarts DIY Cam" hardware.
- Other webcams are attached and must be excluded. Selection is by friendly name + USB device instance path.

**Camera selection approach:**
- `list_devices.py` CLI enumerates all UVC devices via DirectShow and prints: index, friendly name, device instance path, and a frame thumbnail.
- User runs it once, identifies which port-path maps to left/center/right, and fills in `config/cameras.yaml`.
- Startup filters by `friendlyName: "Autodarts DIY Cam"` first, then matches `devicePath` to assign roles `cam_left`, `cam_center`, `cam_right`.
- If all three cameras share the same friendly name (likely), the device path is the stable per-port disambiguator.

**Package toolchain:** `uv` (Python 3.11+).

**Phase 1 smoke test:**
Opens all 3 cameras using the config, captures for 30 seconds, asserts measured FPS >= configured FPS - 5%, asserts per-stage latency (capture → frame-available) is logged for every frame and within budget per `LATENCY_BUDGET.md`.

## How Future Agents Must Update This Document

After every meaningful change, future agents must update this file when the change affects:

- Current phase status.
- MVP scope.
- Architecture direction.
- Runtime contracts.
- Acceptance criteria.
- Smoke test results.
- Known risks or unresolved questions.

Updates must be short, factual, and dated when recording a decision or phase transition.

## Smoke Test Rules

Every phase must have a smoke test that can be run quickly by a future agent or developer. A phase is not complete until its smoke test passes and the result is recorded in this document or in an implementation note linked from this document.

Smoke tests should verify the smallest useful end-to-end behavior for that phase. They are not a replacement for unit, integration, or replay dataset testing.

## Scope Drift Prevention Rules

- Build only the current phase unless explicitly instructed otherwise.
- Do not add player management, match modes, cloud features, or unrelated UI.
- Do not introduce runtime AI or ML detection into the MVP.
- Do not skip calibration quality checks.
- Do not claim accuracy that has not been measured.
- Do not replace deterministic geometry with opaque heuristics unless documented and measured.
- Keep modules small and testable.
- Keep target hardware limits visible in design decisions.
- Keep WebSocket contracts stable once implemented.

## Key Documentation Links

Highest authority:
- [Project Charter](PROJECT_CHARTER.md) — identity, governance, non-negotiable principles.
- [Decisions](DECISIONS.md) — locked architectural decisions; read before suggesting changes.
- [Versioning](VERSIONING.md) — semver policy for every contract; deprecation cycle.

Foundational:
- [Agent Rules](AGENT_RULES.md) — mandatory rules for AI agents.
- [Agent Team](AGENT_TEAM.md) — who does what in the AI team.
- [Glossary](GLOSSARY.md) — shared vocabulary.
- [Repo Layout](REPO_LAYOUT.md) — directory structure and module boundaries.
- [Plugin Architecture](PLUGIN_ARCHITECTURE.md) — extension surface and public API boundary.
- [Risks](RISKS.md) — risk register with mitigations.

Community:
- [CONTRIBUTING](../CONTRIBUTING.md) — contributor guide and RFC process.
- [CODE_OF_CONDUCT](../CODE_OF_CONDUCT.md) — Contributor Covenant 2.1.
- [LICENSE](../LICENSE) — GPL-3.0-or-later.

Plan and contracts:
- [Phased Implementation](PHASED_IMPLEMENTATION.md)
- [Architecture](ARCHITECTURE.md)
- [API and WebSocket Contract](API_AND_WEBSOCKET_CONTRACT.md) + [schemas/dart-event.schema.json](../schemas/dart-event.schema.json)
- [Latency Budget](LATENCY_BUDGET.md)

Subsystems:
- [Detection Pipeline](DETECTION_PIPELINE.md)
- [Calibration System](CALIBRATION_SYSTEM.md)
- [Scoring Engine](SCORING_ENGINE.md)
- [Configuration](CONFIGURATION.md)
- [Debug and Replay](DEBUG_AND_REPLAY.md)
- [Accuracy and Testing](ACCURACY_AND_TESTING.md)

Open items:
- [Open Questions](OPEN_QUESTIONS.md)
