# Calibration System

Calibration maps each camera view to dartboard coordinates. MVP calibration is manual by design because reliability matters more than automation during the first implementation.

## Hard Rule: Image Tuning Must Precede Calibration (D-020)

**Calibration is only valid for the exact camera tuning settings it was captured under.**

Every image tuning parameter — exposure, brightness, contrast, gain, gamma, white balance, saturation, sharpness, backlight compensation, resolution, rotation, crop — affects the pixel-level appearance of the board. A calibration captured under one set of tuning settings is not reliable when the camera operates under different settings.

**Ordering constraint (locked in `D-020`):**
```
Phase 1 (camera selection) → Phase 1.5 (image tuning UI) → Phase 3 (calibration)
```

Do not build or enter the calibration UI until Phase 1.5 image tuning is complete and saved.

### Calibration Tuning Fingerprint

Every calibration profile must include a SHA-256 hash (fingerprint) of the camera tuning settings that were in force when the calibration was performed. The fingerprint is computed over all tuning fields that affect image geometry or appearance: resolution, rotation, crop, exposure (mode + value), gain, brightness, contrast, white balance (mode + value), gamma, saturation, sharpness, backlight compensation.

FPS is recorded in the profile for diagnostics but does NOT contribute to the fingerprint (FPS does not affect image geometry).

### Tuning Match Check

At every entry point to the calibration UI and at runtime startup, the system must:

1. Compute the current tuning fingerprint for each camera.
2. Compare it to the fingerprint stored in the active calibration profile.
3. If any camera's fingerprint does not match:
   - Display: "Current tuning does not match calibration. Camera: [cam_id]. Recalibrate before scoring."
   - Block scoring until the user either restores matching tuning settings or recalibrates.
   - Offer a "Recalibrate" button that launches the calibration assistant.

The calibration page must show a per-camera status indicator: "Tuning matches calibration: Yes / No" with field-level detail where practical.

### Phase 1.5 Tuning UI Integration

The Phase 1.5 image tuning UI "Save and proceed to calibration" button must:
- Warn the user if an existing calibration profile is present and the tuning changes they made will invalidate it.
- Allow the user to confirm the invalidation before proceeding.
- Mark the existing calibration profile as stale (not delete it — the user may want to restore settings).

## Calibration Goals

- Produce stable camera-to-board mappings.
- Support three fixed cameras.
- Make calibration quality visible.
- Save profiles that can be loaded across restarts.
- Allow future semi-automatic and fully automatic calibration without replacing the MVP workflow too early.

## Manual Calibration First

For MVP, the user manually marks key dartboard points in all three camera views.

Manual calibration is acceptable because:

- Camera positions are fixed.
- Calibration is not needed before every throw.
- It gives deterministic, inspectable setup data.
- It avoids brittle early automation.

## Required User-Marked Points

The exact UI can evolve, but the calibration model must capture enough information to map image coordinates to board coordinates.

Recommended marked data:

| Point/Feature | Purpose |
| --- | --- |
| Centre bull | Defines board origin. |
| Inner bull edge or points | Helps validate scale near center if visible. |
| Outer bull edge or points | Helps validate center and radial scale. |
| Triple ring points | Helps map middle scoring ring and perspective. |
| Double ring points | Defines outer scoring boundary. |
| 20 segment orientation | Defines angular rotation of board. |
| Additional ring/segment intersections | Improves perspective fit and validation. |

All points should be stored per camera with image coordinates and semantic labels.

## Board Coordinate System

Calibration output should map each camera view into board coordinates where:

- Bull center is `(0, 0)`.
- Positive and negative axes are consistent across the application.
- Distances are normalized or expressed in board units.
- The scoring engine can consume coordinates without knowing camera image geometry.

The scoring engine should not depend on raw image coordinates.

## Perspective Mapping

Each camera sees the board from an angle, so the board appears distorted.

Calibration should estimate a mapping from image space to board space using:

- Board center.
- Ring geometry.
- Segment orientation.
- Perspective transform or another documented deterministic mapping.

The mapping must be validated by projecting known board geometry back onto the camera image and checking whether overlays align with the real board.

## Saved Calibration Profile

A calibration profile should include:

- Profile ID and version.
- Creation and update timestamps.
- Camera IDs and names.
- Resolution, rotation, and crop used during calibration.
- `fps` at time of calibration (informational; does not contribute to fingerprint, but logged for diagnostics).
- **`tuningFingerprint` per camera** — SHA-256 hash of the tuning fields in force at calibration time. Fields hashed: resolution, rotation, crop, exposure (mode + value), gain, brightness, contrast, white balance (mode + value), gamma, saturation, sharpness, backlight compensation.
- Marked calibration points for each camera.
- Computed mapping parameters.
- Validation metrics.
- Board geometry version.

The profile must be invalidated or flagged when any camera setting that contributes to the tuning fingerprint changes (per `D-020`).

## Recalibration Workflow

Recalibration is required when:

- A camera moves.
- The dartboard moves or rotates.
- Resolution, crop, or rotation changes.
  - **Resolution note (D-019):** Camera intrinsics (focal length, principal point in pixels) scale with resolution. A calibration captured at 1280×720 is invalid at 1920×1080. The camera tuning UI (Phase 1.5) must mark calibration stale and prompt the user to recalibrate whenever resolution changes.
- Overlays no longer match the board.
- Accuracy metrics show systematic location error.

Recommended workflow:

1. Show current camera views.
2. Load existing calibration profile if present.
3. Overlay projected board geometry.
4. Let the user adjust points.
5. Validate projection quality.
6. Save a new profile version.
7. Run a calibration smoke test before enabling scoring.

## Calibration Validation

Validation should check:

- Required points exist for each camera.
- Points are within image bounds.
- Board orientation is consistent.
- Ring projections are plausible.
- Mappings are numerically stable.
- Calibration was captured with matching camera settings.

Calibration should fail closed. If validation fails, live scoring should not start.

## Future Semi-Automatic Calibration

Semi-automatic calibration may assist the user by detecting likely rings, center, and segment orientation.

Rules:

- User correction must remain available.
- Suggested points must be visually confirmed.
- Assisted calibration must produce the same profile format as manual calibration.
- It must remain deterministic and inspectable.

## Future Fully Automatic Calibration

Long-term, the goal is automated calibration with a user experience similar to mature DIY camera scoring systems.

Fully automatic calibration should not become required until it is measured against a representative calibration dataset. It must be developed separately from the manual MVP path and must not reduce reliability.
