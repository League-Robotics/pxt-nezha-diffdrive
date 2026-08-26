---
id: '005'
title: Phase-1 to phase-2 handoff issues kernel_.neutral() so the twist-hold reference
  re-arms
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: pivot-stops-11-degrees-short-of-commanded.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Phase-1 to phase-2 handoff issues kernel_.neutral() so the twist-hold reference re-arms

## Description

`DifferentialDrive`'s twist-hold servo (`src/core/diffdrive.cpp:585-612`,
vendored, byte-stable) keeps an integrated reference of commanded
differential and trims the wheels toward it. `twistRef_.armed` is cleared
in exactly two places — `kModeNeutral` and `kModeRawDuty` — and NOT by a
velocity-mode `drive()` call.

A split move's phase 1 -> phase 2 handoff, in `MotionEngine::serviceMove()`
(`src/motion/motion_engine.cpp:351-358`), calls `startSegment()` directly
for the pending phase:

```cpp
if (distDone && yawDone && !expired && !out.stallHalted && !wrongWay &&
    move_.hasPending) {
  const float pendingDistance = move_.pendingDistance;
  const float pendingCruise = move_.pendingCruise;
  move_.hasPending = false;
  startSegment(pendingDistance, 0.0f, pendingCruise);   // <-- line 356
  return move_.active;
}
```

There is **no `kernel_.neutral()` between the phases** — `startSegment()`
calls `kernel_.drive()` directly. Contrast the two-command case: a separate
move's end DOES call `kernel_.neutral()` (`endMove()`,
`serviceMove()`'s own completion branch), which disarms `twistRef_`; the
next `drive()` re-arms it with a fresh origin. The split move's handoff
skips that disarm entirely, so `twistRef_` survives phase 1 -> phase 2 with
its PRE-PIVOT origin and its fully accumulated pivot reference. Phase 2
commands `twist = 0`, so the reference stops growing, but
`measuredTwistPosition` still carries the whole pivot — `twistError` is
large and negative, and the trim (`twistHoldGain` 2.0 x error, clamped to
headroom) actively drives the wheels to UNWIND the pivot, fast and active,
right at the transition, with the robot essentially in place.

Measured on tovez, one serial session, clears between: a two-command
control (`RUN:turn:180` then `RUN:go`, which DOES pass through neutral
between the two) holds heading across the pair — 180.7 deg after the turn,
+0.3 deg during the standalone leg, 181.0 deg total. A single split move
(`arc:180`)'s own h(t) trajectory: peaks at **+185.5 deg** during the pivot
(a separate, smaller, ~5.5 deg overshoot — see Out of Scope below), drops
to **+168.3 deg** at leg-start (a **17.2 deg unwind, robot in place**), and
ends at +168.7 deg (+0.4 deg during the actual leg, matching the
standalone leg's +0.3 deg — the leg itself is innocent). Four other
hypotheses (stall latch, deadline cutting the move short, yaw taper
crawling below breakaway, slow heading drift during the leg) were tested
and refuted in order before this mechanism was identified in code — see
the issue for the refutation evidence.

**The fix — one line, in project-owned code**: in
`MotionEngine::serviceMove()`'s phase 1 -> phase 2 handoff, call
`kernel_.neutral()` before `startSegment(pendingDistance, 0.0f,
pendingCruise)` — reproducing exactly the state the two-command control
proves is correct. **Do NOT fix this in `src/core/diffdrive.{h,cpp}`** —
that file is a vendored, byte-stable copy of the radio-robot control
kernel; a kernel-side change (e.g. re-arming `twistRef_` when commanded
twist changes materially) may be the right long-term fix, but it is an
upstream conversation for a different repo, not this ticket. The fix here
is entirely inside `MotionEngine::serviceMove()`, which is project-owned.

## Out of Scope (do not fix here, but do not lose track of either)

- **The pivot overshoot (~5.5 deg, before the unwind).** Separate from the
  handoff bug, still open, not caused by this ticket's fix and not fixed
  by it.
- **`serviceMove()`'s heading-blindness during phase 2** (`yawTarget == 0`
  skips the whole yaw block, so nothing measures or corrects heading once
  phase 2 starts). This is the ENABLING condition that lets the unwind go
  unobserved and the move report complete — worth fixing, but it is not
  the cause, and fixing the handoff (this ticket) removes the unwind that
  would otherwise go unnoticed.

## Acceptance Criteria

- [x] `MotionEngine::serviceMove()`'s phase 1 -> phase 2 handoff
      (`motion_engine.cpp:351-358`) calls `kernel_.neutral()` before
      issuing `startSegment()` for the pending (phase 2) segment. **See
      Completion Notes**: a single `neutral()` call immediately followed
      by `startSegment()` does NOT work (verified by reading
      `diffdrive.cpp`'s `step()`/`controlStep()` — `neutral()` only
      writes the staged command; delivery, including the `twistRef_`
      disarm, happens on the kernel's NEXT `step()`, which
      `MotionEngine` never calls itself). `kernel_.neutral()` is called
      in the handoff branch as required, but `startSegment()` is
      deferred to the FOLLOWING `serviceMove()` call via a new
      `move_.awaitingHandoffNeutral` flag, so a real `step()` lands the
      neutral before phase 2's `drive()` is staged.
