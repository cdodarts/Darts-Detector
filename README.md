# Darts Detector

Open-source, deterministic steel-tip darts detection and scoring for a three-camera DIY setup.

See [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md) for project status and [docs/PHASED_IMPLEMENTATION.md](docs/PHASED_IMPLEMENTATION.md) for the roadmap.

---

## Phase 1 Quickstart

### 1. Install dependencies

Requires [uv](https://docs.astral.sh/uv/). Install it with:

```
pip install uv
```

Then sync the project:

```
uv sync
```

### 2. Identify your cameras

Run the device listing tool to find your three Autodarts DIY Cam devices and their USB instance paths:

```
uv run python -m darts_detector.capture.list_devices
```

The tool prints a table like:

```
Idx    Friendly Name             Device Path (USB instance)          Notes
------ ------------------------- ----------------------------------- ----------------
0      Autodarts DIY Cam         USB\VID_0C45&PID_6366\6&...        ** DARTS CAM **
1      Autodarts DIY Cam         USB\VID_0C45&PID_6366\6&...        ** DARTS CAM **
2      Autodarts DIY Cam         USB\VID_0C45&PID_6366\6&...        ** DARTS CAM **
3      Integrated Webcam         USB\VID_0BDA&PID_5520\...
```

For more accurate friendly names and device paths, install optional helpers:

```
uv add pygrabber comtypes
```

### 3. Configure your cameras

Open `config/cameras.yaml` and paste the `Device Path` value for each camera into the correct role (`cam_left`, `cam_center`, `cam_right`).

### 4. Run the Phase 1 smoke test

With all three cameras connected and `cameras.yaml` filled in:

```
uv run pytest tests/smoke/test_phase1_capture.py -v
```

To test with fewer cameras during development:

```
uv run pytest tests/smoke/test_phase1_capture.py -v --cameras 1
uv run pytest tests/smoke/test_phase1_capture.py -v --cameras 2
```

The smoke test captures for 30 seconds and asserts:
- Measured FPS is within 5% of the configured target.
- Per-frame capture latency is logged to a JSONL file.
- At least 80% of frames are within the 50 ms capture budget (Pi 5 target).
