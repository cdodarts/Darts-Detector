# Configuration

Configuration is **YAML** for hand-edited files and **JSON** for machine-generated calibration profiles (locked decision `D-005` in [DECISIONS.md](DECISIONS.md)). All configs are versioned, validated on startup, and fail closed on invalid input.

## Configuration Goals

- Make camera setup repeatable.
- Preserve calibration validity.
- Tune performance for Raspberry Pi 5 4GB.
- Support development and production profiles.
- Avoid hidden runtime defaults.

## Top-Level Configuration Areas

| Area | Purpose |
| --- | --- |
| Cameras | Device IDs, names, image settings, orientation, crop. |
| Calibration | Active profile and validation behavior. |
| Performance | Resolution/FPS presets and processing limits. |
| API | WebSocket host, port, and event settings. |
| Debug | Frame saving, overlays, replay, logging. |

## Camera Configuration

`config/cameras.yaml` is the primary camera configuration file. It is written automatically by the browser-based camera picker (`uv run python -m darts_detector.cli.camera_picker`), which lets the user assign physical cameras to logical roles via a live-preview UI. Users may also edit the file by hand — the format is deliberately human-readable per `D-005`.

Each camera should have:

- `cameraId`: Stable internal ID such as `cam_1`, `cam_2`, or `cam_3`.
- `name`: Human-readable name such as `Left camera`.
- `friendlyName`: DirectShow friendly name used to filter candidate devices (e.g. `"Autodarts DIY Cam"`). On Windows, all three darts cameras share this name; `devicePath` is the disambiguator.
- `devicePath`: USB device instance path (e.g. `USB\VID_0C45&PID_6366\<port-path>`) identifying the exact physical port. Stable per port. Discovered by the picker UI or by running `list_devices`. On Linux, use `/dev/videoN` instead.
- `role`: Logical role — one of `cam_1`, `cam_2`, `cam_3`.
- `resolution`: Width and height.
- `fps`: Target frames per second.
- `pixelFormat`: `"MJPG"` (default) or `"YUYV"`. Sets `CAP_PROP_FOURCC` on the capture device **before** width/height/FPS — DSHOW requires this ordering. `"MJPG"` uses in-camera hardware JPEG compression, reducing USB bandwidth by ~10x compared to uncompressed `"YUYV"` (YUY2). This is essential for three simultaneous 1280×720@30 streams on a single USB controller. Only change to `"YUYV"` if your cameras do not support MJPG or you need uncompressed frames for a specific workflow.
- `exposure`: `{mode: manual|auto, value: int|null}` — forward-compat placeholder (D-021). **NOT applied at runtime.** Users adjust exposure via their own camera software.
- `gain`: `int` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `brightness`: `int` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `contrast`: `int` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `whiteBalance`: `{mode: manual|auto, value: int|null}` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `gamma`: `int|null` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `saturation`: `int|null` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `sharpness`: `int|null` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `backlightCompensation`: `bool` — forward-compat placeholder (D-021). **NOT applied at runtime.**
- `rotation`: Degrees — one of 0, 90, 180, 270.
- `crop`: Optional crop rectangle `{x, y, width, height}`.
- `enabled`: Whether the camera is active.

**Fields in the Pydantic model (`camera_config.CameraEntry`):** `cameraId`, `name`, `friendlyName`, `devicePath`, `role`, `resolution`, `fps`, `pixelFormat`, `exposure`, `gain`, `brightness`, `contrast`, `whiteBalance`, `gamma`, `saturation`, `sharpness`, `backlightCompensation`, `rotation`, `crop`, `enabled`.

**What `Camera.open()` actually applies (Phase 2, D-021, D-022):** Only `FOURCC` (MJPG), `WIDTH`, `HEIGHT`, `FPS` — via the double-FOURCC pattern. All tuning fields are stored in `cameras.yaml` for future use but are not applied to the hardware at runtime.

