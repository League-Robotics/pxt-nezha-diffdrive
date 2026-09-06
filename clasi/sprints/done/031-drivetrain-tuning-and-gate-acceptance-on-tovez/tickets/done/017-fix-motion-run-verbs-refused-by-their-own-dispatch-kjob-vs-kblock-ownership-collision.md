---
id: '017'
title: Fix motion RUN verbs refused by their own dispatch (kJob vs kBlock ownership
  collision)
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Fix motion RUN verbs refused by their own dispatch (kJob vs kBlock ownership collision)

**TYPE**: (b) desk work — firmware fix plus host test. No hardware needed to
fix; hardware confirmation folds into ticket 014.

## Description

Every motion `RUN:` verb is silently refused by its own dispatch and then
emits its normal success receipts. Confirmed in source and measured on
hardware.

MEASURED tovez 2026-09-05, firmware 1.20260904.5, captures/session-b-20260905/notes.md
(commit f186c90): `RUN:straight:8` with the robot idle moved it 0.02 cm,
while a wire `MOVE_X 600` on the same connection seconds later delivered
59.55 cm with STATUS healthy throughout (ready=1 connL=1 connR=1, cyc
advancing, no wedge, no reset).

The chain:
- `Protocol::handleRun()` parks the text in `runQueue_` (src/comms/protocol.h:351).
  Only `abort` and `clearestop` bypass the queue (src/comms/protocol.cpp:145).
- `Protocol::dispatchJob()` sets `motionOwner_ = MotionOwner::kJob`
  (src/comms/protocol.cpp:439) then calls `runDispatch()`.
- The TS handler runs, e.g. `straightRun()` (test/test.ts:465) ->
  `tickedMove()` (test/test.ts:126) -> `diffDrive.startMove()`.
- `startMove()` (src/shims.cpp) begins
  `if (!protocolTryTakeBlockOwnership()) return;`.
- `diffDrive::tryTakeBlockOwnership()` (src/core/motion_owner.h) is
  `if (*owner != MotionOwner::kNone) return false;`. The owner is `kJob`.
  Returns false.
- `startMove()` returns early having commanded nothing. `tickToCompletion()`
  then loops `while (diffDrive.driveTick())`, immediately false, so the
  handler completes and emits `DBG:straight=` / `STRAIGHT:end:` as if it
  had run.

**SCOPE**: `straight`, `tour`, `square`, `infinity`, `snake`, `diamond`,
`circle`, `pivot`, `arc`, `goto` and `face` all reach the drivetrain through
`tickedMove`/`tickedGoTo` (which call `startMove`/`startGoTo`) or
`driveTwist`, and all three entry points carry the same gate. Only the
non-motion verbs (`probe`, `fix`, `gap`, `arm`, `seed`, `clearestop`,
`abort`) still work. The physical buttons are unaffected:
`input.onButtonPressed(A/B/AB)` (test/test.ts:573-581) call
`straightRun`/`tourWorld`/`tourWheels` directly, not through dispatch, so
`motionOwner_` is `kNone` and they legitimately take `kBlock`.

