# Accuracy And Testing

Testing must prove both correctness and practical reliability. Accuracy claims are not valid until measured against a real labelled dataset.

## Testing Principles

- Test deterministic components with unit tests.
- Test camera and API behavior with integration tests.
- Test detection quality with replay datasets.
- Measure latency on target hardware.
- Track false positives and false negatives explicitly.
- Treat border cases as first-class test cases.

## Smoke Tests

Each implementation phase must include a smoke test. Smoke tests verify that the phase works at a basic end-to-end level.

Examples:

- Three cameras stream concurrently.
- Calibration profile saves and reloads.
- Known coordinates score correctly.
- A saved throw replays to a Dart event.

Smoke tests are required before moving to the next phase.

## Unit Tests

Unit tests should cover:

- Board geometry.
- Segment angle mapping.
- Ring classification.
- Score calculation.
- Confidence alternatives near borders.
- Config validation.
- Event schema serialization.
- Pure detection helper functions where deterministic inputs exist.

Unit tests should run without cameras.

## Integration Tests

Integration tests should cover:

- Camera capture startup and shutdown.
- Applying camera settings.
- Loading calibration profiles.
- Detection pipeline stages connected together.
- WebSocket event emission.
- Replay path matching live path as closely as possible.

Hardware-dependent tests should be clearly marked.

## Replay Dataset Testing

Replay dataset testing is required for detection changes.

Dataset entries should include:

- Saved frames from all three cameras.
- Calibration metadata.
- Camera settings.
- Expected label.
- Notes for unusual conditions.

Replay tests should report both scoring result and confidence behavior.

## Labelled Throw Dataset

A labelled dataset should include:

- Normal clear throws.
- Throws near segment wires.
- Throws near triple and double ring borders.
- Bull and outer bull throws.
- Misses.
- Darts blocking each other.
- Different board sectors.
- Different lighting conditions within the supported setup.
- Cases where one camera is obstructed or unusable.

Dataset size and composition must be reported with any accuracy metric.

## Border Case Testing

Border cases should measure:

- Segment boundary ambiguity.
- Ring boundary ambiguity.
- Bull boundary ambiguity.
- Double edge vs miss.
- Triple edge vs single.
- Darts close to existing darts.

Expected behavior may be a low-confidence result with alternatives rather than a high-confidence primary score.

## Lighting Consistency Tests

Lighting tests should cover:

- Light ring on stable setting.
- Minor ambient light changes.
- Camera auto exposure disabled.
- Flicker or reflection cases.

If lighting changes cause false positives, the detection thresholds or setup requirements must be documented.

## Camera Obstruction Tests

Obstruction tests should cover:

- One camera blocked.
- Hand entering frame after throw.
- Dart hidden from one angle.
- Temporary camera disconnect.

The expected behavior is either valid two-camera fallback or clear rejection.

## Scoring Accuracy Metrics

Reports should include:

- Exact score accuracy.
- Segment accuracy.
- Multiplier accuracy.
- Bull accuracy.
- Miss accuracy.
- Accuracy by board region.
- Accuracy by confidence bucket.
- Border-case accuracy.

Accuracy must be calculated against labelled truth, not visual impressions.

## Detection Speed Metrics

Reports should include:

- Time from dart landing to stable detection.
- Frame capture latency.
- Motion settling duration.
- Detection processing time.
- Fusion and scoring time.
- WebSocket emission time.
- End-to-end latency percentiles.

The primary target is under 0.5 seconds after dart lands on Raspberry Pi 5 4GB hardware.

## False Positive Tracking

A false positive occurs when the system emits a dart event when no new valid dart landed.

Track:

- Count.
- Scenario.
- Camera evidence.
- Whether lighting, hand movement, or baseline update caused it.

## False Negative Tracking

A false negative occurs when a valid dart landed but no Dart event was emitted.

Track:

- Count.
- Scenario.
- Whether the system rejected the throw.
- Which pipeline stage failed.
- Whether low camera confidence or fusion disagreement caused it.

## Accuracy Claim Rule

Do not claim 99%+ accuracy until:

- A real labelled dataset exists.
- The dataset size and conditions are documented.
- Metrics are reproducible through replay.
- Failure cases are counted.
- Latency is measured on target hardware.
