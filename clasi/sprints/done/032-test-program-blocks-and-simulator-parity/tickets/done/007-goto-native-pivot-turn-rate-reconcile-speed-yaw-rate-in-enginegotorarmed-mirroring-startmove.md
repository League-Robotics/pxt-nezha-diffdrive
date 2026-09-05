---
id: '007'
title: 'goTo native pivot turn-rate: reconcile speed/yaw-rate in engineGoToRArmed,
  mirroring startMove'
status: done
use-cases:
- SUC-006
depends-on:
- '006'
github-issue: ''
issue: goto-turn-rate-arrival-tolerance-tick-runner-cyclestat.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# goTo native pivot turn-rate: reconcile speed/yaw-rate in engineGoToRArmed, mirroring startMove

## Description

**This finding required re-derivation beyond the issue's own text —
read this description before implementing, it changes the fix's shape
and location.** The issue states "goTo's pivot runs at the linear
cruise instead of honoring 'set default turn rate'" and suggests a
`blocks/motion.ts`-only fix ("convert the default yaw rate to a pivot
cruise in startGoTo"). Tracing the actual call chain shows the fix
CANNOT be TS-only:

- `src/blocks/motion.ts`'s `startGoTo()` calls `_goToR(goalX, goalY,
  goalSpeed, goalArrive)` — note only ONE rate parameter (`goalSpeed`),
  no yaw rate at all.
- `src/shims.cpp`'s `engineGoToRArmed(x, y, speed, arrive)` (the native
  function `_goToR` shims to) passes `speed` straight through to
  `r.engine.goToR(x, y, speed, arrive, timeout)` with no reconciliation.
- `src/motion/motion_engine.cpp`'s `MotionEngine::goToR()` computes its
  own pivot-then-straight split internally (`queuePivotThenStraight()`)
  when `|theta| >= kTurnFirstAngle`, but `queuePivotThenStraight(pivotRotation,
  straightDistance, cruise, deadline)` reuses the SAME `cruise` argument
  for BOTH the pivot phase (`beginSegment(0.0f, yawTarget, cruise,
  deadline)`) and the subsequent straight phase
  (`seg_.pendingCruise = cruise`) — there is exactly one throughput
  speed parameter for the whole call, at the C++ layer, not just the TS
  layer.
- By contrast, `shims.cpp`'s `startMove()` (backing `move()`/`_startMove`)
  ALREADY reconciles two independent rate ceilings (`speed`, `yawRate`)
  into one `cruise` value via a duration-budget calculation ("whichever
  axis takes longer at its own ceiling governs," with a `willSplit`-aware
  budget for the pivot-then-straight case) BEFORE calling
  `r.engine.moveX(distanceF, rotation, cruise, timeout)` — this is why a
  plain `RUN:pivot`/`move()` already correctly honors `defaultYawRate`,
  and it is the exact pattern this ticket mirrors for `goTo`.

There is no way to make `goTo`'s pivot phase honor a distinct yaw rate
without either (a) reconciling speed and yaw-rate into a single
`cruise` value BEFORE the native call, the same way `startMove()`
already does — this ticket's chosen approach — or (b) changing
`MotionEngine::goToR()`'s own signature to accept two cruises, a larger,
more invasive change to a function this project also treats as
carrying real behavioral-fidelity weight (unlike the vendored kernel in
`src/core/diffdrive.{h,cpp}`, `motion_engine.cpp` IS project-owned and
editable — but changing its signature ripples to `moveX()`'s own single-
cruise contract too, which is unrelated to this bug). Approach (a) is
scoped correctly per `sprint.md`'s Design Rationale: the change is
contained to `engineGoToRArmed()` (or a new shim function it delegates
to) plus its two TS-side callers.

## Acceptance Criteria

- [x] `engineGoToRArmed()` (`src/shims.cpp`) gains a `yawRate` parameter
      (mirroring `startMove()`'s existing `(distance, yaw, speed,
      yawRate)` shape) and, BEFORE calling `r.engine.goToR(...)`,
      computes the bearing-then-chord decomposition `goToR()` itself
      will use (`bearingRaw = atan2(y, x)`, `theta = wrap(2*bearingRaw)`,
      `chord = hypot(x, y)`) and applies the SAME duration-budget
      reconciliation `startMove()` already uses (pivot duration from
      `theta`/`yawRate`, straight duration from `chord`/`speed`, budget
      = sum when the split threshold is crossed, matching `goToR()`'s
      OWN split condition `|theta| >= kTurnFirstAngle` — read this
      threshold via `MotionEngine::turnFirstAngle()`, the same public
      accessor `startMove()`'s own shim already uses, never a
      second hand-typed literal) to produce ONE reconciled `cruise`
      value, then calls `r.engine.goToR(x, y, cruise, arrive, timeout)`.
      IMPLEMENTED VIA A PRE-ARMED SETTER, NOT A LITERAL 5TH PARAMETER:
      `engineGoToRArmed()` stays 4-param (`x, y, speed, arrive`) and
      reads a new `Rig::pendingGoToYawRate_`, set by a new
      `engineSetGoToYawRate(int)` shim called immediately before
      `_goToR()` -- the same `engineSetGoToDeadline()`/
      `pendingGoToDeadline_` pre-arm pattern this file already uses for
      `timeout`, for the identical reason: a literal 5th parameter here
      resurrects the exact PXT-packager arity crash that pattern exists
      to avoid (`pendingGoToDeadline_`'s own comment, `shims.cpp`). Also
      corrected: the reconciliation uses `bearingRaw` (the angle
      `queuePivotThenStraight()` actually pivots), NOT `theta` (the
      split-decision angle) -- `motion_engine.cpp` shows these differ in
      the general case (`theta` wraps `2*bearingRaw`); using `theta`
      would double the pivot phase's estimated duration whenever no
      wrap occurs. See this ticket's closing report for the worked
      numeric example.
  - [x] `MotionEngine::goToR()`'s own signature and
        `queuePivotThenStraight()` are UNCHANGED — the reconciliation
        happens strictly before the native call, per the Design
        Rationale.
  - [x] The deadline/timeout computation already in `shims.cpp`
        (`engineGoToRArmed`/`engineSetGoToDeadline`'s split-arm pair)
        is re-examined for consistency with the new reconciliation —
        don't compute two different pivot/straight duration estimates
        (one for the timeout, one for the cruise) that could disagree;
        share the computation if at all reasonable. KEPT SEPARATE after
        re-examination: `motion.ts`'s `timeout` stays a worst-case 180
        deg pivot bound (goToR() never pivots more, by construction of
        its own short-arc wrap) -- always >= the reconciliation's own
        actual-bearing estimate, so a conservative bound can only
        disagree in the safe direction. Noted in `motion.ts`'s comment.
- [x] `src/blocks/motion.ts`'s `startGoTo()` passes `defaultYawRate`
      (converted to the shim's expected units, matching `startMove()`'s
      own `Math.round(defaultYawRate * 100)` centidegree-per-second
      convention) through to `_goToR`/the new shim parameter, instead
      of only ever passing `defaultSpeed`.
- [x] `src/blocks/sim.ts`'s `_goToR` mirror is updated to apply the
      SAME reconciliation (for simulator/hardware parity — this ties
      directly to SUC-004/ticket 005's split work; the simulator's own
      `_goToR` shim signature gains the analogous `yawRate` parameter).
      Same pre-armed-setter shape as the native side
      (`_setGoToYawRate()`/`simPendingGoToYawRate`), not a literal 5th
      `_goToR()` parameter -- the PXT shim arity constraint applies to
      the TS-declared shim signature too. Note: this simulator
      reduction never splits into pivot-then-straight (pre-existing,
      out of this ticket's scope), so the reconciliation applied is the
      max-duration (non-split) form only.
- [x] A host test pins the reconciliation FORMULA itself against
      `startMove()`'s existing one — e.g. a shared/duplicated pure
      function tested for numeric agreement on a handful of
      (x, y, speed, yawRate) cases, not just "the code compiles and
      runs." Stronger than duplicated: `startMove()` and
      `engineGoToRArmed()` now both call the SAME
      `MotionEngine::reconcileDualRateCruise()`, pinned against an
      independently-written Python transcription in
      `tests/host/test_goto_turn_rate_reconciliation.py` (6
      parametrized cases).
- [x] A worked example: `goTo` to a point requiring roughly a 90° pivot
      with `defaultYawRate` and `defaultSpeed` set to visibly different
      values — assert (via the host-testable geometry math, not a robot
      run) that the pivot PHASE's own duration now matches `180° /
      defaultYawRate` to a reasonable tolerance, not
      `180° / (speed-reinterpreted-as-degrees)`.
      `test_worked_example_pivot_duration_follows_default_yaw_rate_not_speed`
      asserts the pivot phase's duration matches `|bearingRaw| /
      defaultYawRate` (90 deg / 45 deg/s = 2.0 s), NOT `speed`
      reinterpreted as an angular rate, AND explicitly pins that it is
      NOT `|theta| / defaultYawRate` (180 deg / 45 deg/s = 4.0 s)
      either -- see this ticket's closing report for why the literal
      "180 deg / defaultYawRate" phrasing is the wrong formula for the
      pivot's own real duration (it describes `motion.ts`'s separate
      worst-case TIMEOUT budget instead).
- [x] `sprint.md`'s Open Question 1 (whether `stopMove()`'s
      unconditional stop is safe to call from `RUN:abort` regardless of
      `motionOwner_`) is UNRELATED to this ticket — do not conflate; if
      this ticket's own testing surfaces anything relevant to that
      question, note it in the ticket's own closing comment for ticket
      001's own record, don't silently fold it in here. Nothing
      relevant surfaced.
- [x] Because a "does this feel right on the fleet's calibrated bake"
      question can only be settled on a robot, mark that specific claim
      UNVERIFIED in this ticket's own closing notes and name the
      follow-up bench check (a `goTo` requiring a large pivot, timed
      against the configured `defaultYawRate`) rather than asserting
      MEASURED parity — this sprint is desk-only. UNVERIFIED: whether
      the reconciled `cruise` actually drives the ROBOT's pivot phase at
      `defaultYawRate` has not been checked on hardware. Follow-up: a
      bench `goTo` requiring a >=50 deg pivot, `defaultYawRate` set well
      away from the linear-cruise-implied rate (~140 deg/s), timed
      against the pivot phase alone -- belongs to sprint 031's own
      session per this ticket's own caution, not run here.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full suite — this changes a native shim many host tests may exercise via ctypes).
- **New tests to write**: the reconciliation-formula-agreement test and the worked-pivot-duration test described above; check whether `tests/host/` already has a ctypes harness that calls `engineGoToRArmed`/`startMove` directly (search for `startMove`/`goToR`/`goToRArmed` in `tests/host/`) — prefer extending that harness's pattern over inventing a new one.
- **TS type-check**: `npx tsc --noEmit` for the TS-side changes; this ticket ALSO changes C++ (`src/shims.cpp`), so the project's host-native test harness (whatever compiles `src/*.cpp` under `tests/host/` via ctypes — check `tests/host/README.md` for the exact build invocation) must be run, not just a Python-only test command.
- **Verification command**: `uv run pytest tests/host/ -k "goto or go_to" -v`
