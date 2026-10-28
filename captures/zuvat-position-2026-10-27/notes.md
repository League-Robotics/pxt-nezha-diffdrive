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
