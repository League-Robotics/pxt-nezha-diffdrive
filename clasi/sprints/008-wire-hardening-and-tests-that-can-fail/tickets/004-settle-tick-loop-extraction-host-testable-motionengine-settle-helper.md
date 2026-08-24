---
id: '004'
title: 'Settle-tick loop extraction: host-testable MotionEngine settle helper'
status: in-progress
use-cases:
- SUC-004
depends-on: []
github-issue: ''
issue: settle-tick-loop-is-not-host-testable.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Settle-tick loop extraction: host-testable MotionEngine settle helper

## Description

`shims.cpp::tickDrive()` (lines ~614-632) runs an inline settle loop
when a move just ended (`wasActive && !moveActive`): up to 12
`kernel.step()` calls, breaking early once both wheels' measured
velocity is within `kRest = 25.0f` counts/s of zero, followed by one
`odomUpdate(r)` call to fold coast counts into pose before the final
telemetry read. Because this loop lives in `shims.cpp` (includes
`pxt.h`), the host harness never links it — a regression that deleted
or shortened it would pass the entire host suite (filed after sprint
003 ticket 009, which could only pin the loop's *necessity* by
argument, not execute it — `settle-tick-loop-is-not-host-testable.md`).

**The extraction**: move the bounded-iteration/break-on-rest *decision*
— not the odometry fold — into a new method on the existing
`MotionEngine` class, defined in `motion_engine.cpp` (already
host-portable, already gate-covered, already composing the `kernel_`
reference this needs — see this sprint's `design/DESIGN.md` §14 Design
Rationale for why a method on the existing class was chosen over a new
standalone header). `shims.cpp::tickDrive()` calls this new method
instead of running its own loop, then calls `odomUpdate(r)` itself,
immediately after, exactly as today — odometry ownership does not move.
A sprint-003-era comment on this loop argued extraction "would
mean moving odometry ownership into motion_engine too" — that objection
applies to extracting the whole settle-then-integrate behavior as one
unit; it does not apply to this narrower cut, which keeps the two
calls (`settleToRest()`-or-similar, then `odomUpdate(r)`) separate.

**Constraint carried from the issue**: exactly ONE fiber may tick a
given move (protocol co-ticking caused heisenbugs before). This
extraction must not create any new call path that could tick a move
from two places — the new method has exactly one caller
(`tickDrive()`), same as the loop it replaces.

## Design Rationale

See `design/DESIGN.md` §9/§14 in this sprint's overlay for the full
entry. Summary: a new method on `MotionEngine` (not a new standalone
header like `heading_wrap.h`) because `motion_engine.cpp` already has
everything the settle decision needs — no missing host-portable home to
build, unlike `otos_port.cpp`/`nezha_port.cpp` in sprint 006's three
extractions. This also means no new file and therefore no new C++11
gate registration (see below).

## Acceptance Criteria

- [x] A new `MotionEngine` method (defined in `motion_engine.cpp`)
      encapsulates the settle decision: steps the kernel up to the same
      bound the inline loop used (12), breaking early once both wheels'
      measured velocity is within the same rest threshold (25.0
      counts/s) — behavior identical to the loop it replaces, not
      merely similar.
- [x] `shims.cpp::tickDrive()`'s `if (wasActive && !moveActive)` branch
      calls the new method, then calls `odomUpdate(r)` itself
      immediately after (odometry ownership unchanged) — no
      settle-decision logic left inline in `tickDrive()`.
- [x] `tests/host/test_regression_post_move_neutral.py` stays green,
      unchanged — it remains the "why this matters" test.
- [x] A new host test (new shim surface on `kernel_shim.cpp` or
      `motion_engine_shim.cpp`, whichever proves the better fit —
      reusing `FakeSleeper::onSleep` from `fake_ports.h` where useful
      to observe iteration count) exercises the extracted method
      directly and asserts: (a) it steps the kernel repeatedly while
      velocity is above the rest threshold; (b) it stops early once
      velocity is at/below the rest threshold, without over-stepping;
      (c) it never re-energizes the motors (a settled/at-rest input
      produces no additional nonzero commanded duty).
- [x] A host test proves the iteration cap is enforced: wheels held
      artificially above the rest threshold for longer than 12
      simulated steps — the method returns after the cap, not
      indefinitely.
- [x] No new fiber or ticker is introduced; `tickDrive()` remains the
      new method's only caller.
- [x] Bench note (no robot required to satisfy this ticket's own
      acceptance criteria — real hardware exercise of the physical
      settle behavior remains this sprint's build-checkpoint ticket's
      and any future bench session's concern, not this ticket's): state
      in this ticket's own notes that the extraction is logic-identical
      to the loop it replaces, for whoever next flashes a robot to
      verify.

