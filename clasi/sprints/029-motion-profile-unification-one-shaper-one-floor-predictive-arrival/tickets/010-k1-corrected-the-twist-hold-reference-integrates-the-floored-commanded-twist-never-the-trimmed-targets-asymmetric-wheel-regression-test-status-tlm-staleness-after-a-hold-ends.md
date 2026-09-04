---
id: '010'
title: 'K1 corrected: the twist-hold reference integrates the floored commanded twist,
  never the trimmed targets; asymmetric-wheel regression test; STATUS/TLM staleness
  after a hold ends'
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ['009']
github-issue: ''
issue: kernel-reference-handling-twist-floor-stale-tick-antiwindup.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# K1 corrected: the twist-hold reference integrates the floored commanded twist, never the trimmed targets; asymmetric-wheel regression test; STATUS/TLM staleness after a hold ends

## Description

**Hardware finding.** Ticket 007's 2026-09-04c bench session on tovez
(`reports/bench-acceptance-029-20260904c.md` §6, `captures/bench-acceptance-029-20260904c/`)
found G5 (continuous `WHEELS_V`) fails with a serious control-loop
defect: `WHEELS_V 200 200 2000` from rest, both wheels commanded
identically, produced a **negative** measured left-wheel velocity
(settled ~-76 mm/s, with negative commanded duty -- the controller
drove that wheel backward while commanded forward) and a **492 mm/s**
right-wheel overshoot against the gate's 210 mm/s ceiling. This is not
a telemetry-freeze artifact -- the trace updates live, tick to tick,
and the camera independently corroborates real (if confusing)
displacement, moving tovez to within 1.4 cm of the field's safety
margin before an `ESTOP` was sent (report §6, `emergency-estop-2.log`).
The same session's G1 (12x alternating 90 deg pivots) shows a
systematic, direction-dependent bias (mean|error| 8.13 deg vs the 0.5
deg bar, every +90 deg pivot undershooting, every -90 deg pivot
overshooting -- report §5) consistent with the same underlying
mechanism running during pivots too, not just the continuous hold.

**The code defect.** `src/core/diffdrive.cpp` line ~661:

```cpp
if (twistHoldActive && dt > 0.0f) {
  twistRef_.reference += 0.5f * (speedRight - speedLeft) * dt;
}
```

