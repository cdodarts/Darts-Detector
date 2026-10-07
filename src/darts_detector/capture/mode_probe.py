# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.capture.mode_probe — MJPG mode detection for USB cameras.

@internal

Mode detection uses a two-tier query strategy:

  1. Fast path (primary): reads the camera's native mode list directly from
     DirectShow via pygrabber's IAMStreamConfig wrapper.  Expected to complete
     in < 200 ms per camera on Windows.  Returns None when pygrabber is
     unavailable or reports no MJPG modes — the caller then falls through to
     the brute-force path.

  2. Brute-force path (fallback): tries 20 (resolution, fps) combinations via
     cv2.VideoCapture.set() + readback.  Takes ~30-90 s per camera on slow
     DirectShow drivers.  Retained for drivers pygrabber cannot read (Linux,
     non-DirectShow backends, future hardware).

Results are cached to config/.mode_cache.json keyed by friendly name +
device path so re-running the picker on the same hardware is instant.

Only modes at >= 15 FPS are returned (D-019 canonical menu floor: 60, 30, 25, 20, 15).

See docs/PHASED_IMPLEMENTATION.md Phase 2 for scope constraints.
"""

from __future__ import annotations

import json
import logging
import platform
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical probe set — 5 resolutions × 4 FPS values = 20 probes per camera.
# ---------------------------------------------------------------------------

_PROBE_RESOLUTIONS: list[tuple[int, int]] = [
    (1920, 1080),
    (1600, 900),
    (1280, 720),
    (800, 600),
    (640, 480),
]

_PROBE_FPS_VALUES: list[int] = [60, 50, 30, 25, 20, 15]

# Minimum FPS threshold — D-019 canonical menu floor.
# The canonical menu is: 60, 30, 25, 20, 15. We also probe 50 for cameras
# that report it (harmless; filtered out by intersection if not all cams share it).
# Modes below 15 fps are filtered out before intersection.
_MIN_FPS: int = 15

# Tolerance for FPS readback match (±5%).
_FPS_TOLERANCE: float = 0.05

# Approximate per-probe time (seconds) — used for progress estimation.
PROBE_TIME_PER_MODE_S: float = 1.5


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CameraMode:
    """A supported (resolution, fps) mode in MJPG."""

    width: int
    height: int
    fps: int  # integer; rounded if driver returns 29.97 etc.

    def __str__(self) -> str:
        return f"{self.width}x{self.height}@{self.fps}fps"

    @property
    def label(self) -> str:
        """Human-readable label for UI dropdowns."""
        return f"{self.width}×{self.height} @ {self.fps} fps"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_key(friendly_name: str, device_path: str) -> str:
    """Stable cache key for a camera identity."""
    return f"{friendly_name}|{device_path}"


def _load_cache(cache_path: Path) -> dict[str, list[dict]]:
    if not cache_path.exists():
        return {}
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        logger.warning("mode_probe: cache at %s is corrupt; ignoring.", cache_path)
    return {}


def _save_cache(cache_path: Path, cache: dict[str, list[dict]]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except OSError as exc:
        logger.warning("mode_probe: could not write cache to %s: %s", cache_path, exc)


# ---------------------------------------------------------------------------
# Fast path via pygrabber (DirectShow IAMStreamConfig)
# ---------------------------------------------------------------------------


def query_supported_modes_fast(device_index: int) -> Optional[list[CameraMode]]:
    """Fast path: read the camera's supported MJPG modes directly via pygrabber.

    Uses DirectShow's IAMStreamConfig::GetStreamCaps (wrapped by pygrabber)
    to enumerate the camera's native format list without opening a capture
    session.  Expected to complete in < 200 ms per camera.

    Returns None if:
    - pygrabber is unavailable (ImportError).
    - The device cannot be queried (any exception during graph construction).
    - No MJPG modes are reported by the driver.

    Caller must fall back to ``probe_supported_modes()``'s brute-force path
    in those cases.

    Format dict fields (pygrabber >= 0.2, DirectShow):
        media_type_str : str   — e.g. "MJPG", "YUY2", "RGB24"
        width          : int
        height         : int
        min_framerate  : float — may equal max_framerate for discrete modes
        max_framerate  : float — may equal min_framerate for discrete modes

    Framerate handling:
        Each format entry describes one discrete mode on the OV2710 / Autodarts
        DIY Cam (min_framerate == max_framerate).  For entries that do express a
        true range (min < max), we expand into the integer fps values from our
        probe set that fall within [min, max].  Point entries (min == max) emit
        the rounded value directly if it is in the probe set and >= 25.
    """
    try:
        from pygrabber.dshow_graph import FilterGraph  # type: ignore[import]
    except ImportError:
        logger.info(
            "mode_probe: pygrabber not available; fast path disabled for device_index=%d.",
            device_index,
        )
        return None

    fg: object = None
    try:
        fg = FilterGraph()
        fg.add_video_input_device(device_index)  # type: ignore[attr-defined]
        raw_formats: list[dict] = fg.get_input_device().get_formats()  # type: ignore[attr-defined]
    except Exception as exc:
        logger.info(
            "mode_probe: pygrabber query failed for device_index=%d: %s",
            device_index, exc,
        )
        return None
    finally:
        # Release the DirectShow graph so we don't hold the device handle.
        if fg is not None:
            try:
                fg.remove_filters()  # type: ignore[attr-defined]
            except Exception:
                pass

    if not raw_formats:
        logger.info(
            "mode_probe: pygrabber returned no formats for device_index=%d.",
            device_index,
        )
        return None

    # Probe-set fps values we care about.
    _probe_fps_set: frozenset[int] = frozenset(_PROBE_FPS_VALUES)

    accepted: list[CameraMode] = []
    for fmt in raw_formats:
        if not isinstance(fmt, dict):
            continue

        # Filter for MJPG media types only (field name varies defensively).
        media_type = (
            fmt.get("media_type_str")
            or fmt.get("media_type")
            or fmt.get("MediaType")
            or ""
        )
        if not isinstance(media_type, str):
            media_type = str(media_type)
        if "MJPG" not in media_type.upper() and "MJPEG" not in media_type.upper():
            continue

        width = fmt.get("width") or fmt.get("Width")
        height = fmt.get("height") or fmt.get("Height")
        if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            continue
        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            continue

        # Framerate: handle both "range" entries and "point" (discrete) entries.
        # pygrabber uses min_framerate / max_framerate.  For discrete modes on
        # the OV2710 these are equal (e.g. both 30.0).
        min_fps_raw = fmt.get("min_framerate") or fmt.get("MinFrameRate") or 0.0
        max_fps_raw = fmt.get("max_framerate") or fmt.get("MaxFrameRate") or 0.0
        try:
            min_fps = float(min_fps_raw)
            max_fps = float(max_fps_raw)
        except (TypeError, ValueError):
            continue

        # Normalise so min <= max.
        lo = min(min_fps, max_fps)
        hi = max(min_fps, max_fps)

        if hi < _MIN_FPS:
            # Entire range below our threshold — skip.
            continue

        # Collect fps candidates from the probe set that fall in [lo, hi].
        if abs(lo - hi) < 0.5:
            # Point (discrete) framerate — use the rounded value directly.
            fps_val = round(hi)
            if fps_val >= _MIN_FPS:
                candidates = {fps_val}
            else:
                candidates = set()
        else:
            # True range — expand to probe-set values within [lo, hi].
            candidates = {
                fps for fps in _probe_fps_set
                if lo - 0.5 <= fps <= hi + 0.5 and fps >= _MIN_FPS
            }

        for fps in candidates:
            mode = CameraMode(width=width, height=height, fps=fps)
            if mode not in accepted:
                accepted.append(mode)

    if not accepted:
        logger.info(
            "mode_probe: pygrabber returned formats for device_index=%d but none were "
            "MJPG with fps >= %d (D-019 canonical menu floor).",
            device_index, _MIN_FPS,
        )
        return None

    logger.info(
        "mode_probe: pygrabber fast path found %d MJPG mode(s) for device_index=%d.",
        len(accepted), device_index,
    )
    return _sort_modes(accepted)


# ---------------------------------------------------------------------------
# Core probe function
# ---------------------------------------------------------------------------


def probe_supported_modes(
    device_index: int,
    *,
    friendly_name: str = "",
    device_path: str = "",
    cache_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[CameraMode]:
    """Return the list of (resolution, fps) MJPG modes the camera accepts.

    Query strategy (two-tier):
      1. Cache hit — return instantly if a previous result exists.
      2. Fast path — pygrabber IAMStreamConfig query (< 200 ms on Windows).
         Returns None when pygrabber is unavailable or reports no MJPG modes.
      3. Brute-force fallback — tries the standard set of (resolution, fps)
         combinations via cv2.VideoCapture.set() + readback.  Takes ~30-90 s
         per camera on DirectShow but works on any platform.

    Brute-force probe details:
        Sets FOURCC=MJPG + width + height + fps + FOURCC (double-set pattern),
        reads back via cap.get(), and includes the mode if the readback matches
        within tolerance (±5% on fps, exact on resolution).

    Standard probe set (brute-force only):
        Resolutions: 1920x1080, 1600x900, 1280x720, 800x600, 640x480
        FPS:         60, 50, 30, 25, 20, 15
        Total:       30 probes per camera

    Modes below 15 fps are dropped (D-019 canonical menu floor).
    Results cached to cache_path keyed by friendly_name + device_path.

    Args:
        device_index:      OpenCV device index.
        friendly_name:     Camera friendly name (for cache key).
        device_path:       USB device path (for cache key).
        cache_path:        Path to the .mode_cache.json file. If None, no
                           caching is performed.
        progress_callback: Called after each probe with (probed_so_far, total).
                           Useful for UI progress reporting.

    Returns:
        Sorted list of CameraMode (by resolution desc, then fps desc).
        Falls back to [CameraMode(1280, 720, 30)] if no modes detected.
    """
    is_windows = platform.system() == "Windows"
    backend = cv2.CAP_DSHOW if is_windows else cv2.CAP_ANY
    fourcc_int = cv2.VideoWriter.fourcc(*"MJPG")

    # Build the full probe list.
    probe_list: list[tuple[int, int, int]] = [
        (w, h, fps)
        for (w, h) in _PROBE_RESOLUTIONS
        for fps in _PROBE_FPS_VALUES
        if fps >= _MIN_FPS
    ]
    total_probes = len(probe_list)

    # --- Cache lookup ---------------------------------------------------------
    if cache_path is not None and friendly_name and device_path:
        key = _cache_key(friendly_name, device_path)
        cache = _load_cache(cache_path)
        if key in cache:
            raw_modes = cache[key]
            modes = [
                CameraMode(width=m["width"], height=m["height"], fps=m["fps"])
                for m in raw_modes
                if m.get("fps", 0) >= _MIN_FPS
            ]
            if modes:
                logger.info(
                    "mode_probe: cache hit for '%s' (%s) — %d modes.",
                    friendly_name, device_path, len(modes),
                )
                return _sort_modes(modes)

    # --- Fast path via pygrabber (DirectShow IAMStreamConfig) ----------------
    fast_modes = query_supported_modes_fast(device_index)
    if fast_modes:
        logger.info(
            "mode_probe: pygrabber fast path returned %d mode(s) for device_index=%d; "
            "skipping brute-force probe.",
            len(fast_modes), device_index,
        )
        if progress_callback is not None:
            progress_callback(total_probes, total_probes)
        if cache_path is not None and friendly_name and device_path:
            key = _cache_key(friendly_name, device_path)
            cache = _load_cache(cache_path)
            cache[key] = [asdict(m) for m in fast_modes]
            _save_cache(cache_path, cache)
        return fast_modes
    logger.info(
        "mode_probe: pygrabber unavailable or returned no MJPG modes for device_index=%d; "
        "falling back to brute-force cv2 probe.",
        device_index,
    )

    # --- Open camera for probing ---------------------------------------------
    logger.info(
        "mode_probe: opening device_index=%d for MJPG mode probe (%d probes).",
        device_index, total_probes,
    )

    accepted: list[CameraMode] = []
    probed = 0

    # Defensive open: catch driver errors that raise instead of returning a
    # non-opened cap (item C).
    try:
        cap = cv2.VideoCapture(device_index, backend)
    except Exception as exc:
        logger.warning(
            "mode_probe: cv2.VideoCapture(%d) raised %s. Returning fallback.",
            device_index, exc,
        )
        if progress_callback is not None:
            progress_callback(total_probes, total_probes)
        return _fallback_modes()

    if not cap.isOpened():
        logger.warning(
            "mode_probe: could not open device_index=%d for probing.", device_index
        )
        if progress_callback is not None:
            progress_callback(total_probes, total_probes)
        return _fallback_modes()

    # Per-camera probe timeout: abort after 90s and return whatever was
    # collected so far (prevents a hung DSHOW call blocking the user forever).
    _PROBE_TIMEOUT_S: float = 90.0
    probe_start = time.monotonic()

    try:
        for (w, h, fps) in probe_list:
            # Check per-camera timeout.
            if time.monotonic() - probe_start > _PROBE_TIMEOUT_S:
                logger.warning(
                    "mode_probe: device_index=%d exceeded %.0fs timeout after %d/%d probes. "
                    "Aborting with partial results.",
                    device_index, _PROBE_TIMEOUT_S, probed, total_probes,
                )
                # Mark remaining probes as skipped in the progress counter.
                if progress_callback is not None:
                    progress_callback(total_probes, total_probes)
                break

            try:
                # Apply double-FOURCC pattern (same as Camera.open()).
                cap.set(cv2.CAP_PROP_FOURCC, fourcc_int)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                cap.set(cv2.CAP_PROP_FPS, fps)
                cap.set(cv2.CAP_PROP_FOURCC, fourcc_int)

                # Small settle delay — driver negotiates media type.
                time.sleep(0.05)

                eff_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                eff_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                eff_fps_raw = cap.get(cv2.CAP_PROP_FPS)
                eff_fps = round(eff_fps_raw)

                res_ok = (eff_w == w) and (eff_h == h)
                fps_ok = (
                    abs(eff_fps_raw - fps) / max(fps, 1) <= _FPS_TOLERANCE
                    and eff_fps >= _MIN_FPS
                )

                if res_ok and fps_ok:
                    mode = CameraMode(width=w, height=h, fps=eff_fps)
                    if mode not in accepted:
                        accepted.append(mode)
                        logger.debug("mode_probe: ACCEPTED %s", mode)
                else:
                    logger.debug(
                        "mode_probe: rejected %dx%d@%d → got %dx%d@%.1f",
                        w, h, fps, eff_w, eff_h, eff_fps_raw,
                    )

            except Exception as exc:
                # Driver weirdness on an individual probe — skip this mode and
                # continue (item C).  A single bad cap.set() should not abort
                # the entire probe run.
                logger.warning(
                    "mode_probe: device_index=%d exception on probe %dx%d@%d: %s — skipping.",
                    device_index, w, h, fps, exc,
                )

            probed += 1
            if progress_callback is not None:
                progress_callback(probed, total_probes)

    finally:
        cap.release()

    # --- Write cache ----------------------------------------------------------
    if cache_path is not None and friendly_name and device_path:
        key = _cache_key(friendly_name, device_path)
        cache = _load_cache(cache_path)
        cache[key] = [asdict(m) for m in accepted]
        _save_cache(cache_path, cache)

    if not accepted:
        logger.warning(
            "mode_probe: no MJPG modes detected for device_index=%d. "
            "Using safe fallback 1280x720@30.",
            device_index,
        )
        return _fallback_modes()

    logger.info(
        "mode_probe: %d MJPG modes detected for device_index=%d.",
        len(accepted), device_index,
    )
    return _sort_modes(accepted)


def _sort_modes(modes: list[CameraMode]) -> list[CameraMode]:
    """Sort modes by (width desc, height desc, fps desc)."""
    return sorted(modes, key=lambda m: (m.width, m.height, m.fps), reverse=True)


def _fallback_modes() -> list[CameraMode]:
    """Safe fallback when no modes are detected."""
    return [CameraMode(width=1280, height=720, fps=30)]


# ---------------------------------------------------------------------------
# Intersection helpers (used by the picker UI)
# ---------------------------------------------------------------------------


def intersect_modes(
    modes_per_camera: list[list[CameraMode]],
) -> list[CameraMode]:
    """Return modes supported by ALL cameras.

    First intersects on (width, height), then within each shared resolution
    intersects the FPS values available on all cameras.

    Falls back to [CameraMode(1280, 720, 30)] if intersection is empty.

    Args:
        modes_per_camera: One list of CameraMode per camera (3 cameras expected).

    Returns:
        Sorted list of shared modes.
    """
    if not modes_per_camera:
        return _fallback_modes()

    # Build resolution sets per camera.
    res_sets = [
        {(m.width, m.height) for m in cam_modes}
        for cam_modes in modes_per_camera
    ]

    # Intersection of resolutions.
    shared_res = res_sets[0]
    for s in res_sets[1:]:
        shared_res = shared_res & s

    if not shared_res:
        logger.warning(
            "mode_probe: no shared resolutions across cameras. "
            "Falling back to 1280x720@30."
        )
        return _fallback_modes()

    # For each shared resolution, find shared FPS.
    shared_modes: list[CameraMode] = []
    for (w, h) in shared_res:
        fps_sets = [
            {m.fps for m in cam_modes if m.width == w and m.height == h}
            for cam_modes in modes_per_camera
        ]
        shared_fps = fps_sets[0]
        for s in fps_sets[1:]:
            shared_fps = shared_fps & s

        for fps in shared_fps:
            shared_modes.append(CameraMode(width=w, height=h, fps=fps))

    if not shared_modes:
        logger.warning(
            "mode_probe: no shared (resolution, fps) combos. "
            "Falling back to 1280x720@30."
        )
        return _fallback_modes()

    return _sort_modes(shared_modes)


def best_default_mode(modes: list[CameraMode]) -> CameraMode:
    """Pick the highest-quality mode from a list (max resolution, then max fps).

    Falls back to 1280x720@30 if the list is empty.
    """
    if not modes:
        return CameraMode(width=1280, height=720, fps=30)
    # _sort_modes already puts the best first (width desc, height desc, fps desc).
    return _sort_modes(modes)[0]


# ---------------------------------------------------------------------------
# Bandwidth advisory
# ---------------------------------------------------------------------------

# MJPG compression factor relative to raw YUY2. Empirically ~7-10x.
# We use 7 (conservative) so the advisory fires at a realistic threshold.
_MJPG_COMPRESSION_FACTOR: float = 7.0
_BYTES_PER_PIXEL_YUY2: float = 2.0  # YUY2 is 16 bits per pixel

# Advisory thresholds in Mbps.
_BANDWIDTH_WARN_MBPS: float = 250.0   # yellow
_BANDWIDTH_ERROR_MBPS: float = 450.0  # red


def bandwidth_advisory(
    width: int,
    height: int,
    fps: int,
    num_cameras: int = 3,
) -> tuple[str, str]:
    """Return (severity, message) for the bandwidth advisory.

    Severity is one of "ok", "warn", "error".
    Message is empty string when severity is "ok".

    MJPG bandwidth estimate:
        (width * height * fps * num_cameras * bytes_per_pixel_yuy2) / compression_factor
    """
    raw_bps = width * height * fps * num_cameras * _BYTES_PER_PIXEL_YUY2
    mjpg_mbps = (raw_bps / _MJPG_COMPRESSION_FACTOR) / 1_000_000

    if mjpg_mbps >= _BANDWIDTH_ERROR_MBPS:
        msg = (
            f"{width}×{height} @ {fps} fps × {num_cameras} cameras "
            f"≈ {mjpg_mbps:.0f} Mbps (MJPG est.) — "
            f"exceeds USB 3.0 safe limit. Camera opens may fail. "
            f"Drop to a lower resolution or FPS."
        )
        return "error", msg

    if mjpg_mbps >= _BANDWIDTH_WARN_MBPS:
        msg = (
            f"{width}×{height} @ {fps} fps × {num_cameras} cameras "
            f"≈ {mjpg_mbps:.0f} Mbps (MJPG est.) — "
            f"close to USB 2.0 limit. If a camera fails to open, drop to 30 fps."
        )
        return "warn", msg

    return "ok", ""
