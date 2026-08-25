---
id: '004'
title: 'Extract stop.ts: stop and fault-latch blocks'
status: done
use-cases:
- SUC-001
- SUC-002
depends-on:
- '001'
github-issue: ''
issue: break-up-main-ts-into-modules.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Extract stop.ts: stop and fault-latch blocks

## Description

Fourth extraction — small and self-contained, same pattern as ticket
003. Moves `stop()`, `emergencyStop()`, `clearEmergencyStop()`,
`isStalled()`, `clearStallLatch()` (Drive toolbox group) out of
`main.ts` into `src/stop.ts`. These call `sim.ts`'s `_stopAll()`,
`_estopAll()`, `_estopClear()`, `_isStalled()`, `_clearStallLatch()`
(moved there in ticket 001, non-exported) — the same proven cross-file
reference pattern.

`stop.ts` owns the robot's two independent fault latches (e-stop and
stall) and nothing else — deliberately not folded into the motion-
commanding module (`motion.ts`, ticket 006): commanding movement and
refusing/halting it are opposite concerns, and bundling them would
force `motion.ts`'s purpose statement to need an "and."

## Acceptance Criteria

- [x] `src/stop.ts` created containing `stop`, `emergencyStop`,
      `clearEmergencyStop`, `isStalled`, `clearStallLatch`, each with
      JSDoc/`//%` annotations (`group="Drive"`) preserved verbatim.
- [x] `main.ts` no longer contains any of the five functions.
- [x] `pxt.json`'s `files` array: `src/stop.ts` inserted (no load-time
      ordering constraint).
- [x] `tsconfig.json`'s `files` array: same insertion.
- [x] A real PXT build succeeds.
- [x] `test/test.ts`/`test/testrig.ts` simulator run matches the prior
      ticket's baseline exactly, including an emergency-stop-then-clear
      sequence (the UC-011 "forgot to clear" scenario sprint 007 fixed
      simulator parity for — confirm that fix's behavior is unaffected
      by this file move).
- [x] Full existing `tests/host/` suite passes unchanged.
- [x] `test_pxt_manifest_completeness.py` passes.
- [x] No acceptance criterion above requires a robot.

## Implementation Plan

**Approach**: cut the five functions out of `main.ts`, paste into
`src/stop.ts` inside the same `namespace diffDrive {}` wrapper.

**Files to create**: `src/stop.ts`.

**Files to modify**: `src/main.ts`, `pxt.json`, `tsconfig.json`.

**Testing plan**: real build, simulator/testrig parity (including the
e-stop/clear sequence), `tests/host/` regression, manifest
completeness.

**Documentation updates**: none beyond the overlay's existing §9/§15
description.

## C++11 Gate Coverage

Not applicable — TypeScript/manifest-only ticket, no C++ source
touched. Evidence: real PXT build, `test_pxt_manifest_completeness.py`,
simulator/testrig parity. No robot required.

## Testing

- **Existing tests to run**: full `pytest tests/host/`; `tsc -p .`.
- **New tests to write**: none.
- **Verification command**: real PXT build; `test/test.ts`/
  `test/testrig.ts` in the PXT simulator; `uv run pytest tests/host/`.
