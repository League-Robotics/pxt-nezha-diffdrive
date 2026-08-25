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
