---
id: '005'
title: 'Blocks: nudge() / nudgeTurn()'
status: done
use-cases:
- SUC-002
depends-on:
- '004'
github-issue: ''
issue: nudge-mode-settle-gated-pulse-stepper-for-sub-floor-micro-moves.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Blocks: nudge() / nudgeTurn()

## Description

This is the ticket that actually completes the
`nudge-mode-settle-gated-pulse-stepper-for-sub-floor-micro-moves.md`
issue's 2026-09-15 update — calibrateL needs a block API, not just an
engine mode, and needs the caller to know what actually moved.

Add two blocks in `src/blocks/motion.ts`, following `move()`'s own
shape (`blocks/motion.ts:302-307`: stage the command, then
`while (_tickDrive());`):

- `nudge(leftMm, rightMm)` — per-wheel distance in mm (or cm, matching
  this file's existing convention — check `move()`'s cm-based
  signature before deciding; the issue text used mm because that is
  the encoder-count resolution's natural unit, but block-layer
  consistency may argue for cm like every other distance block).
- `nudgeTurn(deg)` — rotation in degrees, CCW+ (matching this file's
  existing sign convention, `motion_engine.h`'s header comment).

Both block until the underlying nudge-mode loop (ticket 004) reports
done, then **return the actually-measured encoder displacement** —
not just "done" — so calibrateL's own loop
(`league-projects/scratch/nezha-robot-template/test/calibratel.ts`)
can decide whether to nudge again. This is the one behavioral
requirement the issue's original 2026-08-31 proposal did not have and
the 2026-09-15 update added explicitly.

## Acceptance Criteria

- [x] `nudge(leftMm, rightMm)` and `nudgeTurn(deg)` exist, block until
      the nudge-mode loop reports done, and return the encoder-measured
      displacement (not the requested one). Shipped as `nudge(left,
      right)` / `nudgeTurn(deg)` — the `Mm` unit suffix moved to a
      trailing comment/@param text per
      `.claude/rules/no-units-in-identifiers.md`, enforced by
      `tests/host/test_no_units_in_identifiers_source_pin.py`, which
      scans `src/blocks/*.ts` too, not just C++. `left`/`right` mirror
      `setWheelSpeeds()`'s own existing param-naming precedent.
- [x] Both work forward and reverse (calibrateL's own requirement). The
      shim-layer reductions (`beginNudgeWheels`/`beginNudgeTurn`,
      `shims.cpp`) and the measured-result accessors
      (`nudgeMeasuredDistance`/`nudgeMeasuredRotation`,
      `motion_engine.h`) are sign-symmetric linear formulas with no
      forward/reverse branch; the underlying engine's own reverse
      handling is pinned by ticket 004's
      `test_a_reversed_pulse_takes_the_identical_step_shape_as_a_forward_one`
      (`tests/host/test_motion_engine_nudge_stiction.py`).
- [x] Host/simulator fallback exists (`sim.ts`) consistent with every
      other blocking move block in this file, so browser-simulator
      programs using these blocks do not silently no-op.
      `_beginNudgeWheels`/`_beginNudgeTurn`/`_nudgeActive`/
      `_nudgeMeasuredDistance`/`_nudgeMeasuredRotation` added.
- [ ] A hardware acceptance run (**team-lead**, per
      `hardware-tickets-run-them-yourself`) commands 1/2/3 deg trims and
      5/10 mm nudges, camera-scored, forward and reverse, landing
      within calibrateL's 1 deg tolerance — this is the sprint's
      headline success criterion. **NOT RUN** — programmer scope
      excludes hardware; per the dispatch instructions this is
      team-lead's run and the stakeholder must be asked before it is
      scheduled. Left unchecked deliberately.
- [x] Doc comments follow this file's existing `@param`/`//%
      block=`/`group=` conventions so the generated block surface stays
      consistent.

## Testing

- **Existing tests to run**: any TS-level block test harness this repo
  already has for `motion.ts` (check for one before assuming none
  exists).
- **New tests to write**: a test (host or TS, whichever this file's
  existing blocking-move blocks are tested with) confirming
  `nudge()`/`nudgeTurn()` return the measured, not requested, value.
- **Verification command**: the project's TS/host test runner for
  `blocks/`, plus a real `pxt build`
  (`.claude/rules/extension-publish-pipeline` memory: verify with a
  real build, not just the TS compiler) before the hardware run.
