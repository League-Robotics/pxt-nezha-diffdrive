---
id: '004'
title: Re-check the idle-I2C issue against the obligation fix; record the result either
  way
status: done
use-cases: []
depends-on:
- '003'
github-issue: ''
issue: wire-motion-obligation-never-clears.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Re-check the idle-I2C issue against the obligation fix; record the result either way

## Description

**This is an investigation ticket with a written verdict, not a code
change.** Its job is to re-check
`clasi/issues/i2c-fault-count-climbs-on-idle-bus.md` (claimed by sprint
018, not this sprint — this ticket does not fix or close that issue,
only re-checks its own hypothesis against ticket 003's fix) against
ticket 003's `motionObligationActive_` clearing fix, and record whatever
is found — including a clean "no change observed" or "cannot be
confirmed without hardware" — as a real, useful result. Do not write code
to make a predetermined answer true.

### Background

`wire-motion-obligation-never-clears.md` names the idle-I2C issue as "a
concrete candidate mechanism": before ticket 003, any wire motion verb
kept `protocol.cpp`'s fiber ticking the kernel at 24 ms for up to 24.8
days after the motion actually finished, which puts a second fiber on the
I2C bus during OTOS reads (`blocks/world.ts:9`'s own documented invariant:
OTOS reads "must be called from the same fiber that calls `driveTick()`
-- never concurrently with one"). `i2c-fault-count-climbs-on-idle-bus.md`
independently observed `i2cf` climbing by 45 over ~10 minutes while the
robot was mostly stationary, with only a small part of that increase
attributable to the two commanded legs run in that window.

### What is and is not host-testable here

`shims.cpp`'s `tickDrive()`, `protocol.cpp`'s fiber loop, and the real
Nezha/OTOS I2C drivers all include `pxt.h`/CODAL and are **not**
host-compilable at all (`tests/host/README.md`'s own "What this does NOT
cover yet" section is explicit about this boundary). This means the
*causal* mechanism — real I2C bus contention between the protocol fiber's
`step()` and a `readWorld()` call on another fiber — cannot be measured
on the host. What **can** be checked on the host, using ticket 003's own
`wa` fixture (`test_wire_motion_completion.py`), is the *mechanical
precondition*: how long `hasLiveMotionObligation()` now reads `true`
after a motion naturally completes, compared to before ticket 003. That
is a real, useful, host-provable fact — it bounds the *opportunity* for
the hypothesized collision without proving the collision itself.

### What to do

1. **Host-level check (no hardware needed)**: using the `wa` fixture,
   measure/confirm the obligation-window duration before vs. after ticket
   003's fix for a representative wide-timeout goal-directed verb (e.g.
   `MOVE_X` with a generous `timeout`, reaching its own goal well before
   that timeout) — before ticket 003, `hasLiveMotionObligation()` stays
   true until the wire-side deadline elapses or an explicit `STOP`/`ESTOP`;
   after ticket 003, it clears as soon as something polls
   `lastDone()`/`lastDoneReason()` following the natural completion. State
   this comparison plainly (a sentence or two, with the actual numbers
   from the test) as part of the verdict.
2. **Hardware check (if warranted)**: capture `i2cf` and `cyc` (telemetry
   columns, or `probe(8)`/`probe(16)`) across a session with and without
   a preceding wide-timeout `MOVE_X`, on hardware, following ticket 003's
   fix — this is the only way to directly test whether the climb tracks
   the obligation window, since it requires the real I2C bus and the real
   protocol fiber. **If this needs hardware access this ticket does not
   have readily available (per the sprint's autonomous-overnight
   execution context), do not attempt it** — instead record precisely
   what would be measured and how (exact commands, exact telemetry
   columns/probe ordinals, exact comparison — "capture i2cf/cyc at
   session start, issue one wide-timeout MOVE_X that reaches its goal
   quickly, wait N idle minutes, capture i2cf/cyc again, compare the
   delta to a control run with no preceding MOVE_X") as a **deferred,
   ready-to-run bench protocol**, and say so explicitly in the verdict.
   This satisfies the ticket without needing hardware — "cannot confirm
   without hardware, here is the exact protocol to confirm it" is a valid
   and complete result.
3. **Record the verdict** as a dated addendum to
   `clasi/issues/i2c-fault-count-climbs-on-idle-bus.md`, following that
   file's own existing convention (it already has a dated "## Related
   observation (2026-08-25): ..." section — add a new one, do not rewrite
   the existing content). State plainly: did the host-level check show
   the obligation window narrowing as expected from ticket 003's fix?
   Was a hardware measurement possible or deferred? If deferred, is the
   bench protocol recorded precisely enough that a future sprint (018,
   which owns this issue) can run it without re-deriving it? Also add a
   short pointer in this ticket's own body (a "## Findings" section
   appended below, or the Description above) summarizing the same
   verdict, so it's readable from the ticket alone without following the
   cross-reference.

## Acceptance Criteria

- [x] A host-level test/measurement (using the `wa` fixture) directly
      compares the obligation-window duration for a representative
      wide-timeout motion verb before vs. after ticket 003's fix, and the
      comparison's numbers are stated in the verdict.
- [x] `clasi/issues/i2c-fault-count-climbs-on-idle-bus.md` has a new dated
      addendum recording this ticket's findings, in that file's own
      existing "dated observation" style.
- [x] If a hardware measurement was not performed, the addendum records
      the exact bench protocol that would perform it (commands, telemetry
      columns/probe ordinals, comparison method) precisely enough for
      sprint 018 to run it directly.
- [x] The verdict states plainly whether the climb tracked the obligation
      window or not (or "not determined without hardware, protocol
      recorded") — "no change observed" or "inconclusive without
      hardware" are both acceptable, valuable results. Do not overstate
      confidence the host-only evidence does not support.
- [x] No production code (`src/`) is modified by this ticket. If the
      investigation surfaces an unrelated real defect, file a new issue
      for it rather than fixing it inline — this ticket's scope is the
      re-check, not a fix.

## Verdict

**Summary: the mechanism is real and independently worth having fixed
(ticket 003 is a correct, quantifiable improvement), but it does NOT
explain the specific `i2cf` climb documented in
`i2c-fault-count-climbs-on-idle-bus.md`'s "What was observed" section —
that session almost certainly never armed `motionObligationActive_` in
the first place, because it was driven entirely through the cleartext
`RUN:` bridge, a code path this flag has no connection to.** Not
determined without hardware whether the mechanism matters for a
DIFFERENT session (one driven through the v6 wire-protocol motion verbs
instead) — a precise bench protocol for that is recorded below for
sprint 018.

### 1. Host-level check: the obligation window, quantified

New test: `tests/host/test_wire_motion_completion.py::
test_obligation_window_narrows_after_natural_completion`. Setup: `MOVE_X`
with a 10000 ms declared timeout, reaching its own goal at ~50 ms in
(direct position arming, same technique the ticket-003 tests use).

- **Before ticket 003** (verified directly against the pre-fix
  `wire_adapter.cpp` via `git stash`, during ticket 003's own work —
  see that ticket's Findings): `hasLiveMotionObligation()` stays `true`
  for the entire remaining declared window (in this setup, until
  `now` = 10000 ms) regardless of how many times
  `lastDone()`/`lastDoneReason()` are polled in between, and regardless
  of the move having actually finished at ~50 ms. Only an explicit
  `STOP`/`ESTOP`, or the deadline itself elapsing, ever clears it.
- **After ticket 003** (asserted directly in the new test, against the
  current code): the window closes the moment `last_done_reason()` is
  next polled following the real completion — here, immediately at
  `now` = 50 ms, 9950 ms before the declared deadline.
- Converted to a tick count using `tickDrive()`'s own documented ~24 ms
  self-paced `kernel.step()` cadence (`shims.cpp`, restated in
  `DESIGN.md`/`encoder_glitch_armor.h`/`nezha_port.h`/
  `serial_transport.h`) and the fact that `kernel.step()` is called
  NOWHERE outside `tickDrive()` (confirmed by reading `shims.cpp` in
  full — `cyc`, `diagValue(16)`, is therefore an exact count of
  `tickDrive()` calls): this ticket-003 fix avoids **414** otherwise-
  unnecessary `tickDrive()`/`kernel.step()` calls in this representative
  scenario (`(10000 - 50) / 24 = 414`, integer division). Each of those
  414 calls is a real `kernel.step()` — motor/encoder I/O, though NOT
  necessarily I2C traffic itself; see the caveat in §2 below.

### 2. The critical caveat: this mechanism cannot explain the specific observed session

`motionObligationActive_` is armed in exactly six places in the entire
codebase — `wire_adapter.cpp`'s `onWheelsV()`/`onWheelsX()`/`onMoveX()`/
`onMoveV()`/`onGoToR()`/`onGoToW()` (confirmed by
`grep -rn "motionObligationActive_ = true" src/`) — i.e. only by the
binary, sequenced v6 wire-protocol motion verbs
(`MOVE_X ... #<id>`, `WHEELS_V ... #<id>`, etc.).

`i2c-fault-count-climbs-on-idle-bus.md`'s own "What was observed"
section names the commands actually used in that session: two
`RUN:straight:20` legs and "a handful of `RUN:fix` / `RUN:probe`
calls." `RUN:` (cleartext, colon-prefixed) is a **different parser
path** (`protocol.cpp`'s `handleRun()`, a MessageBus bridge — confirmed
by reading `protocol.cpp:125-171` and the existing
`.claude/rules/playfield-testing.md` note that this vocabulary "is NOT
sequenced"). Read `test/test.ts` in full: every RUN handler that
actually moves the robot (`tourWheels()`/`straightRun()`/`tourRobot()`/
`tourWorld()`/`leverCal()`/`RUN:goto`/`RUN:face`/`RUN:pivot`) calls
`diffDrive.startMove()`/`startGoTo()`/`goToWorld()` directly — CODAL
motion blocks — and never touches `WireAdapter`'s `onWheelsV()`/
`onMoveX()`/etc. at all. There is no path by which a `RUN:` command
arms `motionObligationActive_`.

The one v6-protocol command that session's own "20-column telemetry"
framing implies (a `TLM ... #<id>` to start streaming) does not arm the
flag either — `onTlm()` never touches `motionObligationActive_`. So the
session that produced the `i2cf` climb almost certainly never armed the
obligation flag at all, meaning ticket 003's fix — and the "obligation
keeps the fiber ticking" mechanism generally — could not have been
responsible for what was observed there. This directly narrows, but
does not close, `wire-motion-obligation-never-clears.md`'s own framing
of this as "a concrete candidate mechanism": it is a mechanism, but not
one that reaches the documented evidence.

### 3. A second, independent limitation of the fix's own reach (worth flagging, not fixing here)

Separately from §2: `resolvePendingIfDue()`/`forceResolvePending()` (the
two places ticket 003 added the clear) are reached ONLY via
`lastDone()`/`lastDoneReason()`, which in production are called ONLY
from `WireHandler::replyAck()`/`replyNack()` (`wire_handler.cpp:583-593`
— confirmed by grep; no other call site exists). `protocol.cpp`'s fiber
loop itself calls `hasLiveMotionObligation()` directly, which does
**not** trigger a resolve. So even post-003, a host that issues one
wide-timeout `MOVE_X` and then goes fully silent (no further wire lines
of any kind — TLM streaming alone does not count, since telemetry
emission does not go through `dispatch()`/`replyAck()`) gets **zero**
benefit from this fix: the obligation stays armed for the full declared
timeout exactly as before, because nothing ever polls
`lastDone()`/`lastDoneReason()` to notice the early completion. The fix
only shortens the window when the host continues to send SOME wire-
protocol line (any verb — `STATUS`, `GET`, `PING`, another motion verb)
after the earlier move has already finished. This is not a defect in
ticket 003 (it does exactly what its own acceptance criteria asked for)
but it does bound how much benefit to expect from it in practice, and is
recorded here rather than silently assumed away.

### 4. Hardware measurement: deferred (autonomous overnight execution context — no bench access)

Not performed. Exact protocol for sprint 018 (or anyone with bench
access) to run directly, refined by the §3 finding above to actually
distinguish the two cases that finding shows matter:

**Setup**: vevov (or any robot on this firmware) reachable over USB or
the zavaz radio relay (`tools/robotlink.py`). Per
`.claude/rules/playfield-testing.md`: confirm room lights are on before
placing the robot on the mat, though this specific protocol does not
require real motion (the goal-directed verb below reaches its own goal
in well under a second and can be run with the robot anywhere safe, or
even on the bench stand — it is the FIBER's ticking being measured, not
travel accuracy).

**Telemetry surface**: both columns are readable via a bare `STATUS
#<id>` — no `TLM FULL` subscription needed. `i2cf` = `diagValue(8)` =
`STATUS`'s `i2cf=` field = telemetry `FULL`'s `i2cf` column. `cyc` =
`diagValue(16)` = `STATUS`'s `cyc=` field (sprint 010) = telemetry
`FULL`'s `cyc` column. `cyc` is the exact `tickDrive()`/`kernel.step()`
count (§1 above) and is the variable this whole mechanism predicts will
move; `i2cf` is the one this investigation actually cares about and
cannot measure host-side.

**Three runs, each ~12 minutes, same robot, same session (or as close
together as practical to control for drift in whatever else might be
causing the baseline climb)**:

1. **Control** (no motion verb at all): `STATUS #1` (record `i2cf`,
   `cyc`) → idle 10 minutes, no further wire lines → `STATUS #2`
   (record `i2cf`, `cyc`). Baseline climb rate with the obligation never
   armed.
2. **Armed, then silent** (tests §3's own prediction): `STATUS #1` →
   `MOVE_X 200 0 150 600000 #2` (600000 ms = 10 min declared timeout,
   physically finishes in ~1-2 s) → idle 10 minutes with **no further
   wire lines of any kind** (TLM off, or on but note that TLM frames do
   not count as a poll) → `STATUS #3`. Prediction: `cyc` climbs at
   roughly the full ~24 ms `tickDrive()` rate for the WHOLE 10 minutes,
   indistinguishable from the pre-003 build, because nothing ever polls
   `lastDone()`/`lastDoneReason()` to clear the obligation. If this run
   does NOT show that (i.e. `cyc` stops climbing early even with no
   polling), that contradicts this ticket's own code-reading and is
   worth a fresh look before trusting run 3 below.
3. **Armed, then polled** (tests ticket 003's actual real-world
   benefit): same as run 2, but poll `STATUS #<n>` roughly every 30 s
   during the 10-minute idle window (a realistic bench-tooling cadence).
   Prediction: post-003, `cyc` stops climbing shortly after the
   `MOVE_X`'s own early completion (bounded by the ~30 s poll cadence);
   run this same protocol against a pre-003 build (or the parent commit
   of ticket 003's own commit) and `cyc` should climb for the full 10
   minutes regardless, matching run 2.

**Comparison**: for each run, `Δcyc` and `Δi2cf` over the 10-minute idle
window. If `Δi2cf` in run 3 (post-003) is meaningfully SMALLER than
run 2's (or than a pre-003 run of the same run-3 protocol), that is
direct hardware evidence the mechanism is real and ticket 003 helps it.
If `Δi2cf` tracks `Δcyc` proportionally across all three runs regardless
of which build or protocol, that points at `i2cf` scaling with steps
taken for a DIFFERENT reason (e.g. some other periodic I2C traffic
independent of the protocol-fiber mechanism), not this one. If `Δi2cf`
is flat across all three runs regardless of `Δcyc`, the obligation
mechanism is not a contributor at all under these conditions.

### Bottom line

- Host-provable and now proven: ticket 003 measurably narrows the
  obligation window for the verbs and usage pattern that can arm it —
  414 fewer `tickDrive()` calls in the representative scenario tested,
  and it is a real fix on its own terms regardless of `i2cf`.
- Also host-provable and now proven: that mechanism structurally cannot
  explain the ONE session `i2c-fault-count-climbs-on-idle-bus.md`
  documents, because that session never used the v6 protocol verbs that
  alone arm the flag.
- Not host-provable, and not established here: whether the mechanism
  contributes to `i2cf` growth for sessions that DO use the v6 protocol
  (e.g. `tools/robotlink.py`-driven `MOVE_X`/`WHEELS_V` traffic). The
  bench protocol above is precise and ready to run for sprint 018.

## Implementation Plan

### Approach

1. Read `clasi/issues/i2c-fault-count-climbs-on-idle-bus.md` and
   `wire-motion-obligation-never-clears.md` in full (both already read
   during sprint planning; re-read at execution time in case either
   changed).
2. Using `tests/host/test_wire_motion_completion.py`'s `wa` fixture,
   construct the before/after obligation-window comparison described
   above. This can be written as a throwaway script or as a real
   `pytest` test that documents the comparison — prefer a real test
   (e.g. `test_obligation_window_narrows_after_natural_completion`) so
   the comparison is reproducible and reviewable, not just a one-off
   number pasted into the addendum.
3. Decide whether a hardware measurement is feasible right now (bench
   access, robot powered and reachable). Given this sprint's autonomous
   overnight execution context, the expected outcome is "not feasible
   now" — in that case, write the deferred protocol precisely rather than
   attempting a partial or rushed hardware run.
4. Write the dated addendum to the issue file and the ticket's own
   findings summary.

### Files to modify

- `clasi/issues/i2c-fault-count-climbs-on-idle-bus.md` — dated addendum.
- Possibly a new small test file under `tests/host/` for the
  before/after obligation-window comparison (optional but preferred —
  see above).
- This ticket file itself — a `## Findings` section recording the
  verdict.

### Files explicitly NOT to modify

- Anything under `src/` — this is an investigation, not a fix.

### Testing plan

- **New tests** (optional, preferred): a host-level comparison test as
  described above.
- **Existing tests to run**: none required beyond confirming
  `tests/host/test_wire_motion_completion.py` still passes (it should be
  untouched by this ticket unless the optional new test is added there).
- **Verification command**: `uv run pytest tests/host/test_wire_motion_completion.py`
  if a new test was added there.

### Documentation updates

- `clasi/issues/i2c-fault-count-climbs-on-idle-bus.md` (the ticket's core
  deliverable — see Acceptance Criteria).
