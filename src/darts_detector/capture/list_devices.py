# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.capture.list_devices — enumerate DirectShow/UVC cameras on Windows.

@internal

Exposes two public surfaces:

1. ``enumerate_cameras()`` — returns a list of :class:`CameraDevice` objects.
   Called by the browser-based camera picker UI and any other module that needs
   to list available cameras.

2. ``main()`` / CLI — thin wrapper around ``enumerate_cameras()`` that pretty-
   prints the result.  Useful for headless debugging (no browser) on a Pi 5 or
   SSH session.

Usage (CLI):
    uv run python -m darts_detector.capture.list_devices

Output columns:
    Index  | Friendly Name           | Device Path (USB instance)   | Notes
    -------|-------------------------|------------------------------|-------
    0      | Autodarts DIY Cam       | USB\\VID_0C45&PID_6366\\...  | ** darts cam **
    1      | Integrated Webcam       | USB\\VID_0BDA&PID_5520\\...  |
    ...

The 'Device Path' column is the stable USB instance path you need for cameras.yaml.
It does NOT change as long as you keep each camera plugged into the same physical port.

pygrabber (uv add pygrabber) is used for friendly-name lookup when available.
Without it, names fall back to 'Camera <index>'. Device-path lookup uses the
Windows Device Manager COM API via comtypes when available; otherwise it reports
'unavailable' and you can identify cameras visually from the frame preview note.
"""

from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass
from typing import Optional

import cv2

# Suppress noisy DSHOW probe warnings emitted by cv2.VideoCapture during
# index enumeration ("backend is generally available but can't be used to
# capture by index"). These are expected — we probe past the real device
# count by design — and not actionable for users.
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

# ---------------------------------------------------------------------------
# Optional imports — degrade gracefully if not installed.
# ---------------------------------------------------------------------------
_pygrabber_available = False
_comtypes_available = False

try:
    from pygrabber.dshow_graph import FilterGraph  # type: ignore[import]
    _pygrabber_available = True
except ImportError:
    pass

try:
    import comtypes  # type: ignore[import]  # noqa: F401
    _comtypes_available = True
except ImportError:
    pass

DARTS_CAM_FRIENDLY_NAME = "Autodarts DIY Cam"
_MAX_PROBE_INDEX = 15  # probe indices 0–15


@dataclass
class CameraDevice:
    """All available information about one enumerated camera device.

    Fields
    ------
    index:
        DirectShow (or V4L2 on Linux) device index used by ``cv2.VideoCapture``.
    friendly_name:
        Human-readable name from the OS / DirectShow enumeration.
    device_path:
        Stable USB device instance path (Windows) or ``/dev/videoN`` (Linux).
        ``"unavailable"`` when the OS query fails.
    is_darts_cam:
        ``True`` when ``friendly_name`` contains the expected Autodarts camera
        substring — used by startup to filter out other webcams.
    opened:
        Whether ``cv2.VideoCapture`` could open this index.
    frame_ok:
        Whether at least one frame was grabbed successfully during enumeration.
    """

    index: int
    friendly_name: str
    device_path: str
    is_darts_cam: bool
    opened: bool
    frame_ok: bool

    @property
    def label(self) -> str:
        """Short display label for UI dropdowns: ``"<index>: <name>"``.

        Example: ``"0: Autodarts DIY Cam"``
        """
        return f"{self.index}: {self.friendly_name}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_friendly_names_pygrabber() -> dict[int, str]:
    """Return {index: friendly_name} using pygrabber's DirectShow enumeration."""
    if not _pygrabber_available:
        return {}
    try:
        graph = FilterGraph()
        devices = graph.get_input_devices()
        return {i: name for i, name in enumerate(devices)}
    except Exception:  # noqa: BLE001
        return {}