All tuning fields that affect the camera image (resolution, rotation, crop, exposure, gain, brightness, contrast, whiteBalance, gamma, saturation, sharpness, backlightCompensation) contribute to the calibration tuning fingerprint (`D-021`). See `docs/CALIBRATION_SYSTEM.md`.

Camera IDs must remain stable because calibration profiles depend on them.

## Camera Adjustments

At MVP there is no built-in camera tuning UI. Users adjust their cameras using the tools that came with them:

- **Windows:** Windows Camera Settings, manufacturer utility (e.g. Logitech Capture, OBS Virtual Camera), or any DirectShow-compatible tool.
- **Linux / Raspberry Pi 5:** `v4l2-ctl` (e.g. `v4l2-ctl -d /dev/video0 --set-ctrl=exposure_auto=1,exposure_absolute=200`).
- **Any platform:** OBS Studio's camera settings, if OBS is already installed.

The tuning fields in `cameras.yaml` (`exposure`, `gain`, `brightness`, `contrast`, `whiteBalance`, etc.) are retained as forward-compatibility placeholders for a future post-MVP tuning UI. They are **not applied at runtime** (D-021). Editing them has no effect on live capture.

**Important:** If you change any tuning field after running calibration, you must recalibrate. The system stores a SHA-256 fingerprint of tuning fields in the calibration profile and invalidates it if `cameras.yaml` changes. See `docs/CALIBRATION_SYSTEM.md`.

**Hardware diagnostic tool:** `scripts/probe_exposure.py` probes a camera's driver response to exposure, gain, and white balance settings and reports which controls are functional.

## Resolution And FPS

**Phase 2:** Resolution and FPS are chosen interactively via the camera picker UI (Step 2: "Select Mode"). The picker reads each camera's MJPG-supported (resolution, fps) pairs, computes the intersection across all 3 cameras, and presents only shared modes. The user picks one pair that applies uniformly to all 3 cameras (D-022). The selected values are written to `cameras.yaml` automatically.

**Mode detection (two-tier):**
1. **Fast path (primary):** reads the camera's native format list via pygrabber's DirectShow `IAMStreamConfig` wrapper.  Completes in < 1 s for all 3 cameras on most hardware (< 200 ms per camera after the first call).
2. **Brute-force fallback:** tries 20 (resolution, fps) combinations via `cv2.VideoCapture.set()` + readback.  Takes ~30–90 s per camera.  Used only when the fast path is unavailable (non-DirectShow driver, future Linux support) or reports no MJPG modes.

Results are cached to `config/.mode_cache.json`; subsequent picker runs are instant on the same hardware.

You do not need to hand-edit resolution or fps after running the picker. If you hand-edit them, ensure all three camera entries have identical values.

**Bandwidth advisory:** The picker shows a yellow warning when the estimated MJPG bandwidth exceeds ~250 Mbps (close to USB 2.0 limit) and a red warning above ~450 Mbps. These are estimates based on MJPG compression factor ~7×. If a camera fails to open, try a lower fps or resolution.

**Canonical resolution menu** (only these values are probed and accepted in `cameras.yaml`):

| Value | Width × Height | Notes |
| --- | --- | --- |
| `1920x1080` | 1920 × 1080 | Full HD. High USB bandwidth. |
| `1280x720` | 1280 × 720 | **Default (D-019).** Balanced quality and bandwidth. |
| `800x600` | 800 × 600 | Lower bandwidth; adequate for most detection. |
| `640x480` | 640 × 480 | Low bandwidth; minimum usable. |

**Canonical FPS menu** (only these values are accepted):

| Value | Notes |
| --- | --- |
| 60 | Optional/aspirational. High USB bandwidth. |
| 30 | **Default (D-019).** Balanced. |
| 25 | Acceptable minimum per D-019. |
| 20 | Low-end; accuracy claims require replay-dataset verification. |
| 15 | Minimum; hardware-constrained only. |

Rules:

