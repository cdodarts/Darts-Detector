# SPDX-License-Identifier: GPL-3.0-or-later
"""
darts_detector.cli.camera_picker — launch the browser-based camera picker.

@internal

Usage:
    uv run python -m darts_detector.cli.camera_picker

What it does:
1. Starts the FastAPI camera picker app on http://127.0.0.1:8765 (configurable
   via --port).
2. Opens the user's default browser to that URL.
3. Runs until the user clicks Save (which writes config/cameras.yaml) or the
   process is interrupted with Ctrl+C.

After saving, the server shuts down automatically. The user can then close the
browser tab and run the Phase 1 smoke test.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn

from darts_detector.ui.camera_picker.app import app, _shutdown_event

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def _get_lan_ip() -> str:
    """Return the machine's LAN IP address, or empty string if not determinable."""
    try:
        # Connect to an external address (doesn't actually send data) to find
        # which local interface would be used — gives us the LAN IP.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""


def main(host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> None:
    """Start the camera picker server and open the browser."""
    localhost_url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",  # Keep stdout clean — we're a UI tool.
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Open the browser shortly after the server starts.
    def _open_browser() -> None:
        # Give uvicorn time to bind the socket.
        time.sleep(1.2)
        print(f"  Opening browser at {localhost_url}")
        if host == "0.0.0.0":
            lan_ip = _get_lan_ip()
            if lan_ip:
                print(f"  LAN URL (for phone/tablet on same network): http://{lan_ip}:{port}")
        print("  Select your cameras, then click Save Configuration.")
        print("  Press Ctrl+C to cancel without saving.")
        webbrowser.open(localhost_url)

    browser_thread = threading.Thread(target=_open_browser, daemon=True)

    # Watch for the shutdown event set by /save and stop the server.
    def _watch_shutdown() -> None:
        _shutdown_event.wait()
        print("\n  Configuration saved. Stopping server...")
        server.should_exit = True

    shutdown_thread = threading.Thread(target=_watch_shutdown, daemon=True)

    print(f"\nDarts Detector — Camera Picker")
    print(f"  Server starting at {localhost_url} ...")

    browser_thread.start()
    shutdown_thread.start()

    try:
        server.run()
    except KeyboardInterrupt:
        print("\n  Cancelled. config/cameras.yaml was NOT written.")

    print("  Camera picker closed.\n")


def _cli() -> None:
    """Argument-parsing wrapper for the ``camera-picker`` script entry point."""
    parser = argparse.ArgumentParser(
        prog="camera-picker",
        description="Browser-based camera picker for Darts Detector.",
    )
    parser.add_argument(
        "--host",
        default=_DEFAULT_HOST,
        help=f"Bind host (default: {_DEFAULT_HOST}). Use 0.0.0.0 for LAN access.",
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
