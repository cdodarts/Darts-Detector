# Phased Implementation

This roadmap is designed so each phase can be implemented and smoke tested independently. Future agents must not skip phases unless the project owner explicitly changes the plan in [MASTER_PLAN.md](MASTER_PLAN.md).

Locked decisions ([DECISIONS.md](DECISIONS.md)) apply to every phase:
- Python + OpenCV + NumPy.
- Integer millimetres for board coordinates.
- YAML for hand-edited config, JSON for calibration profiles.
- Per-stage latency instrumentation from Phase 1.

## Parallelisation Map

| Group | Phases | Notes |
| --- | --- | --- |
| Sequential foundation | 0 → 1 | Cannot start coding until docs and decisions are locked. |
| Parallel pair | 2 ∥ 3 | Camera settings and manual calibration may run side-by-side after Phase 1. |
| Sequential calibration gate | 3 → 3.5 | Self-test must follow calibration. |
| Parallel pair | 4 ∥ 4.5 | Scoring engine and frame recorder are independent. |
| Sequential detection chain | 5 → 5.5 → 6 → 7 | Tightly coupled — run with shared replay dataset for fast iteration. |
| Sequential lifecycle | 7 → 7.5 → 8 | State machine sits between fusion and API; emits `TurnState` events. |
| Parallel | 9 ∥ 12 | Debug UI and accuracy measurement can run together after Phase 8. |
| Independent research track | 11 | May start any time; does not gate MVP. |
| Post-MVP | 10, 11 | Not in MVP critical path.

## Phase 0: Documentation And Project Setup Only

| Item | Detail |
| --- | --- |
| Objective | Establish the documentation framework and project rules before production code exists. |
| Inputs | Project requirements and MVP constraints. |
| Outputs | `/docs` documentation set. |
| Acceptance Criteria | Required docs exist, are internally consistent, and make the no-runtime-ML rule explicit. |
| Smoke Test | Verify all required markdown files exist and no production app code has been created. |
| Common Failure Cases | Documentation contradicts itself; scope expands into non-MVP features; future phases are vague. |
| Files/modules likely involved | `/docs/*.md` only. |
| Must Not Be Built Yet | Camera code, detection code, scoring code, WebSocket server, UI, package scaffolding. |

## Phase 1: Camera Capture From 3 Cameras

| Item | Detail |
| --- | --- |
| Objective | Capture frames from three USB cameras concurrently, with a browser-based picker for first-time camera assignment. |
| Inputs | Camera IDs (set via picker or manual edit), selected resolution, selected FPS. |
| Outputs | Timestamped frames and camera status for each camera; `config/cameras.yaml` written by the picker. |
| Acceptance Criteria | Three configured cameras stream concurrently without blocking each other. Camera picker opens in the browser, shows live previews, and writes `cameras.yaml` on save. |
| Smoke Test | Start capture, show or log frames from `cam_1`, `cam_2`, and `cam_3` for at least 30 seconds with measured FPS. |
| Common Failure Cases | Wrong camera ordering, dropped frames, blocking reads, unsupported resolution, unstable USB bandwidth, picker preview leaking camera handles. |
| Files/modules likely involved | `src/darts_detector/capture/*`, `src/darts_detector/config/*`, `src/darts_detector/diagnostics/*`, `src/darts_detector/ui/camera_picker/*`, `src/darts_detector/cli/camera_picker.py`. |
| Must Not Be Built Yet | Dart detection, scoring, WebSocket dart events, calibration UI beyond camera preview. |

**Browser-based camera picker (primary setup flow — D-017, D-018):**
Run `uv run python -m darts_detector.cli.camera_picker`. This starts a local FastAPI server on port 8765 and opens the user's default browser. The picker shows three role dropdowns (Camera 1 / Camera 2 / Camera 3) populated with all enumerated cameras, with a live MJPEG preview (5 fps) under each dropdown. The user selects the correct camera for each slot, clicks Save, and `config/cameras.yaml` is written automatically. The server then exits.

**Windows DirectShow note (dev environment):**
The development environment is Windows 11 with cameras attached via DirectShow. The default capture backend is `cv2.CAP_DSHOW`. On Linux (Pi 5 target), `cv2.CAP_ANY` is used and device paths become `/dev/videoN`.

