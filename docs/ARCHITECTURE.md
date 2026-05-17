# Architecture

This document describes the planned system architecture. It is intentionally implementation-neutral until production code begins.

Architecture decisions are constrained by [PROJECT_CHARTER.md](PROJECT_CHARTER.md), [DECISIONS.md](DECISIONS.md), [VERSIONING.md](VERSIONING.md), and [PLUGIN_ARCHITECTURE.md](PLUGIN_ARCHITECTURE.md). Anything in this doc that conflicts with those is wrong and must be fixed.

## Architecture Goals

- Deterministic runtime dart detection.
- Explainable scoring decisions.
- Low latency on Raspberry Pi 5 4GB.
- Modular components with clear contracts.
- Replayable detection for testing and debugging.
- Stable JSON output for downstream clients.

## High-Level Data Flow

```text
USB cameras
  -> camera capture
  -> camera configuration
  -> calibrated camera views
  -> baseline and frame differencing       ┐
  -> motion + hand + board-clear signals   ┼─► throw lifecycle state machine
  -> dart silhouette and tip candidates    │      │
  -> per-camera confidence                 │      │  TurnState events
  -> multi-camera fusion                   │      ▼
  -> board coordinate                      │   WebSocket
  -> scoring engine                        ┘      ▲
  -> Dart event ─────────────────────────────────┘
  -> debug/replay persistence
```

The state machine in `lifecycle/` is the orchestrator. It owns baseline updates and turn rotation. See [DETECTION_PIPELINE.md](DETECTION_PIPELINE.md) for the state diagram and transition rules.

## Camera Capture Layer

Responsibilities:

- Open and manage three USB camera streams.
- Capture synchronized or near-synchronized frames.
- Track camera health, frame rate, dropped frames, and timestamps.
- Provide frames to detection without unnecessary copies.
- Recover from temporary camera disconnects where possible.

Initial assumptions:

- Three cameras are fixed during play.
- Cameras view the dartboard from roughly 120-degree separation.
- Lighting is stable and controlled.

## Camera Configuration Layer

Responsibilities:

- Store per-camera settings.
- Apply resolution, FPS, exposure, gain, brightness, contrast, white balance, rotation, and crop.
- Support performance profiles for development and Raspberry Pi runtime.
- Report the effective settings actually applied by the camera driver.

The configuration layer must avoid hidden defaults. If a setting cannot be applied, the runtime should expose that fact through camera status and logs.

## Calibration Layer

Responsibilities:

- Guide manual marking of board reference points in each camera view.
- Convert camera image coordinates into normalized board coordinates.
- Save and load calibration profiles.
- Validate calibration quality before detection starts.
- Support future semi-automatic and automatic calibration workflows without breaking the manual MVP.

Calibration output should be versioned and tied to camera IDs, image resolution, rotation, and crop settings.

## Board Geometry And Scoring Engine

Responsibilities:

- Represent board coordinates with the bull at `(0, 0)`.
- Convert `(x, y)` board coordinates into dartboard section, number, multiplier, and score.
- Use the official clockwise segment order:

```text
20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5
```

- Handle bull, outer bull, singles, triples, doubles, and misses.
- Produce confidence alternatives near segment and ring borders.
- Be unit tested independently from camera and detection code.

## Dart Detection Pipeline

Responsibilities:

- Maintain pre-throw baseline frames for each camera.
- Detect meaningful post-throw differences.
- Wait for motion settling before scoring.
- Create dart change masks.
- Extract dart-like edges, lines, silhouettes, and tip candidates.
- Assign per-camera confidence.
- Reject unstable or ambiguous detections.

This is a deterministic computer vision pipeline. It must not depend on AI or machine learning for runtime dart detection.

## Multi-Camera Fusion

Responsibilities:

- Combine two or three per-camera tip candidates into one board coordinate.
- Use calibration transforms and camera geometry to reject inconsistent candidates.
- Produce final confidence and alternatives.
- Continue operating when one camera is unusable if two usable cameras provide sufficient agreement.

