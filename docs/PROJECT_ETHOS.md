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

If a camera setting — exposure, white balance, gamma, brightness, contrast, gain, saturation, sharpness — affects how well the system detects darts, the user must be able to adjust it through a great UI. Hiding settings because "most users won't need them" breaks setups that differ from the reference rig.

This applies in Phase order: image tuning controls are presented **before** calibration so that the camera state the user tuned is the camera state that calibration captures. See `D-020` in `DECISIONS.md`.

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

## Implications For Phase Ordering

Image tuning (exposure, brightness, gamma, white balance, contrast, gain) is exposed in Phase 1.5. Calibration is Phase 3. This ordering is locked in `D-020` and reflected in `docs/PHASED_IMPLEMENTATION.md`. Calibration performed before image tuning is unreliable because the sensor response changes when tuning changes.

## References

- `D-018` (UX quality) — `docs/DECISIONS.md`
- `D-019` (configurable resolution/FPS) — `docs/DECISIONS.md`
- `D-020` (image tuning precedes calibration) — `docs/DECISIONS.md`
- Phase 1.5 deliverables — `docs/PHASED_IMPLEMENTATION.md`
- `docs/PROJECT_CHARTER.md` — governance and non-negotiable principles
