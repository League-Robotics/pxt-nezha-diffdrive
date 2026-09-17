---
status: pending
---

# `nudge()` / `nudgeTurn()` have never been run on a robot

Sprint 039 shipped the nudge blocks (ticket 005, commit `b902c56`)
host-tested only. Its hardware acceptance criterion — camera-scored
1/2/3 degree trims and 5/10 mm nudges, forward and reverse — was left
deliberately unchecked, and the sprint closed with it carried here at
the stakeholder's decision (2026-09-16).

**What IS proven.** The underlying pulse mechanism is measured on
hardware: `captures/039-003-pulse-gate-20260916/notes.md`, vevov
2026-09-16 — 15 % duty at 2 ticks gives 1.79 mm per pulse, sd/mean
0.08, zero dead pulses in 20, warm and cold, cross-checked against the
camera over a 20-pulse burst to within 0.5 %.

**What is NOT proven.** That the settle-gated loop on top of it
(ticket 004) converges on a real robot, that the blocks return
displacements matching what the camera sees, and that a caller can hit
a 1 degree tolerance by looping on the return value. All of that is
host-sim only.

## The run to do

Per ticket 005's own criterion: command 1/2/3 degree trims and 5/10 mm
nudges, forward and reverse, camera-scored, and check the returned
displacement against the camera rather than against the request.

Expect roughly 1.8 mm granularity on distance and about 0.9 degrees per
pulse on rotation — so a 1 degree trim is close to a one-pulse request
and is the interesting case. A 2 degree trim landing at 1.8 or 2.7 is
the mechanism working as measured, not a defect.

## Which robot, and the catch

- **Distance nudges: vevov is fine.** Straight-line wheel travel does
  not depend on its disputed trackwidth.
- **Turn nudges: NOT vevov**, until
  `vevov-trackwidth-is-baked-128-but-measures-111.md` is settled. Its
  pivots fail the pre-flight dance (-9/-31/-6 degrees against commanded
  +90/+180/+90 even after live correction), and the corrections applied
  on 2026-09-16 were live-SET only and died at the next reboot.
  tovez was calibrated to 0.37 % on turns by the nezha-robot-template
  session the same night and is the better candidate — but it carries
  that session's template firmware, so it would need a flash from this
  repo to have the nudge blocks at all.

## Consumer waiting on this

`calibrateL` in the nezha-robot-template repo squares a robot to a floor
line and needs nudge-turns to within 1 degree. It is the reason sprint
039 existed. Until this run happens, that program should keep treating
`diffDrive.move(0, angle)` as its interim turn step and verify by line
reading rather than odometry.
