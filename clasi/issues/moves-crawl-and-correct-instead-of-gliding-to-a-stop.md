---
status: pending
---

# Moves crawl, hunt and reverse instead of gliding to a stop

## Description

Stakeholder observation, watching gopiv drive the tour suite
2026-09-01: *"a lot of crawling. The wheels are slowing down, they're
stopping, and then they're jittering... On some moves, they're going
back and forth. It's like they're overshooting and then trying to
correct. I prefer they just glide into a stop."*

MEASURED on the same run (`reports/run-tours-20260901/square.json`, ten
move endings from one `RUN:square:60`):

| | |
|---|---|
| total crawl (time under 60 mm/s before the stop) | **9.0 s across 10 endings** |
| worst single ending | **1.6 s** |
| duty reversals during the tails | **27** |
| frames still driving after the wheels read zero | **12** |

The tail of a straight leg, as captured:

```
4.80s  vl 135  vr 144   duty 1000/ 800     decel starts
4.86s  vl  72  vr  99   duty  400/ 300
4.92s  vl  30  vr  56   duty  300/   0     144 -> 30 mm/s in ~100 ms
5.03s  vl  26  vr   0   duty  300/ 300
5.14s  vl  20  vr  39   duty  400/ 300     crawl, duty hunting 300-700
5.25s  vl  36  vr  20   duty  700/-300     reversal
5.36s  vl   0  vr   0   duty    0/   0
```

And after a pivot, duty drives *harder negative* once the wheels have
already stopped -- an integrator winding up against a dead wheel:

```
6.82s  vl 0  vr   0   duty    0/   0
6.87s  vl 0  vr -10   duty -300/-300
6.98s  vl 0  vr   0   duty -500/   0
```

Three distinct faults in one tail: the deceleration is a slam, then a
crawl at the speed floor where the PID hunts, then a reversal to null
the overshoot.

## Cause

**The constant-acceleration shaping is switched OFF.** MEASURED on
gopiv 2026-09-01, reading the live config over the wire:

```
get accel 0.000000
get decel 0.000000
get jerk  0.000000
get plateau_min_s 0.000000
```

`0` is the documented "legacy mode" selector (`motion_engine.h`: *"0.0
selects LEGACY MODE"*), and it is the shipped default. So every tour
ever driven has used the old proportional `dist_taper` (400 counts
~ 31 mm) plus `speed_floor` (512 counts/s = 40 mm/s), not the
kinematic profile. The measured deceleration is ~1273 mm/s^2 against an
acceleration ramp of ~400 mm/s^2 -- roughly 4x steeper, which is what
makes it read as a slam and then overshoot.

**This means the trajectory-shaping work is present but has never
actually run on a robot.** The host-driven `.tour` suite does not set
these fields either.

## Progress 2026-09-02

**One real cause found and fixed:** the yaw axis never got the
kinematic braking gate the distance axis got, so `yawTaper_` -- not the
physics -- decided when a pivot started braking. Fixed; pivot scatter
went from sd 1.14 to **sd 0.18** at unchanged bias (vevov, six 90 deg
pivots per arm, same session). Pinned by
`test_motion_engine_acceleration_profile.py` with a negative control.

**The crawl itself is NOT fixed.** Ruled out by measurement, all with
shaping on: `accel`/`decel` (4 pivots, 1.48 s shaped vs 1.52 s legacy),
`yaw_taper` (after the fix, pivot duration no longer tracks it), and
`turn_floor` (0.12 -> 0.01 moved crawl only 381 -> 358 ms/pivot).

A full pivot trace shows the commanded speed **rising again** after it
has already slowed -- duty -300/300 at 0.65 s, then -900/500, then
-1300/900 -- which is a hunt against the completion condition, not a
taper running out. The pure-turn completion margin is **4 counts**
(~0.16 deg) and the straight axis's is 10 counts (~0.79 mm); the move
cannot end until it lands inside that, so it keeps re-driving.

**Tour-level closure is a wash** between legacy and shaped: total spread
across the five figures 45.4 mm legacy vs 46.5 mm shaped, same robot,
same session, three repeats each
(`reports/vevov-shaped-tours-20260902.md`). So shaping alone is not the
answer to what the stakeholder is watching.

## Proposed fix

Not yet settled -- this needs its own measurement pass. What is known:

- Setting `accel 400 decel 400` over the wire halves the measured
  deceleration (1273 -> 636 mm/s^2) and removes the crawl **on an
  isolated `MOVE_X 600`**.
- It does **not** fix the tour: crawl stayed ~2.4 s per tour across
  legacy, `accel/decel 400`, `+ jerk 1500`, and `speed_floor 256`. So
  the tour's crawl has a second cause not yet isolated -- suspect the
  interaction of the taper window, `pos_err_max` (127.6 counts ~ 10 mm)
  and the move-completion test, i.e. the move does not end until the
  position error closes, so it crawls until it does.
- Lowering `speed_floor` to 256 made closure worse (75.7 mm vs 7.8 mm
  on the same figure) without buying much crawl reduction.

Directions worth testing, in order:
1. ~~Find why the tour crawls when an isolated leg does not.~~ Answered:
   the pivots are the crawl (4 pivots alone = 1.5 s), and the yaw-axis
   gate was one cause, now fixed. The residual is the completion hunt.
2. Decide whether a move should end on **profile completion** (glide to
   zero, accept the residual) rather than on position error closing.
   That is the behaviour the stakeholder is asking for and the current
   design does not offer it.
3. Address the post-stop integrator drive separately -- it is a
   distinct fault from the crawl and shows up even on clean endings.
4. Only then pick shipped defaults for `accel`/`decel`/`jerk`, and bake
   them so a robot behaves correctly without a host setting them.

## Verification

Re-run `RUN:square:60` with telemetry and recompute the four numbers in
the table above. A fix should show crawl well under 200 ms per ending,
zero duty reversals in the tails, and no post-stop drive frames.
Closure must not regress -- it varies 20-30 mm run to run on this
figure, so compare distributions over at least three repeats, never
single samples.

## Related

- The shaping knobs themselves were added by the trajectory-shaping
  sprint and are wire-settable; nothing there is missing, it is only
  inert by default.
- `movex-end-bump-is-an-i-term-stall` describes the post-stop
  integrator behaviour from an earlier session.
