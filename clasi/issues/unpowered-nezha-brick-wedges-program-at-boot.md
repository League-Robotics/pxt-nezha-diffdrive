---
status: pending
sprint: '010'
---

# Unpowered Nezha brick wedges the whole program at first I2C touch

## Description

Bench-measured on vevov (2026-08-19): when the Nezha brick is
unpowered (battery off/dead) or otherwise unreachable on I2C, the
first I2C transaction — `kernel.begin()`'s encoder priming inside the
lazy `ensure()` on first block/TLM use — never returns. codal's
NRF52 I2C driver busy-spins on the wedged bus, which freezes the
entire cooperative fiber scheduler: the boot banner is the last serial
output (it precedes the first I2C touch), no TLM is ever emitted, PING
goes unanswered, and button handlers are dead. Externally this looks
like a total firmware hang; the DAPLink debug side stays alive.

Expected behavior: an unreachable brick should degrade gracefully —
`connected=false`, `i2cFaultCount` climbing, protocol/TLM/DIAG alive so
the failure is observable, blocks no-op instead of hanging.

Possible directions (needs investigation): codal I2C timeout options;
pre-flight bus probe with timeout before `begin()`'s priming reads;
guarding the priming path so a dead bus marks the wheel disconnected
instead of blocking. Note the constraint that the kernel's own
step()/tick() I2C also runs every 24 ms — a fix has to cover the
steady-state path, not only boot priming.

Diagnosis session context: DIAG verb (protocol) now exposes
conn/i2cf/stall/estop/lastError, which is how this was isolated.

## Bench observation, tovez, 2026-08-24 — the failure can present WITHOUT a wedge

Stakeholder confirmed the brick was powered on. Firmware flashed from master
`4e14817` (sprints 004+006+007+008). The micro:bit side was **fully alive** —
and yet the motor stack never came up.

### What was observed

```
status ready=0 active=0 connL=0 connR=0 otos=0 wedge=0 flags=0 i2cf=0 tlm=off
```

- v6 protocol fully responsive throughout: `VER`, `ID`, `STATUS`, `GET`,
  `TLM POSE`/`FULL` all replied correctly; telemetry streamed continuously at
  the 50 ms cadence for several minutes.
- **`cyc` (cycleCount) stayed at 0** across every capture — including while a
  valid motion lease was live (`WHEELS_X 100 -100 100 2000`, accepted with no
  error). The kernel never stepped once.
- `i2cf` stayed **0**. No I2C faults were ever counted.
- `dutl`/`dutr` stayed 0; the robot never moved.

### Why this matters for this issue

**This is not the documented failure mode.** This issue describes an
unpowered brick *wedging the whole program* at the first I2C touch —
`kernel.begin()`'s encoder priming busy-spinning on a wedged bus, freezing the
cooperative scheduler so that the boot banner is the last output. That did not
happen here: the scheduler, the protocol fiber, and telemetry all ran normally
for the entire session.

Instead the failure was **silent non-readiness**: `ensure()` ran (confirmed —
`diagValue()` calls it on its first line, and telemetry reads `diagValue`),
`NezhaMotorPort::begin()`'s median-of-3 encoder priming evidently got zero
good reads, so `connected_` stayed false for both wheels and the kernel never
became `ready`. Every subsequent motion command was accepted at the wire and
then refused downstream, with **no error surfaced anywhere** and no fault
counter incrementing.

`i2cf` staying at 0 is explained by the same fact: `i2cFaultCount_` increments
in the kernel's `collect()` path, which only runs when the kernel steps — and
it never stepped. **So a robot in this state reports zero I2C faults precisely
because it is too broken to attempt any I2C.** A monitoring tool that treats
`i2cf == 0` as healthy would read this robot as fine.

### What this suggests for the fix

Whatever remedy this issue lands (codal timeout, pre-flight bus probe, guarded
priming), it should also make this quieter variant observable:

- `begin()` getting zero good priming reads is currently indistinguishable, from
  outside, from a robot nobody has commanded yet. It deserves a distinct,
  readable signal — a status bit, a diag ordinal, or a non-zero counter.
- `ready=0` with `connL=0 connR=0` should arguably be enough for `STATUS` to
  say *why*, rather than leaving an operator to infer it from `cyc` never
  advancing.
- A wire-issued motion verb that is accepted and then silently refused
  downstream is its own defect — related in spirit to
  `stall-latch-invisible-dead-end.md` (sprint 007, closed), which fixed exactly
  this shape of silence for the stall latch.

Root cause of the unreachable brick on this particular robot was not
established in this session and may simply be a sleeping or unseated brick
(this repo's notes record that the Nezha brick auto-sleeps). The value here is
the *presentation*, which the issue text did not previously cover.
