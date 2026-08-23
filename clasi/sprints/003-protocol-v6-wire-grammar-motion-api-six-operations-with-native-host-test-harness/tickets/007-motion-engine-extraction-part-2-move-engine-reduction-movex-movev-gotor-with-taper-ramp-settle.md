---
id: '007'
title: 'Motion engine extraction, part 2: move-engine reduction (moveX, moveV, goToR)
  with taper/ramp/settle'
status: in-progress
use-cases:
- SUC-003
- SUC-004
depends-on:
- '006'
github-issue: ''
issue: implement-motion-api-six-operations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Motion engine extraction, part 2: move-engine reduction (moveX, moveV, goToR) with taper/ramp/settle

## Description

Move `shims.cpp`'s `serviceMove`/`startMove`/`tickDrive` shaping logic
(acceleration ramp, end-of-move taper, wrong-way abort, settle ticks,
stall/deadline handling) into `MotionEngine`, restated as `moveX`
(distance+rotation+cruise+timeout, the reduction `wheels_x(distance -
rot·b/2, distance + rot·b/2)`), `moveV` (v_x+omega+duration, the
reduction onto `wheels_v`), and `goToR` (x, y, speed, arrive, timeout —
the plain spec reduction `move_x(arcLength, 2·atan2(y,x))`, ported from
`main.ts`'s existing `startGoTo` arc math into C++ so it is reachable
from the wire without a round-trip through TypeScript). `main.ts`'s
`move`/`goTo`/`whileMoving`/`whileGoingTo` blocks become thin forwards
into `MotionEngine.moveX`/`goToR`; their observable behavior —
including the taper/ramp shaping and its defaults — is unchanged.
`goToWorld()`'s own richer heuristic (turn-first threshold, capped-arc
curvature) is explicitly NOT ported here (see ticket 010 and sprint.md
Design Rationale — it stays a separate TS-level path).

## Acceptance Criteria

- [x] `MotionEngine::moveX(distance, rotation, cruise, timeout)`
      reproduces `startMove`+`serviceMove`'s existing observable
      behavior byte-for-byte for the cases `test/test.ts`'s tours
      exercise (straight legs, pure turns, arcs), verified against the
      `FakeMotor`.
  - [x] Degenerate cases tested: `move_x(d, 0)` straight, `move_x(0, θ)`
        pivot.
  - [x] The pivot-vs-blend threshold (50°, per `motion-api.md` §3.3,
        `navigator.cpp:237-240`) is tested at and around the boundary —
        this project's own `turnFirstDeg`/`kMaxArc` heuristics in
        `goToWorld()` are a SEPARATE, later-layered concern (ticket
        010) and are not what this criterion tests; this criterion is
        about `moveX`'s own pivot-first-vs-blended-arc behavior per the
        spec table.
- [x] `MotionEngine::moveV(v_x, omega, duration)` reduces onto
      `wheelsV` per `motion-api.md` §2 and is tested against
      hand-computed values.
- [x] `MotionEngine::goToR(x, y, speed, arrive, timeout)` implements
      the PLAIN spec reduction (turn angle `2·atan2(y,x)`, arc length
      per §3.5) with no turn-first/capped-curvature heuristic — a
      distinct algorithm from `goToWorld()`'s TS-level one (sprint.md
      Design Rationale), and is tested against hand-computed values for
      several `(x, y)` cases including a near-zero-`y` straight case.
- [x] `timeout` is respected as a REAL backstop (the wire's own
      required field), distinct from the engine's internally computed
      duration-based lease — verified by a test where a blocked
      `FakeMotor` (never reaching the commanded distance) is stopped by
      `timeout`, not left running.
- [x] `test/test.ts` and `test/testrig.ts` require no changes (their
      block calls are unaffected).
- [x] `src/motion_engine.{h,cpp}` additions are covered by `pxt.json`'s
      `files` array (already added in ticket 006; confirm no new file
      was introduced that needs adding).

## Implementation Plan

**Approach**: Port `serviceMove`'s taper/ramp/wrong-way-abort/settle
logic into `MotionEngine` largely verbatim (the algorithm itself is not
changing, only its home and its calling convention — from `Rig`'s
inline state to `MotionEngine`'s own move-state struct). `goToR`'s arc
math is a small, new, pure-function port of `main.ts`'s existing
`startGoTo` calculation, written directly in C++ so it is reachable
from `wire_adapter` without TypeScript.

**Files to modify**: `src/motion_engine.h`/`.cpp` (add move-engine
state + `moveX`/`moveV`/`goToR`), `src/shims.cpp` (`startMove`/
`serviceMove`/`updateMove`/`tickDrive`/`endMove`/`progress` become thin
forwards), `src/main.ts` (no signature changes — internal call target
only, if anything changes at all).

**Files to create**: none.

**Testing plan**: New host unit tests per Acceptance Criteria; existing
block behavior protected by the observable-contract-preservation
requirement (verified by the two regression tickets 008/009, which
depend on this ticket, plus this ticket's own byte-for-byte comparison
tests).

**Documentation updates**: `motion_engine.h`'s header comment gains the
move-engine's shaping summary (ramp/taper/settle), citing
`motion-api.md` §3.3 for the pivot-vs-blend table.

**Testing**

- **Existing tests to run**: `uv run pytest tests/host/`.
- **New tests to write**: `tests/host/test_motion_engine_reductions.py`
  per Acceptance Criteria above.
- **Verification command**: `uv run pytest tests/host/`
