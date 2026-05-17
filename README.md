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

Then sync the project (installs FastAPI, uvicorn, and all other dependencies):

```
uv sync
```

### 2. Assign your cameras with the browser picker

Plug in all three cameras, then launch the camera picker:

```
uv run python -m darts_detector.cli.camera_picker
```

Your browser opens automatically at `http://127.0.0.1:8765`. You will see:

- Three panels labelled **Camera 1 / Camera 2 / Camera 3**.
- A live preview (5 fps) for each camera.
- A dropdown under each preview to select which physical camera goes in that slot.

Select the correct camera for each slot, then click **Save Configuration**.
The picker writes `config/cameras.yaml` and closes the server. You can then
close the browser tab.

**Setting up from a phone or tablet?** Launch with `--host 0.0.0.0` so the
picker is reachable over your LAN:

```
uv run python -m darts_detector.cli.camera_picker --host 0.0.0.0
```

The terminal will print both the localhost URL and a LAN URL such as
`http://192.168.1.x:8765`. Open the LAN URL on your phone's browser to
complete the setup wirelessly.

**No browser / headless Pi?** Use the CLI fallback instead:

```
uv run python -m darts_detector.capture.list_devices
```

Then edit `config/cameras.yaml` manually with the device paths shown.

### 3. Run the Phase 1 smoke test

With all three cameras connected and `cameras.yaml` written:

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
