# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.ui.camera_picker.app — FastAPI app for the camera picker UI.

@internal

Routes
------
GET  /                      — Picker page: three role dropdowns + MJPEG previews.
GET  /preview/{device_index} — MJPEG stream (5 fps) from the given camera index.
POST /save                  — Write selected cameras to config/cameras.yaml.

Design constraints (D-017, D-018):
- Only one camera may be opened at a time per device index on Windows/DirectShow.
- MJPEG generators release the camera when the client disconnects.
- All state is passed back and forth via the HTML form; no server-side session.
- The picker is a one-shot tool: /save writes the config file and sets a flag
  that causes the uvicorn server to stop after the response is sent.
"""

from __future__ import annotations

import asyncio
import platform
import threading
import time
from pathlib import Path
from typing import AsyncIterator

import cv2
import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from darts_detector.capture.list_devices import CameraDevice, enumerate_cameras

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

# Config is always written to <repo-root>/config/cameras.yaml.
# We walk up from the package src tree to find the repo root.
def _find_config_dir() -> Path:
    """Locate the config/ directory relative to the installed package tree."""
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "config").is_dir():
            return candidate / "config"
    # Fallback: create config/ next to pyproject.toml in cwd
    return Path.cwd() / "config"


_CONFIG_DIR = _find_config_dir()

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

# Set to True by /save to signal the server to shut down.
_shutdown_event = threading.Event()

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
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def picker_page(request: Request) -> HTMLResponse:
    """Render the camera picker page."""
    cameras = _get_cameras()
    # Build a flat list of {index, label} for the template dropdowns.
    camera_options = [
        {"index": c.index, "label": c.label, "is_darts_cam": c.is_darts_cam}
        for c in cameras
    ]
    # Default selection: first three darts cams in index order, or first three.
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
    """Return enumerated cameras as JSON (used by vanilla JS to refresh the list)."""
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
    """Stream MJPEG frames at ~5 fps from the requested camera index.

    The generator opens the camera, yields frames, and releases the handle
    when the client disconnects (GeneratorExit / StopIteration). Only one
    stream should be open at any given time for a particular device_index on
    Windows — the HTML page enforces this by stopping the old stream before
    starting a new one.
    """
    return StreamingResponse(
        _mjpeg_generator(device_index),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


async def _mjpeg_generator(device_index: int) -> AsyncIterator[bytes]:
    """Async generator yielding MJPEG boundary frames."""
    is_windows = platform.system() == "Windows"
    backend = cv2.CAP_DSHOW if is_windows else cv2.CAP_ANY

    cap: cv2.VideoCapture | None = None
    try:
        cap = cv2.VideoCapture(device_index, backend)
        if not cap.isOpened():
            # Yield a single error JPEG placeholder and stop.
            yield _error_frame_bytes("Could not open camera")
            return

        # Target 5 fps for the picker preview — low enough to stay responsive
        # without saturating USB bandwidth during enumeration.
        frame_interval = 1.0 / 5.0
        last_frame_time = 0.0

        while True:
            now = time.monotonic()
            sleep_needed = frame_interval - (now - last_frame_time)
            if sleep_needed > 0:
                await asyncio.sleep(sleep_needed)

            ret, frame = cap.read()
            if not ret:
                # Camera stopped delivering frames — break out cleanly.
                break

            last_frame_time = time.monotonic()

            # Encode to JPEG and yield as MJPEG boundary chunk.
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
        # Client disconnected — clean up below.
        pass
    finally:
        if cap is not None:
            cap.release()


def _error_frame_bytes(message: str) -> bytes:
    """Return a minimal MJPEG boundary chunk with a grey error image."""
    import numpy as np

    img = np.zeros((240, 320, 3), dtype=np.uint8)
    img[:] = (60, 60, 60)
    cv2.putText(
        img,
        message,
        (10, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )
    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        return b""
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n"
        + buf.tobytes()
        + b"\r\n"
    )


@app.post("/save", response_class=HTMLResponse)
async def save_config(
    request: Request,
    cam_1: int = Form(...),
    cam_2: int = Form(...),
    cam_3: int = Form(...),
) -> HTMLResponse:
    """Write the selected cameras to config/cameras.yaml and signal shutdown."""
    cameras_by_index = {c.index: c for c in _get_cameras()}

    def _cam_entry(role_id: str, role_name: str, cam: CameraDevice | None) -> dict:
        if cam is None:
            return {
                "cameraId": role_id,
                "name": role_name,
                "friendlyName": "",
                "devicePath": "",
                "role": role_id,
                "resolution": {"width": 1280, "height": 720},
                "fps": 60,
                "exposure": {"mode": "manual", "value": 100},
                "gain": 0,
                "brightness": 0,
                "contrast": 0,
                "whiteBalance": {"mode": "manual", "value": 4500},
                "rotation": 0,
                "crop": None,
                "enabled": True,
            }
        return {
            "cameraId": role_id,
            "name": role_name,
            "friendlyName": cam.friendly_name,
            "devicePath": cam.device_path,
            "role": role_id,
            "resolution": {"width": 1280, "height": 720},
            "fps": 60,
            "exposure": {"mode": "manual", "value": 100},
            "gain": 0,
            "brightness": 0,
            "contrast": 0,
            "whiteBalance": {"mode": "manual", "value": 4500},
            "rotation": 0,
            "crop": None,
            "enabled": True,
        }

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

    # Signal shutdown after the response is sent.
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
            # Not used in saved state but required by template context
            "cameras": [],
            "default_1": cam_1,
            "default_2": cam_2,
            "default_3": cam_3,
            "camera_count": 0,
        },
    )
