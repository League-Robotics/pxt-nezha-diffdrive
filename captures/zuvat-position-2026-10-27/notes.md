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
