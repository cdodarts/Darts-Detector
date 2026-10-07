# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.capture.camera — single-camera wrapper around cv2.VideoCapture.

@internal

Wraps one physical camera. Opens with DirectShow on Windows (cv2.CAP_DSHOW) and
the default backend elsewhere. Applies ONLY resolution, FPS, and FOURCC (MJPG)
from the CameraEntry config on open(). Exposure, gain, and all other image-tuning
controls are NOT applied at runtime — see D-021. Power users who hand-edit
cameras.yaml can still use _apply_tuning() directly; it is retained as a
forward-compatibility hook for a future tuning UI.

Phase 2.5 addition: on Camera.open(), attempts to load the intrinsics profile
from config/calibration/intrinsics/<cameraId>.json. If present, pre-computes
remap LUTs (cv2.initUndistortRectifyMap) so that undistort() is fast. The
caller decides when to apply undistortion — read() returns raw frames.

See docs/PHASED_IMPLEMENTATION.md Phase 2 and Phase 2.5 for scope constraints.
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from darts_detector.config.camera_config import CameraEntry

logger = logging.getLogger(__name__)

# Path to intrinsics profiles directory (relative resolution deferred to runtime
# so tests can override _INTRINSICS_DIR without import-time side effects).
_INTRINSICS_DIR: Optional[Path] = None


def _default_intrinsics_dir() -> Path:
    """Return the default intrinsics directory (repo-root relative)."""
    # Walk up from this file: capture/ -> darts_detector/ -> src/ -> repo root
    return Path(__file__).resolve().parents[3] / "config" / "calibration" / "intrinsics"


class CameraOpenError(RuntimeError):
    """Raised when a camera fails to open."""


