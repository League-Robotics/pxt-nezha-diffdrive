# zuvat 042 build: bring-up, wire smoke, stop timing (2026-10-27)

Board: zuvat (micro:bit + Nezha brick, M1 left / M2 right, no camera, no OTOS), reached through the
ssh tunnel to the loki serial bridge. All pose / travel numbers are **ENCODER truth** (kernel wheel
odometry in the `TLM POSE` frames); nobody could see the robot, so "wheels at rest" is inferred from
`vl=vr=0` and constant x/h, never watched. Harnesses: `zrun.py` (scripted lines), `zstop.py` (live move,
command fired when |x-x0| reaches a trigger), `analyze_stops.py` -> `stop_timing.csv`.
Frame period is ~55 ms; the tunnel adds a variable uplink/downlink delay (~10-30 ms each way, RTT of
an ack is ~12-55 ms in the logs), and the frame stream drops 1-3 frames around every stop. Times are
therefore UPPER bounds with ~55 ms granularity.

## Flash
- hex: `binary-zuvat-042.hex` (this dir), built from master after sprint 042 closed.
- `mbdeploy deploy --hex ... zuvat`: first erase failed (`flash erase sector failure 0x67`), the tool
  did a CTRL-AP mass erase and retried; second attempt programmed 443392 bytes; "zuvat re-announced
  as NEZHA2 (flash_count=1)". Bridge restarted afterwards.
- Reported identity (`smoke1.log`): `device NEZHA2 robot zuvat 2708918799`,
  `id diffdrive zuvat 1.20261006.1 zuvat`, `ver 1.20261006.1`. The brief expected 0.20261027.1; the
  repo's pxt.json and the version string inside the hex both say 1.20261006.1 (the sprint closes bump
  later), so this IS the 042 build. Profile = zuvat.

## Smoke checklist (smoke1.log, move100_a.log, move100_b.log, getall.log)
| Check | Result |
| --- | --- |
| HELLO / PING / ID / VER | pass (`smoke1.log`) |
| STATUS idle | `ready=0 connL=0 connR=0 cyc=0` until the first motion command, then `ready=1 connL=1 connR=1` (`move100_a.log`) |
| GET position_mode | 0 on fresh boot |
| SET position_mode 1 #n, read back | `ack 2 0 none`, `get position_mode 1.000000` (`smoke1.log`) |
| GET speed_path | 0 (left at 0 throughout) |
| MOVE_X 100 0 100 4000 | moved +x, x 0 -> 100 mm, both wheels vl~vr~110 mm/s, h within -0.55 deg (`move100_a.log`) |
| posmove flips | `posmove=1` mid move (1.70 s), `posmove=0` after (4.26 s) (`move100_a.log`) |
| MOVE_X -100 | reverse, back to x~0 (`move100_b.log`) |
| config persists | position_mode stayed 1 across HELLO reconnects within one boot |
Cruise unit is mm/s. Measured speed ran ~5-10 % over the commanded cruise (cruise 100 -> 105-112 mm/s,
cruise 250 -> 250-275 mm/s).

## Percent mapping (my decision)
The wire has no percent. 30 % and 100 % are taken as 30 % and 100 % of `v_max` = 250 mm/s
(`getall.log`): 75 mm/s and 250 mm/s. This is NOT the duty percent of the 5a rig table; 250 mm/s is the
most the wire will command (about 40 % of what the brick can do on the rig's 100 %).

## Stop timing (stop_timing.csv; reference = host send of the command)
Section 7a = `docs/knowledge/2026-10-27-nezha-brick-opcodes.md` section 5a (micro:bit rig, M1, 83 mm
wheel, unloaded, `docs/code-review/2026-10-27/data/mb_probe_stops1.csv`). The `0x5F` hold column is the
position-mode stop (every stop path hard-stops in 042); the `0x60 0` ramp column is the velocity path.

| Case | Speed | Command fired at | Time to first vl=vr=0 frame | Travel after (encoder) | 7a row | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| STOP, MOVE_X 600, position_mode 1 | 75 mm/s | x=251 | <= 128 ms (stop_30_run1.log) | 2.9 mm | 30 %, hold: 2.2 mm / 96 ms | < 200 ms; travel 0.7 mm above the table mean, inside the 1 mm odometry/frame resolution |
| STOP, same | 250 mm/s | x=301 | <= 125 ms (stop_100_run1.log) | 8.7 mm | 100 %, hold: 8.6 mm / 168 ms | < 200 ms; travel matches |
| ESTOP, same | 75 mm/s | x=249 | UNVERIFIED (see below) | 3.0 mm (x=252 read after clear, estop_30_after2.log) | 30 %, hold: 2.2 mm | travel plausible; time not measurable |
| ESTOP, same | 250 mm/s | x=307 | UNVERIFIED | 7.8 mm (x=315 read after clear, estop_100_clear.log) | 100 %, hold: 8.6 mm | travel plausible; time not measurable |
| MOVE_X deadline (timeout 2000 ms, host silent) | 75 mm/s | deadline | <= 132 ms after the deadline (deadline_30.log) | 4.8 mm | 30 %, hold | < 200 ms |
| MOVE_X deadline (timeout 1000 ms, host silent) | 250 mm/s | deadline | <= 153 ms (deadline_100.log) | 17.4 mm | 100 %, hold: 8.6 mm | time < 200 ms; travel above the table by ~9 mm, but the deadline reference is ~25 ms early (unknown uplink delay, ~6 mm at 250 mm/s) so it is NOT cleanly out of the row; not re-run |
| WHEELS_V lease expiry (velocity path) | 75 mm/s | lease end | <= 90 ms (watchdog_lease_30.log) | 5.6 mm | 30 %, ramp: 11.1 mm / 108 ms | within |
| WHEELS_V lease expiry (velocity path) | 250 mm/s | lease end | <= 179 ms, 207 ms between last moving and first zero frame (watchdog_lease_100.log) | 26.8 mm | 100 %, ramp: 101.9 mm / 314 ms | within the table, but marginal on time (frame dropout) |

Both wheels: in every STOP / deadline / lease case vl and vr drop to 0 in the SAME frame (columns vl, vr
in the logs), so M1 and M2 both stop. For ESTOP see below.

## Findings
1. **ESTOP time to rest cannot be read from telemetry.** After `ESTOP` (reply `estop` ~18 ms later) the
   kernel is latched: `cyc` stops, the next frame repeats the last x/y/h and keeps the STALE `vl/vr`
   (67/87 and 238/268 mm/s) indefinitely (`estop_30_run1.log`, `estop_100_run1.log`). x/h constancy
   there proves nothing about the wheels. Evidence that the wheels did stop: the first fresh odometry
   read after `SET estop_clear 1` is only 3 mm / 8 mm beyond the ESTOP point, matching the hard-stop
   distance. The 200 ms bound for ESTOP is therefore UNVERIFIED, and "both wheels stop" for ESTOP is
   inferred from the post-clear x and h (h moved 1.1 deg at the 100 % clear, noise level for this rig).
   Needs a human watching, or a recovery-free instrument (e.g. a stopwatch / video).
2. **No wire-reachable host-silence watchdog on a position move.** The wire loop is ticked by the
   firmware's own fiber, so the host going silent changes nothing: `hostsilent_30.log` (MOVE_X 150 @75,
   host silent for the whole move) ran to completion, x=150. The starvation watchdog of the README tick
   contract (100-150 ms after the last tick) cannot be triggered from the wire; the closest wire stops
   are the MOVE_X deadline and the WHEELS_V lease (rows above). The true tick-starvation hard-stop is
   UNVERIFIED on hardware: it needs a blocking handler in a RUN function or a block program on the board.
