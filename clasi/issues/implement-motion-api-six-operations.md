---
status: pending
---

# Implement the Motion API — six operations, on two primitives

Implement the full six-operation Motion API specified in
`/Volumes/Proj/proj/RobotProjects/radio-robot-lib/docs/design/motion-api.md`
(canonical). That document is the specification authority; this repo is the
MakeCode/micro:bit implementation of it.

## The six operations

Two axes: **what you command** (wheels / body / position) crossed with **how
it is bounded** (`x` a displacement, `v` a velocity). `go_to` is a deliberate
asymmetry — inherently positional, so its second letter names a **frame**
instead.

| method | wire verb | arguments | bounded by |
|---|---|---|---|
| `wheelsX` | `WHEELS_X` | `left` `right` `cruise` `timeout` | per-wheel encoder distance |
| `wheelsV` | `WHEELS_V` | `left` `right` `duration` | time — `duration` **is** the lease |
| `moveX` | `MOVE_X` | `distance` `rotation` `cruise` `timeout` | body displacement and heading |
| `moveV` | `MOVE_V` | `v_x` `omega` `duration` | time |
| `goToR` | `GO_TO_R` | `x` `y` `speed` `arrive` `timeout` | arrival within tolerance |
| `goToW` | `GO_TO_W` | `x` `y` `speed` `arrive` `timeout` | arrival within tolerance |

Units: `[mm]` for `left`/`right`/`distance`/`x`/`y`/`arrive`, `[mm/s]` for
`cruise`/`speed`/`v_x`, `[deg]` for `rotation`, `[deg/s]` for `omega`, `[ms]`
for `timeout`/`duration`. **One name per operation everywhere** — the wire
verb is the method name upper-cased, so a wire log and a program read as the
same vocabulary.

## The whole design in four lines

They are not six mechanisms; they are four translations onto two primitives
(`motion-api#2`):

```
move_v(v_x, omega)     ==  wheels_v(v_x − omega·b/2,  v_x + omega·b/2)
move_x(distance, rot)  ==  wheels_x(distance − rot·b/2, distance + rot·b/2)
go_to_r(x, y)          ==  move_x(arcLength, 2·atan2(y, x))
go_to_w(x, y)          ==  read pose → world-to-body → go_to_r
```

> Every motion is one or more constant-ratio segments, each bounded by a
> displacement or by a time.

## Load-bearing rules

- **`b` is the EFFECTIVE track width**, `trackwidth / rotational_slip`, derived
  at boot as a *method* not a stored field so config read-back never reports a
  derived number as measured. (`motion-api#2.1`)
- **Never bend `trackwidth` to make turns land.** It is the one independently
  verifiable number in the config — a caliper reaches it. Scrub belongs in
  `rotational_slip`, separately measurable against camera truth. Keeping them
  apart is what lets a bad turn be diagnosed rather than merely compensated.
  This matches the standing instruction on this project: the measured 114.2 mm
  track width is never "corrected".
- **Sign convention is CCW-positive** — positive `omega`/`rotation` turns left
  and increases camera yaw; the left wheel is the slower one. Do not re-derive
  this from cable order; the project has shipped that bug and patched it four
  times downstream.
- **Cruise lives in the X-forms only.** A V-form's commanded velocity IS its
  cruise (still reached through the ramp). `omega` is slaved to `v_x` — one
  ratio held through the ramp, because separately profiling yaw bends the path
  during acceleration.
- **Stopping is two verbs, not two flavours of one**: `stop()` jerk-limited
  ramp (default), `stop(immediate)` zero now accepting jerk, `estop()` zero now
  and **latched**. (`motion-api#3.7`)
- **Three execution modes** (background/fiber, manual tick, blocking) apply
  uniformly. Over the wire "tick" means drain telemetry already pushed and test
  completion — **it never means poll**, measured to matter (197.5 mm → 0.3 mm).
  (`motion-api#5`, `#5.3`)
- Angles are **degrees at the API, milliradian integers on the wire**; the
  conversion lives in the binding, in one place. (`motion-api#9.1`)

## What already exists here to build on

This repo is not starting from zero and should not be rewritten from zero:

- `src/main.ts` already has `move`, `goTo`, `goToWorld`, `startMove`,
  `driveTick`, plus pose and world-pose surfaces.
- `src/shims.cpp` has the segment executor: ramp, end-of-move taper, signed
  yaw progress with wrong-way abort, settle ticks.
- `src/diffdrive.cpp` is the wheel kernel with the lease watchdog.
- `goToWorld` already does the world→body→arc solve that `go_to_w` needs.

The work is largely **restructuring these onto the specified six-operation
surface with the specified names and units**, not inventing new motion code.
Read `motion-api#3.1`–`3.7` for per-operation behaviour before changing any of
it — particularly `#3.3`'s pivot-vs-blend threshold, which is what the current
`turnFirstDeg` approximates.

## Two hard-won behaviours that must survive the refactor

1. **The yaw taper applies only to a pure turn.** In an arc, twist and velocity
   are locked by curvature, so the distance taper already scales yaw and a
   second independent yaw taper double-counts — measured on vevov as three legs
   pinned at the 25% floor (5.0/5.3/5.1 cm/s against a commanded 20) while the
   one leg that took the straight branch ran 20.4. See `src/shims.cpp`
   `serviceMove`, commit `bd9f005`.
2. **A move that ends must still deliver the kernel's neutral to the motors** —
   the staged zero needs one more `kernel.step()` after `serviceMove()` clears
   `moveActive`, or the wheels coast at full duty until the watchdog. Commit
   `3e919e5`.

## Testing

Same constraint as [[implement-protocol-v6-wire-grammar-and-reliability]]:
there is no test suite in this repo, and the kinematics are exactly what CAN be
tested on a laptop — the algebra above is pure arithmetic over a fake motor
port.

- unit-test the four translations against hand-computed values, including the
  effective-track-width correction
- test the degenerate cases the doc calls out: `wheels_x(+d,−d)` is a pivot,
  `wheels_x(d,d)` a straight line, `move_x(d,0)` straight, `move_x(0,θ)` a pivot
- test sign convention explicitly, in both directions, so a future cable-order
  "fix" fails a test instead of shipping
- test the pivot-vs-blend split in `move_x` at its threshold
- drive them through a fake `Motor` port and assert on the commanded segments,
  not on a robot

Hardware validation comes after, with the stakeholder present — do not treat a
green laptop suite as proof the robot drives correctly.
