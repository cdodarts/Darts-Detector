# Risk Register

Risks that can derail accuracy, latency, or delivery. Each risk has an owner phase, a mitigation, and a detection signal so it doesn't surface as a surprise during integration.

## Risk Levels

- **High** — Can break the MVP accuracy or latency target.
- **Medium** — Can cause user-visible bugs or significantly slow delivery.
- **Low** — Annoyance or limitation, not a blocker.

## Risk Table

| ID | Risk | Level | Owner Phase | Mitigation | Detection Signal |
| --- | --- | --- | --- | --- | --- |
| R-01 | USB bandwidth saturation with 3 cameras at high res/FPS | High | 1, 2 | Pick a resolution/FPS profile that fits within a single USB 3 root hub. Document `pi5-balanced` profile. Reject configurations that exceed bandwidth at startup. | `droppedFrames > 0` on `CameraStatus`; FPS lower than configured. |
| R-02 | Auto-exposure or auto-white-balance drifts during play | High | 2 | Force manual exposure / WB in `pi5-*` profiles. Log effective settings. Fail validation if camera refuses manual mode. | Sudden change in baseline brightness; frame-diff false positives correlated with lighting shifts. |
| R-03 | Calibration drifts due to camera bump | High | 3, 3.5 | Periodic calibration self-test using fixed board landmarks; warn user when projection error exceeds threshold. | Scoring accuracy drops without code change; overlays no longer align. |
| R-04 | Dart occluded by previous dart or wire | High | 6, 7 | Two-camera fusion fallback. Reject when geometry inconsistent. Save debug frames for occlusion cases. | Fusion disagreement; one-camera-only candidates. |
| R-05 | Light flicker (AC mains 50/60Hz) causes false positives | High | 5 | Choose FPS to avoid beat frequencies; document required light ring spec; require manual exposure long enough to integrate flicker. | Periodic false positive rate; mask flickering between baselines. |
| R-06 | Motion settling threshold too aggressive — misses fast darts | High | 5 | Tune against replay dataset, not by eyeballing. Settling window must be measurable and configurable per profile. | False negatives in labelled dataset. |
| R-07 | Python hot path too slow for 500 ms budget on Pi 5 | Medium | 5, 6, 7, 12 | Measure per-stage timings from day one (see [LATENCY_BUDGET.md](LATENCY_BUDGET.md)). Vectorise with NumPy/OpenCV. Port hot inner loop to C only if profiled. | Stage exceeds 150% of budget on Pi 5. |
| R-08 | Calibration profile becomes stale when settings change | Medium | 3 | Calibration profile records resolution/rotation/crop and invalidates on mismatch. Fail closed. | Startup validation flags stale calibration. |
| R-09 | Baseline incorrectly updated while a dart is still in the board | Medium | 5 | Baseline only updates when scene is stable AND last throw is fully processed AND no hand motion detected. | Next throw scores wrong because previous dart was "absorbed" into baseline. |
| R-10 | Scoring engine border bugs at segment/ring boundaries | Medium | 4 | Lookup-table-based scoring with explicit tie-breaking rules and unit tests for every boundary. | Failing unit tests; mismatched border alternatives. |
| R-11 | WebSocket contract drift between producer and clients | Medium | 4, 8 | Lock the JSON schema before detection phases. Publish `dart-event.schema.json`. Clients tolerate unknown fields. | Client parse failures after producer update. |
| R-12 | Replay path drifts from live path | Medium | 4.5, 9 | Detection module accepts a frame source abstraction; replay and live use the same module. CI runs the labelled dataset on every detection change. | Replay results differ from live for the same throw. |
| R-13 | Labelled dataset too small or biased | Medium | 12 | Dataset composition documented; minimum size set before accuracy claim. Include border cases, occlusions, misses. | Accuracy varies wildly between dataset slices. |
| R-14 | Debug frame saving fills the SD card | Low | 9 | Cap total debug storage; rotate oldest first; default-off in `pi5-*` profiles. | Disk full; debug saving silently disabled. |
| R-15 | Three USB cameras unstable on the Pi 5 USB controller | Medium | 1 | Test with one powered USB hub if needed. Document required hardware setup. Fail validation early. | Random camera disconnects under load. |
| R-16 | Agents drift from documented contracts without updating docs | High (process) | All | [AGENT_RULES.md](AGENT_RULES.md) requires doc updates on every contract-affecting change. Doc Guardian agent reviews PRs. | Code references fields not in `dart-event.schema.json`. |
| R-17 | Baseline updated mid-turn, absorbing a dart into the empty reference | High | 5.5, 7.5 | Only the throw lifecycle state machine ([DETECTION_PIPELINE.md](DETECTION_PIPELINE.md) Phase 7.5) updates the current baseline. Other modules treat it as read-only. State-machine transitions logged. | Next throw scores wrong because a stuck dart is in the baseline. |
| R-18 | Hand detection misses partial occlusion (player removes one dart at a time) | High | 5.5, 7.5 | Hand threshold tuned against labelled dataset of "removing one dart" cases. `takeoutIncomplete` state holds the system until board-clear is verified. Re-entry of hand transitions back into `takeoutInProgress`. | Turn completes while darts still on board. |
| R-19 | False hand-detection from player walking past camera | Medium | 5.5 | Hand signal debounced over `HAND_DEBOUNCE` frames; hysteresis on threshold. Smoke test includes "walk past" scenario. | False `takeoutInProgress` transitions when no actual takeout is happening. |
| R-20 | Player wearing clothing similar to board colour confuses hand heuristic | Medium | 5.5 | Documented limitation. Per-installation calibration of hand threshold. Future: assist using motion gradient, still without ML. | Hand detection rate drops in field deployments with patterned clothing. |
| R-21 | Empty-board baseline never refreshed; ages with lighting drift | Medium | 5.5 | Empty-board baseline includes timestamp; UI prompts user to recapture when staleness threshold exceeded or after recalibration. | Board-clear detection false-negatives accumulate over weeks. |
| R-22 | Community contributor lands a PR that breaks the wire contract | High | All | CI runs schema validation against test corpus, replay regression tests, and `@public-stable`-imports-only check. PRs touching contract docs require maintainer + doc-guardian approval (see [PROJECT_CHARTER.md](PROJECT_CHARTER.md)). | CI fails; downstream plugin clients break in field. |
| R-23 | Plugin (post-MVP) destabilises detection hot path | Medium | Post-MVP plugin loader | Plugins receive events via async queue, not direct callback ([PLUGIN_ARCHITECTURE.md](PLUGIN_ARCHITECTURE.md)). Per-plugin time budget enforced; auto-disable on repeated breaches. | Detection latency degrades after plugin enabled. |
| R-24 | Contributor churn or maintainer attrition | Medium (long-term) | All | Documentation written for cold readers. Decisions and rationale captured in [DECISIONS.md](DECISIONS.md). RFC process leaves a paper trail. Stability tiers prevent accidental API surface growth. | Knowledge gaps when reviewing PRs; missed context in design discussions. |

## Adding Risks

Append a new row with the next `R-NN` ID. Every risk needs: a clear failure mode, the phase that owns the mitigation, and the signal that tells us it's happening. Risks without a detection signal are wishes, not risks.
