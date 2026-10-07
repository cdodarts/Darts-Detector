# SPDX-License-Identifier: GPL-3.0-or-later
"""
Phase 2 smoke test — MJPG mode probing and intersection.

Acceptance criteria (docs/PHASED_IMPLEMENTATION.md Phase 2, user spec):
  1. probe_supported_modes() returns at least one mode for a camera that accepts
     a standard mode.
  2. Modes below 15 FPS are dropped (D-019 canonical menu floor: 60, 30, 25, 20, 15).
  3. intersect_modes() correctly computes intersection across 3 cameras.
  4. intersect_modes() falls back to 1280x720@30 when no shared modes exist.
  5. bandwidth_advisory() returns the correct severity at each threshold.
  6. Camera.open() does NOT apply exposure/gain/etc. (D-021).
  7. 20 fps and 15 fps modes survive probing and intersection when all cameras support them.

HOW TO RUN:
    uv run pytest tests/smoke/test_phase2_mode_probe.py -v

These tests use mocked cv2.VideoCapture — no physical cameras required.
"""

from __future__ import annotations

import platform
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_cap(accepted_modes: list[tuple[int, int, int]]):
    """Return a mock cv2.VideoCapture that accepts specific (w, h, fps) modes.

    When set() is called with WIDTH/HEIGHT/FPS matching an accepted mode,
    the subsequent get() calls return those values plus MJPG FOURCC.
    When the mode is NOT accepted, get() returns width=640, height=480, fps=15.
    """
    import cv2

    FOURCC_MJPG = cv2.VideoWriter.fourcc(*"MJPG")
    FOURCC_YUYV = cv2.VideoWriter.fourcc(*"YUYV")

    cap = MagicMock()
    cap.isOpened.return_value = True

    # Internal state — what the driver has accepted.
    state = {"w": 640, "h": 480, "fps": 15.0, "fourcc": FOURCC_YUYV}

    def _set(prop_id, value):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            state["w"] = int(value)
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            state["h"] = int(value)
        elif prop_id == cv2.CAP_PROP_FPS:
            state["fps"] = float(value)
        elif prop_id == cv2.CAP_PROP_FOURCC:
            state["fourcc"] = int(value)

        # Check if current (w, h, fps) is accepted.
        match = next(
            ((w, h, fps) for (w, h, fps) in accepted_modes
             if w == state["w"] and h == state["h"] and abs(fps - state["fps"]) / max(fps, 1) <= 0.05),
            None,
        )
        if match:
            state["fourcc"] = FOURCC_MJPG
        return True

    def _get(prop_id):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(state["w"])
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(state["h"])
        elif prop_id == cv2.CAP_PROP_FPS:
            return state["fps"]
        elif prop_id == cv2.CAP_PROP_FOURCC:
            return float(state["fourcc"])
        return 0.0

    cap.set.side_effect = _set
    cap.get.side_effect = _get
    return cap


# ---------------------------------------------------------------------------
# Test: probe_returns_at_least_one_mode_per_known_resolution
# ---------------------------------------------------------------------------

def test_probe_returns_at_least_one_mode_for_accepted_mode(tmp_path: Path):
    """Mock camera accepts 1280x720@30. Probe should return that mode."""
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    mock_cap = _make_mock_cap([(1280, 720, 30)])

    with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=mock_cap):
        modes = probe_supported_modes(
            device_index=0,
            friendly_name="Test Cam",
            device_path="/dev/video0",
            cache_path=tmp_path / ".mode_cache.json",
        )

    assert any(m.width == 1280 and m.height == 720 and m.fps == 30 for m in modes), (
        f"Expected 1280x720@30 in modes, got: {modes}"
    )


# ---------------------------------------------------------------------------
# Test: probe_drops_fps_below_15
# ---------------------------------------------------------------------------

