# Latency Budget

The runtime target is **under 500 ms from dart landing to WebSocket event emission** on Raspberry Pi 5 4GB.

End-to-end measurement alone is not enough. Every stage owns a budget, every stage records its actual time, and every `Dart` event carries a `latency.stageMs` block so regressions are visible without log diving.

## Per-Stage Budget (Pi 5 4GB Target)

| Stage | Budget (ms) | Notes |
| --- | --- | --- |
| Frame capture (per camera, parallel) | 50 | USB transfer + decode. Three cameras run in parallel, so this is wall-clock, not summed. |
| Motion detection + settling wait | 200 | The settling wait dominates this stage. Pure frame-diff compute should be < 30 ms. |
| Frame differencing & mask | 60 | Background subtraction, noise filtering, morphology. Three cameras in parallel. |
| Per-camera candidate detection | 80 | Edge/line extraction, contour analysis, tip estimation. Three cameras in parallel. |
| Multi-camera fusion | 30 | Triangulation, agreement check, board-coord conversion. |
| Scoring | 5 | Lookup-table-backed; should be sub-millisecond once the table exists. |
| WebSocket emit | 10 | JSON serialisation + send. |
| **Sum** | **435** | Leaves ~65 ms of headroom for OS jitter, GC, USB hiccups. |

The settling-wait budget is the largest single slice and the most dependent on physical setup (board vibration, light flicker). Tune it down only with replay-dataset evidence.

## Instrumentation Rules

- Every pipeline stage MUST record start and end times.
- The `Dart` event MUST include `latency.landToEventMs` and `latency.stageMs` (see [API_AND_WEBSOCKET_CONTRACT.md](API_AND_WEBSOCKET_CONTRACT.md)).
- Replay runs MUST report the same stage timings so dev-machine vs Pi 5 comparison is meaningful.
- A stage exceeding 150% of its budget on a normal throw MUST emit a warning log entry; exceeding 200% MUST be treated as a regression and block merge.

## Budget Revision Rules

The budget is allowed to change only when:

1. A documented measurement on Pi 5 shows the current allocation is wrong, **and**
2. The total still sums to under 500 ms with at least 50 ms headroom, **and**
3. The change is recorded in [DECISIONS.md](DECISIONS.md).

Do not rebalance the budget to make a slow stage "fit". Optimise the slow stage first.

## What Does NOT Count Against The Budget

- User-initiated calibration (one-off, not on the dart hot path).
- Baseline re-establishment at end of turn (happens after the `Dart` event has shipped; covered by the separate takeout budget below).
- Debug frame saving (must run asynchronously or be disabled in low-latency profiles).
- Replay-mode runs (no real-time constraint).

## Between-Turn Budget (Hand And Takeout)

The dart-landing budget above is for the time-critical scoring path. The takeout cycle has a separate, more relaxed budget because the player needs seconds to physically remove the darts.

| Signal | Target Detection Latency | Notes |
| --- | --- | --- |
| Hand-present transition (false → true) | < 200 ms | Driven by `HAND_DEBOUNCE` frames; default 3 frames at 60 FPS ≈ 50 ms + processing. |
| Hand-present transition (true → false) | < 200 ms | Same debounce. |
| Board-clear transition (false → true) | < 300 ms | Slightly higher debounce; avoids declaring "clear" while motion is still settling. |
| State machine transition emit | < 50 ms | From signal change to `TurnState` event on the wire. |
| Baseline update on `turnReset` | < 500 ms | Allowed to be slower; happens entirely between turns. Player will not throw again immediately. |

These targets are aspirational floors, not hard SLOs. The hard SLO remains the 500 ms dart-landing budget.

## Instrumentation For Lifecycle Stages

The `TurnState` event SHOULD include in its `extensions` an `x-stageMs` block with the per-signal timing during development; this is removed from production for noise reduction.

## Common Pitfalls

- Computing radius/angle per dart instead of using a precomputed lookup table.
- Saving debug frames synchronously inside the hot path.
- Allocating large NumPy arrays per frame instead of reusing scratch buffers.
- Letting auto-exposure run, which makes frame differencing thresholds chase a moving target.
- Using a Python `for` loop where a vectorised NumPy op or OpenCV call exists.
- Logging at DEBUG level inside the hot path in production profiles.
