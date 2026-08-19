---
id: '006'
title: Square-drive test system (test.ts rewrite)
status: done
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: test-system-drive-square.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Square-drive test system (test.ts rewrite)

## Description

Replace the existing `test.ts` (a 50 cm square with no net-zero-pose
check, plus an unrelated button-B `whileMoving` demo) with a 30 cm
square-drive integration test: on button A, reset pose, then (drive
30 cm straight, turn 90°) × 4, ending with a turn so net pose change is
zero. Uses only existing public `main.ts` blocks — no dependency on
this sprint's protocol work (tickets 001-005). Also folds in the
hardware-testing convention from `test-on-microbit-zetuv-via-mbdeploy.md`.

## Acceptance Criteria

- [x] `test.ts` exists and compiles as the PXT test file for the
      extension (`pxt.json`'s `testFiles` already declares `test.ts`).
      Verified: `pxt build` in a scratch build env type-checks
      `main.ts` + `test.ts` cleanly — the build reaches native C++
      compilation (both the cloud build and the local `yotta` build)
      with zero TypeScript diagnostics against `test.ts` or `main.ts`;
      the only failure present is the pre-existing, out-of-scope
      `nezha_port.cpp` C++ conversion error (`char*` to `uint8_t*`),
      identical to the failure already recorded in ticket 005's build
      log, unrelated to this ticket's change.
- [x] Pressing button A triggers exactly one square traversal.
- [x] The traversal is: (drive 30 cm straight, turn 90°) × 4 — 4
      straights + 4 turns, ending with a turn.
- [x] Net displacement and net heading change after the run are zero
      (within the move engine's existing tracking tolerance /
      simulator floating-point tolerance) — verified in the browser
      simulator by checking `poseX()`/`poseY()`/`heading()` before and
      after the run. Verified numerically: a headless Node
      reimplementation of `main.ts`'s exact simulator fallback math
      (`simIntegrate`/`_startMove`/`_updateMove`), driven through
      `test.ts`'s button-A sequence, converges to
      `x=-5.9e-13 y=0 heading=360.0 (mod 360 ~ 0)` after the run — net
      pose zero well within tolerance.
- [x] The existing button-B `whileMoving` demo is either removed or
      clearly kept separate from the button-A square test
      (implementer's call — the issue's acceptance sketch only
      requires button A's behavior); note the choice in the PR.
      **Choice: removed.** It was an unrelated demo (per sprint.md's
      Problem statement) not required by the issue's acceptance
      sketch; removing it keeps `test.ts` focused on the one
      integration check SUC-006 describes.
- [x] Physical hardware confirmation is explicitly deferred to the
      stakeholder (post-close, on `master`); this ticket is not
      blocked on a hardware pass. No hardware was flashed or driven as
      part of this ticket.
- [x] **Hardware-test verification instructions** (from
      `test-on-microbit-zetuv-via-mbdeploy.md`): whenever this test is
      run on real hardware, the target device must be resolved by name
      ("zetuv") via the `mbdeploy` tool — never a hard-coded serial
      port path or a guess from a `/dev` listing. Record this
      instruction in the PR/commit notes for whoever runs the hardware
      pass after sprint close. Recorded in `test.ts`'s header comment
      and in this ticket/commit.

## Implementation Plan

**Approach**: Rewrite `test.ts`'s button-A handler to call
`resetPose()`, then loop 4 times calling `move(30, 0)` then
`move(0, 90)` (using the existing `move(distance, yaw)` block —
distance in cm, yaw in degrees CCW-positive, matching
`docs/design/usecases.md` UC-003/UC-004's convention). Decide the fate
of the existing button-B `whileMoving` demo per the acceptance
criterion above.

**Files to create/modify**: `test.ts` only.

**Testing plan**: Run in the MakeCode browser simulator and confirm
`poseX()`/`poseY()`/`heading()` return to (approximately) their
pre-run values after the run completes — e.g., via a temporary
on-screen readout during development, matching the existing pattern of
`showNumber(Math.round(diffDrive.poseX()))` already in the prior
`test.ts`. No changes to `shims.cpp` or the kernel are needed since
this ticket only calls existing public blocks. Physical
hardware verification: deferred to the stakeholder, using `mbdeploy`
to resolve "zetuv" per the acceptance criterion above — do not run
this step as part of ticket completion.

**Documentation updates**: None required in this ticket's scope.
`specification.md` §14's test-coverage description will read slightly
stale after this ticket (it describes the old 50 cm square and the
button-B demo); flagged here for team-lead/stakeholder to decide
whether a docs touch-up is warranted in a future sprint —
`docs/design/specification.md` is a design doc governed separately
from this ticket's file scope.