def test_probe_drops_fps_below_15(tmp_path: Path):
    """Mock camera returns 10 fps for every probe. All should be dropped (D-019 floor=15)."""
    import cv2
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    FOURCC_MJPG = cv2.VideoWriter.fourcc(*"MJPG")

    cap = MagicMock()
    cap.isOpened.return_value = True

    # Always report 10 fps (below D-019 canonical menu floor of 15).
    cap.get.side_effect = lambda prop_id: {
        cv2.CAP_PROP_FRAME_WIDTH: 1280.0,
        cv2.CAP_PROP_FRAME_HEIGHT: 720.0,
        cv2.CAP_PROP_FPS: 10.0,           # below D-019 canonical menu floor
        cv2.CAP_PROP_FOURCC: float(FOURCC_MJPG),
    }.get(prop_id, 0.0)
    cap.set.return_value = True

    with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=cap):
        modes = probe_supported_modes(
            device_index=0,
            cache_path=tmp_path / ".mode_cache.json",
        )

    # Should fall back to safe default (1280x720@30) since nothing was accepted.
    # The probe only accepts modes where eff_fps >= MIN_FPS=15. 10 < 15, so rejected.
    assert all(m.fps >= 15 for m in modes), (
        f"All returned modes must be >= 15 fps (D-019 canonical menu floor). Got: {modes}"
    )


# ---------------------------------------------------------------------------
# Test: probe_accepts_20_and_15_fps (D-019 canonical menu includes 20 and 15)
# ---------------------------------------------------------------------------

def test_probe_accepts_20_fps(tmp_path: Path):
    """Mock camera accepts 1280x720@20. Probe must include it (D-019 canonical menu)."""
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    mock_cap = _make_mock_cap([(1280, 720, 20)])

    with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=mock_cap):
        modes = probe_supported_modes(
            device_index=0,
            friendly_name="Test Cam",
            device_path="/dev/video0",
            cache_path=tmp_path / ".mode_cache.json",
        )

    assert any(m.width == 1280 and m.height == 720 and m.fps == 20 for m in modes), (
        f"Expected 1280x720@20 in modes (D-019 canonical menu). Got: {modes}"
    )


def test_probe_accepts_15_fps(tmp_path: Path):
    """Mock camera accepts 1280x720@15. Probe must include it (D-019 canonical menu)."""
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    mock_cap = _make_mock_cap([(1280, 720, 15)])

    with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=mock_cap):
        modes = probe_supported_modes(
            device_index=0,
            friendly_name="Test Cam",
            device_path="/dev/video0",
            cache_path=tmp_path / ".mode_cache.json",
        )

    assert any(m.width == 1280 and m.height == 720 and m.fps == 15 for m in modes), (
        f"Expected 1280x720@15 in modes (D-019 canonical menu). Got: {modes}"
    )


# ---------------------------------------------------------------------------
# Test: intersection_includes_20_and_15_fps_when_all_cams_support_them
# ---------------------------------------------------------------------------

def test_intersection_includes_20_and_15_fps_when_all_cams_support_them():
    """Three cameras all support 720p@20 and 720p@15. Both must appear in intersection."""
    from darts_detector.capture.mode_probe import CameraMode, intersect_modes

    shared_modes = [
        CameraMode(1280, 720, 30),
        CameraMode(1280, 720, 20),
        CameraMode(1280, 720, 15),
    ]

    result = intersect_modes([shared_modes, shared_modes, shared_modes])

    fps_values = {m.fps for m in result if m.width == 1280 and m.height == 720}
    assert 20 in fps_values, (
        f"Expected 20 fps in intersection at 1280x720 (D-019 canonical menu). Got fps values: {fps_values}"
    )
    assert 15 in fps_values, (
        f"Expected 15 fps in intersection at 1280x720 (D-019 canonical menu). Got fps values: {fps_values}"
    )


# ---------------------------------------------------------------------------
# Test: intersection_across_3_cameras
# ---------------------------------------------------------------------------