3. **ESTOP recovery without reboot:** `SET estop_clear 1` then one command (which is consumed with
   `reason=estop`), then motion works again (`estop_30_clear.log`, `estop_30_recover.log`). No power
   cycle or reflash was needed.
4. **i2cf grows.** Position-path moves add ~2-4 per move (e.g. 8 -> 10, `stop_30_run1.log`); the
   WHEELS_V velocity path adds ~7-9 per 1.5 s (20 -> 29 in `watchdog_lease_30.log`, 35 -> 42 in
   `watchdog_lease_100.log`). Total at the end of the session: 117 (`return_10.log`), never a wheel
   stall or stuck wheel. `STATUS` kept `wedge=0`. The growth rate and what the failing transactions are
   is not diagnosed here; flagged for the team lead.
5. Heading wander: WHEELS_V runs curve (h up to 5.9 deg, y up to 36 mm over 260 mm); MOVE_X position
   moves stay straight (|h| <= 1.1 deg). The robot ends the session at x~1, y~15 mm, h~3 deg (`return_10.log`).
6. Telemetry drops 1-3 frames around each stop (frame gap 129-207 ms), which is what limits the timing
   resolution; whether the main fiber blocks on the stop I2C writes for ~75-150 ms is a hypothesis only.

## Files
Raw per-case logs (`<host seconds> <|>  line`) with every received frame; `return_*.log` are the
MOVE_X legs that brought the robot back to x~0 between cases (also valid data of position moves).
`aborted_estop_trigger_not_armed.log` is a discarded run in which the harness never fired (trigger not
armed); the move simply completed to x=599, then was returned (`return_8.log`).
No PNG plots: matplotlib is not installed on this host.

## Percent mapping
30 % and 100 % were taken as 75 and 250 mm/s of v_max 250 mm/s (getall.log). 250 mm/s is the wire's ceiling (the kernel v_max), so "100 %" here is not the rig's 100 % duty.

## Summary of UNVERIFIED items and i2cf (for the ticket record)
- UNVERIFIED: ESTOP time to rest (telemetry freezes on the latch; travel after inferred 3.0 / 7.8 mm from the first x after estop_clear).
- UNVERIFIED: the tick-starvation watchdog hard-stop; it cannot be triggered over the wire because the firmware's own fiber ticks (hostsilent_30.log shows the move completing). The fault-context stop is also UNVERIFIED (cannot be provoked without a fault).
- i2cf growth: 2 to 4 per position move, 7 to 9 per 1.5 s of WHEELS_V, 117 by session end, wedge=0 throughout.

---

# Pivots, 600 mm legs and two-wheel start skew (zuvat, 042 build, 2026-10-27)

Files (all in `pivots/`): harness `zpiv.py` (one connection, HELLO, `SET position_mode N`, `TLM POSE`, MOVE_X per
item, STOP between items, never ESTOP/0x1D), analysis `zpiv_analyze.py` -> `analysis_output.txt` and PNGs.
Raw per-run CSVs: `pivots_m1_c150.csv`, `pivots_m1_c250.csv`, `pivots_m0_c150.csv`, `pivots_m0_c250.csv`,
`legs_m1_c150.csv`, `legs_m0_c150.csv`, each with a `*_frames.csv` of every telemetry frame (t = seconds after the
host sent MOVE_X). Charts: `pivot_90_c150.png`, `pivot_180_c150.png`, `legs_c150.png` (mode 1 left, mode 0 right).
Board zuvat, ssh tunnel to loki bridge, no camera. **Everything below is ENCODER truth**: the odometry heading
change at rest minus the commanded angle. With no camera this says the wheels landed on their counts; it does not
say the chassis turned that far against the floor (wheel slip, tyre scrub and the 111.6 mm placeholder trackwidth /
`travel_calib` are all inside the encoder number, not checked against anything external).

Wire facts found on the way: MOVE_X's rotation field is integer **milliradians**, not degrees (a first probe with
"90" turned 5.2 deg); the harness sends round(deg x pi/180 x 1000). Telemetry `h` is centidegrees. Cruise 150 /
250 is mm/s per wheel. Frames are ~55-65 ms apart.

## Pivot table (cruise 150 mm/s, plus one of each at 250; err = measured - commanded, deg)
Lurch = any vl/vr sample above the commanded wheel speed (strict, as the ticket defines it). Peak is the largest
|vl| or |vr| in the run (`pivots_*.csv` frames).
| mode | cruise | angle | dir | n | mean err | sd | worst err | peak speed (x cruise) | lurch (> cruise) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 150 | 90 | + | 5 | -0.11 | 0.00 | 0.11 | 241 (1.61) | yes |
| 1 | 150 | 90 | - | 5 | +0.11 | 0.00 | 0.11 | 238 (1.59) | yes |
| 1 | 150 | 180 | + | 5 | -0.17 | 0.00 | 0.17 | 221 (1.47) | yes |
| 1 | 150 | 180 | - | 5 | +0.17 | 0.00 | 0.17 | 218 (1.45) | yes |
| 1 | 250 | 90 | + | 1 | -0.11 | n/a | 0.11 | 404 (1.62) | yes |
| 1 | 250 | 90 | - | 1 | +0.11 | n/a | 0.11 | 413 (1.65) | yes |
| 1 | 250 | 180 | + | 1 | -0.25 | n/a | 0.25 | 367 (1.47) | yes |
| 1 | 250 | 180 | - | 1 | +0.25 | n/a | 0.25 | 366 (1.46) | yes |
| 0 | 150 | 90 | + | 5 | +0.33 | 0.21 | 0.53 | 185 (1.23) | yes |
| 0 | 150 | 90 | - | 5 | -0.64 | 0.46 | 1.12 | 182 (1.21) | yes |
| 0 | 150 | 180 | + | 5 | +0.78 | 0.58 | 1.30 | 185 (1.23) | yes |
| 0 | 150 | 180 | - | 5 | -0.12 | 0.39 | 0.43 | 175 (1.17) | yes |
| 0 | 250 | 90 | + | 1 | +0.29 | n/a | 0.29 | 192 (0.77) | no |
| 0 | 250 | 90 | - | 1 | +0.03 | n/a | 0.03 | 192 (0.77) | no |
| 0 | 250 | 180 | + | 1 | +0.62 | n/a | 0.62 | 268 (1.07) | yes |
| 0 | 250 | 180 | - | 1 | -1.05 | n/a | 1.05 | 274 (1.10) | yes |
(+ = counter-clockwise per the odometry convention: positive MOVE_X rotation raised h. Source: `analysis_output.txt`.)