**Camera selection by friendly name and USB device path:**
All three Autodarts DIY Cam devices share the same DirectShow friendly name (`"Autodarts DIY Cam"`). The stable per-camera disambiguator on Windows is the USB device instance path (e.g. `USB\VID_0C45&PID_6366\<port-path>`), which is stable as long as each camera stays in the same physical USB port.

**`list_devices` headless fallback:**
For environments without a browser (headless Pi 5, SSH session), run `uv run python -m darts_detector.capture.list_devices` to enumerate all DirectShow devices and print a table. Copy the device paths manually into `config/cameras.yaml`.

**Startup camera matching:**
At startup, the capture module filters detected cameras by `friendlyName` first, then matches `devicePath` to assign roles `cam_1`, `cam_2`, `cam_3`.

## Phase 2: Camera Settings And Performance Profiles

| Item | Detail |
| --- | --- |
| Objective | Apply and verify camera settings and runtime performance profiles. |
| Inputs | Camera config, profile name, hardware capabilities. |
| Outputs | Effective camera settings and profile status. |
| Acceptance Criteria | Resolution, FPS, exposure, gain, brightness, contrast, white balance, rotation, and crop can be configured where supported. |
| Smoke Test | Apply a low-latency profile and verify effective settings for all three cameras. |
| Common Failure Cases | Driver ignores settings, auto exposure remains enabled, profile exceeds USB bandwidth, crop or rotation breaks calibration assumptions. |
| Files/modules likely involved | `src/config/*`, `src/capture/*`, `config/*`. |
| Must Not Be Built Yet | Automatic calibration, advanced debug UI, scoring logic. |

## Phase 3: Manual Board Calibration

| Item | Detail |
| --- | --- |
| Objective | Allow a user to mark board reference points for all three camera views and save a calibration profile. |
| Inputs | Live or captured frames, user-marked board points. |
| Outputs | Versioned calibration profile (JSON) with camera-to-board transforms. |
| Acceptance Criteria | Calibration can be saved, loaded, validated, and associated with camera settings. Output coordinates are in integer millimetres. |
| Smoke Test | Mark required points for all cameras, save profile, reload it, and project board overlays back onto the views. |
| Common Failure Cases | Ambiguous points, wrong segment orientation, resolution mismatch, camera moved after calibration. |
| Files/modules likely involved | `src/darts_detector/calibration/manual/`, `config/calibration/`, `schemas/calibration-profile.schema.json`. |
| Must Not Be Built Yet | Semi-automatic calibration, fully automatic calibration, dart detection. |

## Phase 3.5: Calibration Self-Test

| Item | Detail |
| --- | --- |
| Objective | Catch calibration errors before they reach scoring by projecting the known board ring geometry back onto each camera view. |
| Inputs | Saved calibration profile, live camera frames. |
| Outputs | Pass/fail self-test result; `calibrationConfirmed` flag in runtime state; user-visible overlay. |
| Acceptance Criteria | Scoring is blocked until the self-test passes AND the user confirms alignment. Mean projection error per ring is recorded with the profile. |
| Smoke Test | Run self-test on a valid calibration → overlay aligns within tolerance, user confirms, scoring becomes enabled. Run on a deliberately bumped camera → self-test fails closed. |
| Common Failure Cases | User confirms misaligned overlay; tolerance too lax; self-test runs on stale frame; flag not reset on recalibration. |
| Files/modules likely involved | `src/darts_detector/calibration/validate/`, `src/darts_detector/calibration/manual/`. |
| Must Not Be Built Yet | Scoring engine integration (Phase 4 picks up the confirmed flag). |

## Phase 4: Board Geometry And Scoring Engine