`speedLeft`/`speedRight` here are the outputs of `applySpeedFloor()`
(line ~649, `applySpeedFloor(targetLeft, targetRight, speedLeft,
speedRight)`), and `targetLeft`/`targetRight` (lines ~645-646) are
`scaledLeft - trim` / `scaledRight + trim` -- i.e. the twist-hold
servo's own `trim` output has already been folded into the values this
line integrates as the reference. The servo's output feeds its own
reference: on a straight command with any wheel asymmetry, a real
`trim` correction on tick N changes `speedLeft`/`speedRight`, which
changes `twistRef_.reference` on that same tick, which changes the
`twistError` computed against it on tick N+1, closing a positive-
feedback loop that ideal (perfectly matched) wheels never excite
because `trim` stays near zero for them. This is exactly the design
K1 row's own account of the defect
(`docs/design/motion-profile-unification.md` §4.5, "Corrected
2026-09-04" text): "the first landing integrated
`0.5*(speedRight - speedLeft)` of the floored *targets*, which include
`+/-trim` -- the servo's own output fed its reference, a positive-
feedback loop that ideal wheels never excite."

**Host-model evidence.** `docs/code-review/2026-09-02/raw/twist_runaway_probe.cpp`
/ `.out`: with a 5% right-wheel gain mismatch and an 80 ms lag model,
`twistHoldGain 0` (servo off) on `moveX(600, 0, 200)` ends at heading
+0.8 deg over the 600 mm straight; `twistHoldGain 2` (servo on, the
defect as landed) ends at **-6.2 deg** -- the servo makes the straight
*worse* than not running it at all, destabilizing instead of holding.
The `WHEELS_V 200 200` case in the same probe shows the same
direction: heading +0.8 deg servo-off vs -1.7 deg servo-on over 1.9 s,
i.e. the servo overcorrects past zero. This is the servo actively
diverging under a wheel mismatch it exists to correct for -- it
plausibly explains both the G5 continuous-hold sign reversal/overshoot
and the G1 pivot CW/CCW asymmetry, since both are continuous
twist-hold operation under whatever real per-wheel asymmetry tovez has
(the same session's `lag` measurement independently found the two
wheels do not even share a control law -- report §3 -- so "some real
per-wheel mismatch exists" is not in doubt, only its magnitude).

**The corrected design** (K1 row, `docs/design/motion-profile-unification.md`
§4.5): `applySpeedFloor()` reports the scale factor it applied
(`floorScale`, 1.0 when the floor does not bind), and the reference
integrates `scaledTwist * floorScale * dt` -- the floored *commanded*
twist -- never the trimmed targets. With `vMin = 0` (this design's own
fleet bake, K5) the floor never binds in practice and `floorScale` is
always 1.0, so this reduces to integrating `scaledTwist * dt`, i.e.
`0.5f * (scaledRight - scaledLeft) * dt` computed from `scaledLeft`/
`scaledRight` (lines ~609-610, before `trim` is ever subtracted/added)
-- textually the same line the pre-K1-patch kernel had. The design
text states this explicitly: "With `vMin = 0` the corrected form
reduces to the original pre-patch line, which was right."

**Second item, investigate-and-fix: telemetry staleness after a hold
ends.** The same 2026-09-04c session independently confirmed (not just
hypothesized, as in the earlier 2026-09-04b diagnostic session) a
distinct bug: after a `WHEELS_V`/G5 hold ended (ESTOP or deadline),
`STATUS`'s `active` bit and `TLM`'s per-tick fields (`vl vr dutl dutr x
y h`) stayed at their last real value for 100+ seconds while
`cyc`/`seq`/`now` kept advancing normally, even though the robot was
independently confirmed at rest by camera (report §8,
`session-end.log`). This is a **different** bug from the G5
control-loop defect above -- keep the two separate. Candidates to
check, per the report's own "what a human needs to do next" list and
this sprint's own architecture (`docs/design/motion-profile-unification.md`
§6, `src/DESIGN.md` §11 build-checkpoint conventions apply to the
motion/comms modules touched here):
- `MotionEngine::isDriving()` / `isMoveActive()` vs the kernel's
  `hold_.active` state after `endMove()`, an ESTOP, or a deadline
  (ticket 003 added `isDriving()` when it wired in the shaper --
  confirm it and `hold_.active` agree once a hold ends, not just while
  one is running).
- `engineMoveActive()` in `src/shims.cpp` -- whether it reads a cached
  or stale value once the engine reports not-driving.
- `WireAdapter::buildSnapshot()` / `computeFlags()` in
  `src/comms/wire_adapter.cpp` -- whether the snapshot is only
  refreshed while a move is considered active, so a `STATUS`/`TLM`
  call after the last "real" tick reads a cached snapshot instead of
  the kernel's actual current state.
- Whether the kernel is still being stepped at all after the hold ends
  (the wire obligation every tick relies on) -- if the fiber that ticks
  `kernel.step()` stops being invoked once the engine goes idle, the
  *kernel's* own state genuinely freezes even though `cyc`/`seq`/`now`
  (which may be driven by a different, still-running fiber) keep
  moving.

Fix what is found. If nothing is wrong in the reviewed code, reproduce
the staleness with a host test that steps the wire adapter through a
`WHEELS_V` command to its deadline and reads `STATUS`/`TLM` afterward,
and report what the host model shows (a host-only repro that does
*not* reproduce the bug is itself useful information -- it would mean
the defect is specific to a codepath the host harness doesn't
exercise, e.g. genuine radio/link timing, and that finding belongs in
this ticket's session notes either way).

## Acceptance Criteria

- [ ] `applySpeedFloor()` returns or otherwise records the scale factor
      it applied (`floorScale`), 1.0 when the floor does not bind.
- [ ] The twist-hold reference integration at `src/core/diffdrive.cpp`
      (~line 661) integrates `scaledTwist * floorScale * dt` and NOT
      the post-floor trimmed targets (`speedLeft`/`speedRight` as
      currently used) -- i.e. it is computed from `scaledLeft`/
      `scaledRight` (or an equivalent pre-trim quantity), never from
      values `trim` has already been folded into.
- [ ] A host test in `tests/host/test_kernel_reference_handling.py`
      exercises the twist-hold servo ON with an asymmetric wheel gain
      (right wheel +5%) and a lag model (port the model from
      `docs/code-review/2026-09-02/raw/twist_runaway_probe.cpp`) on
      both `wheelsV(200, 200)` and `moveX(600, 0, 200)`, and asserts:
      (a) the heading drift with the servo ON is smaller in magnitude
      than with the servo OFF (the servo must help, not hurt), and
      (b) the heading never diverges (drift stays bounded across the
      run, no runaway growth tick to tick).
- [ ] K1's existing floored-pivot host test (from ticket 001, the
      -11% reverse-duty / 1.9 deg-short-vs-2.5 deg-long regression
      cited in the design's original K1 row) still passes unchanged --
      this fix must not reopen the defect K1 originally closed.
- [ ] `twist_runaway_probe`'s ideal-wheel numbers (gain = 1.0, no
      asymmetry) are unchanged by this fix -- the defect and its fix
      are specific to the asymmetric case.
- [ ] The upstream kernel patch file
      `docs/code-review/2026-09-02/raw/kernel-patches-k1-k4.upstream.patch`
      is regenerated against the corrected K1 patch (this kernel file
      is vendored -- see `.claude/rules/fiber-yield-safety.md`'s
      "Related invariants" section and
      `clasi/sprints/029-motion-profile-unification-one-shaper-one-floor-predictive-arrival/issues/done/decide-the-kernel-fork.md`
      for the paired-tree editing convention this repo has already
      adopted for K1-K4).
- [ ] The design's K1 row (`docs/design/motion-profile-unification.md`
      §4.5) and `src/DESIGN.md` §2's patch description are updated to
      describe the corrected integration (they already contain the
      "Corrected 2026-09-04" narrative describing the intended fix --
      confirm the final code matches that text once implemented, and
      tighten the wording if the implementation reveals any deviation
      from what that paragraph currently says).
