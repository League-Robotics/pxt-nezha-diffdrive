---
status: pending
---

# A lift corrupts the estimator's position; use the micro:bit accelerometer to detect it

Seen 2026-10-29 on tovez (sprint 044 firmware, `tovez-015-lin.hex`) with
`tests/dev/disturb_watch.py`. Log: `captures/sprint044-acceptance-20261028/tovez-disturb1.{jsonl,out}`.

Camera vs estimator displacement per phase, the estimator rotated into the
camera frame (heading offset steady at 90.3 to 92.0 deg throughout):

| phase | camera cm | estimator cm | error |
|---|---|---|---|
| bump along the floor, wheels still | (-0.64, +0.04) | (-0.80, +0.08) | 0.17 |
| lift, turn ~88 deg, set down ~5 cm away | (-4.11, +0.49) | (-3.33, -2.79) | 3.37 |
| GO_TO_W back to the estimator's start | (+4.20, +2.36) | (+4.03, +2.91) | 0.57 |

Heading survived the lift (camera +88.35, estimator +88.73) and the gyro
bias stayed put. Position did not: off the floor the OTOS is not tracking
the surface, and the rest gate (ticket 010) cannot tell a lift from a bump,
since both are optical motion with the wheels still.

Eric's suggestion: the micro:bit accelerometer sees a lift directly (z
transient, tilt). On a lift, freeze position, keep integrating heading,
and raise a flag (STATUS/TLM) that position is untrusted until a set-down
plus an external fix such as a camera rebase. A floor bump should keep
being absorbed as now.

## To settle it

- Log the accelerometer through bumps and lifts to pick thresholds; a
  bump must not read as a lift.
- Check how far the OTOS can be lifted before it stops reporting motion
  (its surface-quality register may do the job without the accelerometer).

## Accelerometer data (2026-10-29, `tovez-016-accel.hex`)

TLM FULL now ends `ax ay az apk` (shims.cpp diag 48-51): `apk` is the
largest per-axis jump between 50 Hz reads since the previous row.
Logs `tovez-disturb2.jsonl` (10 min untouched) and `tovez-disturb3.jsonl`
(touch, shove, lift) in `captures/sprint044-acceptance-20261028/`.

| event | median apk mg | max apk mg | duration |
|---|---|---|---|
| rest, 10 min | 8 | 44 | 0.5 s window medians never above 12 |
| hand touch, no motion | 80 | 420 | ~0.3 s |
| shove 3.4 cm along the floor | 334 | 3300 | ~0.5 s |
| lift: pickup | 140 | 176 | ~0.3 s |
| lift: held 5 cm up, ~2 s | 44 | 216 | whole hold |
| lift: set-down | 326 | 480 | ~0.4 s |

A single spike can't mean a lift: a shove's is far bigger. A held lift
looks like sustained hand tremor: every 0.5 s window during the hold had
a median apk of 36 to 120 mg, and no window at rest ever went above 12.
Candidate rule: lifted when consecutive 0.5 s windows (2 or more) each
have a median apk of 24 mg or more; set down after the tremor ends.
Gravity alone shows nothing while held (az stayed about -1 g).

The straight lift cost 1.52 cm of position and 2.5 deg of heading
(camera -6.15 deg, estimator -8.64 deg), so the OTOS gyro also misreads
yaw while the robot is tilted in the hand. The shove was absorbed to
0.1 cm and 0.3 deg.