| Item | Detail |
| --- | --- |
| Objective | Convert board coordinates (integer mm) into correct dart scores using a precomputed lookup table. |
| Inputs | Integer millimetre `(x, y)` board coordinates. |
| Outputs | Section, number, multiplier, score, and border alternatives. |
| Acceptance Criteria | Unit tests cover bull, outer bull, singles, triples, doubles, misses, segment boundaries, ring boundaries, board rotation, and tie-breaking. JSON contract `dart-event.schema.json` is locked at end of this phase. |
| Smoke Test | Run a fixed coordinate test set and verify expected score outputs. Lookup-table generation runs in under 1 second. |
| Common Failure Cases | Incorrect segment order, angle offset error, off-by-one segment boundaries, incorrect bull radii, float-equality bugs. |
| Files/modules likely involved | `src/darts_detector/scoring/`, `tests/unit/scoring/`, `schemas/dart-event.schema.json`. |
| Must Not Be Built Yet | Image processing detection, multi-camera fusion, live WebSocket dart events. |

## Phase 4.5: Frame Recorder And Minimal Replay Runner

| Item | Detail |
| --- | --- |
| Objective | Make detection development possible without live throws by recording frames and replaying them through the same detection code path. |
| Inputs | Live frames from Phase 1 capture; optional manual label per throw. |
| Outputs | On-disk throw records (frames + metadata); CLI replay runner that loads a throw and pushes its frames through the detection pipeline. |
| Acceptance Criteria | A recorded throw replays through the (initially empty or stubbed) detection pipeline using the same module entry point that live capture uses — no parallel code paths. |
| Smoke Test | Record one throw with three camera frames + metadata.json. Replay it. Confirm the frame source abstraction delivers identical frames to detection. |
| Common Failure Cases | Replay path diverges from live path; metadata missing fields needed by detection; timestamps not preserved; storage layout makes labelling hard. |
| Files/modules likely involved | `src/darts_detector/debug/replay/`, `src/darts_detector/capture/`, `datasets/throws/`. |
| Must Not Be Built Yet | Full debug UI (Phase 9), automatic accuracy reports (Phase 12). |

## Phase 5: Frame Differencing And Motion Detection

| Item | Detail |
| --- | --- |
| Objective | Detect when a throw has changed the board view and wait until motion settles. |
| Inputs | Baseline frame, live frames, camera config. |
| Outputs | Motion state and stable dart change mask. |
| Acceptance Criteria | A dart landing produces a stable mask after motion settles, while normal camera noise does not produce a throw. |
| Smoke Test | Replay or perform a throw and confirm the detector transitions through baseline, motion, settling, and stable states. |
| Common Failure Cases | Light flicker, camera auto exposure, shadows, hand movement, board vibration, missed small dart changes. |
| Files/modules likely involved | `src/detection/motion/*`, `src/replay/*`, `tests/detection/*`. |
| Must Not Be Built Yet | Tip scoring, WebSocket scoring events, automated calibration. |

## Phase 5.5: Hand And Takeout Detection

| Item | Detail |
| --- | --- |
| Objective | Detect when a player's hand is in the board area (occluding it) and detect when the board is clear of darts. Both signals feed the throw lifecycle state machine (Phase 7.5). |
| Inputs | Live frames, calibrated board region per camera, empty-board reference baseline. |
| Outputs | Per-camera and fused signals: `handPresent: bool`, `boardClear: bool`, each with a confidence. |
| Acceptance Criteria | Hand detection: triggers when configured % of the calibrated board area is occluded relative to the current scene; debounced over N frames to suppress brief occlusions (e.g. player walking past). Board-clear detection: change mask vs empty-board baseline is below a configurable threshold across all cameras. |
| Smoke Test | Replay or live: a hand entering the board area triggers `handPresent=true` within 200 ms; hand leaving triggers `handPresent=false` within 200 ms; an empty board against the empty baseline produces `boardClear=true`; a board with one or more darts produces `boardClear=false`. |
| Common Failure Cases | Player wearing patterned clothing that matches the board; partial hand entry (single finger) not crossing threshold; light flicker causing false board-clear; reflection on shaft confused with dart silhouette. |
| Files/modules likely involved | `src/darts_detector/detection/takeout/`, `src/darts_detector/detection/motion/`, `tests/unit/detection/`, `tests/replay/`. |
| Must Not Be Built Yet | The state machine itself (Phase 7.5). Skin/hand ML models. Per-finger pose estimation. |

## Phase 6: Dart Silhouette And Tip Candidate Detection

