# API And WebSocket Contract

This document defines the JSON contracts for runtime events. The schema is **locked at the end of Phase 4** (see [DECISIONS.md](DECISIONS.md) `D-006`) and the canonical machine-readable form lives at [schemas/dart-event.schema.json](../schemas/dart-event.schema.json).

Once locked, breaking changes require either a major version bump and a parallel emit period, or a brand new event type.

## General Event Rules

- Events are JSON objects.
- Every event MUST include `version` (semver string, e.g. `"1.0.0"`).
- Every event MUST include `type`.
- Every event MUST include `eventId` (UUIDv4 string) — clients use this for dedupe and log correlation.
- Every event MUST include `timestamp` in ISO 8601 UTC with millisecond precision and `Z` suffix (e.g. `"2026-05-17T10:30:00.123Z"`).
- Every event MUST include a `producer` block describing the emitter.
- Field names use camelCase.
- Unknown fields MUST be ignored by clients (forward compatibility).
- Unknown enum values MUST be tolerated by clients (degraded handling allowed; crashing is not).
- Breaking changes require a new major version.

## Versioning Policy

The wire format uses semver:

- **Patch** (`1.0.0` → `1.0.1`): bug fixes, no schema change.
- **Minor** (`1.0.0` → `1.1.0`): additive fields, additive enum values, new optional event types. Existing clients keep working.
- **Major** (`1.0.0` → `2.0.0`): removed/renamed fields, changed field types, changed enum semantics. Requires:
  - A parallel emit period: producer emits both `v1` and `v2` shapes for at least one minor version cycle.
  - An ADR entry in [DECISIONS.md](DECISIONS.md) explaining why.
  - Client negotiation: clients connect with `?clientVersion=<semver>` and the producer downgrades responses if the major is older.

Producers MUST continue emitting required `1.x` fields for the lifetime of the `1.x` major series.

## The `extensions` Block

Every event MAY include an `extensions` object for fields that are not yet part of the stable contract. Rules:

- Keys MUST be prefixed `x-` (e.g. `x-velocity`, `x-impactAngle`).
- Clients MUST NOT depend on `extensions` fields for correctness.
- Producers MUST be able to disable `extensions` emission entirely (config flag).
- Promotion to a top-level stable field is allowed in a minor version bump; the old `x-` key MUST be emitted for at least one minor version after promotion.

This is the only sanctioned way to ship experimental fields without a major version bump.

## Dart Event

```json
{
  "version": "1.0.0",
  "type": "Dart",
  "eventId": "8d2f1c30-7a1b-4d5e-9b21-5a3f6c1e8d77",
  "timestamp": "2026-05-17T10:30:00.123Z",
  "producer": {
    "appVersion": "0.4.2",
    "schemaVersion": "1.0.0",
    "hardwareProfile": "pi5-balanced"
  },
  "throwContext": {
    "throwId": "f10e9b2c-4e3a-4d72-9b80-1a2b3c4d5e6f",
    "turnId": "c7d8e9f0-1a2b-3c4d-5e6f-7a8b9c0d1e2f",
    "dartIndex": 1
  },
  "outcome": "scored",
  "section": "T20",
  "number": 20,
  "multiplier": 3,
  "score": 60,
  "coordinates": {
    "x": 0,
    "y": 103,
    "unit": "mm"
  },
  "confidence": {
    "amount": 0.92,
    "alternatives": [
      {
        "section": "S20",
        "number": 20,
        "multiplier": 1,
        "score": 20,
        "confidence": 0.34
      }
    ]
  },
  "cameraEvidence": [
    {
      "cameraId": "cam1",
      "usable": true,
      "confidence": 0.86,
      "reason": "candidateAccepted"
    },
    {
      "cameraId": "cam2",
      "usable": true,
      "confidence": 0.91,
      "reason": "candidateAccepted"
    },
    {
      "cameraId": "cam3",
      "usable": false,
      "confidence": 0.12,
      "reason": "occluded"
    }
  ],
  "latency": {
    "landToEventMs": 412,
    "stageMs": {
      "capture": 18,
      "motion": 195,
      "diff": 41,
      "candidate": 72,
      "fusion": 28,
      "score": 1,
      "emit": 6
    }
  },
  "extensions": {}
}
```

### Required Fields For A Dart Event