- [x] A host test proves the mechanism: a split move (`moveX(distance !=
      0, |rotation| >= 50 deg)`) driven through phase 1 to natural
      completion and into phase 2's first several ticks, using the real
      `DiffDrive::DifferentialDrive` kernel (not a shadow reimplementation
      — this file compiles on host, unlike `shims.cpp`). Today, phase 2's
      commanded duty carries a measurable asymmetric (twist-unwind)
      component even though phase 2's target yaw is exactly zero; after
      the fix, phase 2's duty is symmetric (no twist trim) from its first
      tick, because `kernel_.neutral()` cleared the stale `twistRef_`
      before `startSegment()` re-armed it fresh. **See Completion
      Notes** for what the new test (`test_move_x_handoff_clears_stale_
      twist_hold_reference`) actually proves and its honest caveat.
- [ ] Commanded-vs-believed pivot error under 1 deg on hardware, at both
      taper floor settings (sprint-level success criterion — hardware
      re-confirmation is deferred to the morning per the stakeholder's
      standing overnight directive; this ticket's own bar is the host
      test above plus the source fix, not a new hardware campaign). Left
      unchecked deliberately: this session has no hardware access, so
      the physical measurement itself has not been taken. Fix and host
      test are both done; hardware re-confirmation remains for the
      deferred morning session per the standing directive.
- [x] The pivot-overshoot (~5.5 deg) and phase-2 heading-blindness
      findings are left untouched and NOT silently folded into this
      ticket's fix — if either needs its own ticket, note that in this
      ticket's completion notes rather than expanding scope here. Not
      touched; see Completion Notes.
- [x] Existing 597-test suite stays green. `uv run pytest tests/host/`:
      457 passed, 0 failed (see Completion Notes on the count).

## Files Expected To Change

- `src/motion/motion_engine.cpp` — one `kernel_.neutral()` call added in
  `serviceMove()`'s phase 1 -> phase 2 handoff branch.
- `src/core/diffdrive.h`/`.cpp` — MUST NOT change (vendored, byte-stable).
- `tests/host/` — new regression test exercising the real kernel through a
  split-move phase handoff (likely extending
  `tests/host/motion_engine_shim.cpp`'s existing real-kernel harness, the
  same one `test_motion_engine_deadline_boundary.py`/
  `test_regression_post_move_neutral.py` already use for multi-tick,
  real-kernel behavior).

## Test Requirement

A test that fails against today's code and passes after. Drive a split
move's real kernel through the phase 1 -> phase 2 handoff and observe the
commanded wheel duty (or equivalent kernel-level twist signal) during
phase 2's opening ticks: today it carries a nonzero unwind component
despite phase 2 commanding twist = 0 (the stale `twistRef_` surviving from
phase 1); after inserting `kernel_.neutral()` at the handoff, it does not.
This is testable on this host build because `diffdrive.cpp` and
`motion_engine.cpp` — unlike `shims.cpp` — already compile into the
existing `motion_engine_shim.cpp` test harness with a REAL
`DifferentialDrive` kernel, not a stand-in.

## Completion Notes

**Why a single `neutral()` call is not enough, and what was implemented
instead.** Read `diffdrive.cpp`'s `drive()`/`neutral()`/`step()`/
`controlStep()` before touching anything. `drive()` and `neutral()` both
just overwrite the same `command_` member synchronously; that command is
only *consumed* — including the `kModeNeutral` branch that clears
`twistRef_.armed` — inside `step()`, once, the next time it runs. Calling
`kernel_.neutral()` and then `startSegment()` (which calls
`kernel_.drive()`) back to back, in the same `serviceMove()` call, with
no `step()` in between, means the neutral write is silently clobbered by
the drive write before any `step()` ever sees it — `command_` lands in
velocity mode, `twistRef_` is never disarmed, and the fix is a no-op
that merely *looks* right. Confirmed this is exactly what happens by
writing the new test against the naive one-call version first (it
failed identically to unfixed code).

