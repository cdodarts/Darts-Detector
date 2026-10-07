# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.ui.intrinsic_picker.app — FastAPI app for Phase 2.5 lens
intrinsic calibration.

@internal

Routes
------
GET  /                          — Main page; three cameras side-by-side.
GET  /preview/{cameraId}        — MJPEG stream with live chessboard overlay.
POST /capture/{cameraId}        — Capture current frame; return thumbnail + corner state.
DELETE /capture/{cameraId}/{idx} — Remove a captured frame by index.
POST /clear/{cameraId}          — Clear all captured frames for a camera.
POST /calibrate/{cameraId}      — Run cv2.calibrateCamera; return intrinsics.
POST /save/{cameraId}           — Persist calibration to disk.
GET  /status                    — Per-camera frame count, calibration state, error.
GET  /thumbnail/{cameraId}/{idx} — Return a specific captured frame as JPEG.

Design constraints:
- Analogous to camera_picker app (D-017, D-018).
- MJPEG streams closed before calibration runs (avoids DSHOW handle conflicts).
- All captured frames held in-memory until Save; nothing written to disk
  between Capture and Save.
- Intrinsics stored at config/calibration/intrinsics/<cameraId>.json.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import threading
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import cv2
import numpy as np
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from darts_detector.calibration.intrinsics import (
    CameraIntrinsics,
    CalibrationError,
    calibrate_camera,
    detect_chessboard,
    load_intrinsics,
    save_intrinsics,
    undistort_frame,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))
_REPO_ROOT = _HERE.parents[4]
_CONFIG_ROOT = _REPO_ROOT / "config"
_INTRINSICS_DIR = _CONFIG_ROOT / "calibration" / "intrinsics"
_CAMERAS_YAML = _CONFIG_ROOT / "cameras.yaml"

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Darts Detector — Intrinsic Calibration")

app.mount(
    "/static",
    StaticFiles(directory=str(_HERE / "static")),
    name="static",
)

# ---------------------------------------------------------------------------
# Shutdown event (mirrors camera_picker pattern)
# ---------------------------------------------------------------------------
_shutdown_event = threading.Event()

# ---------------------------------------------------------------------------
# Per-camera state
# ---------------------------------------------------------------------------
_CAMERA_IDS = ["cam_1", "cam_2", "cam_3"]

# State stored per camera ID
_captured_frames: dict[str, list[np.ndarray]] = {c: [] for c in _CAMERA_IDS}
_calibration_result: dict[str, Optional[CameraIntrinsics]] = {
    c: None for c in _CAMERA_IDS
}
_calibration_saved: dict[str, bool] = {c: False for c in _CAMERA_IDS}

# Active MJPEG preview captures — tracked so they can be released before
# calibration probing (mirrors camera_picker DSHOW workaround).
_preview_caps: dict[str, cv2.VideoCapture] = {}
_preview_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Camera config helpers
# ---------------------------------------------------------------------------


