# Code review — correctness, landmines, student readability: block/shim layer

**Date:** 2026-08-23
**Scope:** `src/main.ts`, `src/shims.cpp`, `test/test.ts`, `test/testrig.ts`,
`pxt.json`, `tsconfig.json` (guidelines dimensions 1, 2, 5). Kernel / motion
engine / wire internals consulted only where needed to judge the TS↔C++
boundary (`diffdrive.cpp` step ordering, `motion_engine.cpp` endMove /
serviceMove end path, `wire_adapter.cpp` cruise resolution, `protocol.cpp`
RUN bridge).
**Method note:** the shim-signature check (every `//% shim=diffDrive::X`
declaration in `main.ts` against its `//%` C++ definition) was done
mechanically and exhaustively — all 31 pairs; result in "Not findings."
Comment hygiene deliberately not audited (separate reviewer).

Findings are most-severe-first. Every correctness finding was verified by
tracing both sides of the boundary; nothing below is pattern-matched.

---

### BLK-01 — Cross-fiber move teardown during a tick's settle window skips stop delivery; wheels run on until the watchdog

- **File:** `src/shims.cpp:415-425` (`updateMove`), `src/shims.cpp:449-545`
  (`tickDrive`, stop-delivery gate at 482), `src/shims.cpp:648-652`
  (`endMove`); enabling facts in `src/diffdrive.cpp:472-501` (command
  snapshot at 472 precedes the two settle sleeps at 495-501) and
  `src/motion_engine.cpp:69-70, 290-296` (`endMove`/`serviceMove` post
  `kernel_.neutral()` but delivery needs a later `step()`).
- **Dimension:** 1 (correctness — fiber interleaving, silent failure)
- **Severity:** Major
- **Scenario:** `tickDrive()`'s stop-delivery/settle path (shims.cpp:482-500)
  only runs when *this call* observes the active→inactive transition
  (`wasActive && !moveActive`). Any *other* fiber that clears the move
  between a tick's command snapshot and its serviceMove steals that
  transition. Each 24 ms tick spends ~8-10 ms parked in `kernel.step()`'s
  two settle sleeps, and `step()` snapshots the command *before* those
  sleeps — so a neutral staged during them is not applied by that step, and
  no later step ever runs:
  - **(a) Student stop:** blocking `diffDrive.move(0, 180)` on the main
    fiber, `input.onButtonPressed(Button.A, () => diffDrive.stopMove())` on
    another (`stop()` has the same hole; `emergencyStop()` is immune — it
    writes the ports directly). If the press lands in the settle window
    (~35-40 % of the time while moving), `endMove()` stages neutral, the
    in-flight step writes the *old* duty, `tickDrive` sees
    `wasActive == false`, skips delivery, returns false, the
    `while (_tickDrive())` loop exits — and the wheels hold the last
    commanded duty until the starvation watchdog's port-level stop
    ~100-150 ms later. That is the measured +9-13°/turn, +15-22 mm/leg
    overshoot class this very code block exists to prevent
    (shims.cpp:474-481), plus coast counts never folded into odometry.
  - **(b) UC-007's own recommended pattern:** background
    `while (diffDrive.driveTick())` fiber plus main-fiber `isMoving()`
    polling. `isMoving()` maps to `updateMove()` → `serviceMove()` with
    **no `stepBusy` guard**, so when a blocked move's deadline backstop
    expires while the ticker is inside a settle sleep, the *poller's*
    serviceMove ends the move (motion_engine.cpp:291-296) and the same
    abandonment follows: `isMoving()` reports false while the robot is
    still being driven.
- **Remedy:** make delivery unconditional — e.g. `tickDrive()` runs the
  settle path whenever the move was active on the *previous* tickDrive call
  and is inactive now (Rig-level "moveWasActiveLastTick" flag), regardless
  of which fiber ended it; and/or route cross-fiber teardown
  (`endMove`/`stopAll`) through a port-level zero write the way the
  watchdog does; and/or give `updateMove()` the `stepBusy` guard. Cross-ref
  `clasi/issues/settle-tick-loop-is-not-host-testable.md` — that issue pins
  the loop's necessity and its testability gap; this is a new defect in the
  paths *around* the loop, not a re-report.
- **Confidence:** high on the code path (both sides traced, snapshot order
  verified); medium on field frequency (window is ~1/3 of the tick period
  at the moment of teardown; not yet hardware-reproduced).

### BLK-02 — `runArgCount()` dereferences `runParts` with no guard: panic 980 / silent boot death before the first RUN event

