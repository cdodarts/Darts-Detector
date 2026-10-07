# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.capture.device_resolver — Map camera config roles to OpenCV device indices.

@internal

Uses pygrabber (Windows/DirectShow) to match cameras by friendly name, then assigns
device indices in the order they appear in the DirectShow device list. Falls back to
sequential indices when pygrabber is unavailable or devicePath is empty for all cameras.

Extracted from tests/smoke/test_phase1_capture.py so both the tuning UI and the smoke
test use the same resolution logic (DRY).
"""

from __future__ import annotations

import logging
import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from darts_detector.config.camera_config import CamerasConfig

logger = logging.getLogger(__name__)


def resolve_device_indices(cameras_config: "CamerasConfig") -> dict[str, int]:
    """
    Map each enabled camera role to an OpenCV device index.

    On Windows the function enumerates DirectShow devices via pygrabber and
    matches each CameraEntry by friendly name, assigning indices in the order
    they appear in the DirectShow list so that cameras sharing the same friendly
    name (e.g. three "Autodarts DIY Cam" units) are disambiguated by USB port
    position rather than relying on guesswork.

    If pygrabber is unavailable, or if all devicePaths in the config are empty,
    the function falls back to sequential indices (0, 1, 2) and logs a warning.

    Parameters
    ----------
    cameras_config:
        The loaded CamerasConfig.  Only enabled cameras are considered.

    Returns
    -------
    dict[str, int]
        ``{cameraId: device_index}`` for every enabled camera.
    """
    import cv2

    enabled = cameras_config.enabled_cameras()

    # Fast path: all devicePaths empty → sequential fallback.
    if all(not c.devicePath for c in enabled):
        logger.warning(
            "devicePath is empty for all cameras — using sequential indices 0, 1, 2. "
            "Run list_devices and fill in cameras.yaml for reliable assignment."
        )
        return {c.cameraId: i for i, c in enumerate(enabled)}

    if platform.system() != "Windows":
        # Non-Windows: pygrabber not available; use sequential indices.
        logger.warning(
            "Non-Windows platform — device index resolution via pygrabber is not "
            "available. Using sequential indices."
        )
        return {c.cameraId: i for i, c in enumerate(enabled)}

    try:
        from pygrabber.dshow_graph import FilterGraph  # type: ignore[import]
        graph = FilterGraph()
        dshow_devices: list[str] = graph.get_input_devices()
    except Exception as exc:  # ImportError or COM failure
        logger.warning(
            "pygrabber unavailable (%s); falling back to sequential device indices.", exc
        )
        return {c.cameraId: i for i, c in enumerate(enabled)}

    # Build index map by matching friendly name in DirectShow order.
    # Multiple cameras share the same friendly name — claim the first unclaimed index.
    index_map: dict[str, int] = {}
    claimed: set[int] = set()

    for cam in enabled:
        matched = False
        for i, dshow_name in enumerate(dshow_devices):
            if i in claimed:
                continue
            if cam.friendlyName and cam.friendlyName.lower() in dshow_name.lower():
                index_map[cam.cameraId] = i
                claimed.add(i)
                matched = True
                logger.debug(
                    "Resolved %s (%s) → DirectShow index %d (%s)",
                    cam.cameraId, cam.friendlyName, i, dshow_name,
                )
                break
        if not matched:
            # Friendly name not found; take the next unclaimed sequential index.
            fallback = next(j for j in range(20) if j not in claimed)
            index_map[cam.cameraId] = fallback
            claimed.add(fallback)
            logger.warning(
                "Could not match %s (friendlyName=%r) in DirectShow list; "
                "assigned index %d as fallback.",
                cam.cameraId, cam.friendlyName, fallback,
            )

    return index_map