- [ ] `STATUS`'s `active` bit and `TLM`'s per-tick fields read fresh
      (not stale) after a hold ends, verified by a host test driving
      the wire adapter through a `WHEELS_V` command to its deadline (or
      an explicit stop) and reading `STATUS`/`TLM` afterward. Root
      cause (or, if not reproducible on the host model, that finding)
      is written up in this ticket's session notes.
- [ ] Identifier naming in any new or touched code follows
      `.claude/rules/no-units-in-identifiers.md` (unit in a trailing
      `// [unit]` comment, never in the name).
- [ ] Scoped test run for this ticket's touched modules is green:
      `uv run pytest tests/host/ -q --deselect tests/host/test_typescript_typecheck.py::test_tsc_noemit_is_clean`
      (per `.claude/rules/source-code.md`, the full suite runs once at
      `close_sprint`, not per ticket).

## Implementation Plan

**Approach**: Fix the K1 integration line first (small, well-scoped --
change what the reference integrates, not the servo's control law
itself), prove it against the ported asymmetric-wheel host model, then
confirm the existing K1 regression test and the ideal-wheel probe
numbers are unaffected. Investigate the telemetry-staleness bug as a
separate, second pass through the motion-engine/wire-adapter call
chain listed above; treat it as its own root-cause writeup even if the
fix ends up being a one-line change, since the report explicitly warns
against conflating it with the G5 control-loop defect.

**Files to create/modify**:
- `src/core/diffdrive.h` / `src/core/diffdrive.cpp` -- `applySpeedFloor()`
  scale reporting; the K1 reference-integration line.
- `tests/host/test_kernel_reference_handling.py` -- new asymmetric-wheel
  regression test (servo-on vs servo-off comparison); confirm the
  existing K1 pivot regression test here still passes.
- `tests/host/kernel_shim.cpp` -- add a host-visible accessor if the
  corrected integration needs one exposed for the test (e.g. reading
  `floorScale` or the reference directly), following the same pattern
  used for K1-K4's original host tests.
- `tests/host/test_profile_probe.py` -- port the asymmetric-gain +
  lag model from `docs/code-review/2026-09-02/raw/twist_runaway_probe.cpp`
  if that host-model logic belongs alongside the existing lagged-wheel
  probe tests (design §6.3's citation lives here) rather than solely
  in the new `test_kernel_reference_handling.py` file -- use judgment
  on which file owns the model, but do not duplicate it in both.
- `src/motion/motion_engine.h` / `.cpp`, `src/shims.cpp`,
  `src/comms/wire_adapter.cpp` -- only if the telemetry-staleness root
  cause is found to land in one of these; do not touch speculatively.
- `tests/host/test_wire_telemetry_frame.py` / `test_wire_motion_verbs.py`
  -- the staleness-after-a-hold-ends host test; add to whichever file
  already covers `STATUS`/`TLM` after a completed move, or create a
  new one if neither fits.
- `docs/code-review/2026-09-02/raw/kernel-patches-k1-k4.upstream.patch`
  -- regenerated diff.
- `src/DESIGN.md` -- confirm/tighten the K1 patch description.

**Testing plan**: New asymmetric-wheel regression test in
`tests/host/test_kernel_reference_handling.py` (servo-on-must-beat-
servo-off, no divergence); rerun the existing K1 floored-pivot test and
`twist_runaway_probe`'s ideal-wheel case to confirm no regression; new
host test for STATUS/TLM freshness after a hold ends; scoped
`tests/host/` run per this ticket's acceptance criteria.

**Documentation updates**: `docs/design/motion-profile-unification.md`
§4.5 K1 row and `src/DESIGN.md` §2, per the acceptance criteria above.
Session notes on the telemetry-staleness investigation's outcome
(fixed, or host-model could not reproduce it).
