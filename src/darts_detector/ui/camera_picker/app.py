# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.ui.camera_picker.app — FastAPI app for the camera picker UI.

@internal

Phase 1 routes
--------------
GET  /                      — Picker page: three role dropdowns + MJPEG previews.
GET  /preview/{device_index} — MJPEG stream (5 fps) from the given camera index.
POST /save                  — Write selected cameras + mode to config/cameras.yaml.

Phase 2 routes (mode selection panel)
--------------------------------------
POST /start_probe           — Start background MJPG mode probing for 3 cameras.
GET  /probe_status          — Poll probe progress (JSON).
GET  /intersection          — Return intersected modes once probing is complete.

Design constraints (D-017, D-018, D-019):
- Only one camera may be opened at a time per device index on Windows/DirectShow.
- MJPEG generators release the camera when the client disconnects.
- All state is passed back and forth via the HTML form / polling; no server-side
  session.
- The picker is a one-shot tool: /save writes the config file and sets a flag
  that causes the uvicorn server to stop after the response is sent.
- Phase 2: all 3 cameras run the SAME resolution and FPS (locked constraint).
  The picker enforces this by only offering intersection of supported modes.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import platform
import threading
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import cv2
import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from darts_detector.capture.list_devices import CameraDevice, enumerate_cameras
from darts_detector.capture.mode_probe import (
    CameraMode,
    bandwidth_advisory,
    best_default_mode,
    intersect_modes,
    probe_supported_modes,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


def _find_config_dir() -> Path:
    """Locate the project's config/ directory by anchoring to pyproject.toml."""
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").is_file():
            return candidate / "config"
    return Path.cwd() / "config"


_CONFIG_DIR = _find_config_dir()
_MODE_CACHE_PATH = _CONFIG_DIR / ".mode_cache.json"

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

# Set to True by /save to signal the server to shut down.
_shutdown_event = threading.Event()

# ---------------------------------------------------------------------------
# Probe state (protected by _probe_lock)
# ---------------------------------------------------------------------------

_probe_lock = threading.Lock()

# Probe progress per camera slot (index 0 = cam_1, 1 = cam_2, 2 = cam_3).
# Each entry: {"device_index": int, "friendly_name": str, "device_path": str,
#              "probed": int, "total": int, "done": bool, "modes": list[CameraMode]}
_probe_state: list[dict] = []
_probe_thread: Optional[threading.Thread] = None

# ---------------------------------------------------------------------------
# Preview capture registry (protected by _preview_lock)
# ---------------------------------------------------------------------------
# Tracks active cv2.VideoCapture handles opened by _mjpeg_generator, keyed by
# device_index.  /start_probe force-releases all tracked handles before
# starting the probe thread so DSHOW doesn't deadlock.
_preview_lock = threading.Lock()
_preview_caps: dict[int, cv2.VideoCapture] = {}

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Darts Detector — Camera Picker", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Cache enumerated cameras for the lifetime of the process.
_cameras: list[CameraDevice] | None = None


def _get_cameras() -> list[CameraDevice]:
    global _cameras
    if _cameras is None:
        _cameras = enumerate_cameras()
    return _cameras


# ---------------------------------------------------------------------------
# Phase 1 routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def picker_page(request: Request) -> HTMLResponse:
    """Render the camera picker page."""
    cameras = _get_cameras()
    camera_options = [
        {"index": c.index, "label": c.label, "is_darts_cam": c.is_darts_cam}
        for c in cameras
    ]
    darts_cams = [c for c in cameras if c.is_darts_cam]
    defaults = darts_cams[:3] if len(darts_cams) >= 3 else cameras[:3]
    default_1 = defaults[0].index if len(defaults) > 0 else -1
    default_2 = defaults[1].index if len(defaults) > 1 else -1
    default_3 = defaults[2].index if len(defaults) > 2 else -1

    return templates.TemplateResponse(
        request,
        "picker.html",
        {
            "cameras": camera_options,
            "default_1": default_1,
            "default_2": default_2,
            "default_3": default_3,
            "camera_count": len(cameras),
        },
    )


@app.get("/cameras")
async def cameras_json() -> JSONResponse:
    """Return enumerated cameras as JSON."""
    cameras = _get_cameras()
    return JSONResponse(
        [
            {
                "index": c.index,
                "label": c.label,
                "friendly_name": c.friendly_name,
                "device_path": c.device_path,
                "is_darts_cam": c.is_darts_cam,
                "frame_ok": c.frame_ok,
            }
            for c in cameras
        ]
    )


@app.get("/preview/{device_index}")
async def preview_stream(device_index: int) -> StreamingResponse:
    """Stream MJPEG frames at ~5 fps from the requested camera index."""
    return StreamingResponse(
        _mjpeg_generator(device_index),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


async def _mjpeg_generator(device_index: int) -> AsyncIterator[bytes]:
    """Async generator yielding MJPEG boundary frames.

    Registers the open cv2.VideoCapture in _preview_caps so that /start_probe
    can force-release it before starting the probe thread (avoids DSHOW
    deadlock when the same device index is re-opened for probing).
    """
    is_windows = platform.system() == "Windows"
    backend = cv2.CAP_DSHOW if is_windows else cv2.CAP_ANY

    cap: cv2.VideoCapture | None = None
    try:
        cap = cv2.VideoCapture(device_index, backend)
        if not cap.isOpened():
            yield _error_frame_bytes("Could not open camera")
            return

        # Register so /start_probe can find and release this handle.
        with _preview_lock:
            _preview_caps[device_index] = cap

        frame_interval = 1.0 / 5.0
        last_frame_time = 0.0

        while True:
            now = time.monotonic()
            sleep_needed = frame_interval - (now - last_frame_time)
            if sleep_needed > 0:
                await asyncio.sleep(sleep_needed)

            ret, frame = cap.read()
            if not ret:
                break

            last_frame_time = time.monotonic()

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buf.tobytes()
                + b"\r\n"
            )

    except (GeneratorExit, asyncio.CancelledError):
        pass
    finally:
        if cap is not None:
            cap.release()
        # Deregister from the tracking dict.
        with _preview_lock:
            _preview_caps.pop(device_index, None)


def _error_frame_bytes(message: str) -> bytes:
    """Return a minimal MJPEG boundary chunk with a grey error image."""
    import numpy as np

    img = np.zeros((240, 320, 3), dtype=np.uint8)
    img[:] = (60, 60, 60)
    cv2.putText(img, message, (10, 120), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (200, 200, 200), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        return b""
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n"
        + buf.tobytes()
        + b"\r\n"
    )


# ---------------------------------------------------------------------------
# Phase 2 routes — mode probing
# ---------------------------------------------------------------------------

@app.post("/start_probe")
async def start_probe(
    cam_1: int = Form(...),
    cam_2: int = Form(...),
    cam_3: int = Form(...),
) -> JSONResponse:
    """Start background MJPG mode probing for the 3 selected cameras.

    Before starting the probe, force-releases any tracked MJPEG preview
    captures so DSHOW is not holding the device handles when the probe thread
    tries to open the same indices.

    Returns immediately. Poll /probe_status for progress.
    """
    global _probe_state, _probe_thread

    # --- Force-release any open preview captures (item B) --------------------
    with _preview_lock:
        if _preview_caps:
            logger.info(
                "start_probe: force-releasing %d open preview capture(s) "
                "before probing.", len(_preview_caps)
            )
            for idx, cap in list(_preview_caps.items()):
                try:
                    cap.release()
                except Exception:
                    pass
            _preview_caps.clear()

    # Give DSHOW 300ms to settle after forced release before opening again.
    await asyncio.sleep(0.3)

    cameras_by_index = {c.index: c for c in _get_cameras()}
    indices = [cam_1, cam_2, cam_3]

    with _probe_lock:
        _probe_state = [
            {
                "slot": slot + 1,
                "device_index": idx,
                "friendly_name": cameras_by_index[idx].friendly_name
                    if idx in cameras_by_index else "",
                "device_path": cameras_by_index[idx].device_path
                    if idx in cameras_by_index else "",
                "probed": 0,
                "total": 20,  # 5 resolutions × 4 fps values
                "done": False,
                "modes": [],
            }
            for slot, idx in enumerate(indices)
        ]

    if _probe_thread is not None and _probe_thread.is_alive():
        # A probe is already running — return current state.
        return JSONResponse({"status": "running"})

    _probe_thread = threading.Thread(target=_run_probe, daemon=True)
    _probe_thread.start()
    logger.info("start_probe: probe thread started for device indices %s.", indices)
    return JSONResponse({"status": "started"})


def _probe_one_camera(slot: int) -> None:
    """Probe a single camera slot. Runs inside the ThreadPoolExecutor."""
    with _probe_lock:
        entry = _probe_state[slot]
        device_index = entry["device_index"]
        friendly_name = entry["friendly_name"]
        device_path = entry["device_path"]

    logger.info(
        "probe: camera slot %d — device_index=%d ('%s') opening for probe.",
        slot + 1, device_index, friendly_name,
    )

    def make_callback(s: int):
        def cb(probed: int, total: int) -> None:
            with _probe_lock:
                _probe_state[s]["probed"] = probed
                _probe_state[s]["total"] = total
        return cb

    modes = probe_supported_modes(
        device_index=device_index,
        friendly_name=friendly_name,
        device_path=device_path,
        cache_path=_MODE_CACHE_PATH,
        progress_callback=make_callback(slot),
    )

    with _probe_lock:
        _probe_state[slot]["modes"] = modes
        _probe_state[slot]["done"] = True
        _probe_state[slot]["probed"] = _probe_state[slot]["total"]

    logger.info(
        "probe: camera slot %d — device_index=%d done. %d mode(s) found.",
        slot + 1, device_index, len(modes),
    )


def _run_probe() -> None:
    """Background thread: probe all cameras in parallel (item D).

    Uses a ThreadPoolExecutor with max_workers=3 so all three cameras are
    probed concurrently.  Expected total time drops from ~95s to ~35s.

    Top-level exception is caught and logged so a daemon thread crash is never
    silent (item E).
    """
    logger.info("probe thread: started.")
    try:
        with _probe_lock:
            slots = list(range(len(_probe_state)))

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_probe_one_camera, slot): slot for slot in slots}
            for future in concurrent.futures.as_completed(futures):
                slot = futures[future]
                exc = future.exception()
                if exc is not None:
                    logger.error(
                        "probe thread: camera slot %d raised an uncaught exception: %s",
                        slot + 1, exc, exc_info=exc,
                    )
                    # Mark the slot as done with fallback so polling can proceed.
                    from darts_detector.capture.mode_probe import _fallback_modes
                    with _probe_lock:
                        _probe_state[slot]["modes"] = _fallback_modes()
                        _probe_state[slot]["done"] = True
                        _probe_state[slot]["probed"] = _probe_state[slot]["total"]

    except Exception:
        logger.exception("probe thread: uncaught exception — marking all slots done.")
        from darts_detector.capture.mode_probe import _fallback_modes
        with _probe_lock:
            for slot in range(len(_probe_state)):
                if not _probe_state[slot]["done"]:
                    _probe_state[slot]["modes"] = _fallback_modes()
                    _probe_state[slot]["done"] = True
                    _probe_state[slot]["probed"] = _probe_state[slot]["total"]

    logger.info("probe thread: exited.")


