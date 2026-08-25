---
id: '003'
title: 'Extract pose.ts: local pose readback'
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

# Extract pose.ts: local pose readback

## Description

Third extraction — small and self-contained. Moves `poseX()`,
`poseY()`, `heading()`, `resetPose()` (Pose toolbox group) out of
`main.ts` into `src/pose.ts`. These four functions call `sim.ts`'s
`_poseX()`/`_poseY()`/`_poseHeading()`/`_resetPose()` (moved there in
ticket 001, non-exported) — the same cross-file, function-body
reference pattern ticket 001 already proved out; this ticket is
additional confirmation on a second, independent module, not a new
category of risk.

Diverges from the roadmap's DES-05 recommendation to keep config,
motion, and pose in one file — see `sprint.md`'s Architecture section
and `design/src-root-DESIGN.md` §15's Design Rationale for why: pose
never references `defaultSpeed`/`defaultYawRate` (the shared state
DES-05's caution was actually about), and motion reaches pose only
through these four **exported** functions (`whileMoving`/
`whileGoingTo` call `poseX()`/`poseY()`/`heading()`), which resolve
safely across files regardless of load order. Pose earns its own file
on the cohesion test alone.

- [x] `src/pose.ts` created containing `poseX`, `poseY`, `heading`,
      `resetPose`, each with JSDoc/`//%` annotations (`group="Pose"`)
      preserved verbatim.
- [x] `main.ts` no longer contains any of the four functions; any
      caller inside the remaining `main.ts` content (`whileMoving`/
      `whileGoingTo`) now calls `poseX()`/`poseY()`/`heading()`
      cross-file, unchanged in name/signature.
- [x] `pxt.json`'s `files` array: `src/pose.ts` inserted (no load-time
      ordering constraint — position anywhere after `sim.ts`).
- [x] `tsconfig.json`'s `files` array: same insertion.
- [x] A real PXT build succeeds.
- [x] `test/test.ts`/`test/testrig.ts` simulator run matches the prior
      ticket's baseline exactly (pose values in particular — this is
      the module most directly checkable against a numeric trace).
- [x] Full existing `tests/host/` suite passes unchanged.
- [x] `test_pxt_manifest_completeness.py` passes.
- [x] No acceptance criterion above requires a robot.

## Implementation Plan

**Approach**: cut the four functions out of `main.ts`, paste into
`src/pose.ts` inside the same `namespace diffDrive {}` wrapper.

**Files to create**: `src/pose.ts`.

**Files to modify**: `src/main.ts`, `pxt.json`, `tsconfig.json`.

**Testing plan**: real build, simulator/testrig parity, `tests/host/`
regression, manifest completeness — same sequence as tickets 001/002.

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
