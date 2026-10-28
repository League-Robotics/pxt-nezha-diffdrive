# Sprint 043 postmortem: position moves on zuvat, and the defaults that followed

2026-10-27. Sprint 042 put the motor's own position loop behind the engine
(`position_mode`, `speed_path`) on the host. Sprint 043 asked what the
encoders on a real robot say about it, and flipped the defaults on that
evidence.

**Labelling rule.** Every figure below is ENCODER truth: kernel wheel
odometry or the raw wheel counts (`posl`/`posr`) in the telemetry frames of
zuvat (micro:bit + Nezha brick, two motors on M1/M2, no camera, no OTOS).
Nobody could see the robot. The encoders cannot see wheel slip, tyre scrub,
or a wrong trackwidth / `travel_calib` (zuvat runs vevov's placeholder
geometry, trackwidth 111.6, `travel_calib` 0.79324). A closed odometry
square can still be open on the floor. Anything I could not measure is
marked UNVERIFIED or "bar not met".

Capture root: `captures/zuvat-position-2026-10-27/` (abbreviated `Z/` below).
Narrative with every table: `Z/notes.md`. The one-wheel bench rig named in
the tickets no longer exists on local USB (its micro:bit is zuvat), so
every run here is on zuvat over the loki tunnel.

## 1. Decisions

