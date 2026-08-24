---
id: '004'
title: 'Settle-tick loop extraction: host-testable MotionEngine settle helper'
status: open
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

- [ ] A new `MotionEngine` method (defined in `motion_engine.cpp`)
      encapsulates the settle decision: steps the kernel up to the same
      bound the inline loop used (12), breaking early once both wheels'
      measured velocity is within the same rest threshold (25.0
      counts/s) — behavior identical to the loop it replaces, not
      merely similar.
- [ ] `shims.cpp::tickDrive()`'s `if (wasActive && !moveActive)` branch
      calls the new method, then calls `odomUpdate(r)` itself
      immediately after (odometry ownership unchanged) — no
      settle-decision logic left inline in `tickDrive()`.
- [ ] `tests/host/test_regression_post_move_neutral.py` stays green,
      unchanged — it remains the "why this matters" test.
- [ ] A new host test (new shim surface on `kernel_shim.cpp` or
      `motion_engine_shim.cpp`, whichever proves the better fit —
      reusing `FakeSleeper::onSleep` from `fake_ports.h` where useful
      to observe iteration count) exercises the extracted method
      directly and asserts: (a) it steps the kernel repeatedly while
      velocity is above the rest threshold; (b) it stops early once
      velocity is at/below the rest threshold, without over-stepping;
      (c) it never re-energizes the motors (a settled/at-rest input
      produces no additional nonzero commanded duty).
- [ ] A host test proves the iteration cap is enforced: wheels held
      artificially above the rest threshold for longer than 12
      simulated steps — the method returns after the cap, not
      indefinitely.
- [ ] No new fiber or ticker is introduced; `tickDrive()` remains the
      new method's only caller.
- [ ] Bench note (no robot required to satisfy this ticket's own
      acceptance criteria — real hardware exercise of the physical
      settle behavior remains this sprint's build-checkpoint ticket's
      and any future bench session's concern, not this ticket's): state
      in this ticket's own notes that the extraction is logic-identical
      to the loop it replaces, for whoever next flashes a robot to
      verify.

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