Reading it:
- **Accuracy bar (within 0.5 deg, >= 5 repeats per angle and direction): MET at position_mode 1** in encoder terms:
  worst error 0.11 deg at 90 and 0.17 deg at 180 (0.25 at cruise 250). The sd is 0.00 (every repeat lands on the
  same count, error sign follows direction: a small consistent undershoot of ~0.1 %). **NOT met at position_mode 0**
  (the kernel path the user has today): worst 1.12 deg at 90 and 1.30 deg at 180, sd up to 0.58. The mode-1
  number is the brick's own count loop landing on a target, so it is as good as the encoder, no better.
- **No-lurch bar (no vl/vr sample above the commanded speed): NOT MET at position_mode 1, bar not met.** The speed
  panel (`pivot_90_c150.png`, `pivot_180_c150.png`) shows the brick's position loop starting the wheels with a
  near-step instead of a ramp: the first or second sample after the move starts is 1.45-1.65 x cruise (218-241 mm/s
  against 150, and 404-413 against 250), then the wheels sit at roughly 1.15-1.25 x cruise (~175-190 mm/s for a
  150 command) until the final braking ramp. So even the plateau is above the commanded speed. This is a
  speed-from-encoder-differences measurement over a 55-65 ms frame, so the first sample's size is partly the frame
  timing, but the step start with no ramp is visible in the heading trace too (heading is already 10-20 deg in
  the first frame at 150 mm/s). position_mode 0 starts with an acceleration ramp and a smooth plateau, but also
  sits 17-23 % above cruise at 150 (175-185 mm/s) so it also fails the literal "> commanded" test, only by that
  plateau overshoot, not a start spike. I did not tune anything. UNVERIFIED: whether the physical wheels
  actually lurch (no camera, no accelerometer).
- Translation during pivots (encoder): over 24 mode-1 pivots the odometry (x,y) moved from (3,-7) to (17,-10) mm
  (`pivots_m1_c150.csv` first row, `pivots_m1_c250.csv` last row); over the following 24 mode-0 pivots (17,-10) ->
  (26,-22) (`pivots_m0_c250.csv`).

## Two-wheel start skew (UNVERIFIED at 10 ms; supportable bound = one telemetry frame)
Telemetry frames are 55-65 ms apart, so a 10 ms skew cannot be resolved directly, and the left and right
displacements are not separately logged (only x, y, h, vl, vr). Method: take the first frame where either wheel
reaches 10 mm/s and count frames until BOTH have (0 = same frame), and compare the two speeds in that first frame
(`analysis_output.txt`, START SKEW).
| mode | n runs | both wheels moving in the first moving frame | median min/max speed ratio in that frame | worst |
|---|---|---|---|---|
| 1 (brick position loop) | 30 (24 pivots + 6 legs) | 29 of 30 | 0.91 (10th percentile 0.84) | one run (cruise-250 90 deg, `pivots_m1_c250_frames.csv` run 0) had the left wheel 1 frame (~65 ms) behind: right 178, left -1 in the first frame, left -404 in the next |
| 0 (kernel ramp) | 30 | 9 of 30 | 0.00 (typically one wheel is still at zero) | 3 frames (~170 ms); median 2 frames on pivots |
- **10 ms start skew: UNVERIFIED.** What the data supports: at position_mode 1 the two wheels start within one
  telemetry frame (<= ~65 ms) in 29/30 runs and the first-frame speeds differ by a median 9 % (p10 16 %), which if
  read as a pure start delay would be a few ms, but that reading is an inference, not a measurement. The
  one-frame lag in 1/30 puts the worst case at <= ~65 ms. At position_mode 0 the skew is
  several frames (up to ~170 ms) but that is the kernel's separate per-wheel ramps, not the brick. A real 10 ms
  figure needs a faster capture (logic analyser on the two motor I2C writes, or an encoder-edge timestamp log at
  >= 1 kHz).

## 600 mm legs (cruise 150, 3 forward + 3 reverse per mode, ENCODER truth)
Lateral deviation is measured in the leg's own start-heading frame (the robot starts each leg at odometry heading
~3 deg at mode 1 and ~3-7 deg at mode 0, so raw world y over the leg is mostly that offset; raw y is in the
CSVs).
| mode | dir | n | mean heading change (deg) | sd | mean lateral (mm) | sd | worst lateral (mm) | mean x error (mm) | i2cf / leg |
|---|---|---|---|---|---|---|---|---|---|
| 1 | fwd | 3 | -0.08 | 0.00 | -2.7 | 0.8 | 3 | -1.3 | 5.0 |
| 1 | rev | 3 | +0.04 | 0.07 | -3.8 | 0.4 | 4 | +1.7 | 6.0 |
| 0 | fwd | 3 | +1.05 | 2.35 | +18.4 | 25.3 | 47 | -3.3 | 2.3 |
| 0 | rev | 3 | +0.71 | 0.30 | -8.7 | 4.4 | 13 | +3.3 | 1.0 |
Mode-0 forward leg 1 is the outlier (heading +3.75 deg, lateral +47 mm; a 6 deg heading spike in the first 0.3 s,
`legs_c150.png` top right); without it the mode-0 legs are within ~1 deg and 13 mm, still 3-4x looser than mode 1.
**Conclusion: no straight-line correction is needed at position_mode 1.** Over 600 mm the encoder heading ends
within 0.1 deg of where it started (it wanders +/-1.3 deg during the leg and recovers by the end, the chart
shows the same shape every repeat) and the lateral error is <= 4 mm. The kernel twist hold (mode 0) is looser,
and showed one 3.75 deg / 47 mm leg in six; if anything the correction question is for mode 0, not mode 1. n = 3
per cell: enough to say mode 1 is repeatable, not enough to give mode 0 a tail estimate. Distance error is
<= 4 mm of 600 in both modes (encoder).

## i2cf growth (open issue tracks it)
Counter went 140 -> 375 over this ticket's runs (this ticket added ~235 on top of ticket 002's 117), wedge stayed
0 and no stall. Per run (means from the CSVs): mode-1 pivots 4-5 per ~2 s pivot (183 -> 291 over 24 pivots), mode-0
pivots 3.5 per pivot (291 -> 375 over 24), mode-1 600 mm leg 5-6 per ~5 s leg, mode-0 leg 1-2 per leg
(0-6; first leg 6). So the position path (mode 1) fails about 2x as many I2C transactions as the kernel velocity path
per unit time on pivots and ~3-4x on legs; the moves are the same length, so mode 1 is the heavier source. Failure
cause not diagnosed here.

## Acceptance state
- Pivot error <= 0.5 deg, n >= 5, both directions: MET at mode 1 (ENCODER truth); mode 0 does not meet it.
- No lurch: **bar not met** (strict definition), start step 1.45-1.65 x cruise at mode 1.
- Start skew < 10 ms: **UNVERIFIED** (bound <= ~65 ms, one frame; 29/30 within the first frame).
- Leg drift mode 1 vs mode 0 with conclusion: done (no correction needed at mode 1).
- Charts, CSVs, notes: done.

## Finding: MOVE_X rotation is milliradians (wire doc check)
MOVE_X's rotation field is an integer in milliradians (`mradToRad()` in src/comms/wire_adapter.cpp; `execMoveX` in
src/comms/wire_handler.cpp; tests/host/test_wire_motion_verbs.py and tests/calibration/turn_calibration.py both send
`MOVE_X 0 <mrad> ...`). No markdown doc in the repo gives a degrees grammar for MOVE_X (searched outside clasi/,
captures/, .tmp), so no doc fix was needed. This ticket's first probe sent 90 and turned 5.2 deg.