def _get_device_paths_windows() -> dict[str, str]:
    """
    Return {friendly_name: device_instance_path} via Windows SetupAPI / WMI.

    Uses comtypes + WMI query if available. Falls back to 'unavailable'.
    This is best-effort; the device path is also visible in Device Manager.
    """
    if not _comtypes_available or platform.system() != "Windows":
        return {}
    try:
        import comtypes.client  # type: ignore[import]
        wmi = comtypes.client.CreateObject("WbemScripting.SWbemLocator")
        svc = wmi.ConnectServer(".", "root\\cimv2")
        result: dict[str, str] = {}
        query = svc.ExecQuery(
            "SELECT Name, DeviceID FROM Win32_PnPEntity "
            "WHERE PNPClass = 'Camera' OR PNPClass = 'Image' OR Service = 'usbvideo'"
        )
        for item in query:
            name = getattr(item, "Name", "") or ""
            device_id = getattr(item, "DeviceID", "") or ""
            if name:
                result[name] = device_id
        return result
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enumerate_cameras() -> list[CameraDevice]:
    """Probe all camera indices and return a list of :class:`CameraDevice`.

    This is the primary public surface. Called by the camera picker UI,
    the startup matcher, and any other module that needs to list available
    cameras.

    The function opens each device index briefly to confirm it is alive,
    grabs one frame for health-check, then releases the handle immediately.
    Total probe time is typically 2–5 seconds depending on the number of
    attached devices.

    Returns an empty list if no cameras are detected.
    """
    is_windows = platform.system() == "Windows"
    backend = cv2.CAP_DSHOW if is_windows else cv2.CAP_ANY

    friendly_names = _get_friendly_names_pygrabber()
    device_paths = _get_device_paths_windows()

    results: list[CameraDevice] = []

    for idx in range(_MAX_PROBE_INDEX + 1):
        cap = cv2.VideoCapture(idx, backend)
        if not cap.isOpened():
            cap.release()
            continue

        frame_ok = bool(cap.grab())

        friendly = friendly_names.get(idx, f"Camera {idx}")

        dev_path = device_paths.get(friendly, "unavailable — run Device Manager")
        if dev_path.startswith("unavailable"):
            for k, v in device_paths.items():
                if friendly.lower() in k.lower() or k.lower() in friendly.lower():
                    dev_path = v
                    break

        is_darts_cam = DARTS_CAM_FRIENDLY_NAME.lower() in friendly.lower()

        results.append(
            CameraDevice(
                index=idx,
                friendly_name=friendly,
                device_path=dev_path,
                is_darts_cam=is_darts_cam,
                opened=True,
                frame_ok=frame_ok,
            )
        )
        cap.release()
        # Brief pause between opens to avoid overwhelming DirectShow.
        time.sleep(0.1)

    return results


# ---------------------------------------------------------------------------
# CLI formatting (kept for headless / SSH debugging)
# ---------------------------------------------------------------------------

def _print_device_table(devices: list[CameraDevice]) -> None:
    """Pretty-print the device table to stdout."""
    if not devices:
        print("No cameras found. Check USB connections.")
        return

    col_idx = 5
    col_name = max(len(d.friendly_name) for d in devices) + 2
    col_path = max(len(d.device_path) for d in devices) + 2

    header = (
        f"{'Idx':<{col_idx}}  "
        f"{'Friendly Name':<{col_name}}  "
        f"{'Device Path (USB instance)':<{col_path}}  "
        f"{'Notes'}"
    )
    print()
    print(header)
    print("-" * len(header))

    for d in devices:
        note_parts = []
        if not d.frame_ok:
            note_parts.append("no frame")
        if d.is_darts_cam:
            note_parts.append("** DARTS CAM **")
        note = "  ".join(note_parts)

        row = (
            f"{d.index:<{col_idx}}  "
            f"{d.friendly_name:<{col_name}}  "
            f"{d.device_path:<{col_path}}  "
            f"{note}"
        )
        print(row)

    print()

    darts_cams = [d for d in devices if d.is_darts_cam]
    if darts_cams:
        print(f"Found {len(darts_cams)} 'Autodarts DIY Cam' device(s).")
        if len(darts_cams) == 3:
            print(
                "All three darts cameras detected. Run the camera picker to assign "
                "roles:\n  uv run python -m darts_detector.cli.camera_picker"
            )
        else:
            print(
                f"WARNING: Expected 3 darts cameras, found {len(darts_cams)}. "
                "Check USB connections."
            )
    else:
        print(
            "No 'Autodarts DIY Cam' devices found. "
            "Check that cameras are plugged in and drivers are installed."
        )

    if not _pygrabber_available:
        print(
            "\nTIP: Install pygrabber for accurate friendly names: "
            "uv add pygrabber"
        )
    if not _comtypes_available:
        print(
            "TIP: Install comtypes for USB device paths: "
            "uv add comtypes"
        )


def main() -> None:
    """CLI entry point: enumerate cameras and print a human-readable table.

    For headless or SSH environments where the browser-based picker is not
    available.  Recommended flow for GUI environments:
        uv run python -m darts_detector.cli.camera_picker
    """
    if platform.system() != "Windows":
        print(
            "WARNING: This tool is designed for Windows (DirectShow). "
            "On Linux, device paths are /dev/videoN."
        )
    print("Probing camera devices (indices 0–15). This may take a few seconds...")
    devices = enumerate_cameras()
    _print_device_table(devices)
    sys.exit(0)


if __name__ == "__main__":
    main()
