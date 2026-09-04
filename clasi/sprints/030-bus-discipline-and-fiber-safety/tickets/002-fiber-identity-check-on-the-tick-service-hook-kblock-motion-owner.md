---
id: '002'
title: Fiber-identity check on the tick service hook; kBlock motion owner
status: open
use-cases: [SUC-002]
depends-on: ['001']
github-issue: ''
issue: code-review/service-hook-must-check-fiber-identity.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Fiber-identity check on the tick service hook; kBlock motion owner

## Description

`Protocol::serviceHookEntry()` (`src/comms/protocol.cpp:457-460`) gates
on `protocol().motionOwner_ != MotionOwner::kJob` — a piece of STATE —
not on which fiber is calling `tickDrive()`. `tickDrive()` fires the
hook on every call from any fiber (`shims.cpp:764`). Confirmed still
live: a `RUN:tour` job running on the protocol fiber, with a
button-press handler (`test.ts:534-536` → `tourWorld()`, a CODAL
`MessageBus` fiber distinct from the protocol fiber) calling
`driveTick()` in its own loop — each of that second fiber's ticks runs
`serviceOnce()` → `wireHandler_.feed()` → `dispatch()`, which sends the
ack (a yielding serial write) and then executes `fields[]`, pointers
into the shared `lineBuf_`, while the protocol fiber's own
`serviceOnce()` feeds the next line into that same buffer during the
yield. `BusGuard`/`stepBusy` (ticket 001) still serializes
`kernel.step()` itself; this corrupts the wire layer, a different
concern.

Separately (confirmed still live): `motionOwner_` (`kNone`/`kWire`/
`kJob`) never arbitrates the block program's own fiber.
`startMove()`/`driveTwist()`/`startDrive()` (`shims.cpp`) call the
engine unconditionally, so a button-handler tour can supersede a live
wire move with no arbitration at all — the wire's pending completion
then resolves off the student's move and reports `kStop`,
indistinguishable from a genuine stop the host itself caused.

## Remedy

- **Fiber identity.** Capture the protocol fiber's own identity the
  first time `Protocol::run()` executes (a CODAL fiber-id read, or
  equivalent), stored on the `Protocol` instance. Add an injectable
  "current fiber" accessor (a plain function pointer or virtual seam,
  defaulting to the real CODAL read) so a host test can pin a fake
  value for both sides of the comparison. `serviceHookEntry()` becomes:
  return unless `currentFiber() == protocolFiberId_` — full stop, no
  fiber but the protocol fiber's own `tickDrive()` call ever runs
  `serviceOnce()`, regardless of what `motionOwner_` says.
- **Third motion owner.** Add `MotionOwner::kBlock` to the existing
  `kNone`/`kWire`/`kJob` enum (`protocol.h`). The block-motion entry
  points — `startMove()`, `startGoTo()`, `driveTwist()`, `startDrive()`
  (`shims.cpp`) — take `kBlock` ownership when `motionOwner_ == kNone`
  at the point they are called, and release it back to `kNone` when
  their own move ends (mirroring how `dispatchJob()` takes/releases
  `kJob`). **Decision, per the issue's own two acceptable options**:
  do NOT refuse block motion outright while `motionOwner_ != kNone` —
  `test.ts`'s existing button-triggered tours are a real, working,
  idle-time use of the robot, and a blanket refusal would regress
  them. Instead, arbitrate: a block-motion call while `motionOwner_ ==
  kWire` or `kJob` is refused/reported the same way a wire verb
  arriving during a job already is (do not silently supersede); a wire
  verb arriving while `motionOwner_ == kBlock` is refused the same
  `kBusy` a `kJob`-held drivetrain already answers with.
- Fold `motionOwner_`/`jobOwnsMotion_`'s pre-existing duplication
  (review finding CM-14) into this same one-owner field as a byproduct
  of touching this code, not a separate change.
- Document both decisions in `src/DESIGN.md` §8 (already drafted in this
  sprint's `design/` overlay,
  `clasi/sprints/030-.../design/DESIGN.md` — apply that text, adjusting
  for whatever the actual implementation ends up naming, rather than
  re-deriving the design from scratch).

## Acceptance Criteria

- [ ] `serviceHookEntry()` checks fiber identity via the injectable
      accessor, not `motionOwner_`.
- [ ] A host test (decision-logic only, via the injectable seam — real
      CODAL fibers cannot be exercised host-side) confirms: given
      fiber A's id captured as "the protocol fiber" and a call
      presenting fiber B's id, the hook does not invoke `serviceOnce()`.
- [ ] `MotionOwner::kBlock` exists; a host test (same seam) or a
      documented code-review check confirms a block-motion entry point
      takes it and a wire verb arriving while it is held is refused
      `kBusy`.
- [ ] `motionOwner_`/`jobOwnsMotion_` duplication (CM-14) is resolved
      to one field.
- [ ] `src/DESIGN.md` §8 documents the fiber-identity check and the
      `kBlock` decision (apply this sprint's `design/` overlay text).
- [ ] Not fully host-testable — `protocol.cpp` includes `pxt.h`.
      Hardware acceptance (team-lead session, not programmer-dispatched
      per this sprint's Test Strategy): a button-handler tour running
      during a live `RUN:tour` no longer corrupts wire dispatch, and a
      block-side `startMove()` during a live wire obligation is refused
      or reported rather than silently superseding — MEASURED citation
      required, against both the pre-fix reproduction and the fixed
      build, same board, same scenario.

## Testing

- **Existing tests to run**: any existing `protocol.cpp`/`wire_adapter`
  host-side decision-logic tests; `tests/host/` full suite scoped to
  touched files during implementation.
- **New tests to write**: the injectable-fiber-identity decision-logic
  test and the `kBlock` arbitration test described above.
- **Verification command**: `uv run pytest tests/host/ -k "protocol or
  motion_owner or service_hook"` during implementation; full `uv run
  pytest` at `close_sprint`; hardware acceptance is a separate
  team-lead-run bench session (see this sprint's Test Strategy).
