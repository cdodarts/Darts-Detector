# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.calibration.intrinsics — Phase 2.5 lens intrinsic calibration.

@internal

Provides chessboard corner detection, cv2.calibrateCamera wrapper, intrinsics
persistence (JSON conforming to schemas/camera-intrinsics.schema.json), and a
fast per-frame undistort using pre-computed remap LUTs.

Acceptance criteria (PHASED_IMPLEMENTATION.md Phase 2.5):
- detect_chessboard: find inner corners, refine with cornerSubPix.
- calibrate_camera:  min 8 views, mean reprojection error < 1.5 px (caller's
  UI enforces the stricter 0.5 px target before saving).
- save_intrinsics / load_intrinsics: JSON round-trip, schema validated.
- undistort_frame: uses remap LUTs cached per CameraIntrinsics object.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema path (used for validation)
# ---------------------------------------------------------------------------
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[5] / "schemas" / "camera-intrinsics.schema.json"
)
_SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Sub-pixel refinement criteria (used by detect_chessboard)
# ---------------------------------------------------------------------------
_SUBPIX_CRITERIA = (
    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
    30,
    0.001,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class CalibrationError(RuntimeError):
    """Raised when chessboard calibration cannot produce a valid result."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class CameraIntrinsics:
    """
    Intrinsic parameters for one camera, produced by cv2.calibrateCamera.

    Fields match the camera-intrinsics.schema.json v1.0.0 contract.
    """

    cameraId: str
    resolution: tuple[int, int]          # (width, height)
    cameraMatrix: np.ndarray             # shape (3, 3)
    distCoeffs: np.ndarray               # shape (1, 5) or (5,)
    meanReprojectionError: float
    perImageErrors: list[float]
    capturedAt: str                      # ISO 8601 UTC e.g. "2026-05-17T12:00:00.000Z"

    # --- Remap LUT cache (not serialised) -----------------------------------
    # Populated lazily by undistort_frame(); invalidated on None.
    _map1: Optional[np.ndarray] = field(default=None, repr=False, compare=False)
    _map2: Optional[np.ndarray] = field(default=None, repr=False, compare=False)
    _optimal_matrix: Optional[np.ndarray] = field(default=None, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def detect_chessboard(
    frame_bgr: np.ndarray,
    pattern_size: tuple[int, int] = (9, 6),
) -> tuple[bool, Optional[np.ndarray]]:
    """
    Detect inner chessboard corners in a BGR frame.

    Wraps cv2.findChessboardCorners with ADAPTIVE_THRESH + NORMALIZE_IMAGE
    flags.  On success, refines the result with cv2.cornerSubPix.

    Args:
        frame_bgr:    BGR image as returned by cv2.VideoCapture.read().
        pattern_size: Number of inner corners (cols, rows). Default (9, 6).

    Returns:
        (True, corners_float32) if the pattern was found.
        (False, None)           if not found.
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    flags = (
        cv2.CALIB_CB_ADAPTIVE_THRESH
        | cv2.CALIB_CB_NORMALIZE_IMAGE
        | cv2.CALIB_CB_FAST_CHECK
    )
    found, corners = cv2.findChessboardCorners(gray, pattern_size, flags)
    if not found or corners is None:
        return False, None

    # Sub-pixel refinement — improves accuracy by ~0.1–0.3 px.
    corners_refined = cv2.cornerSubPix(
        gray, corners, winSize=(11, 11), zeroZone=(-1, -1), criteria=_SUBPIX_CRITERIA
    )
    return True, corners_refined


def calibrate_camera(
    images: list[np.ndarray],
    pattern_size: tuple[int, int] = (9, 6),
    square_size_mm: float = 25.0,
    camera_id: str = "unknown",
) -> "CameraIntrinsics":
    """
    Run cv2.calibrateCamera over the supplied BGR frames.

    Args:
        images:         List of BGR frames containing a chessboard.
        pattern_size:   Inner corner grid (cols, rows). Default (9, 6).
        square_size_mm: Physical size of one square in mm. Default 25.0.
        camera_id:      Logical camera ID for the resulting profile.

    Returns:
        CameraIntrinsics populated with K, distortion, and error metrics.

    Raises:
        CalibrationError if:
        - Fewer than 8 images contain a detectable chessboard.
        - Mean reprojection error exceeds 1.5 px (caller's UI enforces
          the stricter 0.5 px acceptance threshold before saving).
    """
    _MIN_VALID_IMAGES = 8
    _MAX_MEAN_ERROR_PX = 1.5

    # Build the object-space 3D point grid (Z=0 for planar chessboard).
    cols, rows = pattern_size
    objp = np.zeros((rows * cols, 3), dtype=np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= square_size_mm

    obj_points: list[np.ndarray] = []
    img_points: list[np.ndarray] = []
    image_shape: Optional[tuple[int, int]] = None  # (h, w)

    for idx, frame in enumerate(images):
        found, corners = detect_chessboard(frame, pattern_size)
        if not found:
            logger.debug("Frame %d: chessboard not found — skipping.", idx)
            continue
        h, w = frame.shape[:2]
        if image_shape is None:
            image_shape = (h, w)
        elif image_shape != (h, w):
            logger.warning(
                "Frame %d has different resolution (%dx%d vs %dx%d) — skipping.",
                idx, w, h, image_shape[1], image_shape[0],
            )
            continue
        obj_points.append(objp)
        img_points.append(corners)

    valid_count = len(obj_points)
    logger.info(
        "calibrate_camera: %d/%d images contained a valid chessboard.",
        valid_count, len(images),
    )

    if valid_count < _MIN_VALID_IMAGES:
        raise CalibrationError(
            f"Only {valid_count} of {len(images)} images contained a detectable "
            f"chessboard. At least {_MIN_VALID_IMAGES} are required. "
            "Vary angles more and ensure the board is fully visible and well-lit."
        )

    h, w = image_shape  # type: ignore[misc]
    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, (w, h), None, None  # type: ignore[arg-type]
    )

    # Compute per-image reprojection errors.
    per_image_errors: list[float] = []
    for i, (op, ip, rvec, tvec) in enumerate(
        zip(obj_points, img_points, rvecs, tvecs)
    ):
        projected, _ = cv2.projectPoints(op, rvec, tvec, camera_matrix, dist_coeffs)
        err = float(
            cv2.norm(ip, projected, cv2.NORM_L2) / np.sqrt(len(projected))
        )
        per_image_errors.append(err)

    mean_error = float(np.mean(per_image_errors))

    if mean_error > _MAX_MEAN_ERROR_PX:
        raise CalibrationError(
            f"Mean reprojection error {mean_error:.3f} px exceeds the maximum "
            f"allowed {_MAX_MEAN_ERROR_PX} px. "
            "Capture more frames at varied angles with the board fully in frame."
        )

    logger.info(
        "Calibration complete for '%s': mean reprojection error = %.4f px "
        "(%d valid frames).",
        camera_id, mean_error, valid_count,
    )

    return CameraIntrinsics(
        cameraId=camera_id,
        resolution=(w, h),
        cameraMatrix=camera_matrix,
        distCoeffs=dist_coeffs,
        meanReprojectionError=mean_error,
        perImageErrors=per_image_errors,
        capturedAt=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") +
                   f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z",
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_intrinsics(intr: CameraIntrinsics, path: Path) -> None:
    """
    Write a CameraIntrinsics profile to JSON conforming to
    schemas/camera-intrinsics.schema.json v1.0.0.

    The file is written atomically (temp file + rename) to avoid partial
    writes on power loss or process kill during a calibration session.

    Args:
        intr: Calibrated intrinsics.
        path: Destination .json file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    w, h = intr.resolution
    payload = {
        "schemaVersion": _SCHEMA_VERSION,
        "cameraId": intr.cameraId,
        "resolution": {"w": w, "h": h},
        "cameraMatrix": intr.cameraMatrix.flatten().tolist(),
        "distortionCoefficients": intr.distCoeffs.flatten().tolist(),
        "meanReprojectionError": round(intr.meanReprojectionError, 6),
        "capturedAt": intr.capturedAt,
    }

    # Validate before writing.
    _validate_payload(payload)

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    logger.info("Intrinsics for '%s' saved to %s.", intr.cameraId, path)


def load_intrinsics(path: Path) -> CameraIntrinsics:
    """
    Load and validate a camera intrinsics JSON file.

    Args:
        path: Path to a camera-intrinsics JSON file.

    Returns:
        CameraIntrinsics ready for use.

    Raises:
        FileNotFoundError if the file does not exist.
        ValueError if the JSON fails schema validation.
    """
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    _validate_payload(raw)

    w = int(raw["resolution"]["w"])
    h = int(raw["resolution"]["h"])
    camera_matrix = np.array(raw["cameraMatrix"], dtype=np.float64).reshape(3, 3)
    dist_coeffs = np.array(
        raw["distortionCoefficients"], dtype=np.float64
    ).reshape(1, 5)

    logger.info(
        "Loaded intrinsics for '%s' from %s (mean err=%.4f px).",
        raw["cameraId"], path, raw["meanReprojectionError"],
    )

    return CameraIntrinsics(
        cameraId=raw["cameraId"],
        resolution=(w, h),
        cameraMatrix=camera_matrix,
        distCoeffs=dist_coeffs,
        meanReprojectionError=float(raw["meanReprojectionError"]),
        perImageErrors=[],          # not stored in JSON (space saving)
        capturedAt=raw["capturedAt"],
    )


# ---------------------------------------------------------------------------
# Undistort
# ---------------------------------------------------------------------------

def undistort_frame(frame: np.ndarray, intr: CameraIntrinsics) -> np.ndarray:
    """
    Undistort a single frame using pre-computed remap LUTs.

    The optimal new camera matrix and remap tables are computed on first call
    and cached inside the CameraIntrinsics object. Subsequent calls use
    cv2.remap() directly, which is ~3–5x faster than cv2.undistort().

    Args:
        frame: BGR (or grayscale) frame to undistort.
        intr:  CameraIntrinsics for this camera.

    Returns:
        Undistorted frame with the same dtype and channel count as input.
    """
    h, w = frame.shape[:2]

    if intr._map1 is None or intr._map2 is None:
        new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
            intr.cameraMatrix, intr.distCoeffs, (w, h), alpha=1, newImgSize=(w, h)
        )
        intr._optimal_matrix = new_camera_matrix
        map1, map2 = cv2.initUndistortRectifyMap(
            intr.cameraMatrix, intr.distCoeffs, None, new_camera_matrix,
            (w, h), cv2.CV_16SC2
        )
        intr._map1 = map1
        intr._map2 = map2
        logger.debug(
            "Computed undistort remap LUTs for camera '%s' at %dx%d.",
            intr.cameraId, w, h,
        )

    return cv2.remap(frame, intr._map1, intr._map2, cv2.INTER_LINEAR)


# ---------------------------------------------------------------------------
# Schema validation (lightweight — no jsonschema dep required)
# ---------------------------------------------------------------------------

def _validate_payload(payload: dict) -> None:
    """
    Lightweight validation against camera-intrinsics.schema.json v1.0.0.

    Raises ValueError with a descriptive message on any violation.
    Does NOT require the jsonschema package to be installed.
    """
    required = [
        "schemaVersion", "cameraId", "resolution", "cameraMatrix",
        "distortionCoefficients", "meanReprojectionError", "capturedAt",
    ]
    for key in required:
        if key not in payload:
            raise ValueError(f"camera-intrinsics: missing required field '{key}'.")

    if not isinstance(payload["schemaVersion"], str):
        raise ValueError("camera-intrinsics: 'schemaVersion' must be a string.")
    if not isinstance(payload["cameraId"], str) or not payload["cameraId"]:
        raise ValueError("camera-intrinsics: 'cameraId' must be a non-empty string.")
    res = payload["resolution"]
    if not isinstance(res, dict) or "w" not in res or "h" not in res:
        raise ValueError("camera-intrinsics: 'resolution' must have 'w' and 'h'.")
    if not (isinstance(res["w"], int) and isinstance(res["h"], int)
            and res["w"] > 0 and res["h"] > 0):
        raise ValueError("camera-intrinsics: resolution w/h must be positive integers.")
    cm = payload["cameraMatrix"]
    if not isinstance(cm, list) or len(cm) != 9:
        raise ValueError("camera-intrinsics: 'cameraMatrix' must be a 9-element array.")
    dc = payload["distortionCoefficients"]
    if not isinstance(dc, list) or len(dc) != 5:
        raise ValueError(
            "camera-intrinsics: 'distortionCoefficients' must be a 5-element array."
        )
    err = payload["meanReprojectionError"]
    if not isinstance(err, (int, float)) or err < 0:
        raise ValueError(
            "camera-intrinsics: 'meanReprojectionError' must be a non-negative number."
        )
    at = payload["capturedAt"]
    if not isinstance(at, str):
        raise ValueError("camera-intrinsics: 'capturedAt' must be a string.")
