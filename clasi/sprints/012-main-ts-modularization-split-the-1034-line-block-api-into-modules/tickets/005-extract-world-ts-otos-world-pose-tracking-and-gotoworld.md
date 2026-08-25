---
id: '005'
title: 'Extract world.ts: OTOS world-pose tracking and goToWorld'
status: open
use-cases: [SUC-001, SUC-002]
depends-on: ['001']
github-issue: ''
issue: break-up-main-ts-into-modules.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Extract world.ts: OTOS world-pose tracking and goToWorld

## Description

Fifth extraction, and the largest of the four "spoke" modules (after
`sim.ts`/`run.ts`/`pose.ts`/`stop.ts`; before the final `motion.ts`
consolidation in ticket 006). Moves the whole World toolbox group out
of `main.ts` into `src/world.ts`: `startWorldTracking()`,
`worldTrackingReady()`, `seedPose()`, `readWorld()`, `worldX()`,
`worldY()`, `worldHeading()`, `calibrateWorldSensor()`,
`setWorldSensorOffset()`, plus `goToWorld()`'s own section — its
tuning state (`arriveTolCm`, `turnFirstDeg`), `setArrivalTolerance()`,
`goToWorld()` itself, and the private `tickedMove()` helper `goToWorld`
uses to run its legs.

Two cross-file call sites, both already-proven-safe patterns:
`seedPose()`/`readWorld()`/`worldX()`/etc. call `sim.ts`'s
`otosBegin()`/`otosRead()`/`otosGet()`/`otosCalibrate()`/
`otosSetOffset()` (already **exported** — no visibility question at
all) and `_seedPose()` (non-exported — same pattern ticket 001 proved).
`tickedMove()` calls `startMove()`, which is **exported** and, at the
time this ticket runs, still lives in the shrinking `main.ts`
remainder (it does not move to `motion.ts` until ticket 006) — this is
fine: `startMove` is reachable by name regardless of which file
currently holds it, exactly like any other exported API member a
student's own program calls.

## Acceptance Criteria

- [ ] `src/world.ts` created containing every function/state variable
      listed in the Description, each with JSDoc/`//%` annotations
      (`group="World"`) preserved verbatim, including the doctrine
      comment above the World section ("The OTOS optical tracking
      sensor is the WORLD-POSE AUTHORITY...") and `goToWorld()`'s own
      extensive inline design-rationale comments (pivot-first
      threshold, curvature cap, "ONE PASS" doctrine) — these are
      load-bearing documentation, not filler, and must travel intact.
- [ ] `main.ts` no longer contains any of the moved code.
- [ ] `pxt.json`'s `files` array: `src/world.ts` inserted (no
      load-time ordering constraint on this module itself; it may be
      listed before or after `main.ts`/`motion.ts` — its one call to
      `startMove()` is a function-body reference, safe regardless of
      file order).
- [ ] `tsconfig.json`'s `files` array: same insertion.
- [ ] A real PXT build succeeds.
- [ ] `test/test.ts`/`test/testrig.ts` simulator run matches the prior
      ticket's baseline exactly.
- [ ] Full existing `tests/host/` suite passes unchanged.
- [ ] `test_pxt_manifest_completeness.py` passes.
- [ ] No acceptance criterion above requires a robot (this ticket
      moves `goToWorld()`'s code, not its hardware validation — that
      is sprint 011's job, unaffected by this file move).

## Implementation Plan

**Approach**: cut the World-group functions and `goToWorld()`'s whole
section (state + `setArrivalTolerance` + `goToWorld` + `tickedMove`)
out of `main.ts`, paste into `src/world.ts` inside the same
`namespace diffDrive {}` wrapper, preserving every inline comment.

**Files to create**: `src/world.ts`.

**Files to modify**: `src/main.ts`, `pxt.json`, `tsconfig.json`.

**Testing plan**: real build, simulator/testrig parity, `tests/host/`
regression, manifest completeness. No hardware/OTOS-sensor test is in
scope or possible here (simulator has no OTOS model — `otosBegin`/
`otosRead`/etc. are no-op stubs by design).

**Documentation updates**: none beyond the overlay's existing §9/§15
description.

## C++11 Gate Coverage

Not applicable — TypeScript/manifest-only ticket, no C++ source
touched. Evidence: real PXT build, `test_pxt_manifest_completeness.py`,
simulator/testrig parity. No robot required — this ticket is a pure
code move, not a behavior or hardware-validation change.

## Testing

- **Existing tests to run**: full `pytest tests/host/`; `tsc -p .`.
- **New tests to write**: none.
- **Verification command**: real PXT build; `test/test.ts`/
  `test/testrig.ts` in the PXT simulator; `uv run pytest tests/host/`.
