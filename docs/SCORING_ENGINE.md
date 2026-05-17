# Scoring Engine

The scoring engine converts calibrated board coordinates into dartboard scores. It must be independent from camera capture, image processing, and WebSocket transport.

## Responsibilities

- Convert `(x, y)` board coordinates into section, number, multiplier, and score.
- Handle misses and all standard scoring areas.
- Report confidence alternatives near borders.
- Provide deterministic, unit-tested behavior.

## Board Coordinate System

The board coordinate system is **integer millimetres** (locked decision `D-004` in [DECISIONS.md](DECISIONS.md)):

```text
(0, 0)   = center of bull
+y       = toward the centre of the 20 segment
+x       = right-handed 2D convention (90 deg clockwise from +y when viewed from player)
unit     = mm (integer)
radius   = sqrt(x*x + y*y)            (computed in mm)
angle    = atan2(y, x), adjusted by calibrated board rotation
```

The scoring engine accepts only integer-mm coordinates. Fusion is responsible for any unit conversion. The wire format also uses mm (`coordinates.unit: "mm"` in the Dart event).

## Standard Board Dimensions

Standard steel-tip dartboard dimensions in millimetres (from centre):

| Boundary | Radius (mm) |
| --- | --- |
| Inner bull outer edge | 6.35 |
| Outer bull outer edge | 16.0 |
| Triple ring inner edge | 99.0 |
| Triple ring outer edge | 107.0 |
| Double ring inner edge | 162.0 |
| Double ring outer edge | 170.0 |

Triple ring wire-to-wire width is 8 mm; double ring is 8 mm. The scoring engine MUST use these as defaults and allow override via calibration profile if a non-standard board is used.

## Lookup Table Implementation

For performance and determinism, the scoring engine SHOULD precompute a 2D integer lookup table:

- Index: `(x, y)` in mm, offset to make indices non-negative.
- Cell value: an enum encoding `(section, multiplier)`.
- Size: roughly `360 mm × 360 mm` covering the catch ring, ~130 KB at one byte per cell.
- Rotation: precompute once per calibrated rotation, not per-dart.

Scoring then becomes a single array index plus a border-proximity check for alternatives. Total scoring stage budget: 5 ms (see [LATENCY_BUDGET.md](LATENCY_BUDGET.md)). This is achievable trivially with a lookup table.

## Segment Order

The official clockwise segment order is:

```text
20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5
```

The `20` segment is the orientation reference. Calibration determines where the centerline of the `20` segment lies in board coordinates.

## Ring Logic

The scoring engine classifies by radius first, then by angle.

| Region | Multiplier | Score Rule | Radius Range (mm, inclusive of inner edge, exclusive of outer) |
| --- | --- | --- | --- |
| Inner bull | Special | 50 | `[0, 6.35)` |
| Outer bull | Special | 25 | `[6.35, 16.0)` |
| Inner single | 1 | `number` | `[16.0, 99.0)` |
| Triple ring | 3 | `number * 3` | `[99.0, 107.0)` |
| Outer single | 1 | `number` | `[107.0, 162.0)` |
| Double ring | 2 | `number * 2` | `[162.0, 170.0)` |
| Outside double | 0 | Miss (`outcome: "missed"`) | `[170.0, ∞)` |

Boundary rule: inner edge inclusive, outer edge exclusive. This makes every mm coordinate fall in exactly one region with no ambiguity.

## Miss Logic

A coordinate is a miss when:

- It lies outside the double ring outer boundary (radius ≥ 170 mm).
- Calibration marks it outside the valid board area.
- Fusion produces a coordinate but the scoring engine cannot classify it safely.

Miss results MUST be emitted as a Dart event with `outcome: "missed"`, `section: "MISS"`, `number: 0`, `multiplier: 0`, `score: 0`. They MUST NOT be encoded as an absent event.

## Multiplier Calculation

For numbered segments:

```text
score = number * multiplier
```

For bulls:

```text
inner bull score = 50
outer bull score = 25
```

For miss:

```text
score = 0
multiplier = 0
section = "MISS"
```

## Section Naming

Recommended section names:

| Area | Example |
| --- | --- |
| Inner bull | `BULL` |
| Outer bull | `OUTER_BULL` |
| Single 20 | `S20` |
| Triple 20 | `T20` |
| Double 20 | `D20` |
| Miss | `MISS` |

The API contract should remain stable once these names are implemented.

## Border Alternatives

When a coordinate is close to a segment or ring border, the scoring engine should return plausible alternatives.

Examples:

- A coordinate just inside `T20` near the inner triple boundary may include `S20`.
- A coordinate near the `20`/`1` wire may include both segment numbers.
- A coordinate near the double outer edge may include `MISS`.

Alternatives should include section, number, multiplier, score, and confidence.

## Example Scoring Calculations

| Coordinate Meaning | Expected Result |
| --- | --- |
| Center point | `BULL`, score `50` |
| Within outer bull but outside inner bull | `OUTER_BULL`, score `25` |
| In single 20 wedge outside bull and outside triple/double rings | `S20`, score `20` |
| In triple 20 ring | `T20`, score `60` |
| In double 5 ring | `D5`, score `10` |
| Outside board scoring radius | `MISS`, score `0` |

## Unit Test Requirements

Unit tests must cover:

- All 20 segment numbers.
- Each multiplier region.
- Inner bull and outer bull.
- Miss outside double ring.
- Segment boundaries.
- Ring boundaries.
- Board rotation offset.
- Coordinates exactly on boundaries using documented tie-breaking rules.
- Confidence alternatives near borders.

## Tie-Breaking Rules

Boundary tie-breaking must be deterministic and documented in tests. Recommended approach:

- Exact boundary values are assigned using consistent inclusive/exclusive ring ranges.
- The primary result is the region selected by that rule.
- Adjacent regions appear in alternatives when within the configured border tolerance.

Do not rely on floating-point accident for border decisions.
