# Project Ethos

This document captures the founding principles that define what this project is and who it is for. These principles are not implementation constraints — they are identity. They override product decisions that drift away from them.

## Who This Is For

This project is for the DIY darts enthusiast: someone who has bought a set of USB cameras (any brand), 3D-printed their own mounts, built their own light ring, and wants an open-source system that works with **their** hardware.

This is not a product for a specific polished manufactured kit. There is no single reference camera model, no single mount geometry, no single lighting rig. Users will arrive with:

- Different camera models (OV2710, ELP, cheap no-brand webcams, laptop cams for development).
- 3D-printed mounts with different angles and distances from the board.
- Different light rings (ring LED, strip LED, overhead, natural light).
- Different environments (spare room, garage, bright pub lighting, dim evening light).

**The system must adapt to the user's hardware. The user does not adapt to the system.**

## Core Principles

### 1. Every parameter that affects detection accuracy must be user-controllable

If a camera setting — exposure, white balance, gamma, brightness, contrast, gain, saturation, sharpness — affects how well the system detects darts, the user must be able to adjust it. At MVP, we do not provide a built-in camera control UI. Users with varied hardware adjust their cameras using the tools that came with them — manufacturer utilities, Windows Camera Settings, OBS Virtual Camera, etc. We read whatever frames the user provides.

The `cameras.yaml` schema exposes per-camera tuning fields (exposure, gain, brightness, contrast, whiteBalance, gamma, saturation, sharpness, backlightCompensation) that get applied on `Camera.open()` for power users who want to set them via config, but no tuning UI ships in MVP. A future Phase 1.5 can layer a browser-based tuning UI on top of this hook without changing any contract. See D-021 in `DECISIONS.md`.

The principle remains: camera state when calibration is captured must match camera state at runtime. If `cameras.yaml` tuning fields change, calibration is invalidated. The fingerprint mechanism enforces this regardless of whether a UI was used.

### 2. Reasonable defaults that work on first run

A user with a common setup (Autodarts DIY Cam OV2710, basic USB ring light, Raspberry Pi 5) should be able to run the system with default settings and have it work without reading documentation. Defaults are:

- Resolution: 1280×720.
- FPS: 30.
- Exposure: manual, value 100.
- White balance: manual, 4500K.
- Gain / brightness / contrast: 0.

Users with unusual hardware tune from those defaults. The system must not require tuning to function at all.

### 3. Setup pain is a bug

Per `D-018`: a feature that works correctly but is painful to set up is treated as broken. The setup flow — camera selection → image tuning → calibration → ready — must be completable from a browser UI by a non-developer. No required command-line steps for first-time setup.

### 4. Open and auditable

Deterministic computer vision. No runtime ML. Every detection decision is explainable and reproducible from saved frames. The system produces debug overlays so users can see exactly what the pipeline sees. See `D-001`.

### 5. Long-term community project

This project is built to last, modelled after OBS Studio and Blender. Stability, maintainability, and contributor safety take precedence over rapid feature development. The plugin architecture (`D-013`) and public API (`D-014`) exist from day one so the community can extend the system without forking it. See `D-011` and `docs/PROJECT_CHARTER.md`.

## Adapting To The User's Hardware: A Concrete Example

Real hardware testing on the Autodarts DIY Cam (OV2710, DirectShow, Windows 11) confirmed the limits of a built-in tuning UI:
- The exposure control is completely non-functional on this driver. `cap.set(CAP_PROP_EXPOSURE, ...)` returns True but has no effect. All 30 tested combinations produce identical brightness.
- The gain control works but is inverted — higher gain values produce a darker image.
- The white balance Kelvin value cannot be read back from the driver.

This is why MVP ships without a built-in tuning UI. The driver surface is too varied to abstract reliably across all cameras a DIY user might bring. Users with the OV2710 use Windows Camera Settings or the manufacturer's utility. The system applies whatever is in `cameras.yaml` via `Camera._apply_tuning()` and works with the resulting frames.

When a future Phase 1.5 tuning UI is built, the right approach is to **probe driver capabilities** and adapt the UI rather than showing a fixed control set. The probe methodology and OV2710 findings are documented in `scripts/probe_exposure.py`. That script serves as the reference implementation.

## Implications For Phase Ordering

Phase sequence is now: Phase 1 (camera selection) → Phase 2 (camera settings/performance profiles) → Phase 3 (calibration). Phase 1.5 (camera tuning UI) is deferred to post-MVP per D-021. Users adjust their cameras before calibration using their own software. The calibration fingerprint mechanism ensures that if `cameras.yaml` tuning fields change after calibration, the calibration is invalidated.

## References

- `D-018` (UX quality) — `docs/DECISIONS.md`
- `D-019` (configurable resolution/FPS) — `docs/DECISIONS.md`
- `D-021` (camera tuning UI deferred; calibration fingerprint retained) — `docs/DECISIONS.md`
- `scripts/probe_exposure.py` — hardware capability probe reference implementation
- `docs/PHASED_IMPLEMENTATION.md` — deferred Phase 1.5 spec in "Deferred / Polish Features" section
- `docs/PROJECT_CHARTER.md` — governance and non-negotiable principles