## Notes (implementation report)

- **Extracted method**: `void diffDrive::MotionEngine::settleToRest()`
  (declared `src/motion_engine.h`, defined `src/motion_engine.cpp`), no
  arguments, no return value. Two new private constants carry the old
  loop's magic numbers forward with names instead of a local `kRest`:
  `static constexpr int kSettleMaxSteps = 12;` and
  `static constexpr float kSettleRestCountsPerS = 25.0f;`. The method
  body is the old `shims.cpp` loop moved verbatim (same bound, same
  `<`/`>` comparison against `+-kSettleRestCountsPerS` on both
  `velocityLeft`/`velocityRight`, same break condition) — **logic-
  identical to the loop it replaces**, confirmed both by inspection and
  by the red/green proof below. Whoever next flashes a robot to verify
  the physical settle behavior should expect no change from
  pre-extraction behavior — this was a pure relocation, not a rewrite.
- **`tickDrive()` call site** (`src/shims.cpp`): the
  `if (wasActive && !moveActive)` branch now reads
  `r.engine.settleToRest(); odomUpdate(r);` — two calls, in that order,
  exactly mirroring the old loop-then-`odomUpdate(r)` shape. Odometry
  ownership is unchanged: `settleToRest()` has no knowledge of Rig-local
  `x/y/heading` and calls no odometry function of its own.
