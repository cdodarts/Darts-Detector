# Repository Layout

The planned directory structure once implementation begins. Agents must respect these boundaries — each top-level folder maps to an architectural module from [ARCHITECTURE.md](ARCHITECTURE.md).

## Top-Level Tree

```text
darts-detector/
  docs/                         # Authoritative documentation
  src/
    darts_detector/             # Python package root
      __init__.py
      api_public/               # STABLE PUBLIC API — plugins import only from here
        __init__.py
        events/                 # Event types (Dart, TurnState, CalibrationStatus, CameraStatus, Error)
        enums/                  # Section, Outcome, TurnStateName, TurnStateReason, ...
        constants/              # Standard board dimensions
        schemas/                # Schema path re-exports
      capture/                  # Phase 1, 2 — USB camera capture, settings (@internal)
      config/                   # Config loading and validation (YAML) (@internal)
      calibration/              # Phase 3, 3.5, 10 — board calibration (@internal)
        manual/
        assist/                 # Phase 10 only
        validate/
      scoring/                  # Phase 4 — coordinate -> score (@internal)
      detection/                # Phase 5, 5.5, 6 (@internal)
        motion/                 # Phase 5
        takeout/                # Phase 5.5 — hand + board-clear signals
        candidates/             # Phase 6
      fusion/                   # Phase 7 — multi-camera fusion (@internal)
      lifecycle/                # Phase 7.5 — throw state machine, baseline updates (@internal)
      api/                      # Phase 8 — WebSocket server (@internal)
      events/                   # Internal event factories / validators (@internal)
      debug/                    # Phase 9 — overlays, replay (@internal)
        overlays/
        replay/
      diagnostics/              # Logging, metrics, latency timers (@internal)
      cli/                      # Entry points (@internal)
  plugins/                      # In-tree plugins (post-MVP)
    examples/                   # Example WebSocket consumers in various languages
  config/
    cameras.yaml                # Per-camera settings
    profiles/
      development.yaml
      pi5-balanced.yaml
      pi5-low-latency.yaml
      diagnostic-high-quality.yaml
    calibration/                # JSON profiles (machine-written)
  schemas/
    dart-event.schema.json
    calibration-profile.schema.json
    config.schema.json
  tests/
    unit/
      scoring/
      calibration/
      events/
      config/
      lifecycle/                # State machine unit tests
    integration/
      capture/
      api/
    replay/                     # Phase 4.5+ — replay-based detection tests
    smoke/                      # Phase-level smoke tests
  datasets/
    throws/                     # Saved labelled throws (gitignored by default)
  tools/
    metrics/                    # Phase 12 — accuracy/latency reports
    migrate_config/             # Config schema migrations
    migrate_calibration/        # Calibration profile migrations
    calibration_helpers/
    validate_events/            # CLI: validate a saved event log against the schema
  research/                     # Phase 11 — automatic calibration research
  .claude/
    agents/                     # Subagent definitions (project-manager + specialists)
  .github/
    ISSUE_TEMPLATE/             # bug, feature, rfc templates
    PULL_REQUEST_TEMPLATE.md
    workflows/                  # CI: tests, schema validation, replay regression
  LICENSE                       # GPL-3.0-or-later short notice (canonical text in COPYING)
  COPYING                       # Canonical GPL-3.0 text (run the curl command in LICENSE)
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  CLAUDE.md                     # Pointer for AI agents — read this first
  README.md
  pyproject.toml
  CHANGELOG.md                  # Keep A Changelog format
```

## Module Boundary Rules

- `api_public/` MUST NOT import from any internal module. Internal modules import the public types they need by mirroring/re-exporting only — no upward imports.
- `scoring/` MUST NOT import from `capture/`, `detection/`, `fusion/`, or `lifecycle/`. It accepts mm coordinates and returns scores. Period.
- `detection/` MUST NOT import from `api/`, `events/`, or `lifecycle/`. It produces internal candidate and signal objects, not wire events or state transitions.
- `detection/takeout/` produces `handPresent` and `boardClear` signals. It does NOT decide what they mean — that's the state machine's job.
- `fusion/` MUST NOT import from `detection/`'s internals — only the public candidate type.
- `lifecycle/` is the **only** module allowed to update the current baseline. It consumes signals from `detection/motion`, `detection/takeout`, and `fusion/`. It produces `TurnState` events for `api/` to serialise.
- `api/` is the only module that imports event types from `events/` and `api_public/events/`.
- `debug/` MAY read from anywhere but MUST NOT mutate anything outside `debug/`.
- `replay/` MUST use the same `detection/`, `fusion/`, and `lifecycle/` code paths as live capture. No parallel implementations.
- `plugins/` MUST import only from `darts_detector.api_public`. CI enforces this with `import-linter`.

## Naming Conventions

- Python: `snake_case` for files and functions, `PascalCase` for classes.
- Config files: `kebab-case.yaml`.
- JSON event fields: `camelCase` (matches the WebSocket contract).
- Camera IDs: stable lowercase strings like `cam1`, `cam2`, `cam3`.

## What Goes Where — Quick Reference

| If you are changing… | Edit in… |
| --- | --- |
| The Dart event schema | `schemas/dart-event.schema.json` + `docs/API_AND_WEBSOCKET_CONTRACT.md` |
| The TurnState event | `schemas/dart-event.schema.json` + `docs/API_AND_WEBSOCKET_CONTRACT.md` + `src/darts_detector/api_public/events/` |
| Scoring rules | `src/darts_detector/scoring/` + `docs/SCORING_ENGINE.md` |
| Calibration model | `src/darts_detector/calibration/` + `docs/CALIBRATION_SYSTEM.md` |
| Frame differencing | `src/darts_detector/detection/motion/` + `docs/DETECTION_PIPELINE.md` |
| Hand / board-clear detection | `src/darts_detector/detection/takeout/` + `docs/DETECTION_PIPELINE.md` |
| Tip estimation | `src/darts_detector/detection/candidates/` + `docs/DETECTION_PIPELINE.md` |
| Multi-camera fusion | `src/darts_detector/fusion/` + `docs/DETECTION_PIPELINE.md` |
| Throw lifecycle state machine | `src/darts_detector/lifecycle/` + `docs/DETECTION_PIPELINE.md` |
| WebSocket events | `src/darts_detector/api/` + `src/darts_detector/events/` + `docs/API_AND_WEBSOCKET_CONTRACT.md` |
| Public API surface | `src/darts_detector/api_public/` + RFC + `docs/PLUGIN_ARCHITECTURE.md` |
| Camera config | `src/darts_detector/config/` + `config/cameras.yaml` + `docs/CONFIGURATION.md` |
| Latency budgets | `docs/LATENCY_BUDGET.md` (do not change without measurement) |
| A documented decision | Append to `docs/DECISIONS.md` |
| A risk you spotted | Append to `docs/RISKS.md` |
| A breaking contract change | RFC issue → `docs/DECISIONS.md` ADR → migration tool in `tools/` → schema bump |

## Things That Do NOT Belong In This Repo (MVP)

- Player accounts, match management, league features.
- Mobile app code.
- Cloud sync services.
- ML model weights or training code (research/ exception only).
- Anything in `node_modules/` — this is a Python project.