- The selected settings must support three simultaneous streams within USB bandwidth limits.
- All 3 cameras must run the same resolution and FPS (D-022). The picker enforces this.
- Higher resolution is useful only if detection accuracy improves enough to justify the cost.
- FPS must be high enough to detect motion and settling reliably. D-019 canonical menu: 60, 30, 25, 20, 15. Values below 25 show an accuracy advisory in the picker UI. Values below 15 are filtered out.
- Effective applied settings are logged at startup: `cam_1: requested 1280x720@30 MJPG, effective 1280x720@28.1 MJPG`. If effective FPS differs from requested by > 5%, a WARNING is logged.

## Exposure, Gain, And Lighting

Stable lighting is expected. Camera auto settings can damage frame differencing reliability.

Recommended behavior:

- Prefer manual exposure for MVP runtime.
- Prefer manual white balance for MVP runtime.
- Log or report when a camera cannot disable auto behavior.
- Keep light ring behavior stable during play.

## Rotation And Crop

Rotation and crop affect calibration.

Rules:

- Calibration must record the rotation and crop used.
- Changing rotation or crop should mark calibration stale.
- Cropping should preserve all scoring regions and expected dart silhouettes.

## Lens Intrinsics Profile (Phase 2.5)

`config/calibration/intrinsics/<cameraId>.json` — one file per camera, written by the intrinsic picker UI (`uv run intrinsic-picker`).

**Format:** JSON conforming to `schemas/camera-intrinsics.schema.json` v1.0.0.

**Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `schemaVersion` | `string` | Semver of this schema. Current: `"1.0.0"`. |
| `cameraId` | `string` | Camera role ID (e.g. `"cam_1"`). Must match `cameras.yaml`. |
| `resolution` | `{w: int, h: int}` | Pixel resolution at which the profile was captured. Must match the camera's runtime resolution; otherwise the profile is ignored. |
| `cameraMatrix` | `number[9]` | 3×3 camera matrix **K** flattened row-major: `[fx, 0, cx, 0, fy, cy, 0, 0, 1]`. Units: pixels. |
| `distortionCoefficients` | `number[5]` | Distortion vector `[k1, k2, p1, p2, k3]` as returned by `cv2.calibrateCamera`. |
| `meanReprojectionError` | `number` | Mean reprojection error across all calibration frames (pixels). Must be < 0.5 px for Phase 3 to accept the profile. |
| `capturedAt` | `string` | ISO 8601 UTC timestamp (e.g. `"2026-05-17T12:00:00.000Z"`). |

**Example:**

```json
{
  "schemaVersion": "1.0.0",
  "cameraId": "cam_1",
  "resolution": { "w": 1280, "h": 720 },
  "cameraMatrix": [900.0, 0.0, 640.0, 0.0, 900.0, 360.0, 0.0, 0.0, 1.0],
  "distortionCoefficients": [-0.25, 0.10, 0.001, -0.001, -0.02],
  "meanReprojectionError": 0.21,
  "capturedAt": "2026-05-17T12:00:00.000Z"
}
```

**Runtime behaviour:**

- `Camera.open()` attempts to load `config/calibration/intrinsics/<cameraId>.json` on startup.
- If the profile exists and its resolution matches the camera's effective resolution, `Camera.open()` pre-computes remap LUTs (`cv2.initUndistortRectifyMap`) for fast per-frame undistortion.
- If the profile is absent, `Camera.open()` logs: `"No intrinsics profile for <cameraId> — frames will not be undistorted. Run uv run intrinsic-picker to calibrate."` This is not an error for Phase 1/2 operation; Phase 3 (board calibration) will refuse to start without valid intrinsics.
- If the profile's resolution does not match the camera's effective resolution, `Camera.open()` logs a warning and skips the profile. **Recalibrate at the new resolution.**
- `Camera.undistort(frame)` applies the cached remap LUTs to a single frame. This is the caller-controlled path; `Camera.read()` returns raw frames. Downstream stages (Phase 3, 6, 7) call `Camera.undistort()` when they need geometrically corrected frames.