- **Sprint-003-era objection, re-examined**: read in full (it was still
  present in `shims.cpp` before this ticket's edit). Its exact claim is
  that extracting the loop "would mean moving odometry ownership into
  motion_engine too" — but the passage's own reasoning ties that only to
  extracting the *whole settle-then-integrate* behavior as one unit
  (the loop's "whole point," per that comment, was "folding coast counts
  into `odomUpdate()` ... before the final telemetry read"). It never
  argues that relocating the settle *decision* alone, while leaving
  `odomUpdate(r)` as a second, separate, caller-owned call immediately
  after, has the same problem — and by construction it does not:
  `settleToRest()` never touches odometry state or calls anything
  odometry-related. The planner's reading holds; the objection is not
  broader than that. No exception thrown.
- **Invariants preserved**: (1) one ticker per move —
  `tickDrive()` remains `settleToRest()`'s only caller (grep confirms);
  no new fiber, thread, or launcher call was added anywhere in this
  change. (2) neutral delivery on completion — `settleToRest()`'s first
  internal `kernel.step()` is what delivers the previously-staged
  `kernel_.neutral()` to the motors, exactly as the old loop's first
  iteration did; proven by
  `test_settle_to_rest_stops_early_once_at_rest_and_never_reenergizes`.
  (3) `deliverStopNow(Rig&)` (sprint 006 ticket 002) is untouched — this
  ticket never touches `stopAll()`, `endMove()`, or `updateMove()`'s
  cross-fiber stop path, all of which still call the motor ports
  directly and never `kernel.emergencyStopMotors()`.
- **Red/green proof** (the acceptance test that matters): temporarily
  replaced `MotionEngine::settleToRest()`'s body with an empty no-op and
  ran `tests/host/test_motion_engine_settle.py` —
  `test_settle_to_rest_stops_early_once_at_rest_and_never_reenergizes`
  and `test_settle_to_rest_enforces_the_iteration_cap` both **FAILED**
  (`steps_taken == 0` in both cases, versus the expected 4 and 12).
  Restored the real implementation from a pre-change backup; all 42
  scoped tests (`test_motion_engine_settle.py`,
  `test_regression_post_move_neutral.py`,
  `test_motion_engine_reductions.py`, `test_kernel_harness.py`,
  `test_cxx11_syntax_gate.py`) passed green again, and the full suite
  passed 404/404 (402 baseline + 2 new).
- **`FakeSleeper::onSleep` reuse**: yes, directly — `motion_engine_shim.
  cpp`'s new `meArmSettleProfile()` arms `onSleep` to script a
  step-indexed encoder position/sample-time playback (both wheels, same
  values per step) while `settleToRest()`'s internal loop runs, the only
  way to feed a decaying velocity profile across steps that all happen
  inside one C++ call. Captures `sleeper.sleepCalls` as a `baseline` at
  arm time so the schedule is relative to when it's armed, not to
  process start (`step() -> sleepMillis()` twice per step, `stepIndex =
  (callNumber - baseline - 1) / 2`, matching `FakeSleeper`'s own header
  comment on call-count parity).
- **Shim file choice**: extended `motion_engine_shim.cpp` (new exports
  `meSettleToRest`, `meArmSettleProfile`, `meDisarmSettleProfile`), not
  `kernel_shim.cpp` — `kernel_shim.cpp`'s `Handle` has no `MotionEngine`
  instance to call `settleToRest()` on, while `motion_engine_shim.cpp`'s
  `Handle` already composes `kernel` + `engine` together exactly like
  production `Rig`. This also matches `motion_engine_shim.cpp`'s own
  header comment: "Extend this file's function list -- don't invent a
  second shim." The sprint's `design/DESIGN.md` §9/§14 overlay named
  `kernel_shim.cpp` for this; corrected both mentions to
  `motion_engine_shim.cpp` (reported to team-lead — overlay edit, needs
  `.diff.md` regeneration).
- **New host test file**: `tests/host/test_motion_engine_settle.py` (own
  `_bind()`/`Engine`/`motion_lib` fixture, own compiled `.so`, matching
  this repo's established one-file-per-concern convention for
  `motion_engine_shim.cpp`-based tests) — 2 tests, both passing.
- **C++11 gate**: ran `test_cxx11_syntax_gate.py` after the change —
  passed with **no new registration**, confirming the ticket's claim
  (`motion_engine.cpp` was already in `_CXX11_PORTABLE_SOURCES`).
- **Annex material**: this ticket's plan referenced `design/DESIGN.md`
  §9 ("Shim + blocks") and §14 ("Sprint 008 — architecture diagram and
  change summary") directly by section number, both already present at
  those locations in the overlay — no separate `R-NN`-to-annex lookup
  was needed for this ticket (unlike tickets 001/003, which mapped
  `review.md`-style `R-NN` IDs into per-topic annex files).
- **PXT build evidence**: ran `uv run python tools/make_deploy.py`
  (scratch build, no `--flash`) twice. Attempt 1 hit the documented
  V1-legacy `srec_cat` hex-merge failure followed by a packaging abort
  (`TS9043`, after a pxt-core cache-write `TypeError`) — no hex.
  Attempt 2 hit the same V1-legacy `srec_cat` failure (harmless,
  V1-only) plus `TS9200` on `test.ts`, but still produced the real V2
  hex: `.tmp/deploy-head/built/mbcodal-binary.hex` (1,394,666 bytes,
  fresh mtime). **Both attempts compiled every `.cpp` cleanly, including
  `motion_engine.cpp` and `shims.cpp`'s new call site** — zero compile
  errors in either attempt; only the documented-benign packaging/
  hex-merge steps failed on attempt 1. No robot flash was performed
  (not required by this ticket's acceptance criteria).
- **Nothing found contradicting the sprint's architecture** — the
  overlay's own §9/§14 prose already described this exact extraction
  prospectively (narrower cut than the sprint-003 objection, `settle
  ToRest()` name, `motion_engine_shim.cpp`/`fake_ports.h` reuse) and
  matched what was implemented, aside from the `kernel_shim.cpp` vs
  `motion_engine_shim.cpp` correction noted above.

## C++11 Gate Coverage

- **Inside the gate**: `motion_engine.h`/`.cpp` — already one of the
  four files `test_cxx11_syntax_gate.py` covers. The new method is
  automatically gate-covered with **no new registration** — run the
  gate after this change to confirm (this is a meaningful difference
  from sprint 006's three extractions, each of which needed a new
  dedicated syntax-check translation unit because each was a new file).
- **Outside the gate**: `shims.cpp`'s call-site change
  (`tickDrive()` calling the new method instead of running its own
  loop) is, like every `shims.cpp` change, invisible to the gate and to
  every host test by construction (`src/DESIGN.md` §1's layering
  table) — a green host suite here proves the *decision logic*
  compiles and behaves correctly in isolation; it does **not** prove
  `shims.cpp`'s new call site compiles or links against the method's
  actual signature. This sprint's own build-checkpoint ticket (006,
  which depends on this one) is what proves that.

## Testing

- **Existing tests to run**: `tests/host/test_regression_post_move_neutral.py`,
  `tests/host/test_motion_engine_reductions.py`,
  `tests/host/test_kernel_harness.py` — confirm no regression to
  move-completion behavior or kernel stepping.
- **New tests to write**: the extracted method's own bounded-iteration/
  break-on-rest/no-re-energize test (see Acceptance Criteria); an
  iteration-cap enforcement test.
- **Verification command**: `uv run pytest tests/host/ -k "settle or
  regression_post_move"` during development, then a full
  `uv run pytest` before marking this ticket done.