## Acceptance addendum (coordinator decision)
Ticket accepted as done with two recorded gaps: no-lurch (literal >cruise not measurable at 55-65 ms frames; plateau
17-23 % over cruise is common to both modes; mode 1 starts as a near-step; physical lurch UNVERIFIED) and start skew
(10 ms UNVERIFIED; one-frame bound, 29/30 mode-1 runs both wheels in the first frame, mode 0 one wheel at zero in 21/30).

---

# Square tour closure and speed curves (zuvat, 042 build, 2026-10-27)

Files (all in `square/`): per-lap raw recordings `m<mode>_lap<n>_tlm.csv` (+ `_pose.csv`, `_vel.csv`, `.meta.json`),
scorer output `closure.csv` / `closure.md` (from `tools/square_closure.py`), lap-normalised copies in `norm/`,
charts `m0_lap1_chart.png`, `m0_lap3_chart.png`, `m1_lap1_chart.png`, `m1_lap3_chart.png` (made by `tools/tour_chart.py`
from the normalised CSVs: lap start at the origin, start heading 0, dashed = commanded 500 mm square), set/readback logs
`m1_set.log`, `m0_check.log`, `m1_check.log`, `final_reset.log`.
Run: `tools/tour_capture.py --wifi 127.0.0.1 --run 'square 50'` (new `--run` / `--set` flags), i.e. board `RUN square 50` =
`squareTour(50)`: 4 x (500 mm straight, 90 deg left pivot), one lap per capture, 5 laps per mode, `STOP` between laps.
Mode 0 laps: position_mode read back 0 (`m0_check.log`); mode 1: `SET position_mode 1`, read back 1 (`m1_set.log`,
`m1_check.log`). The pose is NOT reset between laps (squareTour does not call resetPose), so each lap is scored on its own
first and last telemetry frame (robot idle at both); the robot drifted physically over the session (odometry end of the
last lap x=30, y=-39 mm from the session origin; the odometry frame is the robot's own, no floor reference). All laps ran CCW
(the tour only turns left). After the runs: position_mode 0 (read back), TLM OFF (`final_reset.log`), robot idle.

**Every figure below is ENCODER truth (kernel wheel odometry). No camera.** The encoders cannot see wheel slip or tyre scrub
(the wheel turned but the chassis did not), nor a wrong trackwidth or `travel_calib`: zuvat's geometry is vevov's
placeholder (trackwidth 111.6, travel_calib 0.79324), so a lap that closes in odometry can still fail to close on the floor
by the same factor on every lap (a pure scale error cancels in a closed loop and stays invisible). Closure here says the
two wheels' counts return to where they started, no more.

## Per lap (closure.csv; closure = start-to-end distance in the odometry plane, residual = end heading - start heading mod 360)
| mode | lap | closure [mm] | heading residual [deg] | lap time [s] | i2cf growth |
|---|---|---|---|---|---|
| 0 | 1 | 26.4 | +3.05 | 17.1 | 22 |
| 0 | 2 | 3.2 | -0.22 | 17.3 | 24 |
| 0 | 3 | 5.8 | +0.10 | 17.1 | 4 |
| 0 | 4 | 8.6 | -0.57 | 17.1 | 16 |
| 0 | 5 | 5.1 | -1.88 | 17.1 | 14 |
| 1 | 1 | 3.6 | -0.65 | 14.9 | 34 |
| 1 | 2 | 2.2 | -0.46 | 15.0 | 37 |
| 1 | 3 | 1.0 | -0.41 | 15.0 | 35 |
| 1 | 4 | 0.0 | -0.50 | 15.0 | 36 |
| 1 | 5 | 2.2 | -0.29 | 15.0 | 37 |
Lap time = first to last frame with a wheel above 5 mm/s (device clock). i2cf growth = counter at the lap's last frame minus
its first frame.

## Comparison, target closure better than 11 mm (the sprint 031 figure)
| mode | laps | closure mean [mm] | closure worst [mm] | heading mean abs [deg] | heading worst abs [deg] | lap mean [s] | i2cf per lap | target < 11 mm |
|---|---|---|---|---|---|---|---|---|
| 0 (kernel) | 5 | 9.8 | 26.4 | 1.16 | 3.05 | 17.1 | 16.0 | MEAN met (9.8), WORST NOT MET (26.4, lap 1) |
| 1 (brick position loop) | 5 | 1.8 | 3.6 | 0.46 | 0.65 | 15.0 | 35.8 | **MET** (every lap, worst 3.6) |
The scorer's verdict column applies the target to the worst lap, so mode 0 reads "not met": four of five mode-0 laps close
inside 11 mm (3.2 to 8.6), lap 1 does not (26.4 mm, 3.05 deg; it is the first lap after the earlier session, the 600 mm-leg
outlier of the pivot ticket is the same kind of kernel twist-hold excursion). Mode 1 meets the target on all five laps and is
~5x tighter on the mean; mode 1's heading residual is a consistent -0.3 to -0.65 deg (the same small undershoot seen at the
pivots). Mode 1 laps are also 12 % faster (15.0 vs 17.1 s).

## Speed curves (charts, `square/m*_lap*_chart.png`)
Both modes cruise the 500 mm legs at about 200 to 220 mm/s per wheel (the plateau in the chart), and pivot with one wheel
forward and one back at about 100 mm/s (the right wheel +, the left -). Mode 0 ramps up smoothly over ~0.5 s; mode 1 starts
as a near-step and spikes above the plateau at the start of legs (per-lap peak of max(|vl|,|vr|): mode 1 261 to 278 mm/s,
mode 0 222 to 241 mm/s, `m*_lap*_tlm.csv`), consistent with the pivot ticket's no-lurch finding (speeds from encoder
differences over 55-65 ms frames; whether the chassis lurches is UNVERIFIED, no camera). Mode 0 telemetry dropped 5 frames
per lap (1.8 %), mode 1 none (`*_tlm.meta.json`).

## i2cf
Per lap +4 to +24 at mode 0 (mean 16) and +34 to +37 at mode 1 (mean 35.8): the position path fails about twice as many I2C
transactions per lap as the kernel path, again consistent with the pivot ticket. Counter 375 at the start of this block,
634 at the end (`m1_check.log`); `wedge=0`, no stall. Known open issue, cause not diagnosed here.

