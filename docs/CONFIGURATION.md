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
- `exposure`: Manual exposure value where supported.
- `gain`: Manual gain value where supported.
- `brightness`.
- `contrast`.
- `whiteBalance`: Manual value or disabled auto mode where supported.
- `rotation`: Degrees or enum.
- `crop`: Optional crop rectangle.
- `enabled`: Whether the camera is active.

Camera IDs must remain stable because calibration profiles depend on them.

## Resolution And FPS

Resolution and FPS should be selected with target hardware limits in mind. Both fields are per-camera and set via the camera tuning UI (Phase 1.5) or by hand-editing `cameras.yaml`.

**Canonical resolution menu** (only these values are accepted in `cameras.yaml` and in the UI dropdowns):

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
- Higher resolution is useful only if detection accuracy improves enough to justify the cost.
- FPS must be high enough to detect motion and settling reliably.
- Effective applied settings should be reported at runtime.
- Resolution and FPS are configurable from the camera tuning UI (Phase 1.5) with live measured FPS readout and dropped-frame count.

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
