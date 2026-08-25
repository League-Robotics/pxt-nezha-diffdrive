---
status: pending
sprint: ''
---

# The square tour closes at 58 mm by camera while the robot reports 22 mm

Priority: **High** — this is the first square tour this project has ever scored
against independent ground truth, and it fails the stakeholder's 50 mm
acceptance gate. Worse, the robot's own instruments report a number that would
have passed it.

## The run

vevov, 2026-08-25, on the mat, over the zavaz radio relay (channel 4 group 10).
Overhead camera `arducam-ov9782-usb-camera` **freshly recalibrated immediately
before the run**: all 10 ArUco ids matched, reprojection error **1.83 mm**,
`stale: false`. vevov is AprilTag 53 with its measured mount offset registered,
so the camera reports the robot's centre of rotation.

`RUN:tour:world` — the camera-seeded absolute tour. Host seeded the true world
pose first via `RUN:seedxy` from a camera fix (permitted: camera at tour START
and END only, never during). Corners are absolute: (-50,30), (-50,-30),
(50,-30), (50,30) cm. Duration 27.7 s, `GAP:0`, 5 corner fixes, 493 telemetry
frames.

## The result

Final target corner: **(50, 30) cm**.

| source | final position | error vs target |
|---|---|---|
| **camera (ground truth)** | (55.47, 32.02) | **58.3 mm** |
| robot's own live OTOS fix `c4` | (51.03, 28.00) | 22.5 mm |
| divergence: OTOS belief vs camera truth | — | **59.9 mm** |

**The gate:** stakeholder's bar is <50 mm acceptable, <20 mm target. The true
closure is **58.3 mm — outside the acceptable gate.** The robot's own reported
22.5 mm is comfortably inside it.

Post-run stability was verified before trusting this: two camera reads 23 s
apart differ by **0.19 mm** (speed 0.0008 cm/s), so the robot was genuinely at
rest and the discrepancy is not post-tour coasting. An earlier read showed a
0.16 cm/s velocity that turned out to be transient noise — checking it was the
difference between a real number and a wrong one.

## Per-corner arrival error, by the robot's own reckoning

| corner | target | OTOS fix | error |
|---|---|---|---|
| c1 | (-50, 30) | (-46.12, 31.48) | 41.5 mm |
| c2 | (-50, -30) | (-50.57, -27.45) | 26.1 mm |
| c3 | (50, -30) | (46.09, -31.78) | 43.0 mm |
| c4 | (50, 30) | (51.03, 28.00) | 22.5 mm |

Mean ~33 mm by the robot's own instruments. Camera truth is only available at
the endpoints under the standing doctrine, so per-corner *true* error is not
measurable without violating it — the endpoint discrepancy is the honest bound.

## Why this matters more than the number

The failure direction is toward **false confidence**. The robot's own reckoning
was optimistic by 60 mm and would have reported a PASS. Every closure number
this project has ever recorded came from that same reckoning. A tighter
acceptance gate makes this worse, not better: the tighter the bar, the more
convincing a self-reported pass looks.

This is the third instance of the same pattern in two days:
- the fabricated 0.6 mm closure (`tour-corner-fixes-are-stale-cache.md`),
- the frozen `ox`/`oy`/`oh` telemetry projection (same issue, confirmed on
  current firmware today),
- and now a self-reported 22.5 mm against a true 58.3 mm.

## What is NOT established

- **Where the 60 mm accumulates.** Four legs and four turns; nothing here
  isolates translation error from heading error, and per-leg truth is not
  available without mid-tour camera fixes, which doctrine forbids.
- **Repeatability.** This is **n=1**. One tour is not a measurement of a
  distribution. Sprint 011's campaign procedure calls for 10-20 repetitions per
  tour type precisely so a single run is not mistaken for a result.
- **Whether the encoders or the OTOS carry the error.** On straight legs
  measured today the live OTOS beat the encoders (1.2 mm vs 5.5 mm error over
  195 mm). That does not extrapolate to a tour with four turns.
- Heading agreed well at the end: camera 91.6 deg vs OTOS 92.77 deg. So the
  drift is predominantly **translational**, which is a genuine narrowing worth
  following up.

## Related

- `tour-corner-fixes-are-stale-cache.md` — the stale telemetry projection,
  reconfirmed on current firmware in the same session.
- `intermittent-cw-pivot-abort-wheel-reversal.md` — the residual leg fault; its
  campaign procedure is the right vehicle for the repetitions this needs.
- `i2c-fault-count-climbs-on-idle-bus.md` — `i2cf` rose 3 -> 17 during this
  single tour.

---

## RESOLVED (2026-08-25) — root cause found and fixed; n=1 replaced with n=15

The "n=1, not established" caveats above are now answered. **The 58 mm closure
was not drivetrain error. It was a missing lever-arm correction.**

### Root cause

`worldReady()` in `test/test.ts` returned `true` as soon as
`worldTrackingReady()` said the chip was answering. That check is only
`otosGet(7) -> connected_`, which any earlier `otosBegin()` sets — and
`RUN:probe` calls `otosBegin()`. So the first `worldReady()` after a probe
short-circuited and `applyArm()` never ran. The offsets stayed at their `0.0f`
defaults, silently, for the entire session that produced the 58 mm run.

