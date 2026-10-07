# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.cli.intrinsic_picker — launch the Phase 2.5 intrinsic
calibration browser UI.

@internal

Usage:
    uv run intrinsic-picker
    uv run intrinsic-picker --host 0.0.0.0   # phone / LAN access

What it does:
1. Starts the FastAPI intrinsic-picker app on http://127.0.0.1:8766.
2. Opens the user's default browser to that URL.
3. Runs until the user calibrates all cameras and closes the page,
   or presses Ctrl+C.

After all 3 cameras are saved, the intrinsics profiles are at:
    config/calibration/intrinsics/cam_1.json
    config/calibration/intrinsics/cam_2.json
    config/calibration/intrinsics/cam_3.json
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn

from darts_detector.ui.intrinsic_picker.app import app

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8766


def _get_lan_ip() -> str:
    """Return the machine's LAN IP address, or empty string if not determinable."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""


def main(host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> None:
    """Start the intrinsic picker server and open the browser."""
    localhost_url = f"http://127.0.0.1:{port}"
    lan_ip = _get_lan_ip() if host == "0.0.0.0" else ""
    lan_url = f"http://{lan_ip}:{port}" if lan_ip else ""

    print("\nDarts Detector — Lens Intrinsic Calibration (Phase 2.5)")
    if host == "0.0.0.0":
        print(f"  Server bound to all interfaces on port {port}")
        print(f"  On this PC:           {localhost_url}")
        if lan_url:
            print(f"  On phone / tablet:    {lan_url}    (same Wi-Fi required)")
        else:
            print("  LAN IP could not be determined — run 'ipconfig' to find it.")
    else:
        print(f"  Server starting at {localhost_url}")
        print(
            "  (For phone access, relaunch with: intrinsic-picker --host 0.0.0.0)"
        )
    print()
    print("  Steps:")
    print("    1. Print assets/chessboard_9x6_25mm.pdf at 100% scale.")
    print("    2. For each camera: capture 15 frames at varied angles.")
    print("    3. Click Calibrate — verify reprojection error < 0.5 px.")
    print("    4. Click Save.")
    print("    5. Repeat for all 3 cameras.")
    print()
    print("  Press Ctrl+C to cancel.\n")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    def _open_browser() -> None:
        time.sleep(1.2)
        webbrowser.open(localhost_url)

    browser_thread = threading.Thread(target=_open_browser, daemon=True)
    browser_thread.start()

    try:
        server.run()
    except KeyboardInterrupt:
        print("\n  Cancelled. No calibration profiles were saved by this session.")

    print("  Intrinsic picker closed.\n")


def _cli() -> None:
    """Argument-parsing wrapper for the ``intrinsic-picker`` script entry point."""
    parser = argparse.ArgumentParser(
        prog="intrinsic-picker",
        description="Browser-based lens intrinsic calibration for Darts Detector.",
    )
    parser.add_argument(
        "--host",
        default=_DEFAULT_HOST,
        help=(
            f"Bind host (default: {_DEFAULT_HOST}). "
            "Use 0.0.0.0 for LAN/phone access."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_PORT,
        help=f"Port to listen on (default: {_DEFAULT_PORT}).",
    )
    args = parser.parse_args()
    main(host=args.host, port=args.port)


if __name__ == "__main__":
    _cli()