def _load_camera_config() -> dict:
    """Load cameras.yaml; return empty dict if missing."""
    if not _CAMERAS_YAML.exists():
        return {}
    with open(_CAMERAS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get_device_index(camera_id: str) -> Optional[int]:
    """Resolve camera_id to a cv2 device index from cameras.yaml."""
    cfg = _load_camera_config()
    cameras = cfg.get("cameras", {})
    entry = cameras.get(camera_id)
    if entry is None:
        return None
    return entry.get("deviceIndex")


# ---------------------------------------------------------------------------
# MJPEG preview with chessboard overlay
# ---------------------------------------------------------------------------

async def _mjpeg_generator(camera_id: str) -> AsyncIterator[bytes]:
    """
    Async generator that yields MJPEG frames at ~5 fps.

    Draws green crosses on detected chessboard inner corners.
    Yields a blank frame if the camera cannot be opened.
    """
    import platform

    device_index = _get_device_index(camera_id)
    if device_index is None:
        logger.warning("Preview for '%s': no device index in cameras.yaml.", camera_id)
        blank = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(blank, "Not configured", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 1)
        _, jpg = cv2.imencode(".jpg", blank, [cv2.IMWRITE_JPEG_QUALITY, 60])
        body = jpg.tobytes()
        yield (
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + body + b"\r\n"
        )
        return

    backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
    cap = cv2.VideoCapture(device_index, backend)
    if not cap.isOpened():
        logger.warning("Preview for '%s': could not open device %d.", camera_id, device_index)
        cap.release()
        return

    # Apply requested resolution from config.
    cfg = _load_camera_config()
    entry = cfg.get("cameras", {}).get(camera_id, {})
    res = entry.get("resolution", {})
    w = res.get("width", 640)
    h = res.get("height", 480)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

    with _preview_lock:
        _preview_caps[camera_id] = cap

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # Chessboard overlay — draw green crosses on detected corners.
            found, corners = detect_chessboard(frame, (9, 6))
            if found and corners is not None:
                cv2.drawChessboardCorners(frame, (9, 6), corners, found)

            # Encode at reduced quality for streaming bandwidth.
            _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            body = jpg.tobytes()
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + body + b"\r\n"
            )

            # ~5 fps preview
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        pass
    finally:
        with _preview_lock:
            _preview_caps.pop(camera_id, None)
        cap.release()
        logger.debug("Preview stream for '%s' closed.", camera_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Main calibration page."""
    # Check which cameras already have saved intrinsics.
    saved_status = {}
    for cam_id in _CAMERA_IDS:
        path = _INTRINSICS_DIR / f"{cam_id}.json"
        saved_status[cam_id] = path.exists()

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="intrinsic.html",
        context={
            "camera_ids": _CAMERA_IDS,
            "saved_status": saved_status,
        },
    )


@app.get("/preview/{camera_id}")
async def preview(camera_id: str) -> StreamingResponse:
    """MJPEG stream for the specified camera with chessboard overlay."""
    if camera_id not in _CAMERA_IDS:
        return JSONResponse({"error": f"Unknown camera_id: {camera_id}"}, status_code=404)
    return StreamingResponse(
        _mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/capture/{camera_id}")
async def capture(camera_id: str) -> JSONResponse:
    """
    Capture the current frame from a camera and store it in memory.

    Returns a thumbnail (base64 JPEG) plus corner detection state.
    """
    import platform

    if camera_id not in _CAMERA_IDS:
        return JSONResponse({"error": f"Unknown camera_id: {camera_id}"}, status_code=404)

    device_index = _get_device_index(camera_id)
    if device_index is None:
        return JSONResponse(
            {"error": f"Camera '{camera_id}' not configured in cameras.yaml."},
            status_code=400,
        )

    # Stop the MJPEG stream for this camera before opening the capture handle
    # to avoid DSHOW device conflicts.
    with _preview_lock:
        existing = _preview_caps.pop(camera_id, None)
    if existing is not None:
        existing.release()
        time.sleep(0.3)

    backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
    cap = cv2.VideoCapture(device_index, backend)
    if not cap.isOpened():
        return JSONResponse(
            {"error": f"Could not open camera '{camera_id}' (index={device_index})."},
            status_code=500,
        )

    # Apply configured resolution.
    cfg = _load_camera_config()
    entry = cfg.get("cameras", {}).get(camera_id, {})
    res = entry.get("resolution", {})
    w = res.get("width", 640)
    h = res.get("height", 480)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

    # Warm up — discard a few frames to let auto-exposure settle.
    for _ in range(3):
        cap.read()
    ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        return JSONResponse({"error": "Failed to capture frame."}, status_code=500)

    # Detect chessboard in the captured frame.
    found, corners = detect_chessboard(frame, (9, 6))

    # Store frame in memory.
    _captured_frames[camera_id].append(frame.copy())
    frame_idx = len(_captured_frames[camera_id]) - 1

    # Generate thumbnail (160 wide, proportional height).
    th_w = 160
    th_h = int(frame.shape[0] * th_w / frame.shape[1])
    thumb = cv2.resize(frame, (th_w, th_h))
    if found and corners is not None:
        # Draw overlay on thumbnail too.
        scale = th_w / frame.shape[1]
        scaled_corners = (corners * scale).astype(np.float32)
        cv2.drawChessboardCorners(thumb, (9, 6), scaled_corners, found)
    _, jpg = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
    thumb_b64 = base64.b64encode(jpg.tobytes()).decode()

    total = len(_captured_frames[camera_id])
    logger.info(
        "Captured frame %d for '%s': corners_found=%s. Total: %d.",
        frame_idx, camera_id, found, total,
    )

    return JSONResponse({
        "camera_id": camera_id,
        "frame_index": frame_idx,
        "corners_found": bool(found),
        "total_frames": total,
        "thumbnail_b64": thumb_b64,
    })


@app.delete("/capture/{camera_id}/{frame_index}")
async def delete_capture(camera_id: str, frame_index: int) -> JSONResponse:
    """Remove a captured frame by index."""
    if camera_id not in _CAMERA_IDS:
        return JSONResponse({"error": f"Unknown camera_id: {camera_id}"}, status_code=404)
    frames = _captured_frames[camera_id]
    if frame_index < 0 or frame_index >= len(frames):
        return JSONResponse(
            {"error": f"Frame index {frame_index} out of range (have {len(frames)})."},
            status_code=400,
        )
    frames.pop(frame_index)
    # Invalidate calibration since frame set changed.
    _calibration_result[camera_id] = None
    _calibration_saved[camera_id] = False
    return JSONResponse({"camera_id": camera_id, "total_frames": len(frames)})


@app.post("/clear/{camera_id}")
async def clear(camera_id: str) -> JSONResponse:
    """Clear all captured frames for a camera."""
    if camera_id not in _CAMERA_IDS:
        return JSONResponse({"error": f"Unknown camera_id: {camera_id}"}, status_code=404)
    _captured_frames[camera_id].clear()
    _calibration_result[camera_id] = None
    _calibration_saved[camera_id] = False
    logger.info("Cleared all frames for '%s'.", camera_id)
    return JSONResponse({"camera_id": camera_id, "total_frames": 0})


@app.post("/calibrate/{camera_id}")
async def calibrate(camera_id: str) -> JSONResponse:
    """
    Run cv2.calibrateCamera on the accumulated frames for a camera.

    Returns the intrinsics + reprojection error on success, or an error
    message if calibration fails.
    """
    if camera_id not in _CAMERA_IDS:
        return JSONResponse({"error": f"Unknown camera_id: {camera_id}"}, status_code=404)

    frames = _captured_frames[camera_id]
    if len(frames) < 8:
        return JSONResponse(
            {
                "error": (
                    f"Need at least 8 frames with a detected chessboard. "
                    f"You have {len(frames)}. Capture more frames at varied angles."
                )
            },
            status_code=400,
        )

    try:
        intr = calibrate_camera(
            images=frames,
            pattern_size=(9, 6),
            square_size_mm=25.0,
            camera_id=camera_id,
        )
    except CalibrationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    _calibration_result[camera_id] = intr
    _calibration_saved[camera_id] = False

    return JSONResponse({
        "camera_id": camera_id,
        "mean_reprojection_error": round(intr.meanReprojectionError, 4),
        "per_image_errors": [round(e, 4) for e in intr.perImageErrors],
        "frames_used": len(intr.perImageErrors),
        "resolution": {"w": intr.resolution[0], "h": intr.resolution[1]},
    })


@app.post("/save/{camera_id}")
async def save(camera_id: str) -> JSONResponse:
    """Save the current calibration profile for a camera to disk."""
    if camera_id not in _CAMERA_IDS:
        return JSONResponse({"error": f"Unknown camera_id: {camera_id}"}, status_code=404)

    intr = _calibration_result[camera_id]
    if intr is None:
        return JSONResponse(
            {"error": f"No calibration result for '{camera_id}'. Run /calibrate first."},
            status_code=400,
        )

    out_path = _INTRINSICS_DIR / f"{camera_id}.json"
    try:
        save_intrinsics(intr, out_path)
    except Exception as exc:
        logger.exception("Failed to save intrinsics for '%s'.", camera_id)
        return JSONResponse({"error": str(exc)}, status_code=500)

    _calibration_saved[camera_id] = True
    logger.info("Saved intrinsics for '%s' to %s.", camera_id, out_path)

    all_saved = all(_calibration_saved[c] for c in _CAMERA_IDS)
    return JSONResponse({
        "camera_id": camera_id,
        "saved_path": str(out_path),
        "all_cameras_calibrated": all_saved,
    })


@app.get("/status")
async def status() -> JSONResponse:
    """Per-camera calibration status."""
    result = {}
    for cam_id in _CAMERA_IDS:
        intr = _calibration_result[cam_id]
        state = "pending"
        if intr is not None:
            state = "saved" if _calibration_saved[cam_id] else "calibrated"
        result[cam_id] = {
            "frame_count": len(_captured_frames[cam_id]),
            "calibration_state": state,
            "mean_reprojection_error": (
                round(intr.meanReprojectionError, 4) if intr else None
            ),
        }
    return JSONResponse(result)


@app.get("/thumbnail/{camera_id}/{frame_index}")
async def thumbnail(camera_id: str, frame_index: int) -> Response:
    """Return a captured frame as a JPEG thumbnail."""
    if camera_id not in _CAMERA_IDS:
        return Response(status_code=404)
    frames = _captured_frames[camera_id]
    if frame_index < 0 or frame_index >= len(frames):
        return Response(status_code=404)
    frame = frames[frame_index]
    th_w = 160
    th_h = int(frame.shape[0] * th_w / frame.shape[1])
    thumb = cv2.resize(frame, (th_w, th_h))
    _, jpg = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return Response(content=jpg.tobytes(), media_type="image/jpeg")