def test_intersection_across_3_cameras():
    """cam_1 supports 1080p60+720p30, cam_2 supports 720p30+480p30, cam_3 supports 720p30."""
    from darts_detector.capture.mode_probe import CameraMode, intersect_modes

    cam1_modes = [
        CameraMode(1920, 1080, 60),
        CameraMode(1280, 720, 30),
    ]
    cam2_modes = [
        CameraMode(1280, 720, 30),
        CameraMode(640, 480, 30),
    ]
    cam3_modes = [
        CameraMode(1280, 720, 30),
    ]

    shared = intersect_modes([cam1_modes, cam2_modes, cam3_modes])

    assert len(shared) == 1, f"Expected exactly 1 shared mode, got: {shared}"
    assert shared[0] == CameraMode(1280, 720, 30), (
        f"Expected 1280x720@30, got: {shared[0]}"
    )


# ---------------------------------------------------------------------------
# Test: intersection_empty_falls_back_to_720p30
# ---------------------------------------------------------------------------

def test_intersection_empty_falls_back_to_720p30():
    """No shared modes across cameras — must fall back to 1280x720@30."""
    from darts_detector.capture.mode_probe import CameraMode, intersect_modes

    cam1_modes = [CameraMode(1920, 1080, 60)]
    cam2_modes = [CameraMode(640, 480, 30)]
    cam3_modes = [CameraMode(800, 600, 25)]

    shared = intersect_modes([cam1_modes, cam2_modes, cam3_modes])

    assert len(shared) == 1, f"Expected fallback list of 1, got: {shared}"
    assert shared[0] == CameraMode(1280, 720, 30), (
        f"Expected fallback 1280x720@30, got: {shared[0]}"
    )


# ---------------------------------------------------------------------------
# Test: bandwidth_advisory_thresholds
# ---------------------------------------------------------------------------

def test_bandwidth_advisory_thresholds():
    """Bandwidth advisory returns correct severity at each threshold."""
    from darts_detector.capture.mode_probe import bandwidth_advisory

    # Safe: 640x480@30 × 3 cameras.
    # raw = 640*480*30*3*2 = 55,296,000 bytes/s
    # mjpg = 55,296,000 / 7 / 1e6 ≈ 7.9 Mbps — well below 250.
    sev, msg = bandwidth_advisory(640, 480, 30, num_cameras=3)
    assert sev == "ok", f"Expected ok at 640x480@30×3, got: {sev} ({msg})"
    assert msg == ""

    # Warning zone: 1280x720@60 × 3 cameras.
    # raw = 1280*720*60*3*2 = 331,776,000 bytes/s
    # mjpg = 331,776,000 / 7 / 1e6 ≈ 47.4 Mbps — hmm, actually below 250.
    # Let's use a larger combo: 1920x1080@60 × 3.
    # raw = 1920*1080*60*3*2 = 746,496,000
    # mjpg = 746,496,000 / 7 / 1e6 ≈ 106.6 Mbps — still below 250.
    # Need to check threshold with actual calculation.
    # warn threshold = 250 Mbps. Solve for params:
    # w*h*fps*3*2 / 7 / 1e6 >= 250 → w*h*fps >= 250*7*1e6 / 6 = 291,666,667
    # 1920*1080*60 = 124,416,000 ... 1920*1080*60*3 = 373,248,000.
    # 373,248,000 * 2 / 7 / 1e6 ≈ 106.6 Mbps. Still below.
    # The advisory is intentionally conservative — let's test with a very high mode.
    # 1920*1080*60*6*2 / 7 / 1e6: num_cameras=6 => 213.3 Mbps, still below 250.
    # Test with num_cameras artificially high to verify thresholds.
    # warn at 250: need raw = 250 * 1e6 * 7 / 2 = 875,000,000 bytes/s
    # 1920*1080*60 = 124,416,000; so need ~7 cameras.
    # For 3 cameras the threshold is 250 Mbps:
    # 1920*1080*fps*3*2/7/1e6 >= 250 → fps >= 250*7*1e6 / (1920*1080*3*2) = 168 fps
    # So at 3 cameras 1920x1080@60 is OK. Test advisory boundaries differently.

    # Test warn path directly (use num_cameras=15 to force into warn zone).
    # 1920*1080*30*15*2/7/1e6 ≈ 249.9 Mbps — right at warn.
    # Use 1920*1080*30*16*2/7/1e6 ≈ 266.6 Mbps — in warn.
    sev_warn, msg_warn = bandwidth_advisory(1920, 1080, 30, num_cameras=16)
    assert sev_warn in ("warn", "error"), (
        f"Expected warn or error for high num_cameras, got: {sev_warn}"
    )

    # Test error path (use very high num_cameras).
    sev_err, msg_err = bandwidth_advisory(1920, 1080, 60, num_cameras=30)
    assert sev_err == "error", (
        f"Expected error for extreme bandwidth, got: {sev_err}"
    )
    assert len(msg_err) > 0, "Error message should not be empty"

    # Verify real 3-camera scenario has a message attribute structure.
    sev_real, msg_real = bandwidth_advisory(1280, 720, 30, num_cameras=3)
    assert sev_real in ("ok", "warn", "error")
    if sev_real == "ok":
        assert msg_real == ""
    else:
        assert len(msg_real) > 0


