# tests/system — tour scripts run on a real robot

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-01 · **Status:** stable

A tour is a **geometry the robot drives, scored against what it
believed it did**. This directory holds the format, the runner, and the
figures. Nothing here is pytest and nothing here runs in CI — every
test in it needs a board on a bench.

```
uv run --with numpy --with matplotlib python tests/system/run_tour.py \
    tours/square.tour --host localhost --out reports/tours-<date>
```

Output is a PNG (path + wheel-speed panels) and a JSON of every
telemetry frame, so a run can be re-analysed without re-driving it.

## The `.tour` format — `tourfile.py`

One directive per line; the grammar is in `tourfile.py`'s docstring.
`TWIST` is the single motion directive and covers all three shapes,
which is the whole point of the format:

| form | shape |
|---|---|
| `vx` + `dist` | straight |
| `omega` + `angle` | pivot in place |
| `vx` + `omega` + `angle` | **arc** of radius `r = vx / omega` |

The arc form exists because `MOVE_X` takes a body distance *and* a
rotation, so a constant-curvature segment is one command the motion
engine shapes end to end. Chopping a circle into chords instead would
put an accel ramp and an end taper inside every chord, and the robot
would stutter through a polygon.

**Arc segments must stay under 50°.** `moveX()` splits any move with a
nonzero distance and |rotation| ≥ `kTurnFirstAngleRad` (0.8726 rad =
50°) into a pivot *then* a straight. MEASURED 2026-09-01, gopiv,
`reports/tours-20260901/`: `circle.tour` written as one 360° arc drove
a **942 mm straight line** (closure 942.2 mm), and 90° arcs drew a
square. Every circular figure here is therefore built from 45° arcs.

## The figures

| tour | shape | closure, gopiv bench 2026-09-01 |
|---|---|---|
| `square.tour` | 600 mm square, 4 legs + 4 pivots | **5.0 mm** |
| `circle.tour` | one circle, 8 × 45° arcs | 17.8 mm |
| `infinity.tour` | figure-8, two circles r=300 mm, 16 arcs | 25.5 mm |

Closure is the distance from the finish pose back to the start pose in
**pure odometry** — no camera. That is the right score for these: it
asks whether commanded moves produce the intended *believed* geometry,
and wheel-size or slip calibration cannot flatter it, because the same
constants convert counts to millimetres in both directions. A camera
run answers a different question (does believed match physical) and
belongs in a field report, not here.

`infinity.tour` is sized to the playfield: r = 300 mm spans 4r × 2r =
1200 × 600 mm against a ±671.5 × ±446.5 mm centre limit. r = 350 would
span 1400 mm and does not fit.

Each tour's `SET` lines carry the tuned constants
(`pivot_overrun`, `twist_hold_gain`, `speed_floor`, `yaw_taper`) so a
run is reproducible without remembering the configuration — see
`reports/gopiv-closure-20260901.md` for where those numbers came from
and the hard limits on each.

## The same figures, on the robot

`test/test.ts` implements `RUN:square`, `RUN:infinity` and `RUN:spline`
as on-robot programs over `diffDrive.move(distance_cm, yaw_deg)`. Those
need no host in the loop but also produce no chart; use them to drive a
figure from a single wire command, and these `.tour` files to *measure*
one.
