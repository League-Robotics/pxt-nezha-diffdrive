# Pivot over-rotation across three drivetrains: gopiv, tigez, vevov -- 2026-09-04

**Question (stakeholder):** do the three configurations -- vevov with its
flexy wheels, gopiv and tigez with the same rigid wheels but different
drive structures -- overshoot pivots differently?

**Setup.** All three on the playfield at once, north half (a fourth
robot, someone else's, worked the south half and was never addressed).
Firmware 1.20260903.2 on all three (`captures/fleet-flash-20260904/`),
v6 radio link ON, driven through the torture relay pool
(`tests/playfield/turn_calibration.py --radio`), one relay per robot.
Truth is the overhead camera (aprilcam, tags 54/57/53), every pivot
scored rest-to-rest; `TLM FULL` streamed for wheel speeds and the
encoder-believed heading. Pivots are `MOVE_X 0 <angle>` at the default
cruise (~180 mm/s at the wheels on every robot -- see the wheel-speed
overlays). Two rounds:

| round | tigez | vevov | gopiv |
|---|---|---|---|
| **baked** (each robot's own calibration) | slip 0.9617, overrun 5.5 mm | slip 0.987, overrun 2.2 mm | no bake: slip 0.952, overrun 0 |
| **raw** (identical constants on all three, `--set pivot_overrun=0 rotational_slip=0.952`) | `tigez-raw`, 11 pivots | `vevov-raw`, 12 | = gopiv's baked runs (already raw): `gopiv-baked2` 20 + `gopiv-baked3` 14 |

Pivots the drivetrain cannot have produced are excluded and marked in
each run's REPORT.md: the robot was moved by hand between fixes
(9-27 cm of "drift" during the mid-session repositioning), a stale
camera fix, or the robot executed a different angle than commanded by
its own encoders' count (gopiv turned -90 for a commanded -180 once,
-135 once; vevov did not move once). 8 of 129 pivots.

## Result: with identical constants, the three robots over-rotate differently

Camera over-rotation per pivot, mean over left and right, raw round
(`raw/COMPARE.md`, `raw/compare-error.png`):

| robot | wheels | 90 | 107 | 180 | encoders believed | **unseen by the encoders** |
|---|---|---|---|---|---|---|
| **tigez** | rigid | +7.1 | +6.8 | +8.8 | +2.5 to +4.6 | **~+4** |
| **gopiv** | rigid | +8.6 / +10.2 | +9.7 / +10.8 | +7.4 / +9.9 | +3.1 to +7.0 | **~+4** |
| **vevov** | flexy | +11.2 | +11.3 | +13.4 | +3.5 to +5.2 | **~+8** |

![raw round](raw/compare-error.png)

Two separate effects, and they sort the robots differently:

1. **Rotation the wheels never register** (camera minus encoders, the
   body still turning after the controller stopped counting): the same
   ~4 deg on both rigid-wheeled robots, and about twice that, ~8 deg,
   on vevov. That is the wheel-compliance signature the stakeholder
   suspected: flexy wheels wind up under the pivot's lateral load and
   unwind after the drive stops. Per-pivot it is remarkably constant on
   vevov (sd 0.6-1.7 deg) -- an offset, not a scale error (fit gain
   1.027), so `pivot_overrun` is the right knob for it. Note vevov's
   ~4.8 cm "drift" per pivot is the tag-53 lever arm (its mount is
   registered raw, the tag sits 2.7 cm behind the centre), not
   translation.
2. **Where the controller itself stops** (encoder-believed error):
   tigez stops ~2.5-4.5 deg late, vevov ~3.5-5, **gopiv ~5-7**. gopiv's
   kernel runs past the target more than tigez's with identical
   constants and the same peak wheel speeds (`raw/compare-wheel-speed.png`).
   That is the drive-structure difference between the two rigid-wheeled
   robots, and it lives in the kernel's stop, not in the tyres.
   UNVERIFIED why: gopiv has no `travel_calib` bake (firmware default),
   so its encoder-to-mm scale may differ, which would change the ramp
   the controller thinks it is on; a `RUN:straight` tape check would
   settle that.

So: **yes, the configurations overshoot differently, and the split is
not simply rigid vs flexy.** Flexy wheels add ~4 deg of post-stop
rotation; gopiv's drive adds ~3 deg of late stopping. tigez has the
least of both.

## Baked round: what each robot does today

`baked/COMPARE.md`, `baked/compare-error.png`:

| robot | 90 | 107 | 180 | mean abs err | notes |
|---|---|---|---|---|---|
| tigez (baked 0.9617 / 5.5 mm) | +1.4 | -1.1 | +2.9 | 3.1 deg | centred; 3 kernel outliers (below) |
| vevov (baked 0.987 / 2.2 mm) | +5.7 | +5.6 | +5.2 | 5.5 deg | flat +5.5: its 2.2 mm bake is ~3x too small for these wheels |
| gopiv (no bake) | +8.6 | +9.7 | +7.4 | 8.9 deg | flat +9 |

![baked round](baked/compare-error.png)

Suggested constants from each robot's fit (`<run>/summary.json`,
`suggested`), same model as tigez's 2026-09-03 calibration:

| robot | rotational_slip | pivot_overrun_mm | from |
|---|---|---|---|
| vevov | 0.981 | **8.5** | `vevov-baked2` (21 pivots at the live 0.987 / 2.2) |
| gopiv | 0.947 | **11.5** | `gopiv-baked3` (14) / 0.935 and 11.4 from `gopiv-baked2` (20) |
| tigez | keep 0.9617 / 5.5 | | `tigez-baked2`: +1.4 / -1.1 / +2.9, nothing to gain |

Those are default-cruise values; the overrun is speed dependent (tigez
2026-09-03: the same constants under-rotate by ~2 deg at 60 mm/s).
UNVERIFIED on the robot -- the boards cannot be reflashed today (no Pi
Zeros on the field), and a live `SET` does not survive a power cycle.
Bake them into `radio-robot-lib/config/robots/<name>.json`
`geometry.firmware_bake` and flash when a Pi is back on the robot.

## Kernel outliers seen by the encoders -- a firmware finding, not calibration

Across the day, pivots where the **encoders agree with the camera** that
the move ran the wrong length:

| robot / run | pivot | commanded | camera | encoders | wheel trace |
|---|---|---|---|---|---|
| tigez-baked2 | 5 | +180 | +198.5 | +195.2 | a garbled frame (`vr -6393`, `h` back-stepping) at 1.38 s, then the stop |
| tigez-baked2 | 10 | +107 | +100.1 | +96.2 | wheels cut at 0.98 s, 0.3 s early |
| tigez-raw | 1 | +90 | +103.2 | +99.4 | garbled frame (`vr -2565`) at 0.69 s, then a late stop |
| tigez-raw | 9 | -107 | -119.9 | -116.0 | decelerating wheels held 0.4 s longer than the mirror pivot |
| gopiv-baked2 | 23 | -180 | -89.9 | -87.0 | executed as a -90 |
| gopiv-baked3 | 11 | -180 | -135.3 | -129.5 | executed as a -135 |
| vevov-baked2 | 6 | -180 | 0.0 | +2.7 | no motion |
| vevov-baked2 | 5 | +180 | +202.1 | +181.3 | camera-only: a stale fix |

These are 4 of 33 tigez pivots (baked + raw) and 2 of 35 on gopiv, all
over the radio relay with `TLM FULL` streaming, and twice a corrupted
telemetry frame lands exactly where the controller misbehaves. On
2026-09-03, over tigez's Pi serial daemon (lossless, no radio), 0 of
46 pivots did this (`reports/tigez-turn-cal-20260903/`, post-flash
section). UNVERIFIED cause; the pattern says radio traffic overlapping
the control step, which is the family sprint 026's VFP guard closed
for the hard fault and sprint 029's pivot-end termination work should
look at. A pivot run with the radio silent (`TLM OFF`, camera-only
scoring) on the same board would settle it.

## Files

- `tigez-baked2/`, `vevov-baked2/`, `gopiv-baked2/`, `gopiv-baked3/`:
  the baked round (gopiv's is raw by construction; `gopiv-baked3`
  is a rerun after the repositioning, its radio link dropped after
  pivot 15). `vevov-baked2-aborted-rail/`: one pivot before the tool
  refused a robot 11.5 cm from the south rail.
- `tigez-raw/`, `vevov-raw/`: the raw round.
- Each run: `turns.csv`, `frames.csv`, `camera.csv`, `summary.json`,
  `REPORT.md`, `turn-error.png`, `wheel-speeds.png`, `fit.png`;
  driver logs `<run>.log`.
- `raw/`, `baked/`: `COMPARE.md`, `compare-error.png`,
  `compare-wheel-speed.png`.
- Tool fixes made during the day (`tests/playfield/turn_calibration.py`):
  stale camera records rejected by timestamp, 180-deg pivots snapped
  to the commanded lap (the tracker mis-lapped -180 as +169 when it
  dropped samples), disturbed-pivot exclusion, corrupted wheel-speed
  frames clipped, `TLM FULL` header wait tolerant of the lossy relay,
  one retry for an unacked `MOVE_X`, lights re-asserted per pivot.

## Operational notes

- WiFi was unusable: tigez's and vevov's hexes were built without
  `config/wifi_secrets.json` (WiFi link disabled in the build), gopiv's
  TCP link died under motor load. `captures/fleet-flash-20260904/notes.md`.
- A host session killed mid-sweep leaves the robot streaming `TLM FULL`
  over the radio at ~15 frames/s, after which it hears nothing
  (HELLO/TLM OFF/STOP unanswered, ~30 tries) -- only a power cycle
  recovers it (tigez, 11:20). Pool relays differ: guvov needs `!GO`
  before it passes lines through.
- tigez's and vevov's live constants were restored after the raw round
  (`SET` acked: tigez 5.5 / 0.9617, vevov 2.2 / 0.987, vevov verified by
  `GET`; tigez's `GET` replies were lost on the radio).