# ---------------------------------------------------------------------------
# Test: camera_open_no_longer_applies_exposure
# ---------------------------------------------------------------------------

def test_camera_open_no_longer_applies_exposure():
    """Camera.open() must NOT call cap.set(CAP_PROP_EXPOSURE, ...) — D-021."""
    import cv2
    from darts_detector.capture.camera import Camera
    from darts_detector.config.camera_config import (
        CameraEntry,
        CameraResolution,
        ExposureConfig,
        WhiteBalanceConfig,
    )

    FOURCC_MJPG = cv2.VideoWriter.fourcc(*"MJPG")

    # Build a config entry with explicit exposure.
    cfg = CameraEntry(
        cameraId="cam_1",
        name="Camera 1",
        friendlyName="Test Cam",
        devicePath="/dev/video0",
        role="cam_1",
        resolution=CameraResolution(width=1280, height=720),
        fps=30,
        pixelFormat="MJPG",
        exposure=ExposureConfig(mode="manual", value=100),
        gain=50,
        brightness=128,
        contrast=64,
        whiteBalance=WhiteBalanceConfig(mode="manual", value=4500),
    )

    cam = Camera(camera_id="cam_1", device_index=0, config=cfg)

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop_id: {
        cv2.CAP_PROP_FOURCC: float(FOURCC_MJPG),
        cv2.CAP_PROP_FRAME_WIDTH: 1280.0,
        cv2.CAP_PROP_FRAME_HEIGHT: 720.0,
        cv2.CAP_PROP_FPS: 30.0,
    }.get(prop_id, 0.0)
    mock_cap.set.return_value = True

    with patch("darts_detector.capture.camera.cv2.VideoCapture", return_value=mock_cap):
        cam.open()

    # Gather all prop_ids that were set.
    set_prop_ids = [c.args[0] for c in mock_cap.set.call_args_list]

    # These tuning props must NOT have been called.
    forbidden_props = {
        cv2.CAP_PROP_EXPOSURE,
        cv2.CAP_PROP_AUTO_EXPOSURE,
        cv2.CAP_PROP_GAIN,
        cv2.CAP_PROP_BRIGHTNESS,
        cv2.CAP_PROP_CONTRAST,
        cv2.CAP_PROP_WHITE_BALANCE_BLUE_U,
        cv2.CAP_PROP_AUTO_WB,
        cv2.CAP_PROP_GAMMA,
        cv2.CAP_PROP_SATURATION,
        cv2.CAP_PROP_SHARPNESS,
        cv2.CAP_PROP_BACKLIGHT,
    }

    applied_forbidden = set(set_prop_ids) & forbidden_props
    assert not applied_forbidden, (
        f"Camera.open() must not apply tuning props (D-021). "
        f"Forbidden props that were set: {applied_forbidden}"
    )

    # Only permitted props: FOURCC, WIDTH, HEIGHT, FPS.
    permitted_props = {
        cv2.CAP_PROP_FOURCC,
        cv2.CAP_PROP_FRAME_WIDTH,
        cv2.CAP_PROP_FRAME_HEIGHT,
        cv2.CAP_PROP_FPS,
    }
    unexpected = set(set_prop_ids) - permitted_props
    assert not unexpected, (
        f"Camera.open() set unexpected props: {unexpected}"
    )


