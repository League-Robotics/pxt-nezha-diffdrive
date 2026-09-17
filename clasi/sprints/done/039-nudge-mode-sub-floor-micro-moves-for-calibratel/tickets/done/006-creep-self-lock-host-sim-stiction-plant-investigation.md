---
id: '006'
title: 'Creep self-lock: host-sim stiction plant investigation'
status: done
use-cases:
- SUC-004
depends-on: []
github-issue: ''
issue: slow-continuous-creep-self-locks-below-breakaway.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Creep self-lock: host-sim stiction plant investigation

## Description

Independent of the nudge-mode work (tickets 001-005) — a slow
continuous hold (`whileDriving`/`setWheelSpeeds` at a few cm/s, driven
below breakaway) appears to self-lock: the wheel is driven every tick
but its raw encoder count never advances, and the robot never moves,
until the caller's own timeout.

**Now backed by a real capture**, not just the peer's report:
`captures/calibratel-vevov-20260915/bench-log.md` run 5 — reverse
sweep at -4 cm/s for 30 s (its own 30 s time limit), serial link:
`i2cf` 1247 -> 2493 (delta 1246) over `cyc` 1414 -> 2666 (delta 1252),
camera frame `after-back2.jpg` showing the robot unmoved. `i2cf` ~=
`cyc` over the whole sweep is the signature the issue describes: the
wheel is driven on essentially every tick but its sample never
advances. (Applied duty was never captured this session — `TLM FULL`
was not enabled — so the duty-level claim in the issue's source
reading is still UNVERIFIED; this ticket's own investigation should
close that gap on the host-sim side, and flag it for a hardware
`TLM FULL` capture if the sim needs one to confirm.)

**Suspected mechanism** (source reading, `src/core/diffdrive.cpp:977`
area — READ ONLY, do not edit): K2 does not integrate `PositionRef` on
a tick whose sample did not advance, so the I-term (`ki` 6) never
winds up enough to overcome static breakaway; feedforward alone
(~0.5% duty at 40 mm/s) sits below the port's 3% output deadband.
Nothing else rescues it: the continuous-hold path passes floor 0 to
the shaper (`motion_engine.cpp:397`), and `stallDemand` (~400 mm/s
equivalent) never arms at creep speed.

## Scope

1. Build a host-sim stiction plant (fake motor: zero velocity below a
   breakaway duty threshold, quantized increments above), driven
   through the same continuous-hold path `wheelsV()`/`moveV()` use.
2. Reproduce the suspected lock in the sim: confirm (or refute) that a
   driven-but-frozen tick blocks I-term windup the way the source
   reading predicts.