**REGRESSION WINDOW** — a two-sprint collision, neither change wrong alone:
- `c4ed4c3`, 2026-09-02, sprint 028 ticket 003 ("executor inversion —
  collapse RUN dispatch and wire motion onto one fiber") made
  `dispatchJob()` claim `kJob`.
- `6f6a9b0`, 2026-09-04, sprint 030 ticket 002 ("fiber-identity check on the
  tick service hook; kBlock motion owner") added the
  `protocolTryTakeBlockOwnership()` gate to `startMove()`.

Sprint 030's gate did not account for a RUN handler executing inside
sprint 028's `kJob` claim. `RUN` tours worked as recently as 2026-09-01
(test/test.ts's own arc-geometry comment records measuring that day).

**NOTE FOR THE REVIEWER**: sprint 030's own hardware acceptance item for
this was "a block-side `startMove()` during a live wire motion obligation
must be refused (kBusy), not silently superseding it" — deferred into
sprint 031 ticket 009 Item 2(b), never attempted, still UNVERIFIED. The
defect shipped through the exact check meant to catch it. Whatever fix
lands here should come with the host-level test that makes that check
automatic.

## Acceptance Criteria

- [x] A dispatched RUN handler's move actually commands motion. The job
      path gets its own ownership route (for example a
      `tryTakeJobMotion()` alongside `tryTakeBlockOwnership()`, or an
      ownership predicate that accepts `kJob` when the caller is the
      dispatching fiber).
- [x] The existing and CORRECT refusals are preserved: a genuine block-side
      move (button, student script) arriving while `kWire` or `kJob` holds
      the drivetrain is still refused, never superseding.
- [x] A host test fails if a dispatched RUN handler's move is refused.
      Nothing asserts this today, which is why the regression was
      invisible; tests/tools/test_run_verbs.py already pins the verb
      strings and tests/host/ carries the motion-engine harness.
- [ ] A refused motion call is distinguishable on the wire from a
      successful one — today both emit the same receipts. Either emit a
      distinct line or make the receipt carry the outcome.
      **DEFERRED** — see closing note below.
- [x] Hardware confirmation is NOT required by this ticket; ticket 014
      exercises `RUN:tour` and will confirm it incidentally.

## Closing Note

**Fix.** `core/motion_owner.h` gained `tryTakeMotionOwnership(MotionOwner*,
bool isDispatchingFiber)`, alongside the unchanged `tryTakeBlockOwnership()`:
if the caller is running on Protocol's own fiber AND the owner is already
kJob, the call proceeds unchanged (this is the job's own move, already
legitimately holding kJob) — otherwise it falls through to the original,
unmodified kBlock take/refuse rule. `Protocol::tryTakeMotionOwnership()`
(comms/protocol.cpp, renamed from `tryTakeBlockOwnership()`) computes
`isDispatchingFiber` via `currentFiberFn_() == protocolFiberId_`, the SAME
comparison `serviceHookEntry()` already uses for the tick service hook.
shims.cpp's three take sites (startMove/driveTwist/engineGoToRArmed) now
call `protocolTryTakeMotionOwnership()`. `releaseBlockOwnership()` and its
five call sites are unchanged — the job-fiber bypass never sets kBlock, so
there is nothing new to release; `dispatchJob()` still owns clearing kJob
itself.

**Regression window, restated.** Neither of the two commits that produced
this defect was wrong in isolation: one made a dispatched job claim kJob
around its own call into the TS handler; the other added a kBlock gate to
the block-motion entry points those TS handlers also happen to call. The
gate's own host test (kBlock take/release arbitration) was correct and
still passes unmodified — the gap was that nothing tested the WIRING
between "a job claims kJob" and "the gate refuses under kJob," i.e. that a
job's own call would hit its own gate. This ticket's hardware acceptance
item for exactly that collision was deferred one sprint and, once finally
run, found the defect within the same session.

**Deferred: distinguishable refusal receipt.** Acceptance criterion 4 asks
for a refused motion call to look different on the wire from a successful
one. With this fix landed, the only remaining refusal path is a genuine
block/job collision (a button or script call arriving while something else
already holds the drivetrain) — the common case (a dispatched job's own
move) no longer gets silently refused at all. Making that remaining
refusal visible on the wire requires plumbing a "was this refused"
signal from the shims layer back through every one of the ~10 TS handlers
in scope (straight/tour/square/infinity/snake/diamond/circle/pivot/arc/
goto/face), each of which currently emits its own hand-written receipt
line unconditionally after its tick loop returns — a wire-grammar-level
change, not a small one. Deferring it rather than forcing it into this
ticket, per this ticket's own instructions; a follow-up ticket should
scope it explicitly.

## Dependencies

None for the fix. BLOCKS ticket 014, whose scenario is "run `RUN:tour`
with a radio RUN issued mid-tour, then halt with pyOCD and scan the
protocol fiber's stack" — there is no tour to run until this lands.
Ticket 014 can alternatively be staged from button B/AB, which do drive;
note that option in the ticket.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/ tests/tools/`
- **New tests to write**: the dispatched-RUN-commands-motion test
  described above.
- **Verification command**: `uv run pytest tests/host/ tests/tools/`

Note captures/ is gitignored in this repo; the referenced notes file is
committed via `git show f186c90`.