- **File:** `src/main.ts:233-235`; contrast the guarded sibling
  `runArgText()` at `main.ts:226-229`; the hazard class is documented at
  `main.ts:64-72`.
- **Dimension:** 1 (correctness — PXT init-order trap)
- **Severity:** Major
- **Scenario:** `runParts` is deliberately declared with no initialiser
  (main.ts:73) and is first assigned inside the RUN event handler
  (main.ts:164). `runArgCount()` returns `runParts.length - 1` unguarded.
  Any call outside a RUN handler before the first RUN command arrives — for
  example a test program logging `diffDrive.runArgCount()` at top level, or
  a student calling it from a button handler at boot — dereferences an
  undefined array: on hardware this is the documented silent-boot-death
  class (panic 980, no serial output; measured on vevov 2026-08-21 for this
  exact declaration pattern). `test/test.ts:318` happens to call it only
  inside a handler, which is why it has not fired yet — the landmine is
  armed for the next test author, and testFiles get no independent
  type/nullability net.
- **Remedy:** mirror the sibling's guard: `if (!runParts) return 0`.
  One line.
- **Confidence:** high (verified against the dispatcher's assignment path;
  seeded lead 1 confirmed at these line numbers).

### BLK-03 — The wire's `cruise == 0` "configured default" resolves to full-duty velocity: a spec-following host commands ~875 mm/s

- **File:** `src/shims.cpp:340-346` (`engineDefaultCruiseMmS`), consumed at
  `src/wire_adapter.cpp:276-284` (WHEELS_X), 305-309 (MOVE_X), 346-349
  (GO_TO_R), 363-366 (GO_TO_W); inputs `src/shims.cpp:168`
  (`fullDutyVelocity = 10795` counts/s) and `src/motion_engine.h:328`
  (`travelCalib_ = 0.8102` mm/deg).
- **Dimension:** 1 / 2 (correctness of the boundary contract; safety-adjacent
  landmine)
- **Severity:** Major
- **Scenario:** verified arithmetic: `countsPerMm = 10/0.8102 = 12.34`;
  `10795 / 12.34 ≈ 875 mm/s ≈ 87 cm/s`. So `WHEELS_X 500 500 0 5000#7` — a
  host passing 0 per motion-api.md §1.1's "pass 0 for the configured
  default" — commands a half-metre move with cruise at the kernel's
  estimated 100 %-duty speed: feedforward alone saturates duty, the PID has
  zero authority, and the taper floors scale off that rail. For calibration:
  the blocks' default is 15 cm/s, the bench tours run 20 cm/s, and
  `test/test.ts:229-230` records that 60 cm/s "was near the drivetrain
  ceiling and produced unusable runs." The wire default is ~1.5× that. This
  *is* deliberate (the function's own comment and `src/DESIGN.md` §5 both
  say full-duty velocity), but the deliberate choice makes the spec's
  friendly-looking sentinel the fastest, least-controlled move the robot
  can make — the wrong thing made easy, on every one of the four verbs.
