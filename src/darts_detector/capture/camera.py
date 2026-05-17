# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.capture.camera — single-camera wrapper around cv2.VideoCapture.

@internal

Wraps one physical camera. Opens with DirectShow on Windows (cv2.CAP_DSHOW) and
the default backend elsewhere. Applies resolution and FPS from the CameraEntry
config on open(). Does NOT do frame differencing, detection, or calibration.

See docs/PHASED_IMPLEMENTATION.md Phase 1 for scope constraints.
"""

from __future__ import annotations

import logging
import platform
from typing import Optional

import cv2
import numpy as np

from darts_detector.config.camera_config import CameraEntry

logger = logging.getLogger(__name__)


class CameraOpenError(RuntimeError):
    """Raised when a camera fails to open."""


class Camera:
    """
    Single-camera wrapper.

    Args:
        camera_id:    Logical camera ID (e.g. 'cam_left'). Used in log messages.
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

    @property
    def camera_id(self) -> str:
        return self._camera_id

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> None:
        """
        Open the camera and apply resolution / FPS from config.

        Raises CameraOpenError if the device cannot be opened.
        """
        logger.info(
            "Opening camera '%s' (index=%d, backend=%s).",
            self._camera_id,
            self._device_index,
            "CAP_DSHOW" if self._backend == cv2.CAP_DSHOW else "default",
        )
        cap = cv2.VideoCapture(self._device_index, self._backend)
        if not cap.isOpened():
            raise CameraOpenError(
                f"Failed to open camera '{self._camera_id}' at index {self._device_index}. "
                "Check that the device is connected and no other process has it open."
            )

        # Apply resolution and FPS.
        w = self._config.resolution.width
        h = self._config.resolution.height
        fps = self._config.fps

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)

        # Read back effective values and log if they differ.
        eff_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        eff_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        eff_fps = cap.get(cv2.CAP_PROP_FPS)

        if eff_w != w or eff_h != h:
            logger.warning(
                "Camera '%s': requested %dx%d but got %dx%d.",
                self._camera_id, w, h, eff_w, eff_h,
            )
        if abs(eff_fps - fps) > 1:
            logger.warning(
                "Camera '%s': requested %d FPS but got %.1f FPS.",
                self._camera_id, fps, eff_fps,
            )

        self._cap = cap
        logger.info(
            "Camera '%s' opened: %dx%d @ %.1f FPS.",
            self._camera_id, eff_w, eff_h, eff_fps,
        )

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