- `version`, `type`, `eventId`, `timestamp`, `producer` (all events).
- `throwContext.dartIndex` (required); `throwId` and `turnId` (recommended, may be empty string in MVP).
- `outcome` — one of `"scored"`, `"missed"`, `"rejected"`.
- `coordinates` with `unit: "mm"` for v1.
- `confidence.amount`.
- `cameraEvidence` — one entry per *configured* camera (not just usable ones).
- `latency.landToEventMs` and `latency.stageMs` — required when measurable.

When `outcome` is `"rejected"`, `score`, `section`, `number`, and `multiplier` MUST still be present but MAY be set to the conservative best guess; `confidence.amount` MUST be below the configured rejection threshold; `confidence.alternatives` SHOULD list plausible scores.

When `outcome` is `"missed"`, `section` is `"MISS"`, `number` is `0`, `multiplier` is `0`, `score` is `0`.

## Section Enum

Closed enum for v1. Additions require a minor bump.

```text
BULL
OUTER_BULL
S1 .. S20    (single, 20 values)
D1 .. D20    (double, 20 values)
T1 .. T20    (triple, 20 values)
MISS
```

Total: 63 values.

## Outcome Enum

```text
scored      Dart detected and scored.
missed      Dart detected, landed outside the scoring area.
rejected    Detection failed safety checks; do not credit the dart.
```

## Calibration Status Event

```json
{
  "version": "1.0.0",
  "type": "CalibrationStatus",
  "eventId": "...",
  "timestamp": "2026-05-17T10:30:00.123Z",
  "producer": { "appVersion": "0.4.2", "schemaVersion": "1.0.0", "hardwareProfile": "pi5-balanced" },
  "status": "valid",
  "profileId": "default",
  "selfTestConfirmed": true,
  "message": "Calibration profile loaded and self-test confirmed by user",
  "cameraIds": ["cam1", "cam2", "cam3"],
  "projectionErrorMm": { "cam1": 1.2, "cam2": 1.4, "cam3": 1.1 }
}
```

Allowed `status` values: `missing`, `inProgress`, `valid`, `invalid`, `stale`.

`selfTestConfirmed` is `true` only after the user has confirmed alignment in the self-test (Phase 3.5).

## Camera Status Event

```json
{
  "version": "1.0.0",
  "type": "CameraStatus",
  "eventId": "...",
  "timestamp": "2026-05-17T10:30:00.123Z",
  "producer": { "appVersion": "0.4.2", "schemaVersion": "1.0.0", "hardwareProfile": "pi5-balanced" },
  "cameraId": "cam1",
  "name": "Left camera",
  "status": "streaming",
  "resolution": { "width": 1280, "height": 720 },
  "fps": 60,
  "effectiveFps": 59.7,
  "droppedFrames": 0,
  "settings": {
    "exposure": "manual",
    "whiteBalance": "manual"
  }
}
```

Allowed `status` values: `unknown`, `connected`, `streaming`, `degraded`, `disconnected`, `error`.

## TurnState Event

Added in schema version `1.1.0` (additive minor bump from `1.0.0`).

Emitted on every transition of the throw lifecycle state machine ([DETECTION_PIPELINE.md](DETECTION_PIPELINE.md) Phase 7.5). Clients use this to render takeout UI, gate scoreboards, or trigger external integrations.

```json
{
  "version": "1.1.0",
  "type": "TurnState",
  "eventId": "...",
  "timestamp": "2026-05-17T10:30:00.123Z",
  "producer": { "appVersion": "0.4.2", "schemaVersion": "1.1.0", "hardwareProfile": "pi5-balanced" },
  "state": "takeoutInProgress",
  "previousState": "awaitingTakeout",
  "turnId": "c7d8e9f0-1a2b-3c4d-5e6f-7a8b9c0d1e2f",
  "dartIndex": 3,
  "dartsThisTurn": 3,
  "handPresent": true,
  "boardClear": false,
  "reason": "handDetected"
}
```

Allowed `state` values:

- `awaitingThrow` — ready for next dart.
- `motion` — motion detected; dart in flight or scene unstable.
- `settling` — motion stopped; waiting for mask to stabilise.
- `scoring` — computing fusion + score (transient).
- `awaitingTakeout` — three darts scored, waiting for player to remove them.
- `takeoutInProgress` — hand currently in the board area.
- `takeoutIncomplete` — hand left but darts still present.
- `turnReset` — takeout confirmed; baseline updating (transient).

Allowed `reason` values (stable short codes):

- `motionDetected`, `motionSettled`, `dartScored`, `turnFull`, `handDetected`, `handRetracted`, `boardClearConfirmed`, `boardNotClear`, `manualReset`, `bounceTimeout`, `cameraInsufficient`.

