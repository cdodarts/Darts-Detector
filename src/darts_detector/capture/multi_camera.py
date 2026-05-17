# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.capture.multi_camera — threaded capture from up to 3 cameras.

@internal

Starts one background thread per camera. Each thread calls camera.read() in a
tight loop and pushes frames onto a per-camera queue (maxsize=2). The main
thread calls get_frames() to retrieve the most recent frame from each camera.

Design constraints (from docs/LATENCY_BUDGET.md and docs/AGENT_RULES.md):
  - Capture budget: 50 ms wall-clock (cameras run in parallel, not summed).
  - Drop oldest frame on queue overflow — never block the capture thread.
  - Record per-frame capture latency via LatencyLogger.
  - No frame copies beyond what OpenCV allocates internally.

See docs/PHASED_IMPLEMENTATION.md Phase 1 for scope.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

import numpy as np

from darts_detector.capture.camera import Camera, CameraOpenError
from darts_detector.config.camera_config import CameraEntry
from darts_detector.diagnostics.latency import LatencyLogger, StageTimer

logger = logging.getLogger(__name__)

# Type alias: per-camera frame bundle — (frame_ndarray, capture_timestamp_perf_counter)
FrameBundle = tuple[np.ndarray, float]


class MultiCamera:
    """
    Threaded multi-camera capture manager.

    Args:
        configs:         List of CameraEntry objects from cameras.yaml.
        latency_logger:  LatencyLogger instance for per-stage timing.
        device_index_map: Optional override mapping cameraId → OpenCV device index.
                          If omitted, the index is derived from the order of enabled
                          cameras (0, 1, 2 ...). In production, pass the map produced
                          by the device-matching logic that reads devicePath.
    """

    def __init__(
        self,
        configs: list[CameraEntry],
        latency_logger: LatencyLogger,
        device_index_map: Optional[dict[str, int]] = None,
    ) -> None:
        self._configs = configs
        self._latency_logger = latency_logger
        self._device_index_map = device_index_map or {}

        self._cameras: dict[str, Camera] = {}
        self._queues: dict[str, queue.Queue[FrameBundle]] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._stop_event = threading.Event()
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open all cameras and start capture threads."""
        if self._started:
            raise RuntimeError("MultiCamera.start() called twice.")

        self._stop_event.clear()

        for i, cfg in enumerate(self._configs):
            if not cfg.enabled:
                continue
            index = self._device_index_map.get(cfg.cameraId, i)
            cam = Camera(camera_id=cfg.cameraId, device_index=index, config=cfg)
            try:
                cam.open()
            except CameraOpenError as exc:
                logger.error("Could not open camera '%s': %s", cfg.cameraId, exc)
                raise

            q: queue.Queue[FrameBundle] = queue.Queue(maxsize=2)
            t = threading.Thread(
                target=self._capture_loop,
                args=(cam, q),
                name=f"capture-{cfg.cameraId}",
                daemon=True,
            )
            self._cameras[cfg.cameraId] = cam
            self._queues[cfg.cameraId] = q
            self._threads[cfg.cameraId] = t
            t.start()
            logger.info("Capture thread started for camera '%s'.", cfg.cameraId)

        self._started = True

    def stop(self) -> None:
        """Signal capture threads to stop, then close all cameras."""
        self._stop_event.set()
        for cam_id, t in self._threads.items():
            t.join(timeout=2.0)
            if t.is_alive():
                logger.warning("Capture thread for '%s' did not stop cleanly.", cam_id)
        for cam in self._cameras.values():
            cam.close()
        self._started = False
        logger.info("MultiCamera stopped.")

    # ------------------------------------------------------------------
    # Frame access
    # ------------------------------------------------------------------

    def get_frames(
        self,
        timeout: float = 0.1,
    ) -> dict[str, FrameBundle]:
        """
        Return the most recent frame for each active camera.

        Blocks up to `timeout` seconds per camera if no frame is available yet.
        Returns only cameras that produced a frame within the timeout.

        Returns:
            dict mapping cameraId → (frame_ndarray, capture_perf_counter_timestamp)
        """
        result: dict[str, FrameBundle] = {}
        for cam_id, q in self._queues.items():
            try:
                # Drain all but the latest frame so we always get the freshest one.
                bundle = q.get(timeout=timeout)
                while True:
                    try:
                        bundle = q.get_nowait()
                    except queue.Empty:
                        break
                result[cam_id] = bundle
            except queue.Empty:
                logger.debug("get_frames: no frame within %.1f s for '%s'.", timeout, cam_id)
        return result

    @property
    def active_camera_ids(self) -> list[str]:
        """Camera IDs of currently active (open and threaded) cameras."""
        return list(self._cameras.keys())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _capture_loop(self, cam: Camera, q: "queue.Queue[FrameBundle]") -> None:
        """
        Per-camera background thread: read frames and push to queue.

        Capture latency is measured from just before cam.read() to frame available
        in the queue, in accordance with LATENCY_BUDGET.md (budget: 50 ms).
        """
        while not self._stop_event.is_set():
            with StageTimer("capture", self._latency_logger) as timer:
                ok, frame = cam.read()
                ts = time.perf_counter()

            if not ok or frame is None:
                logger.warning("Camera '%s': failed read in capture loop.", cam.camera_id)
                time.sleep(0.005)  # brief back-off on bad frame
                continue

            # Push to queue; drop oldest if full to prevent buffer buildup.
            if q.full():
                try:
                    q.get_nowait()
                    logger.debug(
                        "Camera '%s': queue full, dropped oldest frame (elapsed %.1f ms).",
                        cam.camera_id,
                        timer.elapsed_ms,
                    )
                except queue.Empty:
                    pass
            try:
                q.put_nowait((frame, ts))
            except queue.Full:
                pass  # race condition; safe to skip
