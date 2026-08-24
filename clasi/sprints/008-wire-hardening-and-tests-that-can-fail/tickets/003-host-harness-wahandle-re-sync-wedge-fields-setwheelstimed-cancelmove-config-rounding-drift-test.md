---
id: '003'
title: 'Host-harness WaHandle re-sync: wedge fields, setWheelsTimed/cancelMove, config
  rounding, drift test'
status: open
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: host-harness-double-drift.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Host-harness WaHandle re-sync: wedge fields, setWheelsTimed/cancelMove, config rounding, drift test

## Description

The `WaHandle` test double (`tests/host/wire_motion_verb_shim.cpp`)
claims to mirror production "field-for-field" but has drifted in three
confirmed, load-bearing ways (code review R-25, `host-harness-double-
drift.md`). **This ticket changes only `tests/host/` — no production
`src/` file changes**, because in all three cases the double is wrong,
not the code it mirrors:

1. **Wedge fields** (`wire_motion_verb_shim.cpp:444-445`): the double's
   DIAG shim reads `out.wedgeLeft`/`out.wedgeRight` for ordinals 6/7.
   Production's real `diagValue()` (`shims.cpp:859-860`) reads
   `out.wedgeSuspectLeft`/`out.wedgeSuspectRight` for the same
   ordinals — a **different** field pair on the kernel's `Output`
   struct (`diffdrive.h:147-148` declares both pairs; `wedgeLeft/Right`
   come from `wedged()`, `wedgeSuspectLeft/Right` from
   `wedgeSuspect()` — genuinely different signals). No existing
   `WaHandle` test drives wedge state at all, so this has never been
   caught.
2. **`setWheelsTimed`** (`wire_motion_verb_shim.cpp:241-250`): the
   double calls `g_activeWaHandle->kernel.drive(velocity, twist,
   durationMs)` directly. Production's real `setWheelsTimed()`
   (`shims.cpp:345-352`) calls `r.engine.wheelsV(...)`, whose first act
   is `cancelMove()` (`motion_engine.cpp:45`, motion-api.md S6:
   "wheels_* clears the planner"). The double skips
   `MotionEngine::wheelsV()` (and therefore `cancelMove()`) entirely —
   command-supersession behavior is untested and untestable as wired.
3. **Config rounding** (`wire_motion_verb_shim.cpp:352`): the double's
   `getConfigValue`-equivalent returns
   `static_cast<int>(v * 1000.0f)` (truncating, single-precision
   float). Production's real `getConfigValue()` (`shims.cpp:1058`)
   returns `static_cast<int>(std::lround(v * 1000.0))`
   (round-to-nearest, double precision). The two disagree at exact
   `.5` boundaries and differ in floating-point rounding behavior more
   generally.

## Acceptance Criteria

- [ ] `WaHandle`'s DIAG shim reads `wedgeSuspectLeft`/`wedgeSuspectRight`
      instead of `wedgeLeft`/`wedgeRight`, matching
      `shims.cpp:859-860` exactly.
- [ ] `WaHandle`'s `setWheelsTimed` double routes through the same
      `cancelMove()`-triggering path production's `setWheelsTimed()`
      uses — either by calling the real `MotionEngine::wheelsV()`
      logic against the double's `kernel`/fake motors, or by an
      equivalent sequence that provably calls `cancelMove()` first.
- [ ] `WaHandle`'s config-rounding double matches
      `std::lround(v * 1000.0)` exactly (double precision,
      round-to-nearest), not a truncating single-precision cast.
- [ ] A new drift test is added and **demonstrated** to discriminate:
      temporarily revert each of the three fixes above (one at a time)
      and confirm the new test goes red; restore each and confirm
      green. Record in this ticket's own notes that this demonstration
      was performed (stash/confirm-red/restore/confirm-green), not
      merely that the test exists.
- [ ] No existing `WaHandle`-based test in
      `tests/host/test_wire_motion_verbs.py` (or elsewhere) regresses.

## C++11 Gate Coverage

- **Inside the gate**: none of this ticket's changes touch a file
  `test_cxx11_syntax_gate.py` covers — this ticket is entirely within
  `tests/host/`, which the gate does not check (the gate only checks
  `src/`'s portable translation units).
- **Outside the gate**: not applicable in the usual sense — this ticket
  makes no production `src/` change at all, so there is no target-build
  risk to flag. The three drifts being fixed live entirely in the test
  double; production behavior (`shims.cpp`, `motion_engine.cpp`) is
  untouched and unaffected by this ticket.

## Testing

- **Existing tests to run**: `tests/host/test_wire_motion_verbs.py`
  (full run) — confirm none of the existing `WaHandle`-based assertions
  regress from the double's corrected behavior.
- **New tests to write**: a wedge-state test driving DIAG ordinals 6/7
  through `WaHandle` and asserting agreement with
  `wedgeSuspect`-sourced expectations; a command-supersession test
  (issue a `WHEELS_V`, confirm any in-flight move-engine move is
  cancelled via the same path production uses); a config-rounding
  round-trip test at a `.5`-boundary value that would disagree under
  truncation vs. `std::lround`. Each of these three is also the drift
  test itself, or is accompanied by one per the Acceptance Criteria's
  demonstration requirement.
- **Verification command**: `uv run pytest tests/host/test_wire_motion_verbs.py`
  during development, then a full `uv run pytest` before marking this
  ticket done.