## Postmortem-ready summary
On zuvat (042 build, two motors on M1/M2, 50 cm square, 5 CCW laps per mode, ENCODER truth only: odometry closure, no camera,
no wheel-slip or trackwidth check, geometry is vevov's placeholder), the position-loop path (position_mode 1) closes the square
to a mean of 1.8 mm and a worst of 3.6 mm start-to-end with a heading residual under 0.65 deg, meeting the 11 mm target on every
lap; the kernel path (position_mode 0) closes to a mean of 9.8 mm and a worst of 26.4 mm (one lap of five outside the target,
heading residual up to 3.05 deg), so it meets the target on the mean and four of five laps but not on the worst lap. Mode 1 is
also faster per lap (15.0 vs 17.1 s) but starts legs with a near-step in wheel speed (peaks 261 to 278 mm/s over a ~210 mm/s
plateau) and doubles the failed-I2C growth (35.8 vs 16.0 per lap, wedge stayed 0). These closure numbers say the wheel counts
return to the start; they cannot show whether the floor square closes, which needs the camera or a tape measure.


# Arcs: position_mode 2 vs the kernel (zuvat, circle r=20 cm, 2026-10-27)

Files (all in `circle/`): per-lap recordings `m<mode>_lap<n>_tlm.csv` (+ `_pose.csv`, `_vel.csv`, `.meta.json`), scorer output
`closure.csv` / `closure.md` (`tools/square_closure.py`), `closure_radial.csv` (new `--circle-cm` option: per-lap mean and max
distance of the track from the commanded circle), lap-normalised copies in `norm/`, charts `m0_lap1_chart.png`,
`m0_lap3_chart.png`, `m1_lap2_chart.png`, `m2_lap1_chart.png`, `m2_lap3_chart.png` (`tools/tour_chart.py --circle-cm 20`, new
option: dashed = commanded circle), `final_reset.log`, and `switch_check/` (see below).
Run: `tools/tour_capture.py --wifi 127.0.0.1 --run 'circle 20 1' --set position_mode=<m>`, i.e. board `RUN circle 20 1` =
`circleRun(20, ccw)` = 8 x `tickedMove(arc length 157 mm, +45 deg)`; one lap per capture, `STOP` between laps. Mode 0 x5 laps,
then mode 1 x3, then mode 2 x5. Same session, same build as the square tour (042 hex `binary-zuvat-042.hex`), same floor
patch; the odometry drifted from (30,-39) to (-160,216) mm over the session (the pose is not reset between laps; each lap is
scored on its own first and last frame, idle at both). All laps CCW.

**Every figure is ENCODER truth (kernel wheel odometry). No camera.** Closure in encoder terms says the wheel counts came
back; it does not see slip, scrub, or trackwidth / `travel_calib` error (vevov placeholder geometry), and a motor position loop
that drives each wheel to its own count target will close in counts by construction. The radial-deviation column below is
the commanded-path check that does not have that weakness (still odometry, so it inherits any geometry error).

## Per lap (closure.csv, closure_radial.csv)
| mode | lap | closure [mm] | heading residual [deg] | radial dev mean / max [mm] | lap time [s] | i2cf growth |
|---|---|---|---|---|---|---|
| 0 | 1 | 46.2 | -11.54 | 9.0 / 18.4 | 11.5 | 7 |
| 0 | 2 | 56.9 | -15.81 | 10.1 / 22.0 | 11.5 | 2 |
| 0 | 3 | 58.7 | -15.44 | 11.2 / 24.3 | 11.5 | 2 |
| 0 | 4 | 55.3 | -15.57 | 10.3 / 23.4 | 11.4 | 4 |
| 0 | 5 | 68.6 | -18.53 | 12.0 / 26.8 | 11.4 | 5 |
| 1 | 1 | 66.5 | -17.54 | 12.0 / 24.1 | 11.4 | 3 |
| 1 | 2 | 15.3 | -5.74 | 6.1 / 13.9 | 11.7 | 4 |
| 1 | 3 | 39.1 | -11.27 | 7.5 / 16.7 | 11.6 | 5 |
| 2 | 1 | 48.0 | -0.44 | 37.2 / 68.5 | 9.1 | 56 |
| 2 | 2 | 1.4 | -0.52 | 30.7 / 67.9 | 9.0 | 57 |
| 2 | 3 | 1.4 | -0.45 | 30.6 / 66.9 | 9.0 | 57 |
| 2 | 4 | 2.2 | -0.34 | 30.3 / 66.9 | 9.0 | 57 |
| 2 | 5 | 1.4 | -0.59 | 31.0 / 67.5 | 9.0 | 57 |
Heading residual = end heading - start heading mod 360 (a full circle should read 0).

## Comparison
| mode | laps | closure mean [mm] | closure worst [mm] | heading mean abs [deg] | heading worst abs [deg] | radial dev mean of means / worst max [mm] | lap [s] | i2cf per lap |
|---|---|---|---|---|---|---|---|---|
| 0 (kernel) | 5 | 57.1 | 68.6 | 15.38 | 18.53 | 10.5 / 26.8 | 11.5 | 4.0 |
| 1 (falls back to kernel on arcs) | 3 | 40.3 | 66.5 | 11.52 | 17.54 | 8.5 / 24.1 | 11.6 | 4.0 |
| 2 (motor position loop) | 5 | 10.9 (laps 2-5: 1.6) | 48.0 (lap 1) | 0.47 | 0.59 | 32.0 / 68.5 | 9.0 | 56.8 |
Mode 0 and mode 1 are the same behaviour: the kernel arcs under-rotate by 5 to 18 deg per lap and leave 15 to 69 mm closure
(lap to lap spread is large: mode 1 laps 15, 39, 67 mm), the mode 1 lap time (11.6 s), i2cf growth (4 per lap) and wheel-speed ratio
(median vl/vr 0.55, mode 0 0.56) all match mode 0, so mode 1 does fall back to the kernel on arcs
(`m1_lap2_tlm.csv`, `m0_lap3_tlm.csv`; `posmove` was not sampled mid-run here). The two are equal within noise.

## What mode 2 does on an arc (the charts, `m2_lap3_chart.png` vs `m0_lap3_chart.png`)
Mode 2 returns the heading to the start within 0.6 deg and, in laps 2 to 5, the position within 1.4 to 2.2 mm (`closure.csv`),
and is 22 % faster (9.0 vs 11.5 s). But the speed panel shows each arc as the two wheels running at nearly the SAME speed (median
vl/vr 1.07 over the frames where both exceed 50 mm/s, `m2_lap3_tlm.csv`; the circle needs 0.56, which the kernel delivers:
0.56 in `m0_lap3_tlm.csv`), the left (inner) wheel finishing early (left runs ~0.6 s, right ~1.1 s per arc) and the right wheel
then finishing alone. The speeds are not proportional to the commanded arc lengths, so each 45 deg arc is a near-straight run
plus a one-wheel pivot at the end: the track is a bumpy octagon, offset about 60 mm sideways of the commanded circle
(`m2_lap3_chart.png`), and strays 30 mm on average and 67 to 69 mm at worst from the commanded circle against 6 to 12 mm mean /
14 to 27 mm max for the kernel (`closure_radial.csv`). Peak wheel speed 264 to 291 mm/s against 139 to 231 mm/s for the kernel
(`m*_lap3_tlm.csv`). It also costs 57 failed I2C transactions per lap against 4 (`closure.csv`), the same ratio-of-ten-ish
excess the pivots and square showed. Mode 2 lap 1 ended 48 mm off (x +48) while laps 2 to 5 ended 1.4 to 2.2 mm off. A repeat with a clean
0 -> 2 switch (`switch_check/s0a` kernel 27.1 mm / -7.5 deg, then `s2a` 2.0 mm, `s2b` 1.4 mm, `switch_check/closure.md`) did NOT reproduce the outlier, so
the cause of lap 1 is UNVERIFIED (it came right after the mode 1 laps; one occurrence).

## Decision
**Mode 2 default for arcs: NO. Keep position_mode 1** (arcs on the kernel). Numbers: mode 2 wins on encoder closure (laps 2-5
1.6 mm mean vs 57 mm kernel; heading 0.47 deg vs 15.4 deg) and lap time (9.0 vs 11.5 s), but loses on path fidelity (radial
deviation 32 mm mean vs 10.5, 68 mm max vs 27), has a 48 mm lap-1 outlier, and runs the arcs as straight-plus-pivot segments
with wheel speeds in ratio 1.07 instead of 0.56, plus 14x the I2C failures (57 vs 4 per lap). The kernel arcs close poorly in
encoder terms (heading short by 15 deg per 360) but follow the commanded circle. The closure advantage is also partly
by construction: a per-wheel position loop lands each wheel on its count target whatever path it took between them. Mode 2 is
NOT equal within noise, so the "equal, keep the lower-risk mode" clause does not even apply; the choice rests on shape fidelity.
Follow-up for the team lead: the arc case of the mode 2 path appears not to apply per-wheel proportional speeds (a defect or
missing feature in the arc route; not diagnosed here, no tuning done). Re-run if that is fixed.

## After the runs
The first reset attempt (`final_reset.log`) used ids that did not match the board's counter and did not take (mode still 2, TLM
still on). The corrected sequence in `final_check.log` read position_mode back 2, set it to 0, read it back 0.000000, TLM off
(`tlm=off`), `active=0 posmove=0`: robot idle, TLM off, position_mode 0.

