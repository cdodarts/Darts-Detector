# Calibration System

Calibration maps each camera view to dartboard coordinates. MVP calibration is manual by design because reliability matters more than automation during the first implementation.

## Hard Rule: Calibration Is Invalidated By Tuning Changes (D-021, supersedes D-020)

**Calibration is only valid for the exact camera tuning settings it was captured under.**

Every image tuning parameter — exposure, brightness, contrast, gain, gamma, white balance, saturation, sharpness, backlight compensation, resolution, rotation, crop — affects the pixel-level appearance of the board. A calibration captured under one set of tuning settings is not reliable when the camera operates under different settings.

At MVP there is no built-in camera tuning UI (see D-021). Users adjust their cameras using third-party tools (manufacturer utilities, Windows Camera Settings, OBS Virtual Camera) and optionally hand-edit `cameras.yaml`. The tuning fields in `cameras.yaml` are applied via `Camera._apply_tuning()` on `cap.open()`.

**Ordering guidance:**
```
Phase 1 (camera selection) → adjust cameras via own software → Phase 3 (calibration)
```

If `cameras.yaml` tuning fields change after calibration has been performed, recalibration is required.

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

### Tuning Change Detection At Calibration Time

The calibration UI (Phase 3) must check the fingerprint on entry:
- If `cameras.yaml` has changed since calibration was performed, display a prominent warning: "Camera settings have changed. Recalibrate before scoring."
- Block scoring until the user recalibrates or restores the matching settings.
- Mark the existing calibration profile as stale (not delete it — the user may want to restore settings).

A future Phase 1.5 tuning UI, if built, should also warn the user when saving changes that will invalidate an existing calibration profile.

## Intrinsics vs Extrinsics: Two-Phase Calibration (Phases 2.5 and 3)

Calibration is split into two distinct phases that must be performed in order.

### Phase 2.5: Lens Intrinsic Calibration (per camera)

Each camera has its own lens that introduces barrel distortion. Cheap UVC cameras like the OV2710 have measurable distortion that, if uncorrected, pollutes any homography fit and caps calibration accuracy at 5–8 mm regardless of how many board points are marked.

**Step-by-step user procedure:**

1. **Print the chessboard.** Open `assets/chessboard_9x6_25mm.pdf` and print at 100% scale (no "fit to page"). Confirm with a ruler that one square = 25 mm. Mount on a rigid backing (clipboard or thick cardboard). Keep it flat — do not curve it.
2. **Launch the calibration UI.** Run `uv run intrinsic-picker` (or `uv run intrinsic-picker --host 0.0.0.0` for phone/LAN access). Your browser opens at `http://127.0.0.1:8766`.
3. **For each camera in turn:**
   a. Watch the live preview. When you hold the chessboard in frame, green corner-detection dots appear over the inner corners.
   b. Hold the board at different angles — tilt left, tilt right, near (30 cm), far (60 cm), rotated 30°, rotated 60°. Each capture position should differ visibly from the last.
   c. Click **Capture** (or enable **Auto-capture** to capture automatically every 2 s when detection is stable and the angle differs by > 15° from the previous capture).
   d. Aim for **15 frames** per camera. The thumbnail strip shows all captured frames; click × on a blurry or partial frame to remove it.
   e. When you have at least 10 frames captured, click **Calibrate**.
   f. If mean reprojection error ≤ 0.5 px: click **Save** — profile written to `config/calibration/intrinsics/<cameraId>.json`.
   g. If mean reprojection error > 0.5 px: capture more frames at wider angle variation and click Calibrate again.
4. **Repeat for all 3 cameras.** The UI shows a "All cameras calibrated" banner when all three are saved.
5. **Verify.** Run `uv run pytest tests/smoke/test_phase2_5_intrinsic_calibration.py -v` — all tests should pass.

**What the procedure computes:**
- `cv2.calibrateCamera()` on the captured frames to find:
  - The 3×3 camera matrix **K** (focal lengths `fx`, `fy` and principal point `cx`, `cy`).
  - Five distortion coefficients `(k1, k2, p1, p2, k3)` for radial and tangential distortion.
- Mean reprojection error across all calibration frames (acceptance threshold: < 0.5 px).
- Result saved as `config/calibration/intrinsics/<cameraId>.json` (schema: `schemas/camera-intrinsics.schema.json`).

**Undistort step:** All frames consumed by Phase 3 (board calibration), Phase 5 (motion detection), Phase 6 (tip candidate detection), and Phase 7 (fusion) MUST pass through `cv2.undistort()` (or the faster pre-computed remap table equivalent) using the Phase 2.5 profile before any geometric processing. This is a non-negotiable pipeline step once intrinsics are available.

**Failure mode:** If Phase 2.5 has not been run or the profile has reprojection error > 0.5 px, Phase 3 must fail closed with a plain-language error pointing the user to run intrinsic calibration first. See risk R-25.

### Phase 3: Board (Extrinsic) Calibration (per camera)

Once lens distortion is corrected, Phase 3 maps each undistorted camera view to the board's integer mm coordinate system using a perspective homography.

**Key requirements from Phase 2.5:**
- The Phase 2.5 intrinsics profile must exist and have reprojection error < 0.5 px.
- Frames used during Phase 3 point-marking must be passed through `cv2.undistort()` first.
- The homography solve uses RANSAC with ≥6 input point pairs to produce an over-determined system. The inlier ratio and per-point reprojection error are reported in the profile. Calibration is rejected if any inlier point exceeds 1 mm reprojection error.

**Relationship between phases:**

```text
Phase 2.5: chessboard → cv2.calibrateCamera() → K + distortion coeffs → camera-intrinsics-<id>.json
                                                                                         │
Phase 3:   live frame → cv2.undistort(frame, K, distortion) → mark board points → RANSAC homography → calibration-profile.json
                                                                                         │
Phase 5+:  every live frame → cv2.undistort() → motion / detection / fusion pipeline
```

See `schemas/camera-intrinsics.schema.json` for the intrinsics profile format. See `schemas/calibration-profile.schema.json` for the board calibration profile format (created in Phase 3). See D-023 for the accuracy target this two-phase approach is designed to achieve.

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
- **Any image tuning parameter changes** (exposure, gain, brightness, contrast, white balance, gamma, saturation, sharpness, backlight compensation). The tuning fingerprint stored in the profile will no longer match, and the system must auto-invalidate or warn. See `D-020` and the "Calibration Tuning Fingerprint" section above.
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
