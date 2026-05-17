# Debug And Replay

Debug and replay tooling is required for reliable development. A darts detector cannot be made accurate from live observation alone.

## Goals

- Reproduce failed detections.
- Inspect every stage of the deterministic pipeline.
- Compare detected scores against labelled truth.
- Measure accuracy and latency.
- Tune thresholds without requiring live throws every time.

## Frame Saving Requirements

The system should be able to save:

- Failed detection frames.
- Low-confidence detection frames.
- Before and after frames.
- All three camera frames for a throw.
- Baseline frames.
- Motion frames if storage settings allow.
- Difference images and masks.
- Candidate overlays.
- Final fusion and scoring metadata.

Frame saving should be configurable to avoid uncontrolled storage growth.

## Throw Record

A saved throw record should include:

- Throw ID.
- Timestamp.
- Camera IDs.
- Camera settings.
- Calibration profile ID and version.
- Baseline frames.
- Post-throw frames.
- Optional motion sequence frames.
- Detection result.
- Timing metrics.
- Rejection reasons if any.
- Manual label if available.

The replay system should use the same detection path as live processing wherever possible.

## Replay Saved Throws

Replay tooling should support:

- Running one saved throw.
- Running a directory of saved throws.
- Comparing current results to stored expected results.
- Generating summary metrics.
- Exporting debug overlays.

Replay is required before major detection changes are accepted.

## Manual Truth Labelling

Labelled truth should include:

- Expected section.
- Expected number.
- Expected multiplier.
- Expected score.
- Optional board coordinate if manually measured.
- Label confidence or notes.
- Whether the throw is a border case.

Labels should be stored separately from raw frames when possible so detector outputs can be regenerated.

## Debug Overlays

Debug overlays should visualize:

- Board calibration geometry.
- Baseline vs post-throw changes.
- Difference mask.
- Connected components.
- Detected dart body or shaft line.
- Estimated tip candidate.
- Per-camera confidence.
- Fused board coordinate.
- Score and alternatives.

Overlays must match the actual data used by detection, not a separate approximation.

## Confidence Debugging

Confidence debugging should expose:

- Per-camera candidate confidence.
- Calibration confidence or validation status.
- Fusion agreement.
- Border proximity.
- Alternative score list.
- Rejection reason.

This is necessary because a single confidence number is not enough to diagnose scoring errors.

## Accuracy Statistics

Replay reports should include:

- Total labelled throws.
- Correct score count and percentage.
- Correct segment count and percentage.
- Correct multiplier count and percentage.
- False positives.
- False negatives.
- Rejections.
- Low-confidence events.
- Border-case performance.
- Latency percentiles.

No public 99%+ accuracy claim should be made until this data exists for a real labelled dataset.

## Storage Layout

A future implementation may use a layout like:

```text
debug/
  throws/
    THROW_ID/
      metadata.json
      cam1_baseline.png
      cam1_post.png
      cam1_mask.png
      cam1_overlay.png
      cam2_baseline.png
      cam2_post.png
      cam3_baseline.png
      cam3_post.png
```

This is a documentation example, not a required implementation yet.