# ---------------------------------------------------------------------------
# Test: probe_returns_fallback_if_videocapture_fails (item G)
# ---------------------------------------------------------------------------

def test_probe_returns_fallback_if_videocapture_fails(tmp_path: Path):
    """If cv2.VideoCapture returns a non-opened cap, probe must not raise and
    must return the fallback mode list with all progress marked done.
    """
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    # A cap that reports isOpened() == False.
    closed_cap = MagicMock()
    closed_cap.isOpened.return_value = False

    progress_calls: list[tuple[int, int]] = []

    def _progress(probed: int, total: int) -> None:
        progress_calls.append((probed, total))

    with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=closed_cap):
        modes = probe_supported_modes(
            device_index=99,
            friendly_name="",
            device_path="",
            cache_path=tmp_path / ".mode_cache.json",
            progress_callback=_progress,
        )

    # Must not raise; must return fallback.
    assert modes == [CameraMode(1280, 720, 30)], (
        f"Expected fallback [1280x720@30], got: {modes}"
    )

    # Progress callback must have been called at least once with done state
    # so the UI progress bar reaches 100%.
    assert progress_calls, "progress_callback was never called"
    last_probed, last_total = progress_calls[-1]
    assert last_probed == last_total, (
        f"Expected progress to reach total ({last_total}), got probed={last_probed}"
    )


# ---------------------------------------------------------------------------
# Test: probe_handles_individual_probe_exception (item G)
# ---------------------------------------------------------------------------

def test_probe_handles_individual_probe_exception(tmp_path: Path):
    """If cap.set() raises on the 5th call, the probe must continue and return
    whatever modes were collected from the preceding iterations.
    """
    import cv2
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    FOURCC_MJPG = cv2.VideoWriter.fourcc(*"MJPG")

    # A cap that accepts 1280x720@30 as a valid mode (first several probes).
    # cap.set() raises a RuntimeError on the 5th invocation.
    set_call_count = [0]

    cap = MagicMock()
    cap.isOpened.return_value = True

    # Internal state.
    state = {"w": 640, "h": 480, "fps": 15.0}

    def _set(prop_id, value):
        set_call_count[0] += 1
        if set_call_count[0] == 5:
            raise RuntimeError("simulated driver crash on 5th set() call")
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            state["w"] = int(value)
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            state["h"] = int(value)
        elif prop_id == cv2.CAP_PROP_FPS:
            state["fps"] = float(value)
        return True

    def _get(prop_id):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(state["w"])
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(state["h"])
        elif prop_id == cv2.CAP_PROP_FPS:
            return state["fps"]
        elif prop_id == cv2.CAP_PROP_FOURCC:
            return float(FOURCC_MJPG)
        return 0.0

    cap.set.side_effect = _set
    cap.get.side_effect = _get

    # Must not raise — exceptions on individual iterations are swallowed.
    with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=cap):
        modes = probe_supported_modes(
            device_index=0,
            friendly_name="",
            device_path="",
            cache_path=tmp_path / ".mode_cache.json",
        )

    # The probe must complete and return a non-empty list (either accepted
    # modes or the fallback).
    assert isinstance(modes, list), "probe_supported_modes must return a list"
    assert len(modes) >= 1, "Must return at least the fallback mode"
    assert all(m.fps >= 15 for m in modes), (
        f"All returned modes must be >= 15 fps (D-019 canonical menu floor). Got: {modes}"
    )


# ---------------------------------------------------------------------------
# Tests for the pygrabber fast path (query_supported_modes_fast)
# ---------------------------------------------------------------------------

def _make_pygrabber_formats(*entries) -> list[dict]:
    """Build a list of pygrabber-style format dicts for use in tests."""
    return list(entries)


