---
status: pending
sprint: '030'
---

# The tick service hook must check fiber identity; decide the block fiber's place in motionOwner_

Priority: **High** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: CM-01 ([comms](../../../docs/code-review/2026-09-02/raw/comms.md)), RC-03 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)). Triage #2.

## Description

`Protocol::serviceHookEntry()` (`protocol.cpp:342-345`) gates on
`motionOwner_ == kJob`, not on which fiber is calling, and `tickDrive()`
fires the hook on every call from any fiber (`shims.cpp:715`). Scenario
from the shipped test program: a `RUN:tour` job is running on the protocol
fiber; the operator presses button B (`test.ts:534-536` -> `tourWorld()` on
a MessageBus fiber, `while (driveTick())`). Each of that fiber's ticks now
runs `serviceOnce()` -> `wireHandler_.feed()` -> `dispatch()`, which sends
the ack (a yielding serial write) and then executes `fields[]`, pointers
into `lineBuf_`. The other fiber's `serviceOnce()` feeds the next line
into the same buffer during that yield, and the parked fiber executes a
motion verb with the new line's digits. `stepBusy` still serialises
`step()`; this corrupts the wire layer.

Separately (RC-03): the block program's fiber is a third executor that
`motionOwner_` (`kNone/kWire/kJob`) never arbitrates. `startMove()`
(`shims.cpp:486`) calls `engine.moveX()` unconditionally, superseding a
live wire move; the wire's pending completion then resolves off the
student's move and reports `kStop`.

## Remedy

- Capture the protocol fiber's identity in `run()` and have
  `serviceHookEntry()` return unless the current fiber is that one. Give
  it an injectable "current fiber" seam so a host test can pin it.
- Decide the block fiber's place: refuse block motion while
  `motionOwner_ != kNone` (the bench has the robot), or take ownership
  (`kBlock`) so the wire's completion channel resolves honestly. Either is
  acceptable; document the choice in `src/DESIGN.md` section 8.
- Fold `motionOwner_`/`jobOwnsMotion_` into one owner (CM-14).

## Acceptance

- Host test: a second `tickDrive()` caller during a job never runs
  `serviceOnce()`.
- Host test: a block-side `startMove()` during a live wire obligation is
  refused or reported, never silently superseding.
