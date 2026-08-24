---
id: '003'
title: 'Host-harness WaHandle re-sync: wedge fields, setWheelsTimed/cancelMove, config
  rounding, drift test'
status: done
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

- [x] `WaHandle`'s DIAG shim reads `wedgeSuspectLeft`/`wedgeSuspectRight`
      instead of `wedgeLeft`/`wedgeRight`, matching
      `shims.cpp:859-860` exactly.
- [x] `WaHandle`'s `setWheelsTimed` double routes through the same
      `cancelMove()`-triggering path production's `setWheelsTimed()`
      uses — either by calling the real `MotionEngine::wheelsV()`
      logic against the double's `kernel`/fake motors, or by an
      equivalent sequence that provably calls `cancelMove()` first.
- [x] `WaHandle`'s config-rounding double matches
      `std::lround(v * 1000.0)` exactly (double precision,
      round-to-nearest), not a truncating single-precision cast.
- [x] A new drift test is added and **demonstrated** to discriminate:
      temporarily revert each of the three fixes above (one at a time)
      and confirm the new test goes red; restore each and confirm
      green. Record in this ticket's own notes that this demonstration
      was performed (stash/confirm-red/restore/confirm-green), not
      merely that the test exists.
- [x] No existing `WaHandle`-based test in
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

## Implementation Notes

**R-25's annex material.** Lives in
`docs/code-review/2026-08-23/raw/verify-python.md`, item `PY-03`
("test-double drift (CONFIRMED on all three)", ~lines 100-138) — the
top-level `R-25` ID (`review.md` line 256) does not appear in the
annex itself, same pattern ticket 001 (R-06=KERN-06, R-18=WIRE-02) and
ticket 002 found. `review.md`'s own one-paragraph R-25 summary (line
256) is a compressed shorthand that mislabels item (a) as "harness
STATUS `wedge` reads the latched fields" — the divergent code is
actually in the DIAG double's `diagValue()` switch (ordinals 6/7),
which STATUS's `wedge` field then folds in; PY-03's own detailed
write-up gets this right and is what this ticket followed. Separately,
the sprint-local copy of the issue
(`clasi/sprints/008-.../issues/host-harness-double-drift.md`) names the
wrong file for the same finding — "harness STATUS shim reads
wedgeLeft/Right (latched) at **kernel_shim** 337-338" — the double
actually lives in `wire_motion_verb_shim.cpp` (not `kernel_shim.cpp`,
which is a different shim for a different test file with no wire-layer
DIAG mapping at all); PY-03's own line numbers (337-338 pre-sprint-008,
444-445 by the time this ticket ran, after tickets 001/002 shifted the
file) do say `wire_motion_verb_shim.cpp` correctly. No verdict changes
— all three drifts were CONFIRMED exactly as the ticket's Description
states — but both restatements (review.md's headline and the
sprint-local issue copy) get *which shim/function* wrong in the same
direction, which cost real time to track down; PY-03 itself is the
correct, adversarially-verified source and should be cited over either
restatement in future work.

**The three drifted behaviors, production vs. pre-fix double:**

1. **Wedge fields.** Production `diagValue()` (`shims.cpp:859-860`)
   reads `wedgeSuspectLeft`/`wedgeSuspectRight` for DIAG ordinals 6/7.
   The pre-fix double (`wire_motion_verb_shim.cpp:444-445`) read
   `wedgeLeft`/`wedgeRight` instead — a different, LATCHED pair on the
   same `Output` struct (`wedged()` vs `wedgeSuspect()` on the `Motor`
   port). No `WaHandle` test drove either signal before this ticket.
2. **`setWheelsTimed`/command-supersession.** Production
   (`shims.cpp:345-352`) calls `r.engine.wheelsV(...)`, whose first act
   is the PRIVATE `cancelMove()` (`motion_engine.cpp:45`, motion-api.md
   S6). The pre-fix double computed the identical velocity/twist split
   by hand and called `kernel.drive()` directly, skipping
   `MotionEngine` (and `cancelMove()`) entirely — an in-flight MOVE_X
   would have kept running underneath a WHEELS_V that should have
   superseded it.