- **Remedy:** resolve 0 to a real configured default (a settable
  default-cruise config field, or a documented fraction of full-duty —
  e.g. the block layer's `defaultSpeed` equivalent). At absolute minimum,
  flag in the protocol docs that on this robot `0` means full-rail.
  Whichever way, the finding names the code (and DESIGN.md §5 following
  it) as the wrong side, not the wire grammar.
- **Confidence:** high on behavior (both sides traced, defaults confirmed);
  the "is it intended" question is settled — it is intended, and the
  finding is that the intent is a landmine.

### BLK-04 — The zeguz rig's entire numeric RUN vocabulary is dead: the handler stores the argument (always 0), never the numeric name

- **File:** `test/testrig.ts:47-49` (handler), `test/testrig.ts:62-108`
  (`rigExec`); dispatcher semantics at `src/main.ts:157-172`; host side
  `tools/otos_bench.py:5-12` (sends bare `RUN:20`, `RUN:30000+US`, …).
- **Dimension:** 1 (correctness — silent no-op)
- **Severity:** Major
- **Scenario:** under the named-verb dispatch, `RUN:20` arrives as
  `name = "20"` with **no** arguments, so `runArg(0)` is 0. testrig's
  handler is `function (name: string, n: number) { rigPending = n }` — it
  was widened to two parameters (which fixed the compile error the known
  issue reports) but still stores the *argument*, so every rig command
  parks `rigPending = 0` and `rigExec(0)` matches no branch. Every command
  in the file's own vocabulary table — OTOS probe/zero/stream/cal, servo
  pulses, drum speed, lever-arm offsets — is a silent no-op: no reply line,
  no motion, nothing. The rig harness compiles and is completely
  non-functional. This is a **new fact** on top of
  `clasi/issues/testfiles-are-not-type-checked-testrig-is-broken.md`,
  which covers only the (now-fixed) type error and the deploy-env build
  divergence; that issue's TS2345 claim is stale against current source.
- **Remedy:** `rigPending = parseFloat(name)` (with a NaN guard), or
  convert the rig to named `onRun("...")` verbs as the issue's own
  what-to-do #1 suggests. Append this fact to the existing issue rather
  than opening a second one.
- **Confidence:** high (dispatcher, handler, and host sender all traced).

### BLK-05 — Continuous-mode driving never updates odometry until a pose read, which then integrates one giant chord: pose x/y grossly wrong after any curved drive

- **File:** `src/shims.cpp:213-233` (`odomUpdate` — single midpoint-heading
  chord over the *entire* accumulated delta), gated at
  `src/shims.cpp:421-424` (`updateMove`: only while a move is active) and
  `src/shims.cpp:466-469` (`tickDrive`: same gate).
- **Dimension:** 1 (correctness — unit/kinematics at the boundary)
- **Severity:** Major
- **Scenario:** position-mode moves update odometry every tick, but
  continuous-mode driving (`setWheelSpeeds`/`driveTwist` + a
  `while (diffDrive.driveTick())` loop — UC-002 exactly) updates it only
  when the student happens to read `poseX/poseY/heading`. `odomUpdate`
  integrates whatever has accumulated as *one* straight chord at the
  midpoint heading. Heading comes out right (path-independent), x/y do
  not. Concrete: `driveTwist(15, 90)` ticked for ~4 s is a full 360°
  circle of radius R ≈ 9.5 cm; a first pose read afterwards reports a
  displacement of ≈ 2πR ≈ 60 cm in the direction of the 180°-midpoint
  heading instead of ≈ 0. Any student who drives a curve and then asks
  "where am I?" gets an answer that can be wrong by the entire path
  length; nothing errors.
- **Remedy:** call `odomUpdate(r)` unconditionally in `tickDrive()` (one
  Output snapshot plus trig per 24 ms — cheap, and it makes the "pose is
  always live-updated" claim in UC-009 true), or gate on nonzero applied
  duty rather than `isMoveActive()`.
- **Confidence:** high (all odomUpdate call sites enumerated; no other
  path updates pose during continuous drive; chord-vs-arc error is exact
  math).

### BLK-06 — Simulator `setWheelSpeeds` turns 10× too slowly: stray `/10` in the yaw-rate stand-in

- **File:** `src/main.ts:800-806` (`_setWheels` sim body, the expression at
  804); documented intent at `docs/design/specification.md:213-216`.
- **Dimension:** 1 (correctness — simulator/hardware divergence beyond
  specification.md §5)
- **Severity:** Major
- **Scenario:** `_setWheels` receives mm/s (TS wrapper ×10). Physics — and
  spec §5's own description — say `simYawRate = (right − left) / track` =
  `(right − left) / 115` rad/s. The code computes
  `((right - left) / 10) / 115`, an effective 1150 mm track: yaw rate 10×
  too small. `setWheelSpeeds(-15, 15)` should pivot at ≈ 2.6 rad/s
  (~150 °/s); the simulator turns at ~15 °/s. A UC-016 student
  choreographing differential-wheel turns in the browser ships a program
  that spins 10× faster on hardware. §5 documents only the 115-vs-114.2
  approximation, so this is beyond the documented divergence — and it
  diverges from the spec's own formula, so the code is the wrong side.
  (`driveTwist`'s sim body is correct; only the per-wheel form is broken.)
- **Remedy:** `simYawRate = (right - left) / 115` — delete the `/10`.
- **Confidence:** high (dimensional analysis both ways; wrapper scaling
  verified).

### BLK-07 — Simulator does not latch emergency stop: programs that are dead on hardware run fine in the browser

- **File:** `src/main.ts:908-914` (`_estopAll` = `_stopAll`; `_estopClear`
  empty); documented sim divergences at
  `docs/design/specification.md:224-230` (list omits e-stop entirely).
- **Dimension:** 1 (simulator/hardware divergence beyond spec §5) / 2
- **Severity:** Major
- **Scenario:** on hardware, `emergencyStop()` latches the kernel and every
  subsequent Drive/Move command is *silently* refused until
  `clearEmergencyStop()` (UC-011, which explicitly names
  "forgot to clear" as the classic "why isn't my robot moving" pitfall).
  In the simulator `_estopAll` is just a stop and `_estopClear` is a no-op,
  so `emergencyStop(); ...; setWheelSpeeds(15, 15)` drives happily in the
  browser and does nothing on the robot. The simulator inverts the single
  most-flagged student trap in the use-case doc, and §5 does not document
  the gap. The latch is a command contract, not control-law fidelity — it
  is cheap to model.
- **Remedy:** add a `simEstopped` flag: set in `_estopAll`, cleared in
  `_estopClear`, checked (no-op) in `_setWheels`/`_driveTwist`/`_startMove`;
  add the divergence to §5 if any part is left unmodeled.
- **Confidence:** high (both sides read; §5 checked).

---

## Minor findings (grouped)

- **BLK-08 — `pxt.json:8` dead `microphone` dependency.** Zero references
  to microphone anywhere in `src/` or `test/`. It drags the (V2-only)
  microphone package into every consuming student project; if it exists to
  force V2, `disablesVariants: ["mbdal"]` (pxt.json:47-49) already does
  that. Remedy: delete, or comment why it must stay. *Dimension 2;
  confidence medium (behavioral effect verified; original intent unknown).*
- **BLK-09 — version mirror has actually drifted.** `pxt.json:3` says
  `1.0.10`; `src/protocol.cpp:63` `kVersion` says `"1.0.0"` ("keep in sync
  with pxt.json"). `src/DESIGN.md` §10 records that this *can* drift; it
  has — a wire host's VER/ID reply currently misidentifies the build by
  ten releases. Remedy: bump the constant now; longer-term, generate it.
  *Dimension 2; confidence high.*
- **BLK-10 — `tsconfig.json` cannot type-check its own file set.** Its
  `files` list (lines 11-22) omits `pxt_modules/core/serial.ts`, yet
  `src/main.ts:1016` (`emitLine` sim body) and `test/testrig.ts` call
  `serial.writeLine`, which lives there (not in shims.d.ts). A plain
  `tsc -p .` fails on main.ts itself, so whatever this config was wired
  for (editor/CI) has silently never worked end-to-end. Remedy: add
  serial.ts (and audit for pins/led helpers testFiles use). *Dimension 2;
  confidence high that the set is unresolvable, medium on who consumes it.*
- **BLK-11 — dead/stale seam surfaces in shims.cpp.**
  `driveTwistTimed` (shims.cpp:289-297) has zero callers since the v5→v6
  cutover, yet the file-header contract (shims.cpp:29-36) still names
  protocol.cpp as its caller; `wheelSpeed` (shims.cpp:935-943) has zero
  callers though DESIGN.md §9 lists it as a wire bridge; `moving()`
  (shims.cpp:639-640) is `//%`-annotated with **no** TS declaration —
  `isMoving()` deliberately maps to `updateMove` instead, so a future
  "obvious" rewiring of isMoving→moving would silently change poll
  semantics (see BLK-01); `_cycleStat` (main.ts:875-884) is unexported and
  uncalled on the TS side. Remedy: delete or wire up each, and fix the
  stale caller lists. *Dimension 2/3; confidence high (grepped src, test,
  tests, tools).*
- **BLK-12 — `isMoving()`/`moveProgress()` doc comments are false.** Both
  claim "checks state only — it does not itself advance the move"
  (main.ts:309-331), but they map to `updateMove()` → `serviceMove()`,
  which re-issues `kernel.drive()` with a fresh 500 ms lease, rescales the
  taper, and can *end* the move at the deadline (shims.cpp:415-425,
  motion_engine.cpp:290-296). Students reading the source get a wrong
  model, and the mislabeled side effect is the substrate of BLK-01(b).
  Remedy: either make the doc true (bind to `moving()`) or make it honest.
  *Dimension 5/1; confidence high.*
- **BLK-13 — `diagValue` case 25 interleaved into the 23/24 block.**
  `src/shims.cpp:709-712`: the comment "// 23/24: rejected implausible
  encoder reads" is immediately followed by `case 25`, then cases 23/24.
  Functionally fine; a reader trap in the file students are pointed at for
  the probe index list. Remedy: reorder. *Dimension 5.*
- **BLK-14 — private-convention names on a public surface.**
  `ensure().left.maxDrivenStreak_` / `.glitchCount_`
  (src/shims.cpp:707-712) read trailing-underscore ("private by
  convention") members across class boundaries. Either they are API — then
  drop the underscore or add accessors — or they are not, and diagValue
  should go through one. *Dimension 5.*
- **BLK-15 — sim `moveProgress()` is a constant.** `_progress()`
  (main.ts:886-890) returns 500 while any move is active, so browser
  `moveProgress()` is always 0.5 then 1.0; `simMoveRemainMm/Rad` are
  sitting right there to compute a real fraction. Spec §5's "mirrors the
  contract" is generous. *Dimension 1 (sim fidelity); Minor.*

---

## Not findings

Suspicious-looking things checked and cleared:

- **Shim-signature sweep (done exhaustively): all 31 `//% shim=diffDrive::*`
  declarations in main.ts pair exactly** — name, arity, parameter and
  return types — with `//%` C++ definitions (30 in shims.cpp;
  `startProtocol` in protocol.cpp:321-322, annotation adjacency correct).
  `ConfigField` 0-14 matches both `setKernelValue` and `getConfigValue`
  switches 1:1 (incl. 8→vMin, 13→lambdaEnabled). No mismatches.
- **Forward-declaration sweep:** every same-package forward declaration in
  wire_adapter.cpp (stopAll, estopAll, setWheelsTimed, setKernelValue,
  getConfigValue, diagValue, engineWheelsX/MoveX/DefaultCruiseMmS/MoveV/
  GoToR/GoToW) and protocol.cpp (`bool tickDrive()`) is
  signature-identical to its shims.cpp definition; the reverse-direction
  pair (protocolEmitLine/protocolRunText) matches protocol.cpp.
- **Unit-ladder audit TS↔C++: clean.** cm→mm ×10, deg→cdeg ×100 (speeds
  likewise), track cm→0.1 mm ×100 → ×0.1, calib mm/deg ×10000 → ×1e-4,
  config ×1000 both directions, seedPose mm/cdeg, OTOS offset 0.1 mm/cdeg,
  worldX/Y (0.1 mm → cm /100) and worldHeading (cdeg/100) all verified
  correct, as are goTo/goToWorld's arc chord/bearing math and `face`'s
  ±180° wrap normalization.
- **RUN slot plumbing:** event value is slot+1; `runText` accepts 1..4 and
  returns "" (never nullptr) out of range, so `runCommandText`'s strlen
  loop is safe.
- **Seeded lead 3 (settle loop internals):** no new defect *inside* the
  loop body — kRest 25 counts/s ≈ 2 mm/s checks out; the watchdog cannot
  fire mid-settle (first settle step applies the neutral, so
  `commandLooksActive()` is false even though `lastTickUs` goes stale for
  ~120 ms); `stepBusy` is held throughout. The new defect is the bypass
  *around* the loop (BLK-01). Testability itself: covered by
  `clasi/issues/settle-tick-loop-is-not-host-testable.md`, not re-reported.
- **`startMove`'s dual-rate→single-cruise algebra** (shims.cpp:350-412)
  reproduces the legacy duration for arbitrary distance/yaw combinations;
  zero/zero returns early per UC-003; negative `speed`/`yawRate` are
  clamped to 1 before division (and the TS layer clamps defaults to ≥ 1).
- **The no-initialiser `run*` array pattern holds:** nothing re-initialises
  those arrays after a test file's top-level registration; the initialised
  namespace variables (defaultSpeed, sim state, goToWorld tunables) are
  not touched by any test file's top-level code.
- **`emitLine`'s 200-byte cap** vs the 240-byte line ceiling: real, but
  already documented in `src/DESIGN.md` §8 — not re-reported.
- **testrig servo/lever-arm ranges and conversions** (pulse 500..2500 via
  30500..32500; mm→cm /10 into `setWorldSensorOffset`) are correct;
  `tickedMove`'s duplication in test.ts is deliberate visible-test-code
  style.
- **GO_TO_W with no OTOS refuses honestly** (engineGoToW → false →
  kUnimplemented) — matches
  `clasi/issues/no-encoder-odometry-posesource-fallback.md`; nothing new.
- **pxt.json files list** matches `src/` exactly (all 22 build inputs; no
  strays); testFiles matches `test/`. Both testFiles compile into one test
  program — they coexist without conflict today (testrig's numeric-verb
  deadness aside, BLK-04); the build-path divergence half of that story is
  the known testfiles issue's territory.
- **Known-issue staleness noted in passing:** the TS2345 error quoted in
  `testfiles-are-not-type-checked-testrig-is-broken.md` no longer exists
  in source (handler already two-arg) — the issue's remaining substance is
  the deploy-env divergence plus BLK-04's new fact.
- **Dedup honored:** main.ts size/modularity (break-up-main-ts-into-modules
  — CLAIMED), telemetry absence and radio-RX scope (sprints 004/005,
  planned-not-built), unpowered-brick boot wedge, OTOS/goToWorld tour
  accuracy — none re-reported.
