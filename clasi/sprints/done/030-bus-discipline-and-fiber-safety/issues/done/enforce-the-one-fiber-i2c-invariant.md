---
status: done
sprint: '030'
tickets:
- 030-001
---

# Enforce the one-fiber I2C invariant: bus guard on every OTOS entry, deferred rebase write, no background samplers

Priority: **Critical** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: RC-01 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)), CM-03
([comms](../../../docs/code-review/2026-09-02/raw/comms.md)), BT-04, BT-05 ([blocks-and-test](../../../docs/code-review/2026-09-02/raw/blocks-and-test.md)).
Triage #1.

## Description

`tickDrive()` serialises `kernel.step()` behind `stepBusy` and waits if
another fiber holds it. Nothing else does. Four independent holes let an
OTOS I2C transaction land inside another fiber's encoder select->read
settle window, which destroys that encoder sample (the documented Phase-F
signature, `nezha_port.cpp:376-380`):

1. Every OTOS shim entry (`otosBegin/Read/Zero/Calibrate/SetOffset`,
   `seedPose`) issues I2C with no `stepBusy` check (`shims.cpp:1401-1435,
   1519-1527`; `otos_port.cpp:116-127`).
2. `SET rebase` -> `otosRef().setPose()` runs on the protocol fiber; its
   gate (`hasLiveMotionObligation() || engineMoveActive()`) misses a
   student's `setWheelSpeeds` + `driveTick` loop on the main fiber
   (`wire_adapter.cpp:882-885`; `shims.cpp:1122-1130`).
3. `test/test.ts:808-813` runs `readWorld()` at 10 Hz in
   `control.inBackground` while the job fiber ticks.
4. The `start drive` block forks a background ticker; `read world
   position`, `set world pose`, `calibrate world sensor` next to it in the
   palette are live bus transactions on the main fiber (`motion.ts:178-186`).

Concrete scenario for (1): a student `goToWorld()` on the main fiber while
a bench host has a `MOVE_X` live on the protocol fiber. The protocol fiber
is parked in `step()`'s 4 ms settle after `left_.requestSample()`; the
main fiber's `readWorld()` writes 0x17; the protocol fiber wakes and reads
a destroyed encoder sample.

The invariant is stated in `world.ts:9-12`, `otos_port.h:18-22` and
`src/DESIGN.md` section 7 and enforced nowhere.

## Remedy

- Promote `stepBusy` to a bus-ownership guard with `acquire()` that sleeps
  while held (through the VFP-safe sleeper), taken by `tickDrive()` and by
  every OTOS entry point. Three lines per entry.
- Make `rebase`'s OTOS write deferred to the ticking fiber, the way
  `kernel.rebasePosition()` already is (a `pendingOtosZero` on the Rig,
  performed inside `tickDrive()` after `stepBusy` clears).
- Move `test.ts`'s sampler into the job's own tick loop (every k-th tick);
  for the idle case the protocol fiber's `serviceOnce()` is the place.
- Have `startDrive`'s loop own the OTOS read, or drop `startDrive` in
  favour of `whileDriving`; say in `read world position`'s JSDoc that it
  is a bus transaction.

## Acceptance

- A host test with `FakeSleeper::onSleep` scripting an OTOS entry inside
  the settle window shows the entry waits until `stepBusy` clears.
- `grep -n 'uBit.i2c' src/platform/otos_port.cpp` callers all reach the
  bus through the guard; a source-pin test asserts it.
- `test.ts` has no `control.inBackground` that touches the OTOS.

## Related

- `i2c-fault-count-climbs-on-idle-bus.md` (open) is a symptom this could feed.
- `first-i2c-command-can-wedge-the-program-with-no-recovery.md` (open).
