# SPDX-License-Identifier: GPL-3.0-or-later
"""
One-shot exposure / property probe for a single camera.

Run:
    uv run python scripts/probe_exposure.py

What it does, for the first Autodarts DIY Cam it finds:
  1. Opens it with MJPG @ 1280x720 (same as the tuning UI).
  2. Times every step so we can see where the 20s/cam delay is coming from.
  3. Captures a baseline JPG with whatever the driver gives us at open.
  4. Tries every plausible DSHOW manual-exposure flag value:
        AUTO_EXPOSURE = 0, 0.25, 0.75, 1, 3
     and for each, tries setting CAP_PROP_EXPOSURE to -13, -7, -1.
     Saves a JPG and prints the readback.
  5. Same for gain and white balance.

Output goes to scripts/probe_output/ — visual inspection of the JPGs tells us
which combination actually changes the image on this hardware.
"""

from __future__ import annotations

import platform
import time
from pathlib import Path

import cv2

OUT_DIR = Path(__file__).parent / "probe_output"
OUT_DIR.mkdir(exist_ok=True)


def find_autodarts_index() -> int:
    """Find the first Autodarts DIY Cam index via pygrabber."""
    try:
        from pygrabber.dshow_graph import FilterGraph
    except ImportError:
        print("pygrabber not installed; falling back to index 0.")
        return 0
    graph = FilterGraph()
    devices = graph.get_input_devices()
    for i, name in enumerate(devices):
        if "autodarts" in name.lower():
            print(f"Found Autodarts DIY Cam at index {i} ({name}).")
            return i
    print(f"No Autodarts cam found in {devices}; using index 0.")
    return 0


def save_frame(cap: cv2.VideoCapture, label: str) -> None:
    """Read a frame and save it to OUT_DIR with the label."""
    # Discard a frame so we get a fresh one after the setting change.
    cap.grab()
    ok, frame = cap.read()
    if not ok or frame is None:
        print(f"  [{label}] FRAME READ FAILED")
        return
    mean = frame.mean()
    path = OUT_DIR / f"{label}.jpg"
    cv2.imwrite(str(path), frame)
    print(f"  [{label}] saved {path.name}  mean_brightness={mean:.1f}")


def probe() -> None:
    backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
    idx = find_autodarts_index()

    print(f"\n--- Opening camera idx={idx} (this is where the 20s delay would be) ---")
    t0 = time.monotonic()
    cap = cv2.VideoCapture(idx, backend)
    print(f"  VideoCapture()      took {time.monotonic()-t0:.2f}s")

    t0 = time.monotonic()
    fourcc = cv2.VideoWriter.fourcc(*"MJPG")
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    print(f"  FOURCC + res + fps  took {time.monotonic()-t0:.2f}s")

    t0 = time.monotonic()
    ok, _frame = cap.read()
    print(f"  First read()        took {time.monotonic()-t0:.2f}s  ok={ok}")

    if not cap.isOpened():
        print("Camera failed to open. Aborting.")
        return

    # ----- Baseline -----
    print("\n--- BASELINE (untouched defaults) ---")
    print(f"  AUTO_EXPOSURE = {cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)}")
    print(f"  EXPOSURE      = {cap.get(cv2.CAP_PROP_EXPOSURE)}")
    print(f"  GAIN          = {cap.get(cv2.CAP_PROP_GAIN)}")
    print(f"  AUTO_WB       = {cap.get(cv2.CAP_PROP_AUTO_WB)}")
    print(f"  WB_BLUE_U     = {cap.get(cv2.CAP_PROP_WHITE_BALANCE_BLUE_U)}")
    save_frame(cap, "00_baseline")

    # ----- Try every manual-exposure flag value -----
    for ae_flag in (0, 0.25, 0.75, 1, 3):
        print(f"\n--- Setting AUTO_EXPOSURE = {ae_flag} ---")
        ok_set = cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, ae_flag)
        readback = cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)
        print(f"  set() returned {ok_set}, readback = {readback}")
        time.sleep(0.3)  # give the driver a moment

        for exp_val in (-1, -7, -13):
            ok_set = cap.set(cv2.CAP_PROP_EXPOSURE, exp_val)
            readback = cap.get(cv2.CAP_PROP_EXPOSURE)
            print(f"    set EXPOSURE={exp_val} → returned {ok_set}, readback={readback}")
            time.sleep(0.3)
            save_frame(cap, f"ae{ae_flag}_exp{exp_val}")

    # ----- Gain probe -----
    print("\n--- GAIN probe ---")
    for gain_val in (0, 25, 50, 100):
        cap.set(cv2.CAP_PROP_GAIN, gain_val)
        readback = cap.get(cv2.CAP_PROP_GAIN)
        print(f"  set GAIN={gain_val} → readback={readback}")
        time.sleep(0.3)
        save_frame(cap, f"gain_{gain_val}")

    cap.release()
    print(f"\nDone. Inspect images in {OUT_DIR}")
    print("Look for which ae{N}_exp{M} combination actually darkens the image.")


if __name__ == "__main__":
    probe()