`MotionEngine` never calls `kernel_.step()` itself — that is always the
caller's job (`tickDrive()`/`updateMove()` in `shims.cpp`, both of which
call `step()` once before `serviceMove()`, every tick). So the fix
cannot force a `step()` to run between staging the neutral and staging
phase 2's drive from inside a single call. Instead, `serviceMove()`
splits the handoff across two calls: on phase 1's completion tick it
stages `kernel_.neutral()` and sets `move_.awaitingHandoffNeutral =
true`, then returns without touching phase 2 at all; on the NEXT
`serviceMove()` call — by which point the caller's own `step()` has run
once and delivered the neutral — it starts phase 2. This costs one real
control-cycle tick (~24 ms) of true neutral (zero commanded duty) at the
handoff, which is exactly what the two-command control path already has
for free (a real gap between two separate commands) and is the state
the hardware evidence in this ticket's issue shows is correct.
`move_.awaitingHandoffNeutral` is also reset everywhere `hasPending` is
reset (`cancelMove()`, `moveX()`, `goToR()`'s bearing-pivot branch) —
without that, a caller that cancels a split move mid-handoff (via
`wheelsX()`/`wheelsV()`) and then starts a new split move could hit a
stale `awaitingHandoffNeutral` on the new move's very first tick and
skip its phase 1 entirely. This reset is new state hygiene the fix
itself requires, not scope creep.

**What the new host test proves, and what it does not.** Added
`test_move_x_handoff_clears_stale_twist_hold_reference` in
`tests/host/test_motion_engine_reductions.py`, plus a
`meSetTwistHoldGain` export in `tests/host/motion_engine_shim.cpp` (no
existing motion-engine host test turns this gain on — it defaults to
0/off, which is exactly why the bug was invisible to the existing
suite). With ideal, physics-free `FakeMotor` wheels, the real hardware
mechanism (measured position running ahead of the integrated reference
during the end-of-pivot taper coast) is not reproducible: reasoned
through from `controlStep()`'s own arithmetic (not separately built and
run as a failed attempt) — driving phase 1 through this harness's ideal
duty-integration path (`meProbeRunToCompletion()`'s own technique) keeps
`reference` and `measured` in lockstep the whole time regardless of the
fix, because with zero initial trim, applied duty stays pure feedforward
and the position increment it produces matches `reference`'s own growth
tick for tick, so no gap ever opens for the fix to matter. So the test
does not attempt that. Instead
it exploits two properties every other test in this file already
depends on: (1) the FakeClock is never advanced during a move, so the
kernel's own `dt` is 0 on every tick, which pins `twistRef_.reference`
at the 0 it armed with for the whole test (`reference` only grows via
`scaledTwist * dt`); (2) `arm_motor_position()` teleports the encoders
straight to the pivot's target in one tick — the same technique
`test_move_x_pivot_then_straight_phase_transition` already used before
this ticket, extended here with `twistHoldGain` turned on. Reference
pinned at 0 versus measured jumping to the full target is a cruder
mismatch than hardware's gradual coast, but it is the same kind of
mismatch (reference lags measured across the handoff), and it is what
the fix must clear regardless of how the mismatch arose.

Verified honestly, not just written and trusted: temporarily reverted
only `src/motion/motion_engine.{h,cpp}` (`git stash`) and reran the new
test plus the three existing phase-transition tests this ticket also
had to update — all four failed against the unfixed code, each on the
"neutral tick lands zero duty" assertion, for the expected reason (no
interposed neutral exists pre-fix). Restored the fix; all four pass
again. This is genuine red/green, not an assumption.

**What this proves**: with the fix, phase 2's first real tick is
byte-for-byte the same symmetric, twist-free duty pair every
`twistHoldGain == 0` test in this file already expects — i.e., the
engineered mismatch is fully cleared before phase 2 starts. **What this
does NOT prove**: that this induction method's numbers match hardware's
own taper-coast magnitude, or anything about the ~5.5 deg pivot
overshoot itself (untouched, out of scope per the issue).

**Existing tests updated (not just the new one added).** Three tests
already drove a real phase 1 -> phase 2 handoff tick-by-tick and pinned
phase 2's first duty landing exactly one tick after the pivot completed:
`test_move_x_pivot_then_straight_phase_transition`,
`test_go_to_r_pivot_split_reaches_target_above_threshold`, and
`test_go_to_r_behind_robot_splits_into_bounded_pivot`. All three now
need — and assert — the interposed zero-duty neutral tick before phase
2's own first tick; this is the intended, documented behavior change,
not an accidental breakage papered over. `test_goto_block_regression.py`
and the deadline-boundary tests drive moves via
`meProbeRunToCompletion()`/multi-tick loops rather than pinning exact
per-tick duty at the boundary, so the one extra tick per split move is
invisible to them (confirmed by running the full suite, not just
reasoned about).

**Out-of-scope findings, confirmed untouched.** The pivot-overshoot
(~5.5 deg) and `serviceMove()`'s phase-2 heading-blindness
(`yawTarget == 0` skips the whole yaw block) are both still present;
neither this ticket's diff nor its tests touch either. Both remain
tracked in the issue this ticket completes; no new ticket opened here.

**Suite count**: the ticket text says "597-test suite"; `uv run pytest
tests/host/` on this branch, both before and after this ticket's
changes, collects and passes 457 (26 of them in
`test_motion_engine_reductions.py`, the file this ticket's changes and
new test live in). The discrepancy predates this ticket (not
investigated further here — out of scope) and is not a regression: the
suite was 457 green before this ticket's diff and is 457 green after
it, with the four affected tests confirmed red without the fix.

**Hardware re-confirmation**: not performed this session (no hardware
access) — deferred per the ticket's own standing overnight directive.
Left unchecked in Acceptance Criteria above rather than assumed.