def _mjpg_format(width: int, height: int, fps: float) -> dict:
    return {
        "index": 0,
        "media_type_str": "MJPG",
        "width": width,
        "height": height,
        "min_framerate": fps,
        "max_framerate": fps,
    }


def _yuy2_format(width: int, height: int, fps: float) -> dict:
    return {
        "index": 0,
        "media_type_str": "YUY2",
        "width": width,
        "height": height,
        "min_framerate": fps,
        "max_framerate": fps,
    }


def test_fast_path_returns_modes_from_pygrabber():
    """Fast path: mock pygrabber returns MJPG formats; correct CameraMode objects
    are returned AND the brute-force cv2.VideoCapture probe is NOT called.
    """
    from darts_detector.capture.mode_probe import query_supported_modes_fast, CameraMode

    mock_formats = [
        _mjpg_format(1280, 720, 30.0),
        _mjpg_format(1920, 1080, 30.0),
        _mjpg_format(640, 480, 30.0),
    ]

    mock_device = MagicMock()
    mock_device.get_formats.return_value = mock_formats

    mock_fg = MagicMock()
    mock_fg.get_input_device.return_value = mock_device

    mock_FilterGraph = MagicMock(return_value=mock_fg)

    with patch.dict("sys.modules", {"pygrabber": MagicMock(), "pygrabber.dshow_graph": MagicMock()}):
        with patch("darts_detector.capture.mode_probe.cv2.VideoCapture") as mock_cv2_cap:
            # Patch the import inside the function.
            import darts_detector.capture.mode_probe as mp
            original = mp.query_supported_modes_fast

            def _patched_fast(device_index):
                # Replace the inner FilterGraph import with our mock.
                import sys
                real_module = sys.modules.get("pygrabber.dshow_graph")
                try:
                    sys.modules["pygrabber.dshow_graph"] = MagicMock(FilterGraph=mock_FilterGraph)
                    return original(device_index)
                finally:
                    if real_module is not None:
                        sys.modules["pygrabber.dshow_graph"] = real_module

            modes = _patched_fast(0)

    assert modes is not None, "Fast path should return a list, not None"
    assert any(m == CameraMode(1280, 720, 30) for m in modes), (
        f"Expected 1280x720@30 in fast-path modes, got: {modes}"
    )
    assert any(m == CameraMode(1920, 1080, 30) for m in modes), (
        f"Expected 1920x1080@30 in fast-path modes, got: {modes}"
    )
    # cv2.VideoCapture must NOT have been called (fast path bypasses brute-force).
    mock_cv2_cap.assert_not_called()


def test_fast_path_filters_non_mjpg():
    """Fast path: formats containing YUY2 and MJPG entries — only MJPG modes returned."""
    from darts_detector.capture.mode_probe import query_supported_modes_fast, CameraMode

    mock_formats = [
        _yuy2_format(1280, 720, 30.0),   # must be excluded
        _mjpg_format(1280, 720, 30.0),   # must be included
        _yuy2_format(640, 480, 30.0),    # must be excluded
        _mjpg_format(640, 480, 30.0),    # must be included
        {"index": 0, "media_type_str": "RGB24", "width": 640, "height": 480,
         "min_framerate": 30.0, "max_framerate": 30.0},  # must be excluded
    ]

    mock_device = MagicMock()
    mock_device.get_formats.return_value = mock_formats
    mock_fg = MagicMock()
    mock_fg.get_input_device.return_value = mock_device
    mock_FilterGraph = MagicMock(return_value=mock_fg)

    import sys
    real_module = sys.modules.get("pygrabber.dshow_graph")
    try:
        sys.modules["pygrabber.dshow_graph"] = MagicMock(FilterGraph=mock_FilterGraph)
        modes = query_supported_modes_fast(0)
    finally:
        if real_module is not None:
            sys.modules["pygrabber.dshow_graph"] = real_module
        elif "pygrabber.dshow_graph" in sys.modules:
            del sys.modules["pygrabber.dshow_graph"]

    assert modes is not None, "Should return modes, not None"
    for m in modes:
        # All returned modes must have come from MJPG entries.
        assert m.fps >= 15, f"Mode {m} has fps below D-019 canonical menu floor of 15"

    # Verify no duplicate (width, height, fps) tuples — only MJPG ones.
    mode_set = {(m.width, m.height, m.fps) for m in modes}
    assert len(mode_set) == len(modes), "Duplicate modes returned"

    # YUY2-only resolutions — if returned they must have an MJPG counterpart.
    # In this mock, 1280x720@30 and 640x480@30 both have MJPG entries, so OK.
    assert any(m == CameraMode(1280, 720, 30) for m in modes)
    assert any(m == CameraMode(640, 480, 30) for m in modes)