class Camera:
    """
    Single-camera wrapper.

    Args:
        camera_id:    Logical camera ID (e.g. 'cam_1'). Used in log messages.
        device_index: OpenCV device index (integer). Resolved by the caller via
                      list_devices or config matching.
        config:       CameraEntry from cameras.yaml.
    """

    def __init__(
        self,
        camera_id: str,
        device_index: int,
        config: CameraEntry,
    ) -> None:
        self._camera_id = camera_id
        self._device_index = device_index
        self._config = config
        self._cap: Optional[cv2.VideoCapture] = None
        self._backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY

        # Phase 2.5: intrinsics (None until loaded in open()).
        # Imported lazily to avoid circular imports and to keep Phase 1/2 tests
        # passing even when the calibration package is not yet present.
        self._intrinsics: Optional[object] = None  # CameraIntrinsics | None

    @property
    def camera_id(self) -> str:
        return self._camera_id

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def undistorted(self) -> bool:
        """True if a valid intrinsics profile was loaded and remap LUTs are ready."""
        return self._intrinsics is not None and getattr(self._intrinsics, "_map1", None) is not None

    def open(self) -> None:
        """
        Open the camera and apply resolution / FPS from config.

        Raises CameraOpenError if the device cannot be opened.
        """
        # --- Determine desired FOURCC -----------------------------------------
        # "MJPG" (default) keeps USB bandwidth ~10x lower than "YUYV" (uncompressed
        # YUY2). This is required for three simultaneous 1280×720@30 streams on a
        # single USB controller. On Windows/DSHOW the format must be hinted at
        # VideoCapture construction time via the params vector — the USB isochronous
        # bandwidth allocation happens at open() and cannot be changed afterwards by
        # calling set(CAP_PROP_FOURCC) on an already-open handle in YUY2 mode.
        pixel_format: str = getattr(self._config, "pixelFormat", "MJPG") or "MJPG"
        fourcc_int = cv2.VideoWriter.fourcc(*pixel_format.ljust(4)[:4])

        logger.info(
            "Opening camera '%s' (index=%d, backend=%s, fourcc=%s).",
            self._camera_id,
            self._device_index,
            "CAP_DSHOW" if self._backend == cv2.CAP_DSHOW else "default",
            pixel_format,
        )

        cap = cv2.VideoCapture(self._device_index, self._backend)
        if not cap.isOpened():
            raise CameraOpenError(
                f"Failed to open camera '{self._camera_id}' at index {self._device_index}. "
                "Check that the device is connected and no other process has it open."
            )

        # --- Apply settings in the order required by DSHOW -------------------
        #
        # Empirically verified on OV2710-based Autodarts DIY Cams with Windows DSHOW:
        #   FOURCC (1st) → WIDTH → HEIGHT → FPS → FOURCC (2nd)
        #
        # The first FOURCC call hints the format before the resolution-change
        # triggers internal media-type re-negotiation. The second FOURCC call after
        # FPS "commits" the format — without it the driver reverts to YUY2 at the
        # requested resolution. This two-call pattern is driver-specific but harmless
        # on drivers that don't need it (the second call is a no-op if already set).
        #
        # MJPG keeps USB bandwidth ~10x lower than YUY2, which is required for three
        # simultaneous 1280×720@30 streams on one USB controller.

        w = self._config.resolution.width
        h = self._config.resolution.height
        fps = self._config.fps

        cap.set(cv2.CAP_PROP_FOURCC, fourcc_int)       # hint format first
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_FOURCC, fourcc_int)       # commit format after resolution

        # Read back effective FOURCC and warn if the driver refused.
        eff_fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        eff_fourcc_str = (
            chr(eff_fourcc_int & 0xFF)
            + chr((eff_fourcc_int >> 8) & 0xFF)
            + chr((eff_fourcc_int >> 16) & 0xFF)
            + chr((eff_fourcc_int >> 24) & 0xFF)
        ).rstrip("\x00")
        if eff_fourcc_int != fourcc_int:
            logger.warning(
                "Camera '%s': requested FOURCC '%s' but driver reported '%s'. "
                "USB bandwidth may be higher than expected.",
                self._camera_id, pixel_format, eff_fourcc_str,
            )
        else:
            logger.info(
                "Camera '%s': FOURCC set to '%s'.",
                self._camera_id, eff_fourcc_str,
            )

        # Read back effective resolution and FPS.
        eff_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        eff_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        eff_fps = cap.get(cv2.CAP_PROP_FPS)

        if eff_w != w or eff_h != h:
            logger.warning(
                "Camera '%s': requested resolution %dx%d but driver reported %dx%d.",
                self._camera_id, w, h, eff_w, eff_h,
            )

        self._cap = cap

        # Log effective vs. requested — warn if effective FPS differs by > 5%.
        fps_diff_pct = abs(eff_fps - fps) / max(fps, 1)
        if fps_diff_pct > 0.05:
            logger.warning(
                "Camera '%s': requested %dx%d@%d MJPG, effective %dx%d@%.1f MJPG "
                "(FPS differs by %.0f%% — within normal DSHOW scheduling variability).",
                self._camera_id, w, h, fps, eff_w, eff_h, eff_fps, fps_diff_pct * 100,
            )
        else:
            logger.info(
                "Camera '%s': requested %dx%d@%d MJPG, effective %dx%d@%.1f MJPG.",
                self._camera_id, w, h, fps, eff_w, eff_h, eff_fps,
            )

        # Sub-25 fps accuracy advisory (D-019).
        # We do NOT refuse to open — the DIY ethos says the system adapts to the
        # user's hardware. A dart tip is stationary for many frames after impact;
        # detection geometry still works, but with reduced temporal resolution.
        if eff_fps < 25.0:
            logger.warning(
                "Camera '%s' running at %.1f fps. Detection accuracy may be reduced "
                "below 25 fps (D-019 recommends 30+ fps). Continuing as configured.",
                self._camera_id, eff_fps,
            )

        # NOTE: _apply_tuning() is intentionally NOT called here.
        # Phase 2 / D-021: camera image tuning (exposure, gain, WB, etc.) is
        # the user's responsibility via their own camera software. This call was
        # removed in Phase 2. The _apply_tuning() method is retained below as a
        # forward-compatibility hook for the deferred post-MVP tuning UI.

        # Phase 2.5: load intrinsics profile and pre-compute remap LUTs.
        self._load_intrinsics(eff_w, eff_h)

    # ------------------------------------------------------------------
    # Phase 2.5 — Intrinsics and undistort
    # ------------------------------------------------------------------

    def _load_intrinsics(self, eff_w: int, eff_h: int) -> None:
        """
        Attempt to load the intrinsics profile for this camera.

        Looks at config/calibration/intrinsics/<cameraId>.json.
        On success: pre-computes remap LUTs via cv2.initUndistortRectifyMap()
        so that undistort() is fast (avoids per-call matrix inversion).
        On failure or missing file: logs INFO and leaves _intrinsics as None.
        This is intentional — Phase 2.5 is a prerequisite for Phase 3, NOT
        for Phase 1/2 smoke tests, which must still pass without intrinsics.
        """
        try:
            from darts_detector.calibration.intrinsics import (
                load_intrinsics,
                undistort_frame as _undistort_frame,
            )
        except ImportError:
            logger.debug(
                "Camera '%s': calibration.intrinsics not importable — skipping.", self._camera_id
            )
            return

        intrinsics_dir = _INTRINSICS_DIR if _INTRINSICS_DIR is not None else _default_intrinsics_dir()
        profile_path = intrinsics_dir / f"{self._camera_id}.json"

        if not profile_path.exists():
            logger.info(
                "No intrinsics profile for %s — frames will not be undistorted. "
                "Run `uv run intrinsic-picker` to calibrate.",
                self._camera_id,
            )
            return

        try:
            intr = load_intrinsics(profile_path)
        except Exception as exc:
            logger.warning(
                "Camera '%s': failed to load intrinsics from %s: %s",
                self._camera_id, profile_path, exc,
            )
            return

        # Validate resolution match.
        prof_w, prof_h = intr.resolution
        if prof_w != eff_w or prof_h != eff_h:
            logger.warning(
                "Camera '%s': intrinsics profile resolution %dx%d does not match "
                "effective camera resolution %dx%d — ignoring profile. "
                "Recalibrate at the current resolution.",
                self._camera_id, prof_w, prof_h, eff_w, eff_h,
            )
            return

        # Pre-compute remap LUTs by calling undistort_frame once on a dummy frame.
        # This triggers the lazy LUT initialisation in undistort_frame().
        import numpy as _np
        dummy = _np.zeros((eff_h, eff_w, 3), dtype=_np.uint8)
        try:
            _undistort_frame(dummy, intr)
        except Exception as exc:
            logger.warning(
                "Camera '%s': failed to initialise undistort LUTs: %s", self._camera_id, exc
            )
            return

        self._intrinsics = intr
        logger.info(
            "Camera '%s': loaded intrinsics profile from %s "
            "(mean reprojection error = %.4f px, resolution = %dx%d).",
            self._camera_id, profile_path, intr.meanReprojectionError, eff_w, eff_h,
        )

    def undistort(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply lens undistortion to a single frame using pre-computed remap LUTs.

        This method is the caller-controlled undistort path — Camera.read()
        returns raw (distorted) frames. Call this when a downstream stage needs
        a geometrically correct frame (Phase 3 board calibration, Phase 6
        tip candidate detection, etc.).

        If no intrinsics profile was loaded (Phase 2.5 not yet run), returns
        the input frame unchanged. No exception is raised — callers are safe to
        always call this method without checking undistorted first.

        Args:
            frame: BGR frame as returned by read().

        Returns:
            Undistorted frame (same shape and dtype as input), or the original
            frame if no intrinsics are available.
        """
        if self._intrinsics is None:
            return frame
        try:
            from darts_detector.calibration.intrinsics import undistort_frame
            return undistort_frame(frame, self._intrinsics)  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning(
                "Camera '%s': undistort() failed (%s) — returning raw frame.",
                self._camera_id, exc,
            )
            return frame

    def _apply_tuning(self) -> None:
        """
        Forward-compatibility hook for the deferred post-MVP camera tuning UI.

        REMOVED FROM Camera.open() IN PHASE 2 (D-021).

        Camera image tuning — exposure, gain, brightness, contrast, white balance,
        gamma, saturation, sharpness, and backlight compensation — is the user's
        responsibility via their own camera software (manufacturer utility, Windows
        Camera Settings, OBS Virtual Camera, etc.).

        This method is retained so that:
        1. Power users who hand-edit cameras.yaml can call it directly if they
           know their driver supports the relevant properties.
        2. A future post-MVP tuning UI can layer on top of this method without
           changing any public contract.

        NOT called from open(). The only settings Camera.open() applies are:
        FOURCC (MJPG), WIDTH, HEIGHT, FPS — via the double-FOURCC pattern.
        """
        if self._cap is None or not self._cap.isOpened():
            return

        cfg = self._config

        # ---- Exposure ---------------------------------------------------------
        if cfg.exposure.mode == "manual":
            # Force auto-exposure OFF on DSHOW (1 = manual, 3 = auto).
            self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            if cfg.exposure.value is not None:
                ok = self._cap.set(cv2.CAP_PROP_EXPOSURE, float(cfg.exposure.value))
                if not ok:
                    logger.warning(
                        "Camera '%s': could not set exposure to %d (driver may not support manual exposure).",
                        self._camera_id, cfg.exposure.value,
                    )
                else:
                    logger.debug("Camera '%s': exposure set to %d.", self._camera_id, cfg.exposure.value)
        else:
            # Auto — re-enable auto-exposure.
            self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)

        # ---- Gain -------------------------------------------------------------
        if cfg.gain:
            ok = self._cap.set(cv2.CAP_PROP_GAIN, float(cfg.gain))
            if not ok:
                logger.warning("Camera '%s': could not set gain to %d.", self._camera_id, cfg.gain)
            else:
                logger.debug("Camera '%s': gain set to %d.", self._camera_id, cfg.gain)

        # ---- Brightness -------------------------------------------------------
        if cfg.brightness:
            ok = self._cap.set(cv2.CAP_PROP_BRIGHTNESS, float(cfg.brightness))
            if not ok:
                logger.warning("Camera '%s': could not set brightness to %d.", self._camera_id, cfg.brightness)

        # ---- Contrast ---------------------------------------------------------
        if cfg.contrast:
            ok = self._cap.set(cv2.CAP_PROP_CONTRAST, float(cfg.contrast))
            if not ok:
                logger.warning("Camera '%s': could not set contrast to %d.", self._camera_id, cfg.contrast)

        # ---- White Balance ----------------------------------------------------
        if cfg.whiteBalance.mode == "manual":
            # Disable auto WB first.
            self._cap.set(cv2.CAP_PROP_AUTO_WB, 0)
            if cfg.whiteBalance.value is not None:
                ok = self._cap.set(cv2.CAP_PROP_WHITE_BALANCE_BLUE_U, float(cfg.whiteBalance.value))
                if not ok:
                    logger.warning(
                        "Camera '%s': could not set white balance to %d K.",
                        self._camera_id, cfg.whiteBalance.value,
                    )
                else:
                    logger.debug(
                        "Camera '%s': white balance set to %d K.", self._camera_id, cfg.whiteBalance.value,
                    )
        else:
            self._cap.set(cv2.CAP_PROP_AUTO_WB, 1)

        # ---- Gamma ------------------------------------------------------------
        if cfg.gamma is not None:
            ok = self._cap.set(cv2.CAP_PROP_GAMMA, float(cfg.gamma))
            if not ok:
                logger.warning("Camera '%s': could not set gamma to %d.", self._camera_id, cfg.gamma)

        # ---- Saturation -------------------------------------------------------
        if cfg.saturation is not None:
            ok = self._cap.set(cv2.CAP_PROP_SATURATION, float(cfg.saturation))
            if not ok:
                logger.warning("Camera '%s': could not set saturation to %d.", self._camera_id, cfg.saturation)

        # ---- Sharpness --------------------------------------------------------
        if cfg.sharpness is not None:
            ok = self._cap.set(cv2.CAP_PROP_SHARPNESS, float(cfg.sharpness))
            if not ok:
                logger.warning("Camera '%s': could not set sharpness to %d.", self._camera_id, cfg.sharpness)

        # ---- Backlight Compensation -------------------------------------------
        val = 1.0 if cfg.backlightCompensation else 0.0
        self._cap.set(cv2.CAP_PROP_BACKLIGHT, val)

    def close(self) -> None:
        """Release the camera."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Camera '%s' closed.", self._camera_id)

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        """
        Read one frame from the camera.

        Returns:
            (True, frame_ndarray) on success.
            (False, None) on failure or if the camera is not open.
        """
        if self._cap is None or not self._cap.isOpened():
            logger.error("Camera '%s' read() called but camera is not open.", self._camera_id)
            return False, None
        ok, frame = self._cap.read()
        if not ok:
            logger.warning("Camera '%s' read() returned False.", self._camera_id)
            return False, None
        return True, frame

    def effective_fps(self) -> float:
        """Return the FPS currently reported by the driver (may differ from requested)."""
        if self._cap is None:
            return 0.0
        return self._cap.get(cv2.CAP_PROP_FPS)

    def __repr__(self) -> str:
        return (
            f"Camera(id={self._camera_id!r}, index={self._device_index}, "
            f"open={self.is_open})"
        )