@app.get("/probe_status")
async def probe_status() -> JSONResponse:
    """Return current probe progress for all 3 cameras.

    Response shape:
    {
      "all_done": bool,
      "cameras": [
        {"slot": 1, "probed": 8, "total": 20, "done": false},
        ...
      ]
    }
    """
    with _probe_lock:
        cameras_status = [
            {
                "slot": e["slot"],
                "probed": e["probed"],
                "total": e["total"],
                "done": e["done"],
            }
            for e in _probe_state
        ]
        all_done = bool(_probe_state) and all(e["done"] for e in _probe_state)

    return JSONResponse({"all_done": all_done, "cameras": cameras_status})


@app.get("/intersection")
async def get_intersection() -> JSONResponse:
    """Return the intersected mode list once probing is complete.

    Response shape:
    {
      "ready": bool,
      "modes": [
        {"width": 1280, "height": 720, "fps": 30, "label": "1280x720 @ 30 fps"},
        ...
      ],
      "default_width": 1280,
      "default_height": 720,
      "default_fps": 30
    }
    """
    with _probe_lock:
        if not _probe_state or not all(e["done"] for e in _probe_state):
            return JSONResponse({"ready": False, "modes": []})
        all_modes = [e["modes"] for e in _probe_state]

    shared = intersect_modes(all_modes)
    default = best_default_mode(shared)

    return JSONResponse({
        "ready": True,
        "modes": [
            {
                "width": m.width,
                "height": m.height,
                "fps": m.fps,
                "label": m.label,
            }
            for m in shared
        ],
        "default_width": default.width,
        "default_height": default.height,
        "default_fps": default.fps,
    })


