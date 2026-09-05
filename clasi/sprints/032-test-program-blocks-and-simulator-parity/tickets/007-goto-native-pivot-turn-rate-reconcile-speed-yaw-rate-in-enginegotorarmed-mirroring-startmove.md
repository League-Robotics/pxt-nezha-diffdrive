---
id: "007"
title: "goTo native pivot turn-rate: reconcile speed/yaw-rate in engineGoToRArmed, mirroring startMove"
status: open
use-cases: [SUC-006]
depends-on: ["006"]
github-issue: ""
issue: "goto-turn-rate-arrival-tolerance-tick-runner-cyclestat.md"
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

- [ ] `engineGoToRArmed()` (`src/shims.cpp`) gains a `yawRate` parameter
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
  - [ ] `MotionEngine::goToR()`'s own signature and
        `queuePivotThenStraight()` are UNCHANGED — the reconciliation
        happens strictly before the native call, per the Design
        Rationale.
  - [ ] The deadline/timeout computation already in `shims.cpp`
        (`engineGoToRArmed`/`engineSetGoToDeadline`'s split-arm pair)
        is re-examined for consistency with the new reconciliation —
        don't compute two different pivot/straight duration estimates
        (one for the timeout, one for the cruise) that could disagree;
        share the computation if at all reasonable.
- [ ] `src/blocks/motion.ts`'s `startGoTo()` passes `defaultYawRate`
      (converted to the shim's expected units, matching `startMove()`'s
      own `Math.round(defaultYawRate * 100)` centidegree-per-second
      convention) through to `_goToR`/the new shim parameter, instead
      of only ever passing `defaultSpeed`.
- [ ] `src/blocks/sim.ts`'s `_goToR` mirror is updated to apply the
      SAME reconciliation (for simulator/hardware parity — this ties
      directly to SUC-004/ticket 005's split work; the simulator's own
      `_goToR` shim signature gains the analogous `yawRate` parameter).
- [ ] A host test pins the reconciliation FORMULA itself against
      `startMove()`'s existing one — e.g. a shared/duplicated pure
      function tested for numeric agreement on a handful of
      (x, y, speed, yawRate) cases, not just "the code compiles and
      runs."
- [ ] A worked example: `goTo` to a point requiring roughly a 90° pivot
      with `defaultYawRate` and `defaultSpeed` set to visibly different
      values — assert (via the host-testable geometry math, not a robot
      run) that the pivot PHASE's own duration now matches `180° /
      defaultYawRate` to a reasonable tolerance, not
      `180° / (speed-reinterpreted-as-degrees)`.
- [ ] `sprint.md`'s Open Question 1 (whether `stopMove()`'s
      unconditional stop is safe to call from `RUN:abort` regardless of
      `motionOwner_`) is UNRELATED to this ticket — do not conflate; if
      this ticket's own testing surfaces anything relevant to that
      question, note it in the ticket's own closing comment for ticket
      001's own record, don't silently fold it in here.
- [ ] Because a "does this feel right on the fleet's calibrated bake"
      question can only be settled on a robot, mark that specific claim
      UNVERIFIED in this ticket's own closing notes and name the
      follow-up bench check (a `goTo` requiring a large pivot, timed
      against the configured `defaultYawRate`) rather than asserting
      MEASURED parity — this sprint is desk-only.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (full suite — this changes a native shim many host tests may exercise via ctypes).
- **New tests to write**: the reconciliation-formula-agreement test and the worked-pivot-duration test described above; check whether `tests/host/` already has a ctypes harness that calls `engineGoToRArmed`/`startMove` directly (search for `startMove`/`goToR`/`goToRArmed` in `tests/host/`) — prefer extending that harness's pattern over inventing a new one.
- **TS type-check**: `npx tsc --noEmit` for the TS-side changes; this ticket ALSO changes C++ (`src/shims.cpp`), so the project's host-native test harness (whatever compiles `src/*.cpp` under `tests/host/` via ctypes — check `tests/host/README.md` for the exact build invocation) must be run, not just a Python-only test command.
- **Verification command**: `uv run pytest tests/host/ -k "goto or go_to" -v`
