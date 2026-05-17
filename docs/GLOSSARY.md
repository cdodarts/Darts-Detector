# Glossary

Shared vocabulary. Agents and contributors MUST use these terms consistently across code, comments, docs, and the WebSocket contract.

## Board Geometry

| Term | Meaning |
| --- | --- |
| **Bull** | The innermost red circle. Worth 50. Section name `BULL`. |
| **Outer bull** | The green ring around the bull. Worth 25. Section name `OUTER_BULL`. |
| **Inner single** | The area between the outer bull and the triple ring. Multiplier 1. |
| **Triple ring** | The thin scoring ring at ~107 mm from centre. Multiplier 3. |
| **Outer single** | The area between the triple ring and the double ring. Multiplier 1. |
| **Double ring** | The thin scoring ring at the board's outer scoring edge. Multiplier 2. |
| **Miss** | Anywhere outside the double ring outer edge. Section name `MISS`, score 0. |
| **Segment** | One of the 20 numbered wedges. The segment numbers in clockwise order from the `20`: `20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5`. |
| **Wire** | The metal divider between segments and between rings. Causes occlusion and deflections. |

## Coordinates

| Term | Meaning |
| --- | --- |
| **Board coordinates** | Integer millimetres in 2D. Bull at `(0, 0)`. Positive `y` toward the centre of the `20` segment. Right-handed convention. |
| **Image coordinates** | Pixel coordinates within a camera frame. Origin top-left. Different per camera. |
| **Normalized coordinates** | Coordinates divided by a reference radius. Reserved for future use; not in v1 contract. |

## Pipeline Stages

| Term | Meaning |
| --- | --- |
| **Current baseline** | A reference frame captured when the board is stable and contains all currently-stuck darts. Used for frame differencing (dart landing). |
| **Empty-board baseline** | A reference frame of the board with no darts. Used for board-clear detection. |
| **Frame differencing** | Pixel-level comparison of the current frame against a baseline. |
| **Change mask** | A binary image marking pixels that changed between baseline and current frame. |
| **Motion settling** | The wait period after change is detected, before the system attempts to score. Ends when the change mask is stable. |
| **Candidate** | A per-camera estimate of a dart tip's image position, with confidence and rejection reason. |
| **Fusion** | The step that combines per-camera candidates into one board coordinate. |
| **Tip** | The point where the dart enters the board. The scoring point. |
| **Shaft** | The body of the dart. Used to estimate the tip direction. |

## Takeout And Lifecycle

| Term | Meaning |
| --- | --- |
| **Takeout** | The act of the player removing darts from the board between turns. |
| **Hand present** | Boolean signal: at least the configured percentage of the board area is occluded relative to the current scene, debounced over N frames. |
| **Board clear** | Boolean signal: the current frame differs from the empty-board baseline by less than the configured threshold. |
| **Successful takeout** | A hand-in / hand-out cycle that ends with `boardClear=true`. The state machine transitions into `turnReset` and the current baseline is updated. |
| **False takeout** (also "incomplete takeout") | A hand-in / hand-out cycle that ends with darts still on the board. State machine moves to `takeoutIncomplete` and waits for another hand visit. |
| **Throw lifecycle state machine** | The deterministic state machine in `lifecycle/` that owns transitions between `awaitingThrow`, `motion`, `settling`, `scoring`, `awaitingTakeout`, `takeoutInProgress`, `takeoutIncomplete`, and `turnReset`. The sole module allowed to update the current baseline. |
| **Turn** | A sequence of `dartsThisTurn` darts (default 3) followed by a takeout. |

## Event Types

| Term | Meaning |
| --- | --- |
| **Dart event** | The primary event. One per detected dart. Carries score, coordinates, confidence, latency. |
| **TurnState event** | Emitted on every transition of the throw lifecycle state machine. Drives takeout UI and turn rotation. |
| **CalibrationStatus event** | Reports calibration state changes. |
| **CameraStatus event** | Reports per-camera health and effective settings. |
| **Error event** | Reports recoverable and unrecoverable runtime errors. |
| **Outcome** | `scored`, `missed`, or `rejected`. A `Dart` event always has one. |

## Confidence

| Term | Meaning |
| --- | --- |
| **Per-camera confidence** | A 0.0–1.0 ranking signal from a single camera's candidate. Not a calibrated probability. |
| **Fused confidence** | A 0.0–1.0 signal combining all usable cameras, calibration validity, and border proximity. |
| **Alternative** | A plausible alternate score for the same dart, used near segment/ring borders. |
| **Border case** | A throw whose true position is close enough to a segment or ring boundary that more than one score is plausible. |

## Status / Outcome Vocabulary

| Term | Used By | Meaning |
| --- | --- | --- |
| `valid` | CalibrationStatus | Loaded and self-test passed. |
| `invalid` | CalibrationStatus | Validation failed; scoring is blocked. |
| `stale` | CalibrationStatus | Loaded but resolution/rotation/crop has changed since saved. |
| `missing` | CalibrationStatus | No profile loaded. |
| `inProgress` | CalibrationStatus | User is currently calibrating. |
| `streaming` | CameraStatus | Camera is producing frames at target FPS. |
| `degraded` | CameraStatus | Camera is producing frames but below target (FPS or dropped frames). |
| `disconnected` | CameraStatus | Camera no longer enumerated. |
| `scored` | Dart event | A dart was detected and scored. |
| `missed` | Dart event | A dart was detected but landed outside the scoring area. |
| `rejected` | Dart event | A potential dart was detected but not safe to score (low confidence, fusion disagreement, etc.). |

## Things That Are NOT Synonyms

These get mixed up and shouldn't be:

- **Detection** ≠ **Scoring.** Detection finds *where* the dart is. Scoring converts that location into a number.
- **Candidate** ≠ **Dart.** A candidate is per-camera; a dart is fused.
- **Confidence** ≠ **Accuracy.** Confidence is the system's self-assessment; accuracy is measured against labelled truth.
- **Miss** ≠ **Rejected.** A miss is a real dart that landed outside scoring. A rejected detection is one the system refused to score.
- **Baseline** ≠ **Calibration.** Baseline is a frame snapshot for differencing; calibration is the camera-to-board mapping.
