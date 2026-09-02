---
status: pending
---

# Single executor for command dispatch

## Description

Carried out of sprint 026, which delivered the crash fix (VFP yield
guard) and the RUN queue but deliberately did not attempt this. The
stakeholder's stated model is that the protocol puts messages on a
queue and they get served on a main loop; today command execution
still happens on whatever fiber the MessageBus forks.

**What sprint 026 already settled, so this does not need to re-argue
it:** the crash is fixed (the yield guard, hardware-confirmed 0/25 on
the RUN: kill test and 0/4 under telemetry-plus-motion stress), and the
4-slot ring's silent overwrite is fixed (a real queue with occupancy
and a drop counter at diagValue ordinal 28). What remains is
architectural, not urgent.

**What it is still worth doing for:** the link hang under active
telemetry, whose three suspected causes are two-writer serial
contention, RX ring overflow and fiber starvation -- a single executor
removes the first and third structurally. And it makes the I2C
bus-discipline invariant structural rather than a convention three call
sites each have to remember.

## Cause

Three execution models coexist: wire motion ticks on the protocol
fiber, `RUN:` motion ticks on a forked MessageBus fiber, and student
blocks tick on the calling fiber. Only the third is deliberate.

## Proposed fix
**Do not start this ticket until ticket 001's hardware acceptance has
actually passed on gopiv** (0/10 `RUN:straight:20`, 0/10
`RUN:pivot:90`, 0/5 `RUN:square:20`, baseline 3/3 resets confirmed on
unfixed firmware first). This ticket restructures the very fiber the
VFP guard protects; starting it against an unconfirmed guard makes any
failure here ambiguous between "the guard doesn't work" and "this
restructuring is wrong." This is a hard sequencing dependency, not a
convenience ordering — see `clasi/issues/fiber-safety-and-command-dispatch.md`'s
"Proposed fix," which states step 1 must land and be hardware-confirmed
before step 3 begins.

Three execution models coexist today: wire motion ticks on the
protocol fiber (`protocol.cpp`'s `if
(wireAdapter_.hasLiveMotionObligation()) tickDrive();`), `RUN:` motion
ticks on a MessageBus-forked fiber (`src/blocks/run.ts`'s
`control.onEvent(RUN_EVENT_SOURCE, ...)` handler, running a `while
(driveTick())` loop on its own fiber), and student blocks tick on the
calling fiber. Only the third is deliberate. The second is also where
the FPU hazard actually fires (two fibers doing float work
concurrently) and, not coincidentally, the second fiber's concurrency
is also *why* `RUN:abort` works today — "by accident," per the issue:
MessageBus forks a second fiber, so an abort sent while a tour runs
executes concurrently with it.

**Invert the pump, do not make the executor drive the tour.** An
earlier design proposed arming the motion obligation from TypeScript so
the protocol fiber ticks TS-issued moves — this is explicitly
superseded (see the issue's "Superseded" section): `tourWorld()` reads
the OTOS on the handler's own fiber between moves, and moving the tick
elsewhere would put those reads inside the encoder select-to-read
window `src/DESIGN.md`'s bus-discipline invariant forbids — trading an
FPU hazard for an I2C hazard. Likewise, do not turn the tour into a
state machine the executor steps — that destroys the explicit
`startMove()` + `driveTick()` shape `test/test.ts` calls deliberately.
Instead: the tour keeps its own tick loop; that loop's *iterations* run
on the executor's fiber via a service hook.

## Verification

**Not host-testable at all.** `tests/host/` cannot compile `shims.cpp`
or `protocol.cpp` -- both include `pxt.h` -- so every acceptance
criterion needs a robot. Budget 2-3 bench sessions and do not start
without one reliably reachable: sprint 026 ended with magni's USB port
dropping the board repeatedly (`usb 1-1.5` disconnect, and earlier
`device descriptor read/64, error -110`).

## Related

- The parent issue this was split from, and sprint 026's own record.
- `cleartext-run-hangs-the-link-under-active-telemetry.md` -- the
  concrete symptom this would address.
- `ensure-is-not-reentrant-two-rigs-can-be-constructed.md` -- adjacent,
  independent, not fixed by this.

---

## Triage 2026-09-02 — NEXT, and the "not urgent" framing above is stale

The deferral (commit c834520, 10:48) was written without
`concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`
(10:37, same day), which changes the priority:

- The link hang is no longer a three-hypothesis mystery. It is
  MEASURED on tigez with pyOCD: two fibers writing the UARTE wedge it
  in both directions, permanently, on the **first** `RUN:` with a
  payload, no telemetry or motion needed. Every locally built (docker
  `yotta-compiler`) firmware hits it 100%; the cloud build has the same
  bug and only misses the timing window.
- The **single-producer serial piece** of this design — `emitLine()`
  enqueues into a `Protocol`-owned ring, `Protocol::run()` drains it,
  so `uBit.serial.send` and `RadioTransport::sendLine` have exactly one
  caller — was implemented and verified on that board: `RUN:z`,
  `RUN:ping`, `RUN:spin:10` all answer, 10-command soak, 0 reboots.

So plan this as two tickets, in order:

1. **Single serial producer (emit queue on the protocol fiber).** Small,
   already hardware-proven, closes the UART wedge and the cleartext
   link-hang issue. Needs one bench session, not three. Expose the
   ring's drop count via `diagValue()` next to ordinal 28.
2. **The full executor inversion** described above — still worth it for
   making the I2C bus-discipline invariant structural, still not
   host-testable, still budget 2-3 bench sessions. It can wait for a
   reliably reachable board; ticket 1 cannot.

The hardware caveat stands: sprint 026 ended with magni dropping the
board and vevov disconnecting mid-flash. Ticket 1's proof was taken on
tigez over USB with pyOCD, so that is the rig to reuse.