**When to recalibrate:** Whenever camera resolution changes, the camera is physically moved, or the intrinsics profile `meanReprojectionError` rises above 0.5 px on re-check.

## Calibration Profile

Configuration should specify:

- Active calibration profile ID.
- Calibration profile path.
- Whether scoring may start when calibration is missing or stale.
- Validation thresholds.

Live scoring should not start with invalid calibration.

## Performance Profile

Performance profiles allow repeatable tuning.

Example profile names:

- `development`
- `pi5-balanced`
- `pi5-low-latency`
- `diagnostic-high-quality`

Profiles may control:

- Resolution.
- FPS.
- Processing scale.
- Detection thresholds.
- Frame saving behavior.
- Maximum per-stage processing time.

## WebSocket Configuration

WebSocket settings should include:

- `host` (default: `0.0.0.0`)
- `port` (default: `8765`)
- `path` (default: `/ws`)
- `eventVersion` (default: `1.0.0`)
- `periodicStatusEvents` (default: `true`)
- `validateOnEmit` (default: `true` in development, `false` in `pi5-low-latency` profile)

The default port `8765` is a high port, unprivileged, and unlikely to collide with common services. Override via config.

## Debug Configuration

Debug settings should include:

- `debugMode`.
- Save failed detection frames.
- Save low-confidence frames.
- Save all frames for a throw.
- Save before/after frames.
- Enable overlays.
- Replay dataset path.
- Log level.

Debug saving must be controllable because frame data can consume significant storage.

## Config Validation

Startup validation should check:

- Three enabled camera IDs are present for normal MVP operation.
- Camera IDs match calibration profile IDs.
- Resolution, rotation, and crop match calibration profile metadata.
- WebSocket port is valid and bindable.
- Performance profile exists.
- Debug output paths are writable when debug saving is enabled.
- YAML files parse cleanly and match their declared schema.
- Calibration profile JSON validates against `schemas/calibration-profile.schema.json`.
- Calibration self-test confirmation flag is present (scoring is blocked otherwise).

Invalid config produces clear errors and MUST NOT silently fall back to unsafe defaults.

## Example: cameras.yaml

```yaml
version: 1
cameras:
  - cameraId: cam1
    name: Left camera
    devicePath: /dev/video0
    resolution: { width: 1280, height: 720 }
    fps: 30
    pixelFormat: MJPG   # MJPG = ~10x lower USB bandwidth than YUYV; default for multi-cam rigs
    exposure: { mode: manual, value: 100 }
    gain: 0
    brightness: 0
    contrast: 0
    whiteBalance: { mode: manual, value: 4500 }
    rotation: 0
    crop: null
    enabled: true
  - cameraId: cam2
    name: Right camera
    devicePath: /dev/video2
    resolution: { width: 1280, height: 720 }
    fps: 30
    pixelFormat: MJPG
    exposure: { mode: manual, value: 100 }
    gain: 0
    brightness: 0
    contrast: 0
    whiteBalance: { mode: manual, value: 4500 }
    rotation: 0
    crop: null
    enabled: true
  - cameraId: cam3
    name: Top camera
    devicePath: /dev/video4
    resolution: { width: 1280, height: 720 }
    fps: 30
    pixelFormat: MJPG
    exposure: { mode: manual, value: 100 }
    gain: 0
    brightness: 0
    contrast: 0
    whiteBalance: { mode: manual, value: 4500 }
    rotation: 0
    crop: null
    enabled: true
```

## Example: profiles/pi5-balanced.yaml

```yaml
version: 1
profileName: pi5-balanced
resolution: { width: 1280, height: 720 }
fps: 60
processingScale: 1.0
motionSettlingMs: 200
diffThreshold: 25
saveFailedFrames: true
saveLowConfidenceFrames: true
saveAllFrames: false
maxStageMs:
  capture: 100
  motion: 200
  diff: 60
  candidate: 80
  fusion: 30
  score: 5
  emit: 10
```