3. **Config rounding.** Production `getConfigValue()` (`shims.cpp:1058`
   in this checkout) returns
   `static_cast<int>(std::lround(v * 1000.0))` — double-precision
   product, round-to-nearest. The pre-fix double returned
   `static_cast<int>(v * 1000.0f)` — single-precision product,
   truncating.

**Fix applied.** (1) `diagValue()` case 6/7 now reads
`wedgeSuspectLeft`/`wedgeSuspectRight`. (2) `setWheelsTimed()` now
calls `g_activeWaHandle->engine.wheelsV(static_cast<float>(left),
static_cast<float>(right), durationMs)` — the SAME real
`MotionEngine::wheelsV()` `engineWheelsX()`/`engineMoveX()` already
use, not a hand-rolled sequence, since `cancelMove()` is PRIVATE on
`MotionEngine` and unreachable from the shim any other way. (3)
`getConfigValue()` now returns
`static_cast<int>(std::lround(v * 1000.0))`, matching production
byte-for-byte.

**Drift tests added** (`tests/host/test_wire_motion_verbs.py`, new
section at end of file):
`test_wheels_v_supersedes_in_flight_move_x_via_cancel_move`,
`test_status_wedge_reports_suspect_not_latched`,
`test_status_wedge_ignores_latched_when_suspect_clear`,
`test_config_rounding_matches_double_precision_lround`.

**What each mechanically detects vs. only regression-checks** (asked
for explicitly — being honest about the difference, not just claiming
"drift test" for all four):
- The **wedge pair** and **command-supersession** tests are TRUE drift
  tests: they check an independently-reasoned expectation (which
  Motor signal a given ordinal must read; whether a real, observable
  side effect — `isMoveActive()` going false — occurred) against the
  double's own behavior. Either would fail again if a future edit
  reintroduced the wrong field or bypassed the engine, with **no
  production change required** to trip them — they detect drift
  mechanically, not just today's specific bug.
- The **config-rounding** test is NARROWER: it is a regression test
  pinned to one verified-by-direct-probe divergent input (`v=0.251f`),
  not a structural check that the double calls `std::lround`
  specifically. There is no black-box way to distinguish "rounds
  correctly by construction" from "rounds correctly by coincidence at
  every OTHER input" from outside the shim. It reliably catches a
  revert to the truncating float32 path (proven below) but would not
  catch a different, non-truncating rounding bug that still happened
  to agree with production at `v=0.251`. Recorded here per this
  ticket's own honesty requirement rather than oversold as more than
  it is.

Note on the review's own worked example: PY-03's write-up illustrates
the config-rounding bug with `v=2.3f`, claiming
`2.3f * 1000.0f ≈ 2299.9995 → 2299` vs `lround(2299.99995…) = 2300`. A
direct compiled C++ probe run during this ticket's execution
(`static_cast<int>(2.3f * 1000.0f)` and
`std::lround((double)2.3f * 1000.0)`) found **both paths actually
produce 2300** for that specific input — `2.3f`'s true value
(2.299999952…) multiplied in float32 rounds UP to exactly the
representable value `2300.0f`, so it does not diverge. This is a minor
inaccuracy in the review's illustration, not in its verdict (PY-03's
CONFIRMED finding — that the two casts disagree in general — is
correct; `v=2.3f` alone just isn't a witness for it). This ticket's own
test uses `v=0.251f` instead, found by exhaustively probing
3-decimal-digit values and confirmed by the same compiled-probe method
to actually diverge (`250` vs `251`).