| Item | Detail |
| --- | --- |
| Objective | Extract dart-like shapes and estimate tip candidates per camera. |
| Inputs | Stable dart change masks, post-throw frames, calibration data. |
| Outputs | Per-camera tip candidate, confidence, and rejection reason if unusable. |
| Acceptance Criteria | Each usable camera can produce a candidate from representative saved frames. |
| Smoke Test | Run saved throws through the candidate detector and inspect overlays for mask, shaft/body line, and estimated tip. |
| Common Failure Cases | Dart hidden by wire, dart overlaps previous dart, reflection, weak silhouette, wrong end of shaft selected as tip. |
| Files/modules likely involved | `src/detection/candidates/*`, `src/debug/overlays/*`, `tests/detection/*`. |
| Must Not Be Built Yet | Final multi-camera scoring event, automatic correction from labelled datasets, ML classifiers. |

## Phase 7: Multi-Camera Fusion

| Item | Detail |
| --- | --- |
| Objective | Fuse per-camera candidates into a single board coordinate. |
| Inputs | Per-camera candidates, calibration transforms, camera confidence. |
| Outputs | Final coordinate, fused confidence, alternatives, and camera evidence. |
| Acceptance Criteria | Fusion works with three usable cameras and degrades to two usable cameras when agreement is sufficient. |
| Smoke Test | Replay a saved throw with one camera disabled and verify two-camera fusion still produces a plausible coordinate or a clear rejection. |
| Common Failure Cases | Calibration disagreement, occlusion, inconsistent camera timestamps, one camera dominating bad fusion. |
| Files/modules likely involved | `src/fusion/*`, `src/calibration/*`, `tests/fusion/*`. |
| Must Not Be Built Yet | Public API changes beyond internal result structures, match-level features. |

## Phase 7.5: Throw Lifecycle State Machine

| Item | Detail |
| --- | --- |
| Objective | Coordinate the full throw → score → takeout → next-turn cycle using a deterministic state machine. Owns baseline updates so that no other module updates the baseline outside the state machine. |
| Inputs | Motion signals (Phase 5), hand-present and board-clear signals (Phase 5.5), fused dart coordinate (Phase 7), score result (Phase 4). |
| Outputs | `TurnState` events on every transition; baseline update commands; throw-index and turn-index assignment to outgoing `Dart` events. |
| Acceptance Criteria | The state machine implements the documented states (see [DETECTION_PIPELINE.md](DETECTION_PIPELINE.md)): `awaitingThrow`, `motion`, `settling`, `scoring`, `awaitingTakeout`, `takeoutInProgress`, `takeoutIncomplete`, `turnReset`. False takeouts (hand leaves but darts remain) MUST hold the system in `awaitingTakeout` until the board is verified clear. Baseline is updated only on transition into `turnReset`. State machine survives a one-frame signal glitch via configurable debounce. |
| Smoke Test | Replay a full turn: throw 1 → throw 2 → throw 3 → hand in → hand out + board clear. Confirm correct state transitions and that the baseline is only updated once at end of turn. Replay a false takeout: throw 1 → throw 2 → hand in → hand out + dart still showing → state stays `awaitingTakeout`. |
| Common Failure Cases | Baseline updated mid-turn (absorbs a dart); state machine resets on a brief sensor glitch; turn never completes because hand detection threshold misses partial occlusion; partial takeout misclassified as full takeout. |
| Files/modules likely involved | `src/darts_detector/lifecycle/`, `src/darts_detector/events/`, `tests/unit/lifecycle/`, `tests/replay/`. |
| Must Not Be Built Yet | Match-mode rules (501, Cricket); player turn rotation; UI for the state machine. Those belong in plugins. |

## Phase 8: WebSocket Dart Event Output

