# vevov on the sprint-029 motion engine: lag, pivots, straights -- 2026-09-04

**Firmware:** 1.20260904.4 (master after sprint 029 merged: one
`VelocityShaper`, predictive arrival, `pivot_overrun` replaced by
`stop_distance` + `lag`), built with `make_deploy.py --robot vevov
--radio-link`, WiFi on, flashed through the Pi nada
(`captures/vevov-029-reflash-20260904/`). **Carrier:** nada's serial
daemon for runs 00-12, WiFi TCP for runs 13-15. **Truth:** the overhead
camera; from run 11 on, tag 53's mount is registered with the daemon
from `tools/field_calibration.json` (`camlink.py --register vevov`), so
the daemon reports the centre of rotation and the corrected heading and
nothing is hand-corrected. Runs 00-10 read the raw tag plus a +91.28 deg
heading offset; rest-to-rest heading DELTAS are the same either way, so
those pivot scores stand, but their "drift" column is the unregistered
2.7 cm lever arm, not translation.

Bakes going in: `rotational_slip 0.987`, `stop_distance_mm 0` (the
pre-029 `pivot_overrun_mm 2.2` retired -- it was the old engine's coast),
no `lag_s` (firmware default 0).

## Result

| run | carrier | lag | stop_distance | what | pivots | camera error |
|---|---|---|---|---|---|---|
| 00 | serial | 0 | 0 | dance, turns only | 3 | +5.1 / +1.1 / +2.2 PASS |
| 01 | serial | -- | -- | `lag_measure.py`, 4 x WHEELS_V 200 | -- | **step-response lag 0.131 s** (vl 0.125, vr 0.136) |
| 02 | serial | 0.131 | 0 | 90 deg at the 70 mm/s floor | 10 | **-4.8 deg mean**, encoders agree; 1 early stop |
| 03 | serial | 0.131 | 0 | 90/107/180 default cruise | 12 | **-4.5 deg**, encoders agree; 1 early stop |
| 04 | serial | 0.131 | (-5.1 refused) | same | 12 | -4.9; **5 early stops** |
| 05 | serial | 0.10 | 0 | same | 12 | -4.0; **3 early stops** |
| 06 | serial | 0.131 | 0 | cruise 100 | 12 | -3.3; 1 early stop |
| 07 | serial | 0.131 | 0 | default cruise, **`--no-tlm`** | 12 | -4.3; **0 early stops** |
| 08a | serial | 0.05 | 0 | 90/180, no-tlm | 8 | **-1.1 deg mean abs** |
| 08b | serial | 0.20 | 0 | 90/180, no-tlm | 8 | -7.6 |
| 09 | serial | 0.04 | 0 | 90/180, no-tlm | 8 | **1.35 deg mean abs** (-1.9 / +0.9 / -0.4 / +0.8) |
| 12 | serial | 0.04 vs 0.131 | 0 | 500 mm straights, west/east, registered mount | 4 + 4 | **0.04: -0.2..-2.3 mm; 0.131: -7.9..+4.5 mm** |
| 13 | **WiFi** | 0.04 (SET) | 0 | 90/107/180 default cruise, no-tlm | 12 | **0.96 deg mean abs**, drift 0.5 cm, link held |
| 14 | WiFi | 0.04 **baked** | 0 | same, no live SET | 12 | 1.54 deg mean abs (-1.6 / +2.0 / -1.8 / +1.3 / -2.0 / +0.4) |
| 15 | WiFi | | | `GET` after the flash | | lag 0.040, stop_distance 0, rotational_slip 0.987 |

Per-run tables, `turns.csv`, `frames.csv`, `camera.csv`, `summary.json`
in each `vevov-NN-*/`; driver logs beside them.

## What the data says

1. **The step-response lag is 0.131 s, the same as tovez's 0.13, and it
   is the wrong number to run pivots with.** With it, every pivot lands a
   constant ~4.5 deg SHORT at every cruise (70, 100, default), and the
   encoders agree to within a degree: the kernel stops early on its own
   count. That is the arrival credit `vAct * lag` taken at the 70 mm/s
   floor, where the wheel actually coasts ~4 mm (run 02), not the 9 mm the
   credit assumes. The cure the design provides is `stop_distance`, but the
   residual is NEGATIVE (about -5 mm per wheel) and the setter refuses it
   (`motion_limits.h`: `if (v >= 0.0f) stopDistance = v`), so run 04 silently
   repeated run 03.
2. **The pivot offset is linear in lag** (0.20: -7.6, 0.131: -4.5, 0.10:
   -4.0, 0.05: -1.1, 0.04: ~-1 deg) and **0.04 centres both pivots and
   500 mm straights** (within 2.3 mm; at 0.131 the forward legs stop 4-8
   mm short). Baked as `lag_s 0.04` in radio-robot-lib
   (`config/robots/vevov.json`, provenance in the file), flashed, and
   confirmed post-flash with no live SET: 12/12 pivots, mean abs 1.5 deg.
   tovez's stakeholder-chosen 0.13 went the other way ("0.10 left pivots
   1-6 deg short"); the two robots disagree about the sign of the lag
   effect, which is a sprint 031 question (drivetrain tuning), not a
   calibration one.
3. **`TLM FULL` during a pivot provokes early terminations on this
   engine.** With telemetry streaming, 4-5 of 12 default-cruise pivots
   ended at 0.0 s (one duty tick then stop -- run 04 pivots 8-10, three
   in a row) or mid-turn (146 deg of 180, 109 of 180, 68 of 90), the
   encoders agreeing, on a lossless serial link; 1 of 12 at cruise 100,
   1 of 10 at the floor. With `--no-tlm` (STATUS polling still on): 12/12
   clean, four times in a row (runs 07, 13, 14, plus 08/09). Camera-only
   scoring is the workaround; the telemetry emit path interfering with
   the control step (or the K2 stale-tick freeze misfiring under it) is
   a firmware defect for sprint 031. The pre-029 engine showed a related
   1-in-10 "ran long/short by the encoders' own count" over the radio
   (`reports/turn-compare-20260904/REPORT.md`).
4. **WiFi TCP held under motor load on the field**: runs 13 and 14, 24
   pivots, no dropped reply the tool noticed; the post-flash session
   dropped one `GET` reply (the tool now retries). This morning's gopiv
   dropout was its brick battery.
5. **Register the mount, do not hand-correct.** The daemon applies the
   lever arm and the tag-height parallax itself once the mount from
   `field_calibration.json` is registered. Reading the raw tag and
   dividing by 1.119 mis-projected legs into the rail margin twice today.
6. Reverse `MOVE_X` legs yaw 4-5 deg on vevov (run 12, heading change
   column); forward legs hold within 1 deg.

## Bake and reproduce

```bash
uv run python tests/playfield/turn_calibration.py --robot vevov --dance-only --dance-turns-only --margin 12
uv run python tests/playfield/lag_measure.py --robot vevov --out reports/<dir>/01-lag        # step-response lag, FYI
uv run python tests/playfield/turn_calibration.py --robot vevov --wifi vevov --angles 90 107 180 --reps 2 --cruise 0 --no-tlm --set lag=0.04 --out reports/<dir>/pivots
uv run python tools/camlink.py --register vevov     # once per daemon session
```

`radio-robot-lib` commits: 147f664 (tigez/vevov `pivot_overrun_mm` ->
`stop_distance_mm 0`), 451cd0b (vevov `lag_s 0.04`).

## Not done

- tigez and gopiv: flashed to the 029 build on the farm
  (`captures/{tigez,gopiv}-029-reflash-20260904/`, WiFi 40/40 on tigez,
  39/40 on gopiv with a repeatable GO_TO_W "wheels turned" miss that
  tigez passes), no lag_s baked (stop_distance 0). Same procedure when
  they are on the field; expect a different lag than vevov's.

## Evening: tigez on the secondary playfield (camera 2), 2026-09-04

Firmware 1.20260904.4 on tigez (farm flash, `captures/tigez-029-reflash-20260904/`),
bakes slip 0.9617 / stop_distance 0 / lag 0. Field: secondary playfield,
110 x 70 cm, NO rails, camera 2 (`hd-usb-camera`); the tool grew
`--camera` and `--field-cm`, margin 15 cm, pivots only. tovez (the other
agent's) sat on the main field; vevov shared this one.

| run | carrier | lag | pivots | camera error |
|---|---|---|---|---|
| tigez-01 (main field, before the move) | WiFi | 0 | dance | +0.5 / +6.7 / +4.3 PASS |
| tigez-03 | WiFi | 0 | dance | **WiFi module died at the first MOVE_X** (unacked, socket broke, host down for good); micro:bit fine over the radio |
| tigez-04 | radio | 0 | dance | +3.6 / +4.2 / +6.1 PASS |
| tigez-05-lag0 | radio | 0 | 7 | **+4.3 deg mean** (fit offset +6.6) |
| tigez-05-lag0.04 | radio | 0.04 | 8 | +0.7 / -1.5 / +1.9 / -1.8, offset +0.3, mean abs 2.2 |
| tigez-06-lag0.10 | radio | 0.10 | 8 | -1.1 / -0.4 / +0.5 / +0.4, offset -0.75, mean abs 1.9 |
| tigez-06/07 lag 0.05 confirm | radio | 0.05 | -- | killed: camera 2 stopped delivering frames (twice), relay pool silent once |

- **Same knob, same direction as vevov**: lag 0 over-rotates, a small lag
  centres it. tigez sits on a plateau between 0.04 and 0.10 (vevov's slope
  was steeper). **Baked `lag_s 0.05`** in radio-robot-lib (tigez.json,
  provenance in the file); NOT yet flashed (tigez has no Pi; farm) and
  straights unverified.
- **tigez's WiFi module drops the moment the motors engage** on the field
  (as gopiv's did this morning); the micro:bit keeps answering over the
  radio (5-7 of 8 pings). The brick rail under motor load is the suspect
  on both boards; vevov's module held through 24 pivots.
- **Camera 2 died twice in ~40 min** ("no frame available", daemon lists
  it present/unusable, calibration stale) and did not come back after
  the second Terminal restart of the daemon; camera 3 kept serving. A
  camera/USB fault, not the daemon. The tool now treats a daemon error
  as a missed fix and reconnects through the relay pool after two
  unacked moves (relay gozop passed nothing outbound in two sessions).
- Dance pivots at lag 0 on the 029 engine over-rotate 4-6 deg, i.e. the
  new engine untuned is about where the old engine untuned was; the
  bench squares on gopiv (`reports/gopiv-square-029-20260904/`, closure
  19-24 mm, each pivot +0.3..+1.5 deg by the encoders) say the same.

## Night, 2026-09-05: tigez finished on the secondary playfield (camera 2 repaired)

Camera 2 came back after the stakeholder's fix; tag-57 mount registered
(-0.67 / -0.02 / 11.7 cm, -89.65 deg) and camera 2 knows its own
height (144 cm), so the daemon reports the centre of rotation: per-pivot
centre drift 0.25-0.41 cm across the night, which is the parallax check
passing. tigez had rebooted (lag back to 0); everything over the radio
relay, camera-only scoring, 15 cm margin, tigez's WiFi left alone.

| run | lag | pivots | camera error | notes |
|---|---|---|---|---|
| tigez-08 dance | 0 | 3 | +1.2 / +4.4 / +3.6 PASS, home 0.4 cm | |
| tigez-09 confirm | 0.05 | 10/12 | mean abs 2.2 deg; +90 -0.2, -90 +0.1, +107 -2.3, -107 +3.0, +180 +2.0, -180 -1.6 | relay guvov went silent, reconnect to gozop |
| tigez-10 straights | 0.05 / 0.10 | 4 + 4 x 400 mm | 0.05: +3.6 / -1.7 / +0.9 / -1.6 mm; 0.10: -0.7 / +1.3 / -1.1 / +1.3 mm | east/west legs, heading change < 2.5 deg |
| tigez-12 statistics | 0.10 | 14/24 | **mean abs 0.65 deg**, offset -0.7, all within 1.8 | 10 unacked, 5 relay reconnects |
| tigez-13 statistics | 0.05 | 22/24 | **mean abs 1.1 deg**, offset -0.4; per angle -0.1 / -1.1 / -0.2 / -0.7 / +1.0 / -1.1 | |

**tigez on the 029 engine: lag 0.05 baked (radio-robot-lib tigez.json),
pivots within about 1 deg, 400 mm straights within 4 mm.** 0.10 is
equally good (a plateau from 0.04 to 0.10 on this drivetrain, unlike
vevov's steep slope), so the bake stays at 0.05, the most-measured
value. Still to do: a farm flash of tigez so the bake survives a reboot
(no Pi on tigez); until then `SET lag 0.05` after every power-up.

The relay pool cost 10-20 % of pivots to unacked moves (the tool
reconnects after two); tigez's WiFi would have been lossless but it
drops at the first motor engage on this board.
