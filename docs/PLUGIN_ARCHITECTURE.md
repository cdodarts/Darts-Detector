# Plugin Architecture

The darts detector is designed from day one to support third-party plugins. This is a hard constraint from the [Project Charter](PROJECT_CHARTER.md), not an afterthought.

This document defines the plugin surface: what plugins can do, what they cannot do, how they load, and how they are versioned. It is **a stub for MVP** — the plugin loader itself ships post-MVP — but the rules and the public-API boundary it depends on must be respected from Phase 1 so that retrofitting doesn't require breaking changes later.

## Goals

- Let community contributors add overlays, scoreboards, match modes, integrations (Discord, Twitch, OBS overlay, MQTT, etc.) without touching core.
- Keep core small, stable, and inspectable.
- Prevent plugins from destabilising detection, scoring, or latency.
- Make it possible to ship plugin support post-MVP without rewriting core.

## Non-Goals

- Plugins are NOT allowed to replace detection algorithms in MVP. (A future RFC may add this as a separate plugin tier.)
- Plugins are NOT a way to add ML to the runtime. The no-runtime-ML rule applies to plugins too.
- Plugins are NOT a way to bypass calibration self-test.

## Plugin Categories

Defined now even though most are post-MVP, so the public API surface is shaped correctly from the start:

| Category | When | Description |
| --- | --- | --- |
| **Event Consumers** | MVP via WebSocket | Connect to the WebSocket and consume `Dart`, `CalibrationStatus`, `CameraStatus`, `Error` events. The wire format IS the plugin surface for this category. No code lives in this repo. |
| **Overlay / UI Plugins** | Post-MVP | Render scoreboards, statistics, replay views. Subscribe to events, render to their own UI. |
| **Match-Mode Plugins** | Post-MVP | Implement game modes (501, Cricket, Round-The-Clock, etc.). Subscribe to `Dart` events, hold their own state, expose their own UI/API. |
| **Output Adapters** | Post-MVP | Forward events to third-party services (MQTT, Home Assistant, Discord bots, etc.). |
| **Calibration Helpers** | Post-MVP | Provide alternative or assisted calibration workflows. Must produce profiles that validate against `schemas/calibration-profile.schema.json`. |
| **Detection Adapters** | Post-MVP, RFC required | Inject alternative detection backends. Heavily constrained; subject to the same accuracy and latency tests as core. |

## The Public API Boundary

Plugins (when supported) import from `src/darts_detector/api_public/` only. Everything else is internal.

The public API at MVP is intentionally tiny:

```text
darts_detector.api_public/
  events/        — Pydantic models or TypedDicts for every event type
  schemas/       — re-exports of JSON Schema paths
  enums/         — Section, Outcome, CalibrationStatus, etc.
  constants/     — Standard board dimensions
  __init__.py    — public exports only
```

Note: at MVP we do NOT export detection internals, calibration internals, or scoring internals. The wire format (WebSocket events) is the integration point.

The public API grows by RFC. Each addition needs:

- A documented use case.
- A stability tier (`@public-stable` or `@public-experimental`).
- Tests that lock in the signature.
- An entry in the changelog under "Added (public API)".

## Plugin Loading (Post-MVP Design)

When the plugin loader ships, it will:

1. Discover plugins in `~/.config/darts-detector/plugins/` and `<repo>/plugins/`.
2. Read each plugin's manifest (`plugin.toml`):
   ```toml
   [plugin]
   name = "discord-bot"
   version = "0.3.0"
   author = "..."
   license = "GPL-3.0-or-later"
   entry_point = "discord_bot.main:register"
   core_api_min = "1.2.0"
   core_api_max = "1.x"
   category = "output-adapter"
   ```
3. Verify `core_api_min`/`core_api_max` are compatible with the running core version (see [VERSIONING.md](VERSIONING.md)).
4. Verify the license is GPL-3.0-compatible.
5. Call the plugin's `register()` function with a `PluginContext` that exposes the public API only.
6. Sandbox plugin failures: a crashing plugin MUST NOT bring down detection. Plugin errors emit an `Error` event with `code: "PLUGIN_FAILED"`, `severity: "warning"`, and `details.pluginName`.

Plugins run in the same Python process for performance, but are isolated by:

- Importing only from `darts_detector.api_public`.
- Receiving events via an asyncio queue, not a direct callback (so a slow plugin can't block the hot path).
- A per-plugin time budget; plugins exceeding it are logged and may be auto-disabled.

## What Plugins Are Allowed To Do

- Read events from the queue.
- Render their own UI in their own window or web page.
- Open their own sockets, HTTP endpoints, files.
- Maintain their own state.
- Declare their own config (validated against their own JSON Schema, stored under `~/.config/darts-detector/plugins/<plugin-name>/config.yaml`).
- Emit their own log entries to a plugin-scoped logger.

## What Plugins Are NOT Allowed To Do

- Modify the baseline frame.
- Modify a calibration profile.
- Skip the calibration self-test.
- Override scoring results before they are emitted.
- Import from anywhere other than `darts_detector.api_public`.
- Block the detection hot path.
- Run ML on the dart-detection path.

Violations cause the plugin to be refused at load time, with a clear error.

## Plugin Discovery Of Events At MVP

Before the in-process plugin loader exists, the only sanctioned plugin path is **the WebSocket**. This is good — it forces every plugin to use the same stable wire contract that we already version. It also means many useful "plugins" can be written in any language, not just Python.

The MVP plugin story is therefore: **write a WebSocket client.**

The plugin author writes a separate program in any language, connects to the darts detector WebSocket, consumes events, and does whatever. The schema is documented in [API_AND_WEBSOCKET_CONTRACT.md](API_AND_WEBSOCKET_CONTRACT.md) and validated by [dart-event.schema.json](../schemas/dart-event.schema.json).

This is by design. It matches how OBS supports WebSocket-based third-party tools (the `obs-websocket` plugin model).

## Why We Lock The Public API Boundary Now (Even Pre-Plugin-Loader)

Two reasons:

1. **It costs nothing now.** Creating `src/darts_detector/api_public/` and putting our event types in it is free. Adding it later means rewriting every plugin's imports.
2. **It forces clean separation.** Core code that accidentally imports detection internals into the API layer reveals coupling we need to fix anyway. Better to catch it during Phase 1 than during Phase 12.

## What Future Agents Must Do

- Treat `src/darts_detector/api_public/` as a stable surface from the moment it exists.
- Refuse to add anything to it without a documented use case.
- When adding a new internal module, ask: "does this need a public face?" Usually the answer is no.
- When changing an internal module, do NOT update the public API to match unless explicitly required.
- Route plugin-architecture changes through the RFC process in [PROJECT_CHARTER.md](PROJECT_CHARTER.md).