| Decision | Value | Evidence |
|---|---|---|
| `position_mode` default | **1** (straights and pivots through the motor's loop; arcs stay on the kernel) | sections 2.1 to 2.4 |
| `position_mode` 2 (arcs too) | rejected | section 2.6 |
| `speed_path` default | stays **0** (`0x60` integer percent) | section 2.7 |
| zuvat kernel bake | `decel` 1000, `stop_distance_mm` 0.3 | section 2.8 |
| compiled fleet defaults (`v_floor`, `pid_ki`, `omega_floor`, `v_max`, ...) | unchanged | section 2.8 |

The boot default is one constant, `MotionEngine::kDefaultPositionMode`,
and `Rig::positionMode` (what `GET position_mode` reads) seeds from it, so
the compiled default reaches the engine at boot with no `SET`. Host tests:
`tests/host/test_sim_position_routing.py` (a fresh sim Rig routes straights
and pivots to the position path, arcs to the kernel) and
`tests/host/test_wire_motion_verbs.py::test_fresh_engine_routes_a_straight_without_any_set`.
The Cutebot sim tour (ports without a position motor) still passes: with
`supportsPositionMove()` false the engine falls back to the kernel.

Flashed build `Z/binary-zuvat-043.hex`, `id diffdrive zuvat 0.20261027.1`;
`GET position_mode` = 1 with no SET, `GET speed_path` = 0, `GET decel` =
1000, `GET stop_distance` = 0.3; FUNCS has no `brick*` (`Z/flash043/smoke.log`,
`Z/flash043/funcs.log`).

## 2. What the encoders said on zuvat

### 2.1 50 cm straights (`Z/fiftycm/position_summary.csv`, `kernel_summary.csv`)
24 trials per mode, 75 / 150 / 250 mm/s, both directions, each wheel scored
from its own count. Position mode (1): worst 0.49 mm short per wheel
(`Z/fiftycm/position.csv`), `posmove=1` mid-move and 0 after in 24 of 24.
Kernel (0): worst 11.8 mm (`Z/fiftycm/kernel.csv`, trial `kernel_75_6.csv`,
L -11.76 / R +11.64 with `i2cf` +22; an outlier that yawed). Position mode
meets the 0.5 mm bar; the kernel misses it by 5 to 25x.

### 2.2 Pivots (`Z/pivots/analysis_output.txt`, `pivots_m*_c*.csv`)
At least 5 repeats per angle and direction. Mode 1: worst 0.11 deg at 90 and
0.17 deg at 180 (0.25 at cruise 250), sd 0.00. Mode 0: worst 1.12 deg at 90,
1.30 deg at 180, sd up to 0.58. The bar (0.5 deg) is met by mode 1 and not
by mode 0. Charts: `Z/pivots/pivot_90_c150.png`, `pivot_180_c150.png`.

### 2.3 600 mm legs (`Z/pivots/legs_m*_c150.csv`, `legs_c150.png`)
Mode 1: heading change within 0.1 deg over 600 mm, lateral 4 mm at worst,
x error at most 1.7 mm. Mode 0: one leg in six showed +3.75 deg / +47 mm
(forward leg 1). No straight-line correction is needed at mode 1; n = 3 per
cell, so this says repeatable, not a tail estimate for mode 0.

### 2.4 Square tour, the progress gauge
Two runs of `tools/tour_capture.py --run 'square 50'` (4 x 500 mm straight
plus 90 degree left pivot per lap), scored by `tools/square_closure.py`,
target "closure better than 11 mm" (the sprint 031 figure).

| run | mode | laps | closure mean [mm] | closure worst [mm] | heading worst abs [deg] | lap [s] | i2cf per lap | 11 mm target | source |
|---|---|---|---|---|---|---|---|---|---|
| 042 build, ticket 004 | 1 | 5 | 1.8 | 3.6 | 0.65 | 15.0 | 35.8 | met every lap | `Z/square/closure.csv` |
| 042 build, ticket 004 | 0 | 5 | 9.8 | 26.4 | 3.05 | 17.1 | 16.0 | mean met, worst lap not | `Z/square/closure.csv` |
| flashed 043 build, default, no SET | 1 | 5 | 3.9 | 6.1 | 2.43 | 15.1 | 43.4 | met every lap | `Z/square2/closure.csv` |
| flashed 043 build, `SET position_mode 0` | 0 | 3 | 11.8 | 14.4 | 1.99 | 17.2 | 25.3 | not met (mean) | `Z/square2/closure.csv` |

Charts: overlay of all laps with the 11 mm line,
`Z/square2/progress_2026-10-27_flashed.png` (earlier build:
`Z/square/progress_2026-10-27.png`); one lap per mode with the wheel-speed
panels, `Z/square2/m1_lap3_chart.png` and `Z/square2/m0_lap3_chart.png`
(earlier build: `Z/square/m1_lap3_chart.png`, `m0_lap3_chart.png`). The
overlay reads the normalised pose files, so its mode 0 figures (mean 11.6,
worst 13.9) differ from `closure.csv` by 0.2 to 0.5 mm; `closure.csv` is the
table of record.

Reading it: the flashed default is about 3x tighter than the kernel on the
mean and meets the target on every lap in both runs. It closed a little
looser on the second run (3.9 vs 1.8 mm): lap 1 after the reboot ended
+2.43 deg / 6.1 mm, laps 2 to 5 were 2.2 to 5.4 mm. Mode 1 laps are 2.1 s
faster. Mode 1 starts legs with a near-step in wheel speed rather than a ramp
(peaks 261 to 278 mm/s over a ~210 mm/s plateau, `Z/square/m1_lap*_tlm.csv`)
and fails more I2C transactions (section 4).

### 2.5 Stop timing (`Z/stop_timing.csv`, notes.md "Stop timing")
All times are upper bounds with ~55 ms granularity (frame period plus
tunnel). STOP during a live 600 mm MOVE_X at mode 1: wheels at rest within
128 ms at 75 mm/s with 2.9 mm travel, within 125 ms at 250 mm/s with 8.7 mm
travel (reference rows 2.2 mm / 8.6 mm from
`docs/code-review/2026-10-27/data/mb_probe_stops1.csv`). MOVE_X deadline
stops 4.8 mm (75 mm/s) and 17.4 mm (250 mm/s; reference row 8.6 mm, but the
deadline reference is ~25 ms early). WHEELS_V lease stops 5.6 and 26.8 mm.
M1 and M2 reached zero in the same frame in every case.

### 2.6 Arcs: mode 2 vs the kernel (`Z/circle/closure.csv`, `closure_radial.csv`)
Circle r = 20 cm, 5 laps mode 0, 3 laps mode 1, 5 laps mode 2.
Mode 2 closes best in encoder terms (laps 2 to 5 mean 1.6 mm, heading
0.47 deg against the kernel's 57 mm / 15.4 deg) and is 22 % faster (9.0 vs
11.5 s). But its arcs run the two wheels at nearly equal speed (median
vl/vr 1.07; the circle needs 0.56, which the kernel delivers), so the track
strays 32 mm mean / 68 mm max from the commanded circle against 10.5 / 27 mm
for the kernel, with 57 vs 4 failed I2C transactions per lap and a 48 mm
lap-1 outlier that a clean 0-to-2 switch (`Z/circle/switch_check/`) did not
reproduce. Mode 1 on arcs is the kernel (same lap time, i2cf and wheel
ratio as mode 0). Decision: arcs stay on the kernel. The closure advantage
is partly by construction: a per-wheel position loop lands each wheel on its
count target whatever path it took between them.

### 2.7 speed_path A/B (`Z/speedpath/wheels_summary.csv`, `legs_summary.csv`, `refresh_p1_120_speed.csv`)
WHEELS_V, five speeds x two directions per path. Path 0 holds 70 to 250 mm/s
to within 0.2 to 3.6 mm/s (sd 5 to 10) but does not run at 40 mm/s (and adds
~80 i2cf per run). Path 1 runs 40 mm/s and has no stall frame anywhere, but
its sd is 14 to 88 and it is 10 to 14 % low at 200 and 250 mm/s. On 600 mm
legs the distance error is the same (L +3.9, R 0 mm), heading about 2 deg
both, lateral 17.4 mm (path 1) vs 11.8 mm (path 0), path 1 270 ms slower.
The 400 ms refresh keeps the motor running (min 49 to 61 mm/s at a 120
command, never zero) but ripples about +-50 %. Default stays 0; path 1 only
wins below the 70 mm/s floor.

### 2.8 Kernel defaults (`Z/kdefaults/kd_summary.csv`)
Baked for zuvat only: `decel` 1000 and `stop_distance_mm` 0.3 (pooled 16
legs vs 8: mean |err L| 3.81 to 2.21 mm, modest, measured jointly). Left
unchanged for lack of evidence: `v_floor` 70 (50 no gain, 40 unsupported),
`pid_ki` 6 (0 worse), `omega_floor` 20, `v_max` 250, accel, lag, jerk,
arrive_*, and every compiled fleet default.

## 3. Unmet or UNVERIFIED bars

| Bar | State | Number and capture |
|---|---|---|
| 50 cm at 100 % in under 1.2 s | **bar not met** | 2.53 to 2.58 s (`Z/fiftycm/position.csv`). The bar came from the bench rig at about 830 mm/s; this wire's MOVE_X ceiling is `v_max` 250 mm/s, so 500 mm needs at least 2.0 s. Raising the ceiling is a stakeholder decision |
| ESTOP time to rest | UNVERIFIED | telemetry freezes on the latch and keeps stale vl/vr (`Z/estop_30_run1.log`, `estop_100_run1.log`); travel after inferred 3.0 / 7.8 mm from the first x after `estop_clear` (`Z/estop_30_after2.log`, `estop_100_clear.log`) |
| Tick-starvation watchdog hard-stop | UNVERIFIED on hardware | cannot be triggered over the wire (the firmware's own fiber ticks): `Z/hostsilent_30.log` ran to completion |
| Fault-context stop | UNVERIFIED on hardware | cannot be provoked without a fault |
| No lurch | **bar not met** in the literal sense | mode 1 starts with a near-step (first sample 1.45 to 1.65 x cruise, `Z/pivots/analysis_output.txt`); plateau 17 to 23 % over cruise in both modes; whether the chassis physically lurches is UNVERIFIED (55 to 65 ms frames, no camera) |
| Two-wheel start skew under 10 ms | UNVERIFIED | bound one frame (~55 to 65 ms): both wheels moving in the first frame in 29 of 30 mode-1 runs (`Z/pivots/analysis_output.txt` START SKEW); needs a logic analyser or a 1 kHz encoder log |
| Mode 2 arcs | **rejected** | section 2.6; arcs do not apply proportional per-wheel speeds |
| i2cf growth | open | position path adds about 2x the kernel's failed I2C transactions (square 43.4 vs 25.3 per lap, `Z/square2/closure.csv`; pivots 4 to 5 vs 3.5; `wedge=0` and no stall throughout); cause not diagnosed |
| Square floor closure | UNVERIFIED | encoder truth only; no camera, placeholder geometry |
| WHEELS_V 40 mm/s on speed_path 0 | not supported | WHEELS_V 40 does not run (`Z/speedpath/wheels_summary.csv`) |

## 4. Things found on the way

- `MOVE_X`'s rotation field is integer milliradians, not degrees (a probe
  with "90" turned 5.2 deg; `src/comms/wire_adapter.cpp` `mradToRad`).
- A live `SET` from an earlier session survives until reboot (`v_max` read
  200 at the start of the 50 cm run; the kernel set was rerun at 250).
- `SET estop_clear 1` recovers from ESTOP without a reflash
  (`Z/estop_30_clear.log`, `estop_30_recover.log`).
- Telemetry drops 1 to 3 frames around each stop, which limits the timing
  resolution.
- The RUN brick probes in `test/test.ts` were removed once the evidence runs
  needed them no more (FUNCS has no `brick*`, `Z/flash043/funcs.log`).

## 5. Open issues

- `clasi/issues/estop-and-tick-watchdog-stop-timing-unverified-on-hardware.md`
- `clasi/issues/position-mode-2-arcs-run-both-wheels-at-the-same-speed.md`
- `clasi/issues/zuvat-i2c-fault-count-grows-during-position-moves.md`

Not filed as issues, recorded here: the physical lurch at the start of a
mode-1 move (needs a camera or a high-rate encoder log), the 10 ms start
skew (needs a logic analyser), and the 1.2 s time bar (stakeholder decision
on the `v_max` ceiling).

## 6. What would change the call

A camera or tape-measure square on zuvat (the closure here is the wheels'
own count); a diagnosis of the i2cf growth, which is the one cost of the
mode-1 default; a fix to mode-2's arc speeds, after which the arc comparison
should be re-run; and a trackwidth measurement for zuvat.