@app.get("/bandwidth_advisory")
async def get_bandwidth_advisory(
    width: int,
    height: int,
    fps: int,
    num_cameras: int = 3,
) -> JSONResponse:
    """Return bandwidth advisory for a given mode.

    Response shape: {"severity": "ok"|"warn"|"error", "message": str}
    """
    severity, message = bandwidth_advisory(width, height, fps, num_cameras)
    return JSONResponse({"severity": severity, "message": message})


# ---------------------------------------------------------------------------
# Save route (Phase 1 + Phase 2: now includes resolution/fps from mode picker)
# ---------------------------------------------------------------------------

@app.post("/save", response_class=HTMLResponse)
async def save_config(
    request: Request,
    cam_1: int = Form(...),
    cam_2: int = Form(...),
    cam_3: int = Form(...),
    selected_width: int = Form(default=1280),
    selected_height: int = Form(default=720),
    selected_fps: int = Form(default=30),
) -> HTMLResponse:
    """Write the selected cameras and mode to config/cameras.yaml and signal shutdown."""
    cameras_by_index = {c.index: c for c in _get_cameras()}

    def _cam_entry(role_id: str, role_name: str, cam: CameraDevice | None) -> dict:
        base: dict = {
            "cameraId": role_id,
            "name": role_name,
            "friendlyName": cam.friendly_name if cam else "",
            "devicePath": cam.device_path if cam else "",
            "role": role_id,
            "resolution": {"width": selected_width, "height": selected_height},
            "fps": selected_fps,
            # MJPG keeps USB bandwidth ~10x lower than uncompressed YUY2.
            "pixelFormat": "MJPG",
            # Tuning fields kept as forward-compat placeholders (D-021).
            # NOT applied at runtime — users adjust via their own camera software.
            "exposure": {"mode": "manual", "value": 100},
            "gain": 0,
            "brightness": 0,
            "contrast": 0,
            "whiteBalance": {"mode": "manual", "value": 4500},
            "rotation": 0,
            "crop": None,
            "enabled": True,
        }
        return base

    config = {
        "version": 1,
        "cameras": [
            _cam_entry("cam_1", "Camera 1", cameras_by_index.get(cam_1)),
            _cam_entry("cam_2", "Camera 2", cameras_by_index.get(cam_2)),
            _cam_entry("cam_3", "Camera 3", cameras_by_index.get(cam_3)),
        ],
    }

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cameras_yaml_path = _CONFIG_DIR / "cameras.yaml"
    with open(cameras_yaml_path, "w", encoding="utf-8") as fh:
        yaml.dump(config, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def _trigger_shutdown() -> None:
        time.sleep(0.5)
        _shutdown_event.set()

    threading.Thread(target=_trigger_shutdown, daemon=True).start()

    cam_1_device = cameras_by_index.get(cam_1)
    cam_2_device = cameras_by_index.get(cam_2)
    cam_3_device = cameras_by_index.get(cam_3)

    return templates.TemplateResponse(
        request,
        "picker.html",
        {
            "saved": True,
            "cameras_yaml_path": str(cameras_yaml_path),
            "label_1": cam_1_device.label if cam_1_device else f"index {cam_1}",
            "label_2": cam_2_device.label if cam_2_device else f"index {cam_2}",
            "label_3": cam_3_device.label if cam_3_device else f"index {cam_3}",
            "saved_width": selected_width,
            "saved_height": selected_height,
            "saved_fps": selected_fps,
            # Not used in saved state but required by template context.
            "cameras": [],
            "default_1": cam_1,
            "default_2": cam_2,
            "default_3": cam_3,
            "camera_count": 0,
        },
    )
