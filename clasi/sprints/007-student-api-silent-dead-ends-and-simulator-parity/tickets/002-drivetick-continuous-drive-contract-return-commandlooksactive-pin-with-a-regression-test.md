---
id: '002'
title: 'driveTick() continuous-drive contract: return commandLooksActive, pin with
  a regression test'
status: open
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: drivetick-contract-broken-idiom.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# driveTick() continuous-drive contract: return commandLooksActive, pin with a regression test

## Description

`tickDrive()` (`shims.cpp`) returns `moveActive` — the move-*engine's*
post-`serviceMove()` state. `wheelsV()`/`wheelsX()` (called by
`setWheelsTimed()`/`driveTwistTimed()`, which back `setWheelSpeeds()`/
`driveTwist()`) **clear the move planner first**, so after a
continuous-mode command there is never an active move-engine move, and
the documented idiom

    diffDrive.driveTwist(20, 0)
    while (diffDrive.driveTick()) { }

exits on its very first iteration; the watchdog stops the robot ~150 ms
later. **Every** documentation site prescribes exactly this idiom
(README, two worked examples; `specification.md` §4.2;
`usecases.md` UC-002 step 4) while `test/testrig.ts` quietly uses a
different, working pattern (a bare `diffDrive.driveTick()` inside
`basic.forever()`, ignoring the return value) — no in-tree program
uses the documented form (code review R-10/API-01, the review's top
API finding).

