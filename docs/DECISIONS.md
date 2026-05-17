# Decisions Log

Architectural decisions that future agents and contributors must respect. Each entry is dated and explains *why* so edge cases can be judged against intent, not just rules.

Format: lightweight ADR. Status values: `accepted`, `superseded`, `deprecated`.

---

## D-001: Deterministic Runtime Detection (No ML)

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Runtime dart detection uses deterministic computer vision and board geometry only. AI/ML may be used for offline labelling, code review, or research, but never on the runtime hot path.
- **Why:** Explainability, reproducibility, predictable latency on Pi 5, no model versioning surface area, easier debugging via overlays.
- **Consequences:** Manual or semi-automatic calibration is required for MVP. Detection improvements must come from better geometry, thresholds, and fusion, not from learned models.

## D-002: Three Fixed USB Cameras At ~120 Degrees

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Three cameras, roughly 120° apart, fixed during play, stable lighting via ring light.
- **Why:** Three views give robust tip triangulation, tolerate one camera failing, and avoid the parallax/occlusion problems of single-camera setups.
- **Consequences:** Calibration is per-camera. Fusion must handle two-camera fallback. Recalibration is required if any camera moves.

## D-003: Primary Language Is Python + OpenCV + NumPy

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Implementation uses Python 3.11+, OpenCV, NumPy. WebSocket via `websockets` or `fastapi`. Config via PyYAML.
- **Why:** Largest CV ecosystem, fastest iteration, runs well on Pi 5, AI agents are most reliable in Python.
- **Escape hatch:** If profiling shows per-frame Python overhead exceeds the latency budget, port only the hot inner loop to C (via `ctypes`/`cffi`) or Cython. Do not pre-optimise.