Fusion must expose enough evidence for debugging, including per-camera usability and confidence.

## Confidence Engine

Responsibilities:

- Represent uncertainty without hiding failure cases.
- Combine detection confidence, calibration confidence, geometry agreement, and scoring-border proximity.
- Generate alternatives for nearby plausible scores.
- Mark low-confidence events clearly.

Confidence is not an accuracy guarantee. Accuracy must be measured against labelled data.

## WebSocket/API Output

Responsibilities:

- Emit versioned JSON events.
- Provide Dart, calibration status, camera status, and error events.
- Preserve stable field names after MVP contracts are implemented.
- Include timestamps and enough evidence for clients to understand the result.

The WebSocket output is the primary integration surface for future UI and external consumers.

## Debug UI

Responsibilities:

- Show live camera views.
- Show calibration marks and projected board geometry.
- Show detection masks, candidate lines, estimated tips, and final fused coordinate.
- Display confidence components and alternatives.
- Provide operator controls for calibration and replay.

The debug UI is a development and setup tool. It should not expand into match management during MVP.

## Replay And Testing System

Responsibilities:

- Save pre-throw, during-throw, and post-throw frames from all cameras.
- Replay saved throws without live cameras.
- Compare detected results against manually labelled truth.
- Produce accuracy, false positive, false negative, and latency metrics.
- Preserve enough metadata to reproduce bugs.

Replay support is a core architecture requirement because reliable scoring cannot be developed from live testing alone.

## Config Persistence

Responsibilities:

- Persist camera settings, performance profiles, calibration profiles, WebSocket settings, and debug settings.
- Validate config on startup.
- Make config human-readable unless a later decision chooses a database.
- Version config formats for future migration.

Configuration must be easy to inspect and edit during early development.

## Planned Runtime Boundaries

| Boundary | Owns | Does Not Own |
| --- | --- | --- |
| Capture | Raw frames and camera status | Scoring or calibration logic |
| Calibration | Camera-to-board mapping | Live capture device management |
| Detection (motion) | Per-camera change masks and motion state | Tip estimation |
| Detection (takeout) | Hand-present and board-clear signals | State machine transitions |
| Detection (candidates) | Tip candidates from frames | Final score contracts |
| Fusion | Final coordinate from candidates | Segment scoring rules |
| Scoring | Coordinate to score | Image processing |
| Lifecycle | Throw lifecycle state machine, baseline updates, turn rotation | Image processing |
| API | Event serialization for `Dart`, `TurnState`, `CalibrationStatus`, `CameraStatus`, `Error` | Detection internals |
| Debug/replay | Observability and reproducibility | Production scoring decisions |

The lifecycle layer is the only module allowed to update the current baseline. All other modules treat it as read-only. See risk `R-17` in [RISKS.md](RISKS.md).

## Stability Tiers And Public API Surface

Every module declares a stability tier in its docstring header (see [DECISIONS.md](DECISIONS.md) `D-014`):

- `@public-stable` — part of the public API, deprecation-cycle protected.
- `@public-experimental` — public but unstable.
- `@internal` — free to change.
- `@plugin` — lives in `plugins/`.

The public API lives under `src/darts_detector/api_public/` and exports only:

- Event Pydantic models (or TypedDicts) for `Dart`, `TurnState`, `CalibrationStatus`, `CameraStatus`, `Error`.
- Re-exports of JSON Schema paths.
- Enums: `Section`, `Outcome`, `TurnStateName`, `TurnStateReason`, `CalibrationStatus` values.
- Standard board geometry constants.

Plugins import only from `darts_detector.api_public`. Anything outside this directory is internal and may change without notice between minor versions.

CI enforces this with an import-linter check.

## Plugin Surface

See [PLUGIN_ARCHITECTURE.md](PLUGIN_ARCHITECTURE.md). MVP supports the WebSocket-based plugin model only; the in-process plugin loader is post-MVP. The architectural boundary that supports it (`api_public/`) is created in Phase 1 and respected from day one.