3. Recommend a fix location. Implement it **only if it is
   `MotionEngine`-level and small** — e.g., a floor or breakaway
   allowance for a continuous `Hold` (today it passes floor 0,
   `motion_engine.cpp:397`). Do not patch
   `src/core/diffdrive.{h,cpp}` — that needs the paired-upstream-patch
   process or an explicit stakeholder decision
   (`.claude/rules/fiber-yield-safety.md`'s "Related invariants"),
   neither of which this ticket is positioned to produce.
4. `crawl_pulse` is not a known-good fix for this — it made end-of-leg
   stalls worse on tovez
   (`captures/tovez-taper-20260829/variants.json`). Creep is a
   different use case, but treat that measurement as prior evidence
   against reaching for the same knob without a fresh test.

## Result

**Confirmed in sim; no safe `MotionEngine`-level fix exists. Closes as
a documented recommendation with a follow-up issue
(`clasi/issues/creep-self-lock-needs-a-k2-patch-or-a-stakeholder-
decision.md`), per this sprint's own stated fallback for this
ticket.**

### The sim (`tests/host/test_creep_self_lock_stiction_sim.py`, 3 tests)

Extended ticket 004's own `StictionMotor`
(`tests/host/motion_engine_nudge_stiction_shim.cpp`) with a
`withholdStampOnStiction` mode (default false — every ticket 004 test
is byte-for-byte unaffected) that mirrors
`NezhaMotorPort::collect()`'s real stamp-withholding behavior
(`src/platform/nezha_port.cpp:391-406`, READ ONLY): a driven-but-
frozen tick withholds the sample stamp instead of always advancing it.
Without this, the shim CANNOT reproduce the lock — ticket 004's
original model advances the stamp every tick regardless of physical
motion, which keeps K2's `advanced` gate permanently open and would
mask the very mechanism under test. Drove `wheelsV()` (the continuous-
hold primitive) through the same real kernel via new exported entry
points (`mnWheelsV`/`mnMoveV`/`mnIsDriving`/`mnOutVelocity*`/
`mnOutAppliedDuty*`/`mnOutI2cFaultCount`/`mnSetVFloor`/`mnSetVMax`/
`mnConfigureCreepPlant`).

Stiction plant parameters, documented (not tuned to fit): breakaway
duty 15% is THIS SPRINT's own measured value for what reliably breaks
a wheel loose (`captures/039-003-pulse-gate-20260916/notes.md`, ticket
003's GO gate); the commanded creep (-40 mm/s) matches the bench-log
capture's own commanded speed; `fullDutyVelocity` (80000 counts/s) is
picked so that creep's feedforward-only duty lands at ~0.5%, the
issue's own cited source-reading figure — not reverse-engineered from
a desired result. `ki=6` is the issue's own cited value.

1. **`test_creep_below_breakaway_self_locks_with_stamp_withholding`
   CONFIRMS the K2 lock**: with stamp-withholding armed, the wheel
   never clears breakaway for the whole 30 s / 1250-tick hold, duty
   stays flat at feedforward, and `i2cFaultCount` tracks `cycleCount`
   almost exactly — the same shape
   `captures/calibratel-vevov-20260915/bench-log.md` run 5 shows
   (`i2cf` 1247 -> 2493 / delta 1246 over `cyc` 1414 -> 2666 / delta
   1252, camera frame `after-back2.jpg` unmoved). Cited exactly, not
   re-derived; this ticket's own sim numbers are SIM RESULTS, not a
   hardware measurement, and are labeled as such throughout the test
   file.
2. **`test_creep_recovers_when_stamp_is_not_withheld` is the
   refutation control**: identical rig, identical creep, identical
   breakaway — the ONE change is stamp-withholding off, so K2's
   `advanced` gate is always true. The I-term winds up and the wheel
   breaks free well inside the 30 s window. This isolates the lock to
   K2's guard specifically, not the plant, gains, or shaper.
3. **`test_hold_vfloor_value_has_no_effect_on_commanded_ramp` rules out
   the sprint plan's own suggested candidate location.** The Hold
   branch of `MotionEngine::service()` hardcodes `remain = -1.0f` in
   its `shaper_.advance()` call (`src/motion/motion_engine.cpp:397`
   area). `VelocityShaper::advance()`'s floor-snap step is gated on
   `remain >= 0.0f` (`src/motion/velocity_shaper.cpp`, step 4), so the
   `floor` VALUE passed there (today `0.0f`) is provably inert for a
   continuous hold — three otherwise-identical runs with
   `limits().vFloor` at 0/70/250 mm/s produce BIT-IDENTICAL per-tick
   duty trajectories. Changing the floor value, the literal fix the
   sprint plan names, fixes nothing.

   Making a floor genuinely apply to a Hold would need a structural
   change (e.g. a large `remain` sentinel instead of `-1.0f`), and
   that would reverse a DELIBERATE, PINNED design decision from an
   earlier sprint:
   `tests/host/test_velocity_shaper.py::
   test_continuous_hold_has_no_floor_and_never_arrives` (sprint 029
   ticket 002) asserts the opposite as intentional — "a continuous
   hold below the floor is a legitimate request, e.g. a student's own
   slow WHEELS_V". This ticket has no standing to reverse that
   decision, so no such change was made.

### Recommendation

No safe, small `MotionEngine`-level fix exists that makes the wheel
actually move: the one candidate the sprint plan named is a dead
parameter as literally described, and the structurally-real version of
that candidate contradicts a pinned cross-sprint design decision this
ticket cannot unilaterally override. The only mechanism that would
make a sub-breakaway creep move lives inside K2
(`src/core/diffdrive.cpp:955-991`) — vendored, out of scope per this
ticket's own constraint (needs the paired-upstream-patch process or an
explicit stakeholder decision). Filed as
`clasi/issues/creep-self-lock-needs-a-k2-patch-or-a-stakeholder-
decision.md`, which also notes a smaller, non-K2, non-floor candidate
worth scoping separately if wanted: a Hold-specific no-progress
detector that ends a self-locked hold and reports it (rather than
silently spinning to the caller's own timeout), distinct from the
kernel's own `stallDemand` (which never arms at creep speed). Not
implemented here, to keep this ticket's own fix scope to "only where
one is safe and small" — a new failure-reporting behavior is a
legitimate but separate design decision, not something to slip in
alongside an investigation ticket.

## Acceptance Criteria

- [x] A host-sim stiction plant exists, testable in isolation, and its
      breakaway/quantization parameters are documented (not tuned to
      make a predetermined conclusion true). **DONE** — see "The sim"
      above; `tests/host/motion_engine_nudge_stiction_shim.cpp`'s
      `StictionMotor`, extended.
- [x] The sim either confirms or refutes the suspected K2 lock
      mechanism, with the host-sim run itself as the artifact (a host
      test, not a captured hardware run). **DONE, CONFIRMS** — see
      "The sim" above, tests 1 and 2.
- [x] `captures/calibratel-vevov-20260915/bench-log.md` run 5's
      i2cf/cyc numbers are cited as the hardware anchor exactly as
      given above — cite the artifact, do not re-derive or round the
      numbers from memory (`.claude/rules/measurement-citations.md`).
      **DONE** — cited verbatim in this ticket, the follow-up issue,
      and the test file's own module docstring.
- [x] A written recommendation exists regardless of outcome: either a
      landed `MotionEngine`-level fix with a host-sim regression test,
      or a documented "needs a kernel patch, needs a stakeholder
      decision" conclusion with a follow-up issue filed. **DONE, second
      branch** — see "Recommendation" above and
      `clasi/issues/creep-self-lock-needs-a-k2-patch-or-a-stakeholder-
      decision.md`.
- [x] No edit to `src/core/diffdrive.{h,cpp}`. **DONE** — confirmed by
      `git diff --stat` at close; only `tests/host/` and `clasi/`
      files touched.

## Testing

- **Existing tests to run**: `MotionEngine` continuous-hold host
  suites (`wheelsV`/`moveV` paths).
- **New tests to write**: the stiction-plant sim itself, plus (if a fix
  lands) a regression test pinning the fix's behavior against the sim.
- **Verification command**: the project's host test runner, scoped to
  touched modules. No hardware run is required for this ticket — the
  bench-log capture already anchors it; a fresh `TLM FULL` hardware
  capture is a candidate follow-up only if the sim result is
  ambiguous.