# Ticket 001: 50 cm acceptance on zuvat (2026-10-27)

Scope change: the one-wheel micro:bit bench rig is gone (its board became zuvat), so the 50 cm protocol
ran on zuvat over the loki tunnel, replacing `captures/bench-position-<date>/`. Evidence is in `fiftycm/`
(per-trial CSV `position.csv` / `kernel.csv`, per-trial frame CSVs `<tag>_<cruise>_<trial>.csv`,
`<tag>_summary.csv`, stdout `../fiftycm_position.log` / `../fiftycm_kernel.log`,
`restore_readback.log`). Hex: `binary-zuvat-042.hex` (this directory; no reflash for this ticket).
Tool: `tools/mb50.py --wifi 127.0.0.1 --mode position|kernel`.

All numbers are ENCODER truth. Nobody watched the robot and there is no camera or OTOS.

## Method
- Per-wheel read: the TLM FULL frame carries `posl` / `posr`, the raw wheel counts. Each trial reads both
  at rest (two or more consecutive frames, both wheels |v| <= 2 mm/s, counts unchanged) before the move and
  0.3 s after it. 1 count = 0.1 deg of shaft; `GET wheel_diameter` = 90.899 mm, so 0.079322 mm/count
  (`getall.log` has the same diameter). Error = signed travel along the commanded direction minus 500 mm.
- Cross-checks in the CSV: `int_l_mm`/`int_r_mm` (vl/vr trapezoid-integrated over the device clock) and
  `odo_mm` (hypot of x/y odometry). Odometry vs the mean of the two encoder travels differs by at most
  0.9 mm in either set.
- "Percent" is cruise mm/s of v_max 250: 75 / 150 / 250. MOVE_X +-500 0 <cruise> 8000, 8 legs per cruise
  (4 forward, 4 reverse, alternating), 24 per mode. STOP between runs.
- posmove: one STATUS sent at max(0.4 s, 0.4 x nominal duration) after the ack, and one STATUS after the
  move; both are columns `posmove_mid` / `posmove_after` in the trial CSV.
- Time: host clock from the MOVE_X ack to the first frame with both wheels at rest (|v| <= 2 mm/s); the
  device-clock span first-moving frame to first-rest frame (`ms_device`) agrees within 5 ms.
- Kernel set: `position_mode 0` with `v_floor 40`, `decel 1000`, `stop_distance 0.3`. The config names
  exist as written in `src/comms/config_fields.h` (`v_floor`, `decel`, `stop_distance`, `v_max`,
  `position_mode`).

## Position mode (position_mode 1), `fiftycm/position_summary.csv`
Err = travel - 500 mm, per wheel, mm. Time = ack to rest, ms.

| cruise | dir | wheel | n | mean | sd | worst | time |
|---|---|---|---|---|---|---|---|
| 75 | fwd | L | 4 | -0.26 | 0.00 | -0.26 | 6656 |
| 75 | fwd | R | 4 | -0.36 | 0.12 | -0.42 | 6656 |
| 75 | rev | L | 4 | -0.26 | 0.00 | -0.26 | 6674 |
| 75 | rev | R | 4 | -0.36 | 0.12 | -0.42 | 6674 |
| 150 | fwd | L | 4 | -0.26 | 0.00 | -0.26 | 3375 |
| 150 | fwd | R | 4 | -0.18 | 0.00 | -0.18 | 3375 |
| 150 | rev | L | 4 | -0.26 | 0.00 | -0.26 | 3367 |
| 150 | rev | R | 4 | -0.18 | 0.00 | -0.18 | 3367 |
| 250 | fwd | L | 4 | -0.26 | 0.00 | -0.26 | 2564 |
| 250 | fwd | R | 4 | -0.08 | 0.08 | -0.18 | 2564 |
| 250 | rev | L | 4 | -0.26 | 0.00 | -0.26 | 2542 |
| 250 | rev | R | 4 | -0.41 | 0.15 | -0.49 | 2542 |

Worst of 48 wheel readings: 0.49 mm, short. `posmove` read 1 mid-move and 0 after in 24 of 24 trials
(`position.csv`); `reason=stop` in all. The ~0.26 mm short is the 3 or 4 counts the wheel always stops
short, constant per wheel (quantisation of 0.079 mm/count).

## Kernel set (position_mode 0), `fiftycm/kernel_summary.csv`
| cruise | dir | wheel | n | mean | sd | worst | time |
|---|---|---|---|---|---|---|---|
| 75 | fwd | L | 4 | -1.59 | 7.67 | -11.76 | 6833 |
| 75 | fwd | R | 4 | 2.34 | 7.11 | 11.64 | 6833 |
| 75 | rev | L | 4 | 0.73 | 1.33 | 2.36 | 6751 |
| 75 | rev | R | 4 | 1.35 | 1.57 | 3.07 | 6751 |
| 150 | fwd | L | 4 | 1.11 | 1.11 | 2.36 | 3530 |
| 150 | fwd | R | 4 | -0.79 | 1.79 | -2.87 | 3530 |
| 150 | rev | L | 4 | -1.03 | 2.10 | -3.35 | 3560 |
| 150 | rev | R | 4 | 2.18 | 1.04 | 3.31 | 3560 |
| 250 | fwd | L | 4 | -0.64 | 1.61 | -2.72 | 2471 |
| 250 | fwd | R | 4 | 1.01 | 1.49 | 2.84 | 2471 |
| 250 | rev | L | 4 | -0.14 | 1.26 | 1.57 | 2450 |
| 250 | rev | R | 4 | 0.46 | 1.83 | 2.36 | 2359-2480 |