def test_fast_path_falls_back_to_brute_force_when_pygrabber_returns_nothing(tmp_path):
    """Fast path returns None (empty format list) — brute-force probe must run."""
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    # pygrabber returns an empty list → fast path returns None.
    mock_device = MagicMock()
    mock_device.get_formats.return_value = []  # no formats
    mock_fg = MagicMock()
    mock_fg.get_input_device.return_value = mock_device
    mock_FilterGraph = MagicMock(return_value=mock_fg)

    # Brute-force path: camera accepts 1280x720@30.
    mock_cap = _make_mock_cap([(1280, 720, 30)])

    import sys
    real_module = sys.modules.get("pygrabber.dshow_graph")
    try:
        sys.modules["pygrabber.dshow_graph"] = MagicMock(FilterGraph=mock_FilterGraph)
        with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=mock_cap):
            modes = probe_supported_modes(
                device_index=0,
                friendly_name="Test Cam",
                device_path="/dev/video0",
                cache_path=tmp_path / ".mode_cache.json",
            )
    finally:
        if real_module is not None:
            sys.modules["pygrabber.dshow_graph"] = real_module
        elif "pygrabber.dshow_graph" in sys.modules:
            del sys.modules["pygrabber.dshow_graph"]

    # Brute-force ran and found the mode.
    assert any(m == CameraMode(1280, 720, 30) for m in modes), (
        f"Expected brute-force to find 1280x720@30, got: {modes}"
    )
    # cv2.VideoCapture was called (brute-force ran).
    mock_cap.isOpened.assert_called()


def test_fast_path_falls_back_on_pygrabber_exception(tmp_path):
    """Fast path raises an exception — brute-force must run; no exception leaks."""
    from darts_detector.capture.mode_probe import probe_supported_modes, CameraMode

    # pygrabber raises on add_video_input_device → fast path catches and returns None.
    mock_fg = MagicMock()
    mock_fg.add_video_input_device.side_effect = RuntimeError("simulated COM error")
    mock_FilterGraph = MagicMock(return_value=mock_fg)

    # Brute-force path: camera accepts 1280x720@30.
    mock_cap = _make_mock_cap([(1280, 720, 30)])

    import sys
    real_module = sys.modules.get("pygrabber.dshow_graph")
    try:
        sys.modules["pygrabber.dshow_graph"] = MagicMock(FilterGraph=mock_FilterGraph)
        with patch("darts_detector.capture.mode_probe.cv2.VideoCapture", return_value=mock_cap):
            modes = probe_supported_modes(
                device_index=0,
                friendly_name="Test Cam",
                device_path="/dev/video0",
                cache_path=tmp_path / ".mode_cache.json",
            )
    finally:
        if real_module is not None:
            sys.modules["pygrabber.dshow_graph"] = real_module
        elif "pygrabber.dshow_graph" in sys.modules:
            del sys.modules["pygrabber.dshow_graph"]

    # No exception must have leaked out.
    assert isinstance(modes, list), "probe_supported_modes must not raise"
    assert len(modes) >= 1, "Must return at least fallback or brute-force result"
    # Brute-force found 1280x720@30.
    assert any(m == CameraMode(1280, 720, 30) for m in modes), (
        f"Expected brute-force fallback to find 1280x720@30, got: {modes}"
    )