**Demonstrated red/green** (per this ticket's own AC): each of the
three fixes above was reverted individually in
`wire_motion_verb_shim.cpp`, the affected test(s) were re-run and
observed to fail (RED), then the fix was restored and the same test(s)
re-run and observed to pass (GREEN), in this order:
1. Wedge fix reverted -> both wedge tests failed (`wedge=0`/`wedge=1`
   observed instead of the expected opposite) -> restored -> both pass.
2. `setWheelsTimed` fix reverted -> the command-supersession test
   failed (`engine_move_active()` read `True` after WHEELS_V) -- and,
   as a bonus confirmation, 3 of the 4 updated WHEELS_V real-effect
   duty tests ALSO went red at the same time (they now assert the real
   `countsPerMm()`-scaled duty, which the reverted double no longer
   produces) -> restored -> all pass.
3. Config-rounding fix reverted -> the rounding test failed
   (`0.250000` observed, `0.251` expected) -> restored -> passes.

Full suite after final restore: `uv run pytest` = 402 passed (398
baseline + 4 new drift tests). No existing test was deleted or weakened
to make this pass.

**Most valuable finding: an existing test changed meaning.** The four
pre-existing `WHEELS_V` real-effect duty tests
(`test_wheels_v_real_effect_pure_forward`,
`test_wheels_v_real_effect_differential_reconstructs_left_right`,
`test_wheels_v_duration_at_ceiling_is_accepted`,
`test_stop_real_effect_returns_duty_to_zero`) were passing before this
ticket by asserting duty values computed as if `countsPerMm() == 1.0`
(e.g. `WHEELS_V 200 200` with `fullDutyVelocity=1000` asserted
`duty == 0.2`). That was never true of production: `MotionEngine`'s
real `travelCalib_` default is `0.8102` mm/deg, i.e.
`countsPerMm() = 10/0.8102 ≈ 12.343`, not `1.0` — a fact `WHEELS_X`'s
own real-effect tests in this same file already accounted for (via
`wa.counts_per_mm()`), but `WHEELS_V`'s did not, because its double
bypassed the real `MotionEngine` and hand-computed velocity/twist with
an implicit `1.0` factor. These tests were GREEN while modeling a
robot production cannot produce. Fixing `setWheelsTimed()` to route
through the real engine (required for the `cancelMove()` fix) also
applies the real `countsPerMm()` scaling, which would have saturated
these tests' duty at the `maxDuty` rail and erased the
differential/sign-convention signal they exist to check. All four were
updated to read `wa.counts_per_mm()` dynamically and use a larger
`full_duty_velocity` (`_WHEELS_V_FULL_DUTY_VELOCITY = 5000.0`, matching
`_WHEELS_X_FULL_DUTY_VELOCITY`'s own existing convention) so they stay
unsaturated and meaningful under the real, calibrated scaling — this is
a correction, not a weakening: reverting the `setWheelsTimed` fix while
keeping the updated tests turns 3 of these 4 tests red on its own (see
red/green log above), so they now actually exercise the real
production math instead of passing by construction.

**`host-DESIGN.md` overlay edited: yes**
(`clasi/sprints/008-wire-hardening-and-tests-that-can-fail/design/host-DESIGN.md`,
§2 "Orientation"). The overlay's pre-written sprint 008 addendum
already anticipated this ticket's wedge/`setWheelsTimed`/config-
rounding fix accurately, but its base sentence ("mirroring the
production math field-for-field with counts-per-mm fixed at 1.0")
would have become inaccurate for `setWheelsTimed` once this ticket
landed (that verb no longer fixes counts-per-mm at 1.0 — see finding
above). Tightened the base sentence to scope "fixed at 1.0" to
`getConfigValue`/`setKernelValue` only, and added the "test changed
meaning" finding (the `WHEELS_V` real-effect duty tests) to the same
paragraph, since it is a coverage-boundary fact the overlay's job is to
carry. **Team-lead: this overlay edit needs its `.diff.md` sibling's
`source_hash` regenerated before `close_sprint`, per your own note.**
No canonical `tests/host/DESIGN.md` edit was made (out of scope for a
programmer agent; applied from the overlay at sprint close).

**Contradicting the sprint architecture:** none found. The overlay's
pre-written description of this fix (host-DESIGN.md §2/§6, written
before this ticket ran) matched what the ticket's own Description
specified and what code inspection confirmed, with the one refinement
above (the cpm-scaling consequence for `setWheelsTimed`, and the
resulting existing-test-meaning change) that the overlay's original
text did not spell out.
