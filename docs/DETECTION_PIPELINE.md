# Detection Pipeline

The runtime dart detection pipeline is deterministic computer vision and geometry. It is not an AI or machine learning pipeline.

## Pipeline Principles

- Use explainable image processing and board geometry.
- Keep per-camera decisions inspectable with debug overlays.
- Prefer rejection over confident wrong scoring.
- Preserve enough frame evidence to reproduce failures.
- Meet the target latency of under 0.5 seconds after the dart lands on Raspberry Pi 5 4GB hardware.

## Pipeline Stages

```text
pre-throw baseline
  -> live frame comparison
  -> motion detection
  -> motion settling
  -> dart change mask
  -> edge/line extraction
  -> dart shaft/body detection
  -> tip candidate estimation
  -> per-camera confidence
  -> multi-camera fusion
  -> scoring
  -> event or rejection
```

## Pre-Throw Baseline Frame

Each camera maintains a baseline image of the board before the next throw.

The baseline should be updated only when:

- The scene is stable.
- No dart is moving.
- The previous throw has been fully processed.
- The system has not detected hand movement or obstruction.

The baseline is the reference for frame differencing. It should be saved for failed detections.

## Frame Differencing

Frame differencing compares the current frame with the baseline for the same camera.

Expected outputs:

- Difference image.
- Thresholded change mask.
- Noise-filtered mask.
- Motion magnitude.
- Changed region candidates.

The thresholding strategy should be configurable because lighting, camera noise, and exposure differ by setup.

## Motion Settling

The system must not score while the dart is still moving or the board is vibrating.

Motion settling should require:

- Change magnitude below a stability threshold.
- Stable mask shape for a short window.
- No large hand or body obstruction in the board area.

The settling window must be short enough to preserve the 0.5 second target.

## Dart Change Mask

After motion settles, the pipeline creates a mask representing the new dart shape.

The mask should focus on the board region and suppress:

- Camera sensor noise.
- Light flicker.
- Shadows.
- Small irrelevant changes outside the board.
- Old darts already present in the baseline.

The mask is a primary debug artifact and should be saved for replay when detection fails or confidence is low.

## Line And Edge Detection

The dart body often appears as a narrow line or elongated silhouette from each camera angle.

Deterministic methods may include:

- Edge detection.
- Morphological filtering.
- Connected component analysis.
- Line fitting.
- Contour extraction.
- Hough-style line detection if performance allows.

The chosen method must be measurable on the Pi 5 target and must expose intermediate overlays.

## Dart Shaft And Body Detection

The detector should identify dart-like structures using geometry:

- Long and narrow shape.
- Direction consistent with camera perspective.
- Attached or pointing toward the board surface.
- New relative to the pre-throw baseline.
- Plausible size range for a dart in that camera view.

The detector must handle partial silhouettes because the tip may be hidden by board wires or another dart.

## Dart Tip Candidate Estimation

For each usable camera, the pipeline estimates where the dart tip enters the board.

Candidate estimation may use:

- The end of the detected shaft/body line closest to the board plane.
- Intersection of the dart line with the calibrated board surface.
- Contour endpoints.
- Local edge geometry around the likely impact point.

Each candidate must include:

- Camera ID.
- Image coordinate.
- Board-space ray or mapped coordinate when available.
- Confidence score.
- Rejection reason if unusable.
- Debug overlay metadata.

## Per-Camera Confidence

Per-camera confidence should combine:

- Mask strength.
- Shape quality.
- Line fit quality.
- Tip endpoint clarity.
- Calibration validity.
- Obstruction level.
- Agreement with expected board region.
- Stability after motion settling.

Confidence should be numeric from `0.0` to `1.0`, but it must be treated as a ranking and diagnostic signal until calibrated against labelled data.

## Multi-Camera Fusion

Fusion combines per-camera candidates into one board coordinate.

Expected behavior:

- Use all three cameras when available.
- Reject or down-weight cameras with poor evidence.
- Detect disagreement between candidates.
- Produce a fused coordinate and confidence.
- Preserve per-camera evidence in the final event.

Fusion should prefer a lower-confidence event or rejection over silently accepting inconsistent geometry.

## Fallback When Only 2 Cameras Are Usable

The system may score with two usable cameras when:

