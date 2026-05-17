# Open Questions

Unresolved decisions. Resolved items move to [DECISIONS.md](DECISIONS.md). Update this file as questions are answered.

## Recently Resolved (Moved To DECISIONS.md)

| Question | Resolution | Decision |
| --- | --- | --- |
| Implementation language? | Python + OpenCV + NumPy | `D-003` |
| Coordinate unit? | Integer millimetres | `D-004` |
| Config format? | YAML for hand-edited, JSON for calibration profiles | `D-005` |
| When to lock JSON contract? | End of Phase 4 | `D-006` |
| When to build replay tooling? | Phase 4.5, before detection phases | `D-007` |
| Calibration self-test required? | Yes, Phase 3.5 | `D-008` |
| Latency budget enforcement? | Per-stage, instrumented from Phase 1 | `D-009` |
| Default WebSocket port? | `8765` | `D-005` (config doc) |
| Project identity / governance? | Long-term community project, OBS/Blender model | `D-011`, `PROJECT_CHARTER.md` |
| License? | GPL-3.0-or-later | `D-012` |
| Plugin architecture? | Defined now, loader post-MVP; WebSocket is MVP plugin surface | `D-013`, `PLUGIN_ARCHITECTURE.md` |
| Public vs internal API? | Stability tiers (`@public-stable`, `@public-experimental`, `@internal`, `@plugin`) | `D-014` |
| Takeout detection in MVP? | Yes, Phase 5.5 (CV signals) + Phase 7.5 (state machine) | `D-015` |
| Hand detection ML or heuristic? | Heuristic only (% of board area occluded), no ML | `D-016` |

## Hardware

- What exact USB camera models will be used?
- What lens field of view will each camera have?
- Are the cameras global shutter or rolling shutter?
- What is the ideal default resolution and FPS for the selected cameras?
- What USB topology will the Raspberry Pi 5 use for three simultaneous cameras (direct, hub, powered hub)?
- What light ring model and brightness settings are expected?
- How rigid is the camera mounting hardware (does it pass a calibration self-test after a knock)?

## Camera Geometry

- What are the expected camera distances from the board?
- What are the expected camera heights and angles?
- Are cameras mounted at exactly 120-degree spacing or only roughly around the board?
- Can any camera see the board center and all scoring rings clearly?
- How often should users be expected to recalibrate (target: weeks, not minutes)?

## Runtime Platform

- What target Linux distro will the Raspberry Pi 5 run (Raspberry Pi OS Bookworm vs Ubuntu)?
- Should the app run headless with a browser-based UI, or with a local Qt/Tk window for setup?
- Should the app start as a `systemd` service?
- What package or deployment method is preferred (pip + venv, Docker, native .deb)?

## Configuration

- Where should calibration profiles be stored by default (`/var/lib/darts-detector/`, `~/.config/darts-detector/`, or repo-relative)?
- Should debug frame saving be enabled by default in development only? (Recommendation: yes.)
- How should camera device IDs remain stable across reboots (udev rules, by-id symlinks)?

## UI

- What UI framework for the debug/calibration UI (recommendation: a simple FastAPI + HTMX or static HTML + JS connected via the WebSocket, served by the same process)?
- Is the MVP UI only for calibration/debug, or should it include a minimal scoring display?
- What browsers must the setup UI support (Chromium-only acceptable for a kiosk)?

## Detection And Scoring

- What confidence threshold should block Dart event emission and trigger `outcome: "rejected"`?
- How should dart removal and next-turn baseline updates be handled (timer, motion-based, explicit user signal)?
- Should `turnId` be tracked in MVP, or always emit empty string and add turn logic post-MVP?

## Data And Testing

- Where will labelled throw datasets be stored (repo `datasets/throws/` gitignored, or external storage)?
- What minimum dataset size is required before publishing any accuracy claim (recommendation: ≥500 labelled throws covering all 20 segments, bull, miss, and border cases)?
- Who will manually label replay throws?
- What metrics format should accuracy reports use (HTML report, JSON for CI, both)?

## Project Direction

- Will this become part of Vertex/CDO later?
- What license should the open-source project use (recommendation: MIT or Apache-2.0)?
- What operating name should the project use publicly?
- What external integrations are expected after MVP?
