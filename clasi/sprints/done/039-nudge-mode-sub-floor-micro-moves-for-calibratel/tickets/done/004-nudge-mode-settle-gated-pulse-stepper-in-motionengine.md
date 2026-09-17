---
id: '004'
title: 'Nudge mode: settle-gated pulse stepper in MotionEngine'
status: done
use-cases:
- SUC-002
depends-on:
- '003'
github-issue: ''
issue: nudge-mode-settle-gated-pulse-stepper-for-sub-floor-micro-moves.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Nudge mode: settle-gated pulse stepper in MotionEngine

## Description

**Proceeds only if ticket 003 returned GO.** If ticket 003 was NO-GO,
do not start this ticket — see `sprint.md`'s NO-GO fallback note.

Build the settle-gated stepper on top of ticket 001's pulse primitive,
using ticket 003's accepted (amplitude, width) cell(s) as the default
config values:

1. New engine state (a struct alongside `Segment`/`Hold` in
   `MotionEngine`, e.g. `Nudge`), holding a target (distance and/or
   rotation, converted to counts exactly as `beginSegment()` does) and
   a pulse budget/deadline.
2. Loop, ticked from `service()` (or a parallel path — decide based on
   whether reusing `service()`'s single dispatch point is cleaner than
   adding a second one; either way, exactly one of seg_/hold_/nudge_
   is ever live, matching the existing "exactly one of seg_/hold_"
   invariant in `motion_engine.h`):
   - If both wheels read at rest (reuse `settleToRest()`'s rest test)
     and remaining error (re-read from encoder counts, not carried
     state) exceeds margin: fire one pulse via ticket 001's primitive,
     straight (`driveDuty(±A, ±A)`) or pivot (`driveDuty(±A, ∓A)`).
   - Otherwise: stage zero, wait.
   - Terminate on margin, deadline, or the pulse budget (raw-duty mode
     updates no stall latch, so this IS the runaway backstop — keep it
     conservative, ~40 pulses per the issue's own suggestion).
3. Per-wheel asymmetry: use ticket 003's measured per-wheel increments,
   not a fixed 50/50 split, if ticket 003 found a meaningful
   difference.
4. Direction flips pay exactly one reversal dwell (the port already
   handles this, `nezha_port.cpp:236-250`) — do not add a second
   dwell of your own; the settle gate should absorb it naturally.
5. New config fields via the single-source table
   (`src/comms/config_fields.h`): nudge amplitude (duty %), nudge
   width (ticks), nudge settle time (ms). Use the next free ordinals
   (40, 41, 42 — the table's highest live ordinal is 39
   `GoToTimeout`; the retired gaps 22-27/29/31 are never reused, per
   the table's own header comment). Re-run
   `tools/gen_config_field_enum.py` and commit its output;
   `tests/tools/test_gen_config_field_enum.py` and
   `tests/host/test_config_surface_single_source.py` both fail the
   build on any mismatch.

## Acceptance Criteria

- [x] A host test with a fake motor + stiction model (no motion below a
      breakaway duty, quantized increments above) pins: pulses fire
      only when settled; the remaining-error ledger re-reads from
      encoder counts and converges; the pulse budget and the deadline
      both terminate the loop independently; a direction flip pays
      exactly one reversal dwell. **DONE** —
      `tests/host/test_motion_engine_nudge_stiction.py`, over a
      dedicated `StictionMotor` double
      (`tests/host/motion_engine_nudge_stiction_shim.cpp`); the
      encoder-velocity half of "fires only when settled" is additionally
      pinned against a plain `FakeMotor` in
      `tests/host/test_motion_engine_nudge.py`.
- [x] The three new config fields are reachable via `GET`/`SET`, with
      the generator re-run and its test passing. **DONE** —
      `nudge_amplitude`/`nudge_width`/`nudge_settle`, ordinals 40-42,
      `src/comms/config_fields.h`; `tools/gen_config_field_enum.py`
      re-run and `src/blocks/motion.ts` committed;
      `tests/tools/test_gen_config_field_enum.py` and
      `tests/host/test_config_surface_single_source.py` both pass.
- [x] No edit to `src/core/diffdrive.{h,cpp}`. **DONE** — confirmed via
      `git status`, neither file appears in this ticket's diff.
- [x] Any new yield point goes through
      `vfpSafeSleep()`/`vfpSafeYield()`. **DONE** — no new yield point:
      `serviceNudge()`'s only sleeps are inside `firePulseAndSettle()`'s
      reused `kernel.step()`/`settleToRest()` calls, already
      VFP-guarded (same as `pulseWheels()`, ticket 001).
- [x] No unit suffix in any new identifier
      (`.claude/rules/no-units-in-identifiers.md`). **DONE** —
      `tests/host/test_no_units_in_identifiers_source_pin.py` passes;
      `nudgeSettle()` (not `nudgeSettleMs()`) and `lastDistStep`/
      `lastYawStep` (not `...StepCounts`) were renamed during
      implementation to hold this.
- [x] E-stop and lease expiry still force neutral mid-nudge (inherited
      from `driveDuty()`, confirm with a host test rather than assuming
      it). **DONE** —
      `test_motion_engine_nudge.py::test_estop_before_begin_nudge_ends_it_on_the_first_service_call_with_no_duty`
      and `::test_estop_mid_nudge_ends_it_promptly_without_a_further_pulse`
      call `kernel.estop()` directly (never through anything resembling
      `estopAll()`'s ordering, matching
      `test_motion_engine_estop_and_refusal.py`'s own precedent). Lease
      expiry is inherited via the identical re-arm-every-iteration
      `firePulseAndSettle()` code path `pulseWheels()` already uses and
      ticket 001 already tests directly — not re-tested here since
      nothing in this ticket touches that mechanism.

## Testing

- **Existing tests to run**: `MotionEngine`/`Rig` host suites, plus
  `test_config_surface_single_source.py` and
  `test_gen_config_field_enum.py`. **RUN** — 409 passed (see this
  ticket's own implementation notes below for the exact command).
- **New tests to write**: the stiction-plant fake-motor test described
  above; a test confirming exactly one of seg_/hold_/nudge_ is ever
  active; a test for the per-wheel asymmetry path if ticket 003 found
  one. **DONE** — the stiction-plant suite
  (`test_motion_engine_nudge_stiction.py`, 7 tests) and the engine-
  surface suite (`test_motion_engine_nudge.py`, 11 tests, including
  mutual-exclusion coverage). No separate per-wheel-asymmetry test:
  ticket 003 found no MAGNITUDE difference between wheels (only
  consistency/scatter), so a single `nudgeAmplitude()` applied
  identically to both wheels is correct per ticket 003's own "a 50/50
  split of magnitude is justified" finding — the requirement ticket 003
  actually imposes (re-reading real encoder deltas every pulse rather
  than trusting either wheel's nominal step) is what the ledger
  convergence tests already pin.
- **Verification command**:
  `uv run pytest tests/host/test_motion_engine_nudge.py
  tests/host/test_motion_engine_nudge_stiction.py
  tests/host/test_config_surface_single_source.py
  tests/host/test_wire_motion_verbs.py
  tests/tools/test_gen_config_field_enum.py
  tests/host/test_no_units_in_identifiers_source_pin.py -q` — 262
  passed. Also re-ran the full existing `MotionEngine` host suite
  (pulse/primitives/reductions/settle/estop/deadline/stall/gotow/
  acceleration-profile/default-cruise/shaping-fields, plus the cxx11
  and vfp-guard source-pin gates) unchanged: 409 passed total across
  both runs. `uv run python tools/make_deploy.py --robot vevov
  --profile-suffix=-nudge0916` builds cleanly (hex, 1,827,673 bytes) —
  not flashed; team-lead runs hardware.