| Item | Detail |
| --- | --- |
| Objective | Emit structured JSON events for detected darts and runtime status. |
| Inputs | Fused coordinate, score result, confidence, camera evidence, per-stage latency timings. |
| Outputs | Versioned WebSocket events validated against `schemas/dart-event.schema.json`. |
| Acceptance Criteria | Events conform to [API_AND_WEBSOCKET_CONTRACT.md](API_AND_WEBSOCKET_CONTRACT.md). Every event passes JSON Schema validation. `latency.stageMs` populated for every Dart event. |
| Smoke Test | Connect a WebSocket client, trigger a replayed detection, validate event against schema, confirm `landToEventMs < 500` on the replay. |
| Common Failure Cases | Unstable field names, invalid timestamps, missing confidence details, blocking detection while sending, schema drift. |
| Files/modules likely involved | `src/darts_detector/api/`, `src/darts_detector/events/`, `tests/integration/api/`. |
| Must Not Be Built Yet | Authentication, cloud sync, lobby/match services. |

## Phase 9: Debug UI And Replay Tooling

| Item | Detail |
| --- | --- |
| Objective | Make detections reproducible and inspectable via the same FastAPI+browser stack introduced in Phase 1 (camera picker). |
| Inputs | Saved frames, detection metadata, labelled truth where available. |
| Outputs | Replay runner, debug overlays, browser-based inspection UI, statistics reports. |
| Acceptance Criteria | A saved throw can be replayed without cameras and compared to expected truth. Debug UI served by FastAPI at a browser-accessible URL per `D-017`. |
| Smoke Test | Load a saved throw, replay detection, view overlays in the browser, and export the result summary. |
| Common Failure Cases | Missing metadata, replay path differs from live path, overlays do not match actual processed frames. |
| Files/modules likely involved | `src/darts_detector/debug/replay/*`, `src/darts_detector/debug/overlays/*`, `src/darts_detector/ui/debug/*`, `tests/replay/*`. |
| Must Not Be Built Yet | Non-debug match UI, online data sharing, automated accuracy claims. |
| UI Note | Must meet the UX quality checklist in `D-018`. Visible state, plain-language errors, LAN accessible. |

## Phase 10: Semi-Automatic Calibration

| Item | Detail |
| --- | --- |
| Objective | Assist calibration while preserving manual correction. |
| Inputs | Camera frames, existing manual calibration workflow. |
| Outputs | Suggested calibration marks and validation warnings. |
| Acceptance Criteria | The system can propose useful points but the user can override them. |
| Smoke Test | Run assisted calibration on a representative board image and confirm the overlay is close enough for manual refinement. |
| Common Failure Cases | False ring detection, poor lighting, unusual board design, user trusts bad suggestions. |
| Files/modules likely involved | `src/calibration/assist/*`, `src/ui/calibration/*`. |
| Must Not Be Built Yet | Fully automatic mandatory calibration, ML-based board recognition. |

## Phase 11: Fully Automated Calibration Research

| Item | Detail |
| --- | --- |
| Objective | Research whether calibration can become fully automatic without reducing reliability. |
| Inputs | Saved board images, calibration profiles, failure examples. |
| Outputs | Research notes, prototypes, measured reliability. |
| Acceptance Criteria | Research is isolated from MVP runtime and does not replace manual calibration until proven. |
| Smoke Test | Run prototype on a small labelled calibration dataset and report success/failure cases. |
| Common Failure Cases | Works only on one board style, brittle lighting assumptions, hidden dependency on manual setup. |
| Files/modules likely involved | `research/calibration/*`, `docs/research/*`, maybe later `src/calibration/auto/*`. |
| Must Not Be Built Yet | Required automatic calibration in production runtime. |

## Phase 12: Accuracy Testing And Optimisation

| Item | Detail |
| --- | --- |
| Objective | Measure and improve scoring reliability and speed against labelled data. |
| Inputs | Labelled throw dataset, replay tooling, performance metrics. |
| Outputs | Accuracy reports, latency reports, optimisation decisions. |
| Acceptance Criteria | Reports include score accuracy, false positives, false negatives, confidence calibration, and latency percentiles. |
| Smoke Test | Run the labelled replay dataset and generate a metrics summary. |
| Common Failure Cases | Dataset too small, biased test throws, missing border cases, unmeasured hardware latency. |
| Files/modules likely involved | `tests/replay/*`, `datasets/*`, `tools/metrics/*`, `docs/accuracy/*`. |
| Must Not Be Built Yet | Public accuracy claims not supported by measured data. |