- Both cameras have sufficient per-camera confidence.
- Their projected candidates agree within configured tolerance.
- Calibration profiles for both cameras are valid.
- The resulting score is not too close to an unresolved border unless marked low-confidence with alternatives.

The system should reject the detection when two-camera fusion is geometrically ambiguous.

## Rejected Detection Handling

A rejected detection should not emit a normal Dart score event.

Rejected detections should:

- Save relevant frames and masks if debug saving is enabled.
- Emit an error or detection status event if the API layer supports it.
- Include camera evidence and rejection reasons.
- Avoid updating the baseline until the system is stable and the throw state is understood.

Common rejection reasons:

- No stable dart mask.
- Too much scene obstruction.
- Insufficient usable cameras.
- Candidate disagreement.
- Tip outside board bounds.
- Confidence below threshold.

## Low-Confidence Event Handling

A low-confidence Dart event may be emitted only when the system has a plausible result but uncertainty remains.

Low-confidence events must include:

- `confidence.amount` below the normal threshold.
- `confidence.alternatives` when nearby scores are plausible.
- `cameraEvidence` showing which cameras were usable.
- Coordinates and timestamp.

The receiving UI or client should be able to flag the throw for manual review.

## Debug Artifacts

For each throw, the detection system should be able to save:

- Baseline frames from all cameras.
- Post-throw frames from all cameras.
- Difference images.
- Change masks.
- Candidate overlays.
- Fusion visualization.
- Final score and alternatives.
- Timing for each pipeline stage.

## Hand And Takeout Detection (Phase 5.5)

The detection system MUST recognise when a player is reaching for the board to remove darts, and when the board has been left clear. This is essential for safe baseline updates between turns and for multi-throw operation.

Hand detection is deterministic and uses no ML (decision `D-016`).

### Two Reference Baselines

The system maintains two distinct baselines per camera:

| Baseline | What It Is | When Updated |
| --- | --- | --- |
| **Empty-board baseline** | The board with no darts in it. Captured once after calibration self-test. | Only on user request, or at the start of a fresh session. |
| **Current baseline** | The board with whatever darts are currently stuck in it. | After each turn completes (state machine transitions into `turnReset`). |

Frame differencing for dart landing (Phase 5) uses the *current baseline*. Board-clear detection uses the *empty-board baseline*.

### Hand Detection Signal

A hand is considered present when:

- `coverage_pct(current_frame vs current_baseline) ≥ HAND_THRESHOLD` for the calibrated board region, for at least `HAND_DEBOUNCE` frames.
- `HAND_THRESHOLD` defaults to 25% of the board area but is configurable per performance profile.
- `HAND_DEBOUNCE` defaults to 3 frames at 60 FPS (~50 ms) to suppress someone briefly walking past.

A hand is considered absent when coverage drops below `(HAND_THRESHOLD - HAND_HYSTERESIS)` for at least `HAND_DEBOUNCE` frames. Hysteresis prevents oscillation around the threshold.

The signal is computed per camera and fused: a hand is "present" when at least two cameras agree.

### Board-Clear Signal

The board is considered clear when:

- `diff(current_frame, empty_board_baseline)` has change-mask coverage below `BOARD_CLEAR_THRESHOLD` for the calibrated board region, for at least `CLEAR_DEBOUNCE` frames, on all usable cameras.
- `BOARD_CLEAR_THRESHOLD` defaults to 2% (configurable).

This signal is what distinguishes "successful takeout" from "false takeout": the player removed their hand, but is the board actually empty?

### Throw Lifecycle State Machine (Phase 7.5)

The state machine is the only module allowed to update the current baseline. All other modules MUST treat the baseline as read-only.