`handPresent` and `boardClear` are convenience booleans; clients can rely on `state` alone.

`dartsThisTurn` is configurable per [DECISIONS.md](DECISIONS.md) `D-015`; default 3.

## Error Event

```json
{
  "version": "1.0.0",
  "type": "Error",
  "eventId": "...",
  "timestamp": "2026-05-17T10:30:00.123Z",
  "producer": { "appVersion": "0.4.2", "schemaVersion": "1.0.0", "hardwareProfile": "pi5-balanced" },
  "code": "INSUFFICIENT_CAMERAS",
  "severity": "warning",
  "message": "Only one usable camera produced a dart candidate",
  "recoverable": true,
  "details": { "usableCameraCount": 1 }
}
```

`severity` is one of `info`, `warning`, `error`, `fatal`.

Error events MUST NOT expose stack traces by default.

## Producer Block

Required on every event.

```json
{
  "appVersion": "0.4.2",
  "schemaVersion": "1.0.0",
  "hardwareProfile": "pi5-balanced"
}
```

- `appVersion`: the running application semver.
- `schemaVersion`: the wire-format semver (matches the top-level `version`).
- `hardwareProfile`: one of the documented performance profiles (see [CONFIGURATION.md](CONFIGURATION.md)).

## Throw Context Block

```json
{
  "throwId": "uuid",
  "turnId": "uuid",
  "dartIndex": 1
}
```

- `throwId`: unique per detected throw. Lets clients group debug data and event sequence.
- `turnId`: unique per turn (typically three throws). MVP may leave it as empty string if no turn concept exists yet; clients must tolerate that.
- `dartIndex`: 1, 2, or 3 within the turn. MVP may set this to 1 if turn tracking isn't yet implemented.

## Confidence Object

```json
{
  "amount": 0.92,
  "alternatives": []
}
```

- `amount` is a number from `0.0` to `1.0`.
- `amount` is NOT a calibrated probability. Treat as ranking until validated against labelled data.
- `alternatives` is an array of plausible alternate scores, sorted most to least plausible.
- Low-confidence events MUST include meaningful alternatives when available.
- Alternatives MUST NOT duplicate the primary result.

## Alternatives Object

```json
{
  "section": "S20",
  "number": 20,
  "multiplier": 1,
  "score": 20,
  "confidence": 0.34
}
```

Each alternative is a complete score, not a delta.

## Coordinate Object

```json
{ "x": 0, "y": 103, "unit": "mm" }
```

- `(0, 0)` is the bull centre.
- `+y` points toward the centre of the `20` segment.
- `unit` is `"mm"` for v1. Future major versions may add other units.
- Values are integers in v1.

## Camera Evidence Object

```json
{
  "cameraId": "cam1",
  "usable": true,
  "confidence": 0.86,
  "reason": "candidateAccepted"
}
```

- Producers SHOULD include one entry per *configured* camera (not just usable ones) so consumers see which cameras were considered.
- `reason` is a stable short code. Documented values: `candidateAccepted`, `noCandidate`, `lowConfidence`, `occluded`, `disagreement`, `cameraOffline`, `calibrationInvalid`.

## Latency Object

```json
{
  "landToEventMs": 412,
  "stageMs": {
    "capture": 18,
    "motion": 195,
    "diff": 41,
    "candidate": 72,
    "fusion": 28,
    "score": 1,
    "emit": 6
  }
}
```

- `landToEventMs` is the time from estimated dart-landing instant to event emission.
- `stageMs` keys match the stages in [LATENCY_BUDGET.md](LATENCY_BUDGET.md).
- Producers SHOULD emit `0` for stages that didn't run rather than omit them, to keep monitoring dashboards simple.

## Client Negotiation

A WebSocket client SHOULD include a `clientVersion` query parameter when connecting:

```text
ws://host:port/path?clientVersion=1.0.0
```

If the producer's current major matches, events are emitted as-is. If the producer's major is newer than the client's, the producer SHOULD downgrade events to the client's last supported major for the duration of a parallel-emit window. After that window expires, the connection is rejected with code `4001 unsupported_client_version`.

If `clientVersion` is absent, the producer assumes the latest version.

## JSON Schema

The authoritative schema lives at [schemas/dart-event.schema.json](../schemas/dart-event.schema.json). Producers MUST validate every event against this schema before emitting in development and CI builds. Validation MAY be disabled in production for performance, but the contract is the schema.

Clients SHOULD validate incoming events for the first connection and log mismatches; continuous validation is optional.