With no arm the OTOS reports the SENSOR's path, not the centre's. Every
in-place pivot injects `2 * 38.2mm * sin(theta/2)` of phantom translation —
about 54 mm at each of the tour's four 90 deg corners.

Measured directly against camera truth:

| pivot | robot reported | camera actual |
|---|---|---|
| 84 deg, **no arm** | **52.0 mm** of travel | 2.5 mm |
| 90 deg, **arm applied** | **1.2 mm** | agreed to 2.1 mm, heading 0.07 deg |

The predicted swing for an uncorrected 38.2 mm arm over 84 deg is
`2*38.2*sin(42) = 51.1 mm`. Measured 52.0 mm. That is the mechanism, not a
correlation.

Fixed in commit **27cf24b**.

### Campaign after the fix — n=15 total, n=10 with full CSV capture

| metric | before fix | after fix |
|---|---|---|
| path deviation, median | 6.6 cm | **~2.2 cm** |
| path deviation, max | 10.1 cm | 5.4-7.2 cm (one 29.1 outlier) |
| robot-vs-camera corner disagreement | 5.2-18.6 cm | **2.4-4.2 cm** |
| closure, median | (58.3 mm, n=1) | **15.3 mm**, 6/10 inside the 20 mm target |

**Closure now meets the stakeholder's gate**: 7/10 within 50 mm, 6/10 within
20 mm, best runs 2.0 and 2.9 mm.

### What this issue got RIGHT, and what it got wrong

Right: the failure direction was toward false confidence, and the robot's
self-reported 22.5 mm would have passed a gate it should have failed.

Wrong: it implied the error was accumulated drift of unknown origin. It was a
single deterministic bug with an exact closed-form signature, findable in one
pivot against camera truth. The lesson is that **n=1 plus a mechanism beats
n=20 without one** — the repetitions confirmed the fix, but the pivot
measurement is what found it.

### What remains — split out, not closed here

Absolute arrival at the target corner is still **median 48.1 mm (0/10 within
20 mm)**, and that is a separate, systematic defect now filed as
`gotoworld-overshoots-by-fixed-stopping-distance.md`. Closure largely cancels
it, which is exactly why it survived until absolute arrival was measured.

This issue's own closure question is answered. The absolute-accuracy question
is not, and lives in that issue.

---

## Re-run on FIXED FIRMWARE (2026-08-25) — gate met, 10/10

The n=15 campaign above ran with the lever arm applied *manually* via `RUN:arm`
on unfixed firmware. vevov has now been flashed with the fix (commits 27cf24b +
fa1eddf) and the campaign re-run end to end, n=10, camera-scored.

| metric | before any fix | manual `RUN:arm` | **fixed firmware** |
|---|---|---|---|
| closure, median | 58.3 mm (n=1) | 15.3 mm | **7.6 mm** |
| closure, best | — | 2.0 mm | **2.3 mm** |
| within 50 mm gate | 0/1 | 7/10 | **10/10** |
| within 20 mm target | 0/1 | 6/10 | **7/10** |
| path deviation, median | 6.6 cm | ~2.2 cm | **0.7-3.1 cm** |
| per-corner NW/SW/SE | 5.2-18.6 cm | 2.4-4.2 cm | **0.3-2.3 cm** |

**The stakeholder's 50 mm acceptance gate is met on every run.** The 20 mm
target is met on 7 of 10.

### The residual is the OTHER defect, and it is visible here

Per-corner errors are now 0.3-2.3 cm at NW/SW/SE but **consistently 3.5-4.5 cm
at NE** — the final corner. Absolute arrival vs (50,30) is median 42.6 mm,
essentially unchanged by this fix. That is
`gotoworld-overshoots-by-fixed-stopping-distance.md` showing through, and it is
why absolute arrival is still only 2/10 within 20 mm while closure is 7/10.

It also compounds across chained runs: each run starts where the last ended, and
the robot walked from (49.9, 29.6) to settle around (53.4, 27.4) over ten tours.
Closure stays excellent throughout because the overshoot is consistent.

### Two operational notes from the same runs

- **Runs 1-2 are not usable.** Run 1 produced no `completed` line and 2940
  telemetry frames (vs ~900 typical) with SW/SE corner errors of 116 cm and
  59 cm; run 2 similar at 98 cm. These look like a mis-started tour or camera
  mis-track immediately after the flash, not robot behaviour. They are excluded
  from the per-corner reading above and included in the closure table, where
  they happen to score well (2.3 and 8.9 mm) — which is itself a caution about
  scoring closure without checking the run completed.
- **Telemetry loss degraded badly across the session**: 5.5% early, then 44%,
  88%, and 98% on the last four runs. The tours still completed and scored fine
  (the tour does not depend on telemetry), but any analysis reading those
  captures is working from ~2% of the stream. Worth its own look; not chased
  here.