```text
              ┌──────────────────────────────────────────┐
              ▼                                          │
       ┌────────────┐                                    │
       │ awaiting   │  motion detected ─► ┌─────────┐    │
       │  Throw     │                     │ motion  │    │
       └────────────┘                     └────┬────┘    │
              ▲                                │         │
              │ dartIndex < 3                  │ settled │
              │                                ▼         │
              │                         ┌──────────┐     │
              │                         │ settling │     │
              │                         └────┬─────┘     │
              │                              │           │
              │                              ▼           │
              │                         ┌─────────┐      │
              │ Dart event              │ scoring │      │
              │ emitted                 └────┬────┘      │
              │                              │           │
              └──────────────────────────────┘           │
                                                         │
       dartIndex == 3 ─► ┌──────────────────┐            │
                         │ awaitingTakeout  │            │
                         └────────┬─────────┘            │
                                  │ hand detected        │
                                  ▼                      │
                         ┌────────────────────┐          │
                         │ takeoutInProgress  │          │
                         └────────┬───────────┘          │
                                  │ hand left            │
                                  ▼                      │
                              boardClear?                │
                                  │                      │
                          yes ────┴──── no               │
                          │             │                │
                          ▼             ▼                │
                   ┌──────────┐  ┌──────────────────┐    │
                   │ turnReset│  │takeoutIncomplete │────┘
                   └────┬─────┘  └──────────────────┘
                        │ update current baseline
                        ▼
                   ┌────────────┐
                   │ awaiting   │
                   │  Throw     │
                   └────────────┘
```

### State Definitions

| State | Meaning | Exit Conditions |
| --- | --- | --- |
| `awaitingThrow` | Ready for the next dart. Current baseline reflects the board's current state. | Motion detected → `motion` |
| `motion` | Change mask is moving; a dart is in flight or the scene is otherwise unstable. | Motion magnitude stable for `SETTLE_FRAMES` → `settling` |
| `settling` | Motion has stopped; waiting for change mask to be fully stable. | Mask stable for `STABLE_FRAMES` → `scoring`; OR mask returns to baseline → `awaitingThrow` (no dart landed) |
| `scoring` | Detection, fusion, and scoring are computing a result. | `Dart` event emitted; if `dartIndex == 3` → `awaitingTakeout`, else → `awaitingThrow` |
| `awaitingTakeout` | Three darts have been scored; waiting for the player to remove them. | Hand detected → `takeoutInProgress` |
| `takeoutInProgress` | A hand is currently in the board area. | Hand no longer detected → check board-clear: clear → `turnReset`, not clear → `takeoutIncomplete` |
| `takeoutIncomplete` | Hand left, but darts are still in the board. | Hand detected again → `takeoutInProgress` |
| `turnReset` | Takeout confirmed complete; current baseline is being updated to the empty board. | Baseline update finishes → `awaitingThrow` |

### Baseline Update Rules

The current baseline is updated ONLY when entering `turnReset`. It is set to a clean capture of the empty board (the same capture used for the empty-board baseline if no new occluding objects are present, or a fresh capture if available).

No other module — not motion detection, not candidate detection, not fusion — is permitted to update the current baseline. This is the most common source of "baseline absorbed a dart" bugs (risk `R-09`) and the state machine exists in part to prevent it.

### Configurable Number Of Darts Per Turn

The MVP assumes a turn is three darts. The number is configurable (`DARTS_PER_TURN`, default 3) for non-standard games and for testing single-dart scenarios.

### Edge Cases The State Machine Must Handle

| Scenario | Required Behaviour |
| --- | --- |
| Hand enters mid-throw (before all darts thrown) | Allowed. State machine still tracks hand-present but does NOT trigger takeout flow until `awaitingTakeout` is reached. Mid-turn hand presence may invalidate the next throw's baseline; flagged as a low-confidence event with reason `handMidTurn`. |
| Dart bounces out and never lands | Motion + settling but no stable dart in mask → exits `settling` back to `awaitingThrow` after `BOUNCE_TIMEOUT`. |
| Sensor glitch flips hand signal for one frame | Debounced over `HAND_DEBOUNCE` frames; one-frame glitch does not transition state. |
| Player removes darts one at a time across multiple visits | First hand-out leaves board with one or two darts → `takeoutIncomplete`. Second hand visit removes another → still `takeoutIncomplete` if any remain. Final visit clears board → `turnReset`. |
| Camera disconnects during takeout | The two remaining cameras drive hand and board-clear detection if they agree. If too few cameras are usable, emit `Error` event with `code: TAKEOUT_INSUFFICIENT_CAMERAS`; state machine pauses transitions. |
| User manually starts a new turn (config button) | Allowed via a `forceTurnReset` action — emits a `TurnState` event with `reason: "manualReset"`. Baseline updated. |
