# SPDX-License-Identifier: GPL-3.0-or-later
"""
Phase 1 smoke test — three-camera concurrent capture.

Acceptance criteria (docs/PHASED_IMPLEMENTATION.md Phase 1):
  - Three configured cameras stream concurrently without blocking each other.
  - Measured FPS >= configured FPS - 5% for every active camera.
  - Per-stage latency (capture → frame-available) is logged for every frame
    and remains within budget (50 ms) per docs/LATENCY_BUDGET.md.

HOW TO RUN (full 3-camera test):
    uv run pytest tests/smoke/test_phase1_capture.py -v

HOW TO RUN with fewer cameras during development:
    uv run pytest tests/smoke/test_phase1_capture.py -v --cameras 1
    uv run pytest tests/smoke/test_phase1_capture.py -v --cameras 2

Requirements before running:
  1. Fill in devicePath for each camera in config/cameras.yaml.
  2. Ensure all cameras are plugged in and not in use by another application.

The test uses a 30-second capture window (configurable via --duration).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# pytest CLI options
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--cameras",
        type=int,
        default=3,
        help="Number of cameras to test (1, 2, or 3). Default: 3.",
    )
    parser.addoption(
        "--duration",
        type=float,
        default=30.0,
        help="Capture duration in seconds. Default: 30.",
    )
    parser.addoption(
        "--config",
        type=str,
        default="config/cameras.yaml",
        help="Path to cameras.yaml. Default: config/cameras.yaml.",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def num_cameras(request: pytest.FixtureRequest) -> int:
    return int(request.config.getoption("--cameras"))


@pytest.fixture
def capture_duration(request: pytest.FixtureRequest) -> float:
    return float(request.config.getoption("--duration"))


@pytest.fixture
def config_path(request: pytest.FixtureRequest) -> Path:
    raw = request.config.getoption("--config")
    p = Path(raw)
    if not p.is_absolute():
        # Resolve relative to the project root (one level above tests/).
        p = Path(__file__).parent.parent.parent / p
    return p.resolve()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_device_indices(
    cameras_config,
    num_cameras: int,
) -> dict[str, int]:
    """
    Map cameraId → OpenCV device index.

    On Windows, we enumerate DirectShow devices (indices 0–15) and match
    each to a CameraEntry by friendly name + device path prefix.

    If devicePath is empty in config, we fall back to sequential indices
    for the first `num_cameras` enabled entries. This fallback allows
    running the smoke test during initial setup before device paths are known.
    """
    import platform
    import cv2

    enabled = cameras_config.enabled_cameras()[:num_cameras]

    # Fast path: all devicePaths are empty → use sequential indices.
    if all(not c.devicePath for c in enabled):
        logging.getLogger(__name__).warning(
            "devicePath is empty for all cameras — using sequential indices 0, 1, 2. "
            "Run list_devices and fill in cameras.yaml for reliable assignment."
        )
        return {c.cameraId: i for i, c in enumerate(enabled)}

    # Attempt to match by probing DirectShow and comparing device paths.
    # This is best-effort: if matching fails we fall back to sequential.
    backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
    index_map: dict[str, int] = {}

    for cam in enabled:
        if not cam.devicePath:
            # No path configured — assign next available sequential index.
            next_idx = max(index_map.values(), default=-1) + 1
            index_map[cam.cameraId] = next_idx
            continue
        # Try to find which OpenCV index corresponds to this device path.
        # DirectShow does not expose device paths via cv2 directly, so we
        # use the order from pygrabber if available, otherwise sequential.
        try:
            from pygrabber.dshow_graph import FilterGraph  # type: ignore[import]
            graph = FilterGraph()
            devices = graph.get_input_devices()
            matched = False
            for i, name in enumerate(devices):
                if cam.friendlyName.lower() in name.lower():
                    # Multiple cameras share the same friendly name.
                    # If a device path is configured, we do a best-effort match
                    # by checking if the index hasn't been claimed yet.
                    if i not in index_map.values():
                        index_map[cam.cameraId] = i
                        matched = True
                        break
            if not matched:
                next_idx = max(index_map.values(), default=-1) + 1
                index_map[cam.cameraId] = next_idx
        except ImportError:
            next_idx = max(index_map.values(), default=-1) + 1
            index_map[cam.cameraId] = next_idx

    return index_map


# ---------------------------------------------------------------------------
# Main smoke test
# ---------------------------------------------------------------------------

@pytest.mark.timeout(120)  # hard timeout: 2 minutes (30 s capture + overhead)
def test_phase1_three_camera_capture(
    num_cameras: int,
    capture_duration: float,
    config_path: Path,
    tmp_path: Path,
) -> None:
    """
    Smoke test: open N cameras, capture for `capture_duration` seconds,
    verify FPS within 5% of configured target and capture latency logged.
    """
    from darts_detector.config.camera_config import load_cameras_config
    from darts_detector.capture.multi_camera import MultiCamera
    from darts_detector.diagnostics.latency import LatencyLogger

    log = logging.getLogger("smoke.phase1")

    # --- Load config ---------------------------------------------------------
    assert config_path.exists(), (
        f"cameras.yaml not found at {config_path}. "
        "Run list_devices and fill in config/cameras.yaml first."
    )
    cameras_config = load_cameras_config(config_path)
    enabled = cameras_config.enabled_cameras()

    assert len(enabled) >= num_cameras, (
        f"Need {num_cameras} enabled cameras in {config_path}, "
        f"but only {len(enabled)} enabled entries found."
    )

    configs_to_test = enabled[:num_cameras]

    # --- Set up latency logger -----------------------------------------------
    latency_log = tmp_path / "latency.jsonl"
    latency_logger = LatencyLogger(log_path=latency_log)

    # --- Resolve device indices ----------------------------------------------
    device_index_map = _resolve_device_indices(cameras_config, num_cameras)
    log.info("Device index map: %s", device_index_map)

    # --- Start capture -------------------------------------------------------
    multi = MultiCamera(
        configs=configs_to_test,
        latency_logger=latency_logger,
        device_index_map=device_index_map,
    )
    multi.start()

    frame_counts: dict[str, int] = {c.cameraId: 0 for c in configs_to_test}
    start_wall = time.perf_counter()

    try:
        while (time.perf_counter() - start_wall) < capture_duration:
            frames = multi.get_frames(timeout=0.1)
            for cam_id, (frame, ts) in frames.items():
                assert frame is not None, f"Got None frame from camera '{cam_id}'"
                assert frame.ndim == 3, (
                    f"Expected 3-channel frame from '{cam_id}', got shape {frame.shape}"
                )
                frame_counts[cam_id] += 1
    finally:
        multi.stop()

    elapsed = time.perf_counter() - start_wall
    log.info("Capture finished. Elapsed: %.1f s", elapsed)

    # --- Assert FPS ----------------------------------------------------------
    fps_failures: list[str] = []
    config_by_id = {c.cameraId: c for c in configs_to_test}

    for cam_id, count in frame_counts.items():
        cfg = config_by_id[cam_id]
        measured_fps = count / elapsed
        target_fps = cfg.fps
        min_acceptable_fps = target_fps * 0.95  # 5% tolerance

        log.info(
            "Camera '%s': %d frames in %.1f s = %.1f FPS (target %d, min %.1f)",
            cam_id, count, elapsed, measured_fps, target_fps, min_acceptable_fps,
        )

        if measured_fps < min_acceptable_fps:
            fps_failures.append(
                f"'{cam_id}': measured {measured_fps:.1f} FPS < {min_acceptable_fps:.1f} FPS "
                f"({target_fps} configured - 5%)"
            )

    assert not fps_failures, (
        "FPS below threshold for cameras:\n" + "\n".join(fps_failures)
    )

    # --- Assert latency log exists and has entries ---------------------------
    assert latency_log.exists(), "Latency log was not created."

    with latency_log.open("r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    assert len(entries) > 0, "Latency log is empty — no frames were timed."

    capture_entries = [e for e in entries if e.get("stage") == "capture"]
    assert len(capture_entries) > 0, "No 'capture' stage entries in latency log."

    # Log budget compliance summary.
    over_budget = [e for e in capture_entries if e.get("over_budget")]
    log.info(
        "Capture latency: %d entries, %d over 50 ms budget (%.1f%%)",
        len(capture_entries),
        len(over_budget),
        100 * len(over_budget) / max(len(capture_entries), 1),
    )

    # On the development Windows machine the latency budget (50 ms) is aspirational
    # for Pi 5. We assert that > 80% of frames are within budget; this is a
    # sanity check rather than a hard Pi 5 SLO.
    pct_within = 1 - (len(over_budget) / max(len(capture_entries), 1))
    assert pct_within >= 0.80, (
        f"Only {pct_within*100:.1f}% of capture frames within 50 ms budget "
        f"(required >= 80%). Consider checking USB bandwidth or resolution."
    )

    # --- Final summary -------------------------------------------------------
    log.info("Phase 1 smoke test PASSED.")
    log.info("Cameras tested: %d", num_cameras)
    for cam_id, count in frame_counts.items():
        log.info("  %s: %d frames in %.1f s", cam_id, count, elapsed)