`posmove` stayed 0 throughout (mid and after) in all 24. The 75 fwd outlier is trial 6
(`kernel_75_6.csv`): L -11.76 / R +11.64, opposite signs, so the robot yawed rather than mis-stopped;
`i2cf_delta` was 22 for that leg against a median of 3 (`kernel.csv`). Not diagnosed
(see `clasi/issues/zuvat-i2c-fault-count-grows-during-position-moves.md`).

## Bars
- Every trial within 0.5 mm of 500 mm, per wheel (position set): MET, worst 0.49 mm (`position.csv`).
  The kernel set misses it by 5 to 25x (worst 11.8 mm); that is the comparison, not a bar.
- Time at 100 % (250 mm/s) under 1.2 s: **NOT MET**. Measured 2.53 to 2.58 s, ack to rest
  (`position.csv`, cruise 250). Physical floor: 500 mm at v_max 250 mm/s takes at least 2.0 s even with
  no ramps, so 1.2 s is unreachable on this wire (the old rig's 100 % was ~792 mm/s). Not tuned.
- posmove=1 mid-move in every position trial and 0 after: MET, 24 of 24.

## Things found on the way
- `v_max` read 200 (not the 250 of `getall.log`) when this ticket began, left over from an earlier
  session on this board (unknown which). A first kernel set at 250 therefore clamped at ~220 mm/s;
  it was discarded and rerun with `SET v_max 250` first (`fiftycm_kernel.log` is the rerun; the position
  set is unaffected since the motor runs its own profile). The first kernel run's numbers are not kept.
- Position mode peaks above the commanded cruise on vl/vr (258 on 250; 201 on 150 in trial 0),
  as the 042 notes already said (~5-10 % over).
- `i2cf` growth per leg: mean 4.9 (position) vs 4.0 (kernel) (`i2cf_delta`).

## Restored state
`restore_readback.log`: v_floor 70, decel 400, stop_distance 0, position_mode 0, v_max 250 (these are the
`getall.log` boot values), TLM off, `active=0 posmove=0`.

## Coordinator decision (ticket 001)
Accepted as done. The 1.2 s bar came from the bench rig at 100 % duty (about 1150 deg/s, roughly 830 mm/s on an
83 mm wheel, nezha-esp32/docs/fifty-cm.md); it is unreachable on this wire (MOVE_X cruise ceiling v_max 250 mm/s,
500 mm needs 2.0 s with no ramps). Measured 2.53 to 2.58 s (`fiftycm/position.csv`). Raising the ceiling is a
decision for ticket 007 and the stakeholder. Findings recorded above: stale `v_max` 200 (a live SET from an earlier
session survived; kernel set rerun at 250) and kernel trial-6 outlier (L -11.76 / R +11.64 mm, i2cf +22,
`fiftycm/kernel_75_6.csv`).

# Ticket 006: speed_path A/B (zuvat, 2026-10-27)

Scope change: the one-wheel bench rig no longer exists (its micro:bit is zuvat), so "both rigs" collapses to zuvat and the
per-rig table is a per-path table on zuvat. Everything is ENCODER truth (TLM FULL `posl`/`posr` raw counts, 0.079322 mm/count;
heading from (dR-dL)/111.6 mm, zuvat.json trackwidth placeholder, so heading is UNVERIFIED in absolute terms but comparable
between paths). Driver `speedpath/sp_run.py`, analysis `speedpath/sp_analyze.py`, raw per-run CSVs in `speedpath/`
(`wheels_p<path>_<speed>_<dir>.csv`, `leg_p<path>_<i>_<dir>.csv`, `refresh_p1_120.csv`), summaries `speedpath/wheels_summary.csv`,
`speedpath/legs_summary.csv`, `speedpath/refresh_p1_120_speed.csv`, tables `speedpath/tables.md`.
`speed_path` was read back (GET) at the start of every block (`sp_run.py` asserts it). WHEELS_V grammar: `WHEELS_V L R duration_ms #n`,
duration is the lease (`src/comms/wire_handler.cpp` execWheelsV, ceiling 5000 ms); each hold used a 2400 ms lease and a STOP at about
2.0 s, so the lease never expired during a hold. Directions alternated (fwd then rev) so the robot stays in place.

## 1. WHEELS_V hold, 5 speeds x 2 directions per path (steady window = onset+0.7 s .. +1.5 s; speeds in mm/s per wheel)
Mean = encoder displacement / device time over the window. sd = sd of the TLM `vl`/`vr` frames in the window (about 56 ms apart).
`min` = lowest per-frame encoder speed in the window. "stall frames" = frames with zero count change on that wheel while running
(-1 = the wheel never moved). i2cf = growth over the whole run (STOP and settle included). Source: `speedpath/wheels_summary.csv`.

| path | cmd mm/s | dir | mean L | mean R | err L | err R | sd L (tlm) | sd R (tlm) | min L / R | stall frames L/R | i2cf |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 40 | fwd | 4.2 | 0.0 | -35.8 | -40.0 | 9.2 | 0.0 | 0.0 / 0.0 | 18/25 | 81.0 |
| 0 | 40 | rev | 0.0 | 0.0 | -40.0 | -40.0 | 0.0 | 0.0 | 0.0 / 0.0 | -1/-1 | 80.0 |
| 0 | 70 | fwd | 70.2 | 71.6 | 0.2 | 1.6 | 5.4 | 7.0 | 56.2 / 57.3 | 0/0 | 16.0 |
| 0 | 70 | rev | 78.0 | 60.3 | 8.0 | -9.7 | 16.5 | 15.7 | 51.3 / 36.1 | 5/0 | 31.0 |
| 0 | 120 | fwd | 120.4 | 119.9 | 0.4 | -0.1 | 9.9 | 8.0 | 103.8 / 99.5 | 0/0 | 2.0 |
| 0 | 120 | rev | 119.0 | 117.9 | -1.0 | -2.1 | 10.1 | 10.3 | 102.8 / 95.2 | 0/0 | 5.0 |
| 0 | 200 | fwd | 201.7 | 200.5 | 1.7 | 0.5 | 7.2 | 7.7 | 164.4 / 168.7 | 0/0 | 1.0 |
| 0 | 200 | rev | 201.2 | 199.6 | 1.2 | -0.4 | 5.7 | 9.7 | 168.7 / 168.7 | 0/0 | 3.0 |
| 0 | 250 | fwd | 253.4 | 252.3 | 3.4 | 2.3 | 9.6 | 9.7 | 216.3 / 215.9 | 0/0 | 1.0 |
| 0 | 250 | rev | 253.4 | 253.6 | 3.4 | 3.6 | 7.1 | 7.6 | 220.3 / 219.2 | 0/0 | 3.0 |
| 1 | 40 | fwd | 38.4 | 33.2 | -1.6 | -6.8 | 14.4 | 19.5 | 26.8 / 13.4 | 0/0 | 10.0 |
| 1 | 40 | rev | 39.1 | 41.4 | -0.9 | 1.4 | 18.7 | 12.0 | 28.1 / 25.4 | 0/0 | 4.0 |
| 1 | 70 | fwd | 70.6 | 72.2 | 0.6 | 2.2 | 35.7 | 34.0 | 29.9 / 37.4 | 0/0 | 4.0 |
| 1 | 70 | rev | 74.3 | 71.4 | 4.3 | 1.4 | 31.5 | 26.4 | 37.4 / 28.4 | 0/0 | 1.0 |
| 1 | 120 | fwd | 120.9 | 116.1 | 0.9 | -3.9 | 31.9 | 41.0 | 79.3 / 70.3 | 0/0 | 2.0 |
| 1 | 120 | rev | 119.3 | 116.5 | -0.7 | -3.5 | 37.8 | 45.5 | 74.8 / 67.3 | 0/0 | 4.0 |
| 1 | 200 | fwd | 183.4 | 179.2 | -16.6 | -20.8 | 77.7 | 76.6 | 101.5 / 98.8 | 0/0 | 2.0 |
| 1 | 200 | rev | 180.9 | 185.3 | -19.1 | -14.7 | 65.1 | 59.8 | 119.7 / 104.8 | 0/0 | 2.0 |
| 1 | 250 | fwd | 228.6 | 216.3 | -21.4 | -33.7 | 87.8 | 85.3 | 133.2 / 116.7 | 0/0 | 2.0 |
| 1 | 250 | rev | 232.5 | 229.2 | -17.5 | -20.8 | 56.4 | 53.8 | 145.2 / 116.7 | 0/0 | 2.0 |

Findings (wheels):
- Path 0 (0x60 integer percent) holds 70..250 mm/s to within 0.2..3.6 mm/s (mean), sd 5..10 mm/s, no stalls, except 70 mm/s reverse
  (L 78.0 / R 60.3, sd 16, 5 stall frames on L) and **40 mm/s, which does not run at all**: forward L 4.2 / R 0.0 mm/s
  (net 19 mm / 0.2 mm), reverse zero on both wheels. i2cf grew by 81 and 80 in those two runs against 1..5 elsewhere, so the
  too-low command also floods the bus with faults (not diagnosed).
- Path 1 (0x77 + 0x70 mode 3) runs 40 mm/s (mean 33..41, err -6.8..+1.4) and 70 mm/s, which path 0 cannot do at 40. But its
  speed is far less steady: sd 14..45 at 40..120 and 54..88 at 200..250 against 5..10 on path 0, per-frame speed swings
  between roughly half and 1.7x the command, and above 120 it under-delivers: 200 mm/s gives 179..185 (err -15..-21), 250 gives
  216..233 (err -17..-34). No frame with a wheel at zero in any path-1 run (stall frames 0, `speedpath/wheels_summary.csv`).
- i2cf growth: path 0 1..5 per run (excluding the sub-floor 40 runs and the 70 rev run: 16 and 31); path 1 1..10 per run.
  Path 1 does not cost more faults per run than path 0, so the two-frames-per-change plus refresh traffic is not visible in i2cf.

## 2. 600 mm kernel legs (`MOVE_X +-600 0 150 8000`, position_mode 0), 6 per path, alternating direction
Source: `speedpath/legs_summary.csv`. Travel L/R from posl/posr (`speedpath/leg_p*_*.csv`). Heading = encoder-derived, lateral =
deviation in the start-heading frame (y), both ENCODER truth.

| path | leg | dir | travel L | travel R | err L | err R | heading deg | lateral mm | time ms | i2cf |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | fwd | 603.32 | 600.63 | +3.32 | +0.63 | -1.39 | -5.7 | 4254.0 | 1.0 |
| 0 | 1 | rev | 603.96 | 600.23 | +3.96 | +0.23 | +1.91 | -10.5 | 4254.0 | 0.0 |
| 0 | 2 | fwd | 603.72 | 600.23 | +3.72 | +0.23 | -1.79 | -10.1 | 4307.0 | 1.0 |
| 0 | 3 | rev | 603.96 | 600.23 | +3.96 | +0.23 | +1.91 | -11.7 | 4254.0 | 0.0 |
| 0 | 4 | fwd | 604.20 | 598.48 | +4.20 | -1.52 | -2.93 | -21.1 | 4254.0 | 2.0 |
| 0 | 5 | rev | 604.20 | 600.63 | +4.20 | +0.63 | +1.83 | -12.0 | 4307.0 | 0.0 |
| 1 | 0 | fwd | 602.85 | 601.26 | +2.85 | +1.26 | -0.81 | -10.3 | 4595.0 | 0.0 |
| 1 | 1 | rev | 604.83 | 599.28 | +4.83 | -0.72 | +2.85 | -25.1 | 4541.0 | 2.0 |
| 1 | 2 | fwd | 603.24 | 600.15 | +3.24 | +0.15 | -1.59 | -16.2 | 4598.0 | 0.0 |
| 1 | 3 | rev | 604.35 | 599.99 | +4.35 | -0.01 | +2.24 | -17.3 | 4493.0 | 2.0 |
| 1 | 4 | fwd | 602.85 | 600.47 | +2.85 | +0.47 | -1.22 | -8.8 | 4598.0 | 2.0 |
| 1 | 5 | rev | 605.54 | 598.88 | +5.54 | -1.12 | +3.42 | -26.9 | 4421.0 | 1.0 |

path 0: heading mean abs 1.96 deg, lateral mean abs 11.8 mm, err L +3.89 R +0.07, time 4272 ms, i2cf mean 0.7
path 1: heading mean abs 2.02 deg, lateral mean abs 17.4 mm, err L +3.94 R +0.00, time 4541 ms, i2cf mean 1.2

Findings (legs): final distance error is the same on both paths (L about +3.9 mm, R about 0 mm; a constant left-versus-right count
scale offset, not a speed_path effect). Heading change over the leg is about 2 deg on both paths (forward legs drift negative,
reverse legs positive, so it is a path-independent mechanical or encoder-scale bias). Lateral deviation is worse on path 1 (mean abs 17.4 mm
vs 11.8 mm). Path 1 legs take about 270 ms longer (4541 vs 4272 ms) because of the slower, rougher speed. i2cf growth 0..2 per leg on both.

## 3. Explicit refresh check: WHEELS_V 120 120 3600, held ~3 s, path 1 (`speedpath/refresh_p1_120.csv`, `speedpath/refresh_p1_120_speed.csv`)
Run 2977 ms from first motion to last, 68 frames. In the steady part (0.3..2.7 s, 41 frames) the lowest per-frame encoder speed was
L 61.4 / R 49.4 mm/s against 120 commanded and never zero; the speed varies 50..210 mm/s frame to frame with no visible period matching the
400 ms refresh. Verdict: the 400 ms bare 0x70 refresh does keep the motor running (no stall, no zero frame), but speed ripples by about +-50 %
within and between refreshes, so "never drops" holds only in the sense of never stopping.

## Decision line
`speed_path` default stays 0. Path 1 is clearly better in one place only (40 mm/s, where path 0 does not run and floods the bus),
and it is stall-free, but it is noticeably worse everywhere else (speed sd 3 to 8 times larger, 10 to 14 percent low at 200..250 mm/s,
17.4 vs 11.8 mm lateral on a 600 mm leg, 270 ms slower), and equal on final distance and heading. Not "clearly better". Ticket 009
keeps the default 0; path 1 is worth offering as the explicit fine-speed option below v_floor only. Bar not met / nothing tuned.

## Restored state
`speedpath/restore_readback.log`: speed_path 0, position_mode 0, v_max 250, v_floor 70, decel 400, stop_distance 0, TLM off, `active=0 posmove=0`.