## D-004: Coordinate Unit Is Integer Millimetres

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Board coordinates are integer millimetres. Bull centre is `(0, 0)`. Positive `y` points toward the centre of the `20` segment. Positive `x` follows a right-handed 2D convention (i.e. positive `x` is 90° clockwise from positive `y` when viewed from the player's perspective).
- **Why:** Avoids floating-point boundary bugs in scoring, makes lookup tables practical (a ~500×500 mm int grid is ~1MB), and standard board dimensions are defined in mm.
- **Consequences:** All inter-module APIs (fusion → scoring → API) use mm. Calibration converts image pixels → mm. The API field `coordinates.unit` is always `"mm"` for v1.

## D-005: Config Format Is YAML

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Configuration files use YAML. Calibration profiles use JSON (machine-written, machine-read, no comments needed).
- **Why:** YAML is human-friendly for hand-edited config (camera settings, performance profiles); JSON is safer for machine-generated calibration data where comments and whitespace are noise.
- **Consequences:** Add `pyyaml` as a runtime dependency. All YAML files validated on startup with explicit schema.

## D-006: WebSocket JSON Contract Locked Before Detection Code

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** The `Dart` event schema is frozen at the end of Phase 4 (scoring engine), before Phase 5 (motion detection) starts. Any change after that requires either an additive minor bump or a parallel `v2` event type with overlap period.
- **Why:** Detection and fusion code targets a stable shape. Late contract changes cause cascading refactors.
- **Consequences:** [API_AND_WEBSOCKET_CONTRACT.md](API_AND_WEBSOCKET_CONTRACT.md) and `dart-event.schema.json` are authoritative once Phase 4 is signed off.

## D-007: Replay Tooling Lands Before Detection Phases

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** A minimal frame recorder and replay runner (Phase 4.5) is built before motion detection (Phase 5). Full debug UI (Phase 9) remains where it is.
- **Why:** Detection cannot be developed reliably from live throws alone. Replay is the iteration substrate.
- **Consequences:** Phases 5–7 use saved labelled throws as their primary test surface.

## D-008: Calibration Self-Test Required Before Scoring

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Phase 3.5 — after calibration, the system projects the board rings back onto each camera view and the user must confirm alignment before scoring is enabled.
- **Why:** Catches calibration errors immediately instead of after detection produces wrong scores.
- **Consequences:** Scoring is gated by a `calibrationConfirmed: true` state. Recalibration resets the flag.

## D-009: Latency Budget Is Per-Stage, Not Just End-To-End

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** The 500 ms target is broken into per-stage budgets in [LATENCY_BUDGET.md](LATENCY_BUDGET.md). Each pipeline stage records its elapsed time; the `Dart` event includes a `latency.stageMs` block.
- **Why:** End-to-end measurement only catches regressions after they ship. Per-stage budgets catch them in PR review.
- **Consequences:** Stage timing instrumentation is added from Phase 1, not retrofitted in Phase 12.

## D-010: Semi-Automatic And Full-Automatic Calibration Are Post-MVP

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Phase 10 and Phase 11 do not block the MVP. MVP ships with manual calibration + self-test only.
- **Why:** Manual calibration is reliable and inspectable. Automating it before measuring MVP accuracy is premature.
- **Consequences:** Phase 12 (accuracy testing) runs against manual-calibration-only data. Automation is added only if measured to not reduce reliability.

## D-011: Long-Term Community Project (OBS/Blender Model)

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** This is a long-lived community project modelled after OBS Studio and Blender. Stability, maintainability, and contributor safety take precedence over rapid feature development. Governance, contribution rules, and architectural principles are documented in [PROJECT_CHARTER.md](PROJECT_CHARTER.md) and are non-negotiable without an RFC.
- **Why:** A clear long-term identity prevents accidental drift into a throwaway prototype. The OBS/Blender model is proven for FOSS projects in this domain (open-source, hobbyist hardware, plugin ecosystems).
- **Consequences:** All non-negotiable principles in the charter apply from day one. RFC process gates architecture-level changes. Public/internal API distinction is enforced. Backwards compatibility cycle in [VERSIONING.md](VERSIONING.md) applies to every contract.

## D-012: License Is GPL-3.0-Or-Later

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** The project is licensed under GNU General Public License v3.0 or later. All contributions are licensed under the same terms. Plugins distributed in this repository must be GPL-3.0-compatible.
- **Why:** Copyleft protects the open-source nature of the project against proprietary forks, matching the Blender precedent for a FOSS application with a plugin ecosystem.
- **Consequences:** Every source file carries an `SPDX-License-Identifier: GPL-3.0-or-later` header. New dependencies must be GPL-3.0-compatible. Third-party code with incompatible licenses cannot be merged.

## D-013: Plugin Architecture Defined From MVP, Loader Ships Post-MVP

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** A formal plugin architecture is defined now (see [PLUGIN_ARCHITECTURE.md](PLUGIN_ARCHITECTURE.md)) including the public API boundary at `src/darts_detector/api_public/`. The in-process plugin loader is post-MVP. Until the loader ships, the sanctioned plugin interface is the WebSocket event stream.
- **Why:** Locking the public API surface now costs nothing and prevents retrofitting later. The WebSocket-first plugin model lets contributors build useful tools in any language without core changes.
- **Consequences:** `src/darts_detector/api_public/` exists from Phase 1 even if mostly empty. No internal module is allowed to leak into the public API without an RFC. The wire format is treated as a stable plugin contract.

## D-014: Stability Tiers For Every Module

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Every module declares a stability tier in its docstring header: `@public-stable`, `@public-experimental`, `@internal`, or `@plugin`. Missing tier defaults to `@internal`.
- **Why:** Without explicit tiers, every accidental import becomes a backwards-compatibility liability. Tiers let core evolve while keeping public surfaces stable.
- **Consequences:** Linter enforces tier headers on every module. CI fails if `@public-stable` modules import from `@internal` modules. Removing or breaking a `@public-stable` surface requires the deprecation cycle in [VERSIONING.md](VERSIONING.md).

## D-015: Takeout Detection And Throw Lifecycle State Machine Are MVP

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Detection of player hands entering the board area and detection of "board clear of darts" are first-class MVP features (Phase 5.5). A throw lifecycle state machine (Phase 7.5) consumes these signals plus motion and fusion outputs, drives baseline updates, and emits `TurnState` events.
- **Why:** Without takeout detection the system either updates the baseline at the wrong time (absorbing a dart into the baseline) or refuses to start the next turn. Multi-throw operation is broken without it. The state machine is the only safe place to coordinate baseline updates with the throw cycle.
- **Consequences:** A new wire event `TurnState` is added at minor version `1.1.0` (additive). Baseline update logic is owned by the state machine, not the motion stage. Hand detection uses a simple percentage-of-board-area-occluded heuristic; no ML. Partial takeout is an explicit state — the system does NOT reset baseline until the board is verified clear.

## D-016: Hand Detection Is Heuristic, Not ML

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Hand-in-board-area detection uses a simple deterministic heuristic: % of the calibrated board region whose change-mask differs from the empty-board baseline exceeds a configurable threshold. No skin segmentation, no pose model, no ML.
- **Why:** Matches the no-runtime-ML rule (`D-001`). A hand covers a large fraction of the board area; a dart does not. The signal is robust to lighting changes that have already been controlled by manual exposure (`D-002`-adjacent).
- **Consequences:** Threshold tuned against a labelled dataset of hand-in / hand-out cases. Edge case: player wearing a darts shirt that visually resembles the board background — flagged as a known limitation in [RISKS.md](RISKS.md), debounced over multiple frames.

## D-017: Browser-Based HTML Frontend For All User-Facing Surfaces

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** All user-facing UI — camera picker, calibration assistant, operator/debug console, and scoring display — is delivered as a browser-based HTML/JS page served by the project's local FastAPI server. No native desktop GUI. No tkinter, no PySide6, no Electron.
- **Why:** Aligns with the WebSocket/JSON contract (`API_AND_WEBSOCKET_CONTRACT.md`, `D-006`). Works headlessly on the Raspberry Pi 5 over LAN — the user opens a browser on any machine on the same network. Gives an Autodarts-style UX that users already understand. Single UI delivery stack means no second toolkit to maintain. FastAPI is already load-bearing for the data API; extending it to serve static assets costs nothing architecturally.
- **Consequences:** FastAPI is now load-bearing for the operator experience, not just the data API. UI changes ship as static assets served under `src/darts_detector/ui/` (Jinja2 templates + static files). Each UI surface lives in its own subdirectory (`ui/camera_picker/`, `ui/calibration/`, `ui/debug/`). The camera picker entry point opens the browser automatically on first run. The calibration assistant and debug console will follow the same pattern in their respective phases.

## D-018: UX Quality Is A First-Class Requirement

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Every user-facing surface must be designed to be obvious on first use. A feature that works correctly but is painful to set up will be treated as broken.
- **Why:** The user's exact words: "users will not use it if it is hard to setup." An open-source project with a hard setup experience will not build a community. The camera picker, calibration workflow, and operator display are the first things a new user sees; they set the tone for the entire project.
- **UX Quality Checklist (binding for every phase that ships a UI surface):**
  1. **Visible state** — every screen shows the current system state. No silent waiting.
  2. **Live feedback** — actions produce immediate visual confirmation (e.g. camera preview updates when the user changes a dropdown).
  3. **Plain-language errors** — errors are explained in terms a non-developer understands. No raw exception tracebacks in the UI.
  4. **Sensible defaults** — fields are pre-filled with the most common values. The user should be able to click through without reading docs.
  5. **No required CLI step for first-time setup** — the recommended flow for a new user must be achievable entirely through the browser UI.
  6. **LAN accessible** — the UI must work from any browser on the same network (not just `localhost`). Useful when the Pi is headless.
  7. **No external JS frameworks** — vanilla JS only, no npm, no build step. Keeps the project dependency footprint minimal and the UI auditable.
- **Consequences:** Phases 1 (camera picker), 3/3.5 (calibration assistant), 9 (debug UI), and any future operator display must be reviewed against this checklist before the phase is declared complete. `test-qa` includes a UX checklist review as part of phase sign-off.

## D-019: User-Configurable Per-Camera Resolution And FPS; 30 FPS As Default Baseline

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** `cameras.yaml` supports a per-camera `resolution` (from canonical menu: 1920×1080, 1280×720, 800×600, 640×480) and `fps` (from canonical menu: 60, 30, 25, 20, 15). **Defaults: 1280×720 @ 30 FPS.** The project does NOT require 60 FPS for accuracy targets; 25 FPS gives acceptable accuracy per well-established deterministic darts scoring implementations.
- **Why:** User hardware varies widely (laptop webcam to dedicated Raspberry Pi rig). Autodarts and comparable deterministic systems run at 25–30 FPS. A thrown dart tip is stationary for many frames after impact — the pipeline depends on settling-period geometry, not sub-30 FPS motion capture. Forcing 60 FPS as a baseline raises USB bandwidth requirements unnecessarily and causes the Phase 1 smoke test to fail on typical laptop webcams.
- **Consequences:**
  - Default FPS changes from 60 to 30 in `cameras.yaml` defaults, in `config/cameras.yaml` examples, and in all profile examples.
  - Latency budget in `LATENCY_BUDGET.md` is re-derived for 30 FPS (33.3 ms frame interval); the 60 FPS budget is preserved for reference tagged with its regime.
  - The camera tuning UI (Phase 1.5, added by this decision) must present discrete resolution and FPS menus from the canonical lists above rather than free-text fields.
  - Calibration must be regenerated whenever resolution changes (intrinsics depend on resolution); the UI must enforce this.
  - Accuracy target (~98%) applies across the full envelope (down to 640×480 @ 15 FPS). Detection geometry must not assume a fixed resolution.
- **Supersedes:** The 60 FPS assumption implicit in `LATENCY_BUDGET.md`'s original capture budget and in the `cameras.yaml` example in `CONFIGURATION.md`. Those documents are updated in the same change; original values are preserved with "prior to D-019" labels where useful.

## D-020: Image Tuning Precedes Calibration; Calibration Is Invalidated By Tuning Changes

- **Date:** 2026-05-17
- **Status:** accepted
- **Decision:** Per-camera image tuning — exposure, brightness, contrast, gain, gamma, white balance, saturation, sharpness, backlight compensation — MUST be configured and saved BEFORE calibration is performed. A calibration profile is only valid for the exact tuning settings it was captured under. If tuning changes after calibration, the calibration is invalidated.
- **Why:** Calibration captures the geometric and photometric response of the camera at one operating point. Exposure affects where an edge appears in pixel space; white balance affects colour-channel weighting used by thresholds; gamma affects the apparent brightness of the board surface. A calibration captured at one tuning state is not reliable when the camera operates under different tuning. The sensor response is parameterised by tuning — calibration captures one operating point only.
- **Consequences:**
  - Phase ordering: Phase 1 (camera selection) → Phase 1.5 (image tuning UI, covering ALL controls not just resolution/FPS) → Phase 3 (calibration). This is non-negotiable.
  - Calibration profiles must record a fingerprint (SHA-256 hash) of the camera tuning settings in force when the calibration was captured.
  - At runtime and at the start of the calibration assistant, the system must compare the current tuning settings against the fingerprint stored in the active calibration profile.
  - If tuning has changed since calibration, the system must either auto-invalidate the calibration or display a prominent warning and offer a "Recalibrate" action.
  - The calibration UI must show: "Current tuning matches calibration? Yes / No" and highlight mismatches field-by-field where practical.
  - The Phase 1.5 tuning UI "Save and proceed to calibration" button must warn the user if a prior calibration exists and will be invalidated.
  - This applies to every tuning field that affects the camera image: resolution, rotation, crop, exposure, gain, brightness, contrast, white balance, gamma, saturation, sharpness, backlight compensation.
  - FPS does NOT invalidate calibration geometry (it is informational only), but IS recorded in the profile for diagnostics.

---

## How To Add A Decision

1. Append a new entry with the next `D-NNN` number.
2. Date it (absolute date, never "today").
3. State the decision in one or two sentences.
4. Write the *why* — the constraint, incident, or tradeoff that drove it.
5. State the consequences for code, agents, or contracts.
6. Update [MASTER_PLAN.md](MASTER_PLAN.md) if the decision changes scope, contracts, or phase order.