**The fix already exists in the file, unused for this purpose.**
`commandLooksActive(const Rig&)` (`shims.cpp`, added by sprint 006 for
the starvation watchdog) returns `r.engine.isMoveActive() ||
out.appliedDutyLeft != 0.0f || out.appliedDutyRight != 0.0f` — exactly
"is anything still commanding the wheels," which is precisely what the
documented idiom needs and precisely the fix the review's own remedy
(a) names ("return 'anything is active' — `commandLooksActive()`... —
so the documented idiom works"). This ticket changes `tickDrive()`'s
final `return moveActive;` to `return commandLooksActive(r);` and
forward-declares `commandLooksActive` before `tickDrive()` (it is
currently defined later in the file, near the watchdog section) — **no
new logic is written.**

**Why this doesn't break blocking moves:** `move()`/`goTo()`
(`main.ts`) are ALSO built on `while (_tickDrive())` — they are not a
separate code path. On the tick that ends a position-mode move,
`serviceMove()` posts `kernel.neutral()` and `tickDrive()`'s existing
12-iteration settle loop (sprint 006, unchanged by this ticket) then
steps the kernel repeatedly with that neutral command already in
effect — `stageDuty()` writes `appliedDutyLeft/Right = 0` from the
FIRST settle step, so by the time this function computes its return
value, `commandLooksActive(r)` already reads `false` for the same
reason `moveActive` did. The documented "a move's final tick still
returns false, ending the loop on the same call that finishes the
move" behavior is unchanged — verified by tracing the settle loop's
existing code, not assumed.

**The simulator gets the equivalent fix.** `_tickDrive()` (`main.ts`)
currently returns raw `simMoveActive`, the same broken pattern. It
changes to return `simMoveActive || simVel !== 0 || simYawRate !== 0`
— the simulator-state equivalent of `commandLooksActive()`. (Sim
`emergency stop` handling, ticket 004, keeps `simVel`/`simYawRate` at
`0` while latched, so this composes correctly with that fix without
either ticket needing to know about the other's internals.)

**Doc sites need no content rewrite.** README, spec §4.2, and UC-002
already describe *this exact contract* — they were aspirational, not
wrong, before the code caught up. Verify this by re-reading all four
sites after the fix lands: none should describe behavior the fixed
code doesn't deliver. Each site gets a small addition pinning the fix
to the new regression test (see Acceptance Criteria) so the two cannot
silently diverge again, per this sprint's own requirement.

## Design Rationale

**Why "fix the return value" and not a new `driveHold()` idiom:**
issue text explicitly offered both options. Redefining the return
value requires zero doc-text rewrites (see above) and reuses a helper
already proven correct in production by the starvation watchdog — a
one-expression change with no new edge case, versus inventing and
documenting a second continuous-mode idiom across four files that
would also contradict `testrig.ts`'s existing bare-tick usage, for no
behavioral gain. See `sprint.md`'s Architecture section and
`design/DESIGN.md` §9/§13 for the full alternatives analysis.

## Acceptance Criteria

- [ ] `tickDrive()`'s `return moveActive;` becomes
      `return commandLooksActive(r);`; `commandLooksActive` is
      forward-declared (or moved) so it is visible at `tickDrive()`'s
      call site. No other line inside `tickDrive()` changes — confirm
      via diff review that the settle loop, the concurrency guard, and
      the pacing logic are byte-identical to before.
- [ ] `main.ts`'s `_tickDrive()` returns
      `simMoveActive || simVel !== 0 || simYawRate !== 0` instead of
      raw `simMoveActive`.
- [ ] A **shape-mirror host test** (following the precedent set by
      sprint 006's settle-loop shape test, per `src/DESIGN.md` §9's
      "not host-testable... bolted to Rig-local odometry" note for
      why `shims.cpp`'s actual body can't be compiled on host):
      construct a `DifferentialDrive` + `FakeMotor` pair directly
      (the existing `tests/host/test_kernel_harness.py` pattern), post
      a nonzero `drive()` velocity command, step the kernel, and
      assert `isMoveActive() == false && (appliedDutyLeft != 0 ||
      appliedDutyRight != 0)` — i.e., assert the exact condition
      `commandLooksActive()` checks holds true for a continuous-mode
      command with no move-engine move active, proving the CONCEPT
      the fix depends on. This does **not** call `tickDrive()` itself
      (impossible on host — see C++11 Gate Coverage) but proves the
      condition its new return expression relies on.
- [ ] Existing settle-loop-shape tests
      (`tests/host/test_regression_post_move_neutral.py` and similar)
      still pass unchanged, confirming a position-mode move's final
      tick still drives `appliedDuty` to zero.
- [ ] A PXT build succeeds with `_tickDrive()`'s new return expression;
      manually confirm (code review, not an automated check — no host
      test reaches `main.ts`) that `move()`/`goTo()`'s
      `while (_tickDrive());` loops are unaffected in the simulator.
- [ ] README (both worked examples), `specification.md` §4.2, and
      `usecases.md` UC-002 step 4 are each re-read against the fixed
      behavior and confirmed accurate; each gains one sentence
      cross-referencing the new host test by name as the mechanism
      that now pins this contract against silent regression. (Direct
      edits on the sprint branch — none of these three files is part
      of this project's canonical design-doc-overlay set.)
- [ ] Full existing host suite passes with no regressions.

## C++11 Gate Coverage

- **Inside the gate**: none of this ticket's actual fix — `tickDrive()`
  and `commandLooksActive()` both live in `shims.cpp`, which includes
  `pxt.h` and is not part of `tests/host/`'s compiled surface at all.
- **Outside the gate**: `shims.cpp`'s two changed lines (the return
  expression and the forward declaration), and all of `main.ts`
  (`_tickDrive()`'s changed return expression). A green host suite
  proves the underlying CONCEPT (`commandLooksActive()`'s condition
  holds for a continuous-mode command) via the shape-mirror test
  above — it does **not** prove `shims.cpp`'s actual `tickDrive()` or
  `main.ts`'s `_tickDrive()` compile for either real embedded target,
  or that the fix behaves correctly on hardware. Do not report "host
  tests pass" as target-build evidence for this ticket. A robot is not
  required to complete this ticket (see the bench-verification
  checklist ticket, 008, for the hardware confirmation step) — this
  ticket's acceptance criteria are all satisfiable by the shape-mirror
  test, code review, and a PXT build.

## Testing

- **Existing tests to run**: `tests/host/test_regression_post_move_neutral.py`,
  `tests/host/test_kernel_harness.py`, `tests/host/test_motion_engine_primitives.py`.
- **New tests to write**: the shape-mirror test described above,
  asserting `commandLooksActive()`'s condition for a continuous-mode
  command with no move-engine move active.
- **Verification command**: `pytest tests/host/ -k "tick or command_looks_active"`
  plus a full `pytest tests/host/` run before marking this ticket done.
