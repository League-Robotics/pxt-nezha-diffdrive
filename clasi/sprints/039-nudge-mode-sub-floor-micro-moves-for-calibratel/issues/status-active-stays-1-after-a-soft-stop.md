---
status: in-progress
sprint: 039
tickets:
- 039-002
---

# STATUS `active=1` stays stuck after a soft stop of a continuous drive

## Evidence

Reported 2026-09-15 by the nezha-robot-template session. vevov was on
zilch, running template pin v1.20260914.1. **No capture file in this repo
yet.**

Sequence:
1. A RUN job ran `setWheelSpeeds(10,10)` with a `driveTick()` loop.
2. `stop()` was called.
3. A wire `STOP` was sent and acked.

After step 3, STATUS read
`ready=1 active=1 connL=1 connR=1 flags=31 i2cf=2541 cyc=2901`, with cyc
and i2cf flat across reads. Nothing was ticking, yet the robot reported
active.

## Source reading (UNVERIFIED on hardware)

- STATUS `active` is `ready && !estopped && !leaseExpired && !stallHalted
  && diag velocity != 0` (`src/comms/wire_adapter.cpp:312`).
- `stop()` and wire `STOP` both reach `Rig::softStop()`
  (`src/shims.cpp:928-934`). That zeroes the motor ports and stages a
  neutral, but it **never steps the kernel**. The published `Output`
  therefore keeps the last mid-drive wheel velocity until something ticks
  again.
- This is the same frozen-Output shape `tickDrive()`'s settle loop already
  fixed for a Hold's *natural* deadline (`shims.cpp:677-687`,
  `settleToRest()`). The explicit soft-stop path never got that fix.

The motors really are stopped, so the flag is a frozen snapshot, not
motion. It still makes STATUS lie. Any host that waits on `active=0`
(robotlink, calibration scripts) will hang or misreport.

## Also open from the same report (not explained by source)

A `setWheelSpeeds` loop asked for 40 `driveTick()`s ended after cyc +16
and +17. The RUN job's completion line never appeared.

Candidates:
- The starvation watchdog soft-stopped after a >100 ms gap between ticks.
- `kernel.drive()` refused the command.
- `emitLine()` dropped the line because the emit ring was full. That drop
  is silent and counted in diag 29.

A rerun reading diag 29 and the lease-expiry/refusal diags before and
after would separate them.
