---
id: '001'
title: 'Extract sim.ts: the browser-simulator shim surface, plus the pre-split baseline
  build'
status: open
use-cases: [SUC-001]
depends-on: []
github-issue: ''
issue: break-up-main-ts-into-modules.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Extract sim.ts: the browser-simulator shim surface, plus the pre-split baseline build

## Description

First of six extractions splitting `src/main.ts` (1128 lines as of
this planning pass — re-verify the exact count fresh; sprint 009's
comment cleanup lands before this ticket executes and will shift it)
into cohesion-sized modules per `sprint.md`'s Architecture section and
`design/src-root-DESIGN.md` §9/§15. This ticket does two things before
any other ticket touches the file:

1. **Capture the pre-split baseline** — build the project as it stands
   today (before any extraction) and archive the resulting `.hex` plus
   a listing of the generated block surface (captions, `group=`
   values, parameter ranges, toolbox order). Ticket 007 diffs its
   final build against this baseline — without it, "byte-identical" or
   "block-surface identical" has nothing to compare against.
2. **Extract `sim.ts`** — move every `//% shim=`-annotated function's
   TypeScript body out of `main.ts`: the simulator kinematic state
   (`simX`/`simY`/`simHeading`/`simVel`/`simYawRate`/`simLastMs`/
   `simMoveRemainMm`/`simMoveRemainRad`/`simMoveActive`/`simEstopped`/
   `kSimTickPeriodMs`/`simTickDeadlineMs`/`simCycleCount`/
   `simTickOverrunCount`) and `simIntegrate()`; the shim bodies with
   real kinematic behavior (`_setWheels`, `_driveTwist`, `_startMove`,
   `_updateMove`, `_tickDrive`, `_cycleStat`, `_progress`, `_endMove`,
   `_stopAll`, `_estopAll`, `_estopClear`, `_poseX`, `_poseY`,
   `_poseHeading`, `_resetPose`, `_seedPose`); and the no-op stand-ins
   with no browser model (`_clearStallLatch`, `_isStalled`,
   `_setGeometry`, `_setKernelValue`, `_startProtocol`, `probe`,
   `setTaperWindows`, `setTaperFloors`, `setRampMs`, `otosBegin`,
   `otosRead`, `otosGet`, `otosZero`, `otosCalibrate`,
   `otosSetOffset`, `emitLine`, `runCommandText`). Everything else
   (config, direct-drive, position-mode motion, pose readback, stop/
   latch blocks, world tracking, RUN dispatch) stays in `main.ts` for
   now — later tickets extract those.

This is the sprint's **empirical proof ticket** for the one open
technical question the whole split depends on: whether PXT's
compiled-as-one-Program model resolves a **non-exported** TypeScript
function/`let` declared in one file when called from another file that
reopens the same `namespace diffDrive`, the way TypeScript's documented
multi-file-namespace-merging semantics say it should (see
`design/src-root-DESIGN.md` §15 Design Rationale). After this
extraction, `main.ts`'s remaining code calls `sim.ts`'s non-exported
functions (e.g. `poseX()` still in `main.ts` calling `_poseX()` now in
`sim.ts`) — exactly the scenario in question. A green build plus a
correct simulator/testrig run **is** the proof; no separate spike
ticket is needed (see Design Rationale's sequencing decision).

**The one load-time ordering constraint this sprint has**: `main.ts`'s
top-level `_startProtocol()` call (unchanged position in this ticket —
it stays in `main.ts` until ticket 006) needs `sim.ts`'s
`_startProtocol` definition to already exist when it runs. `sim.ts`
**must** be listed before `main.ts` in both `pxt.json`'s and
`tsconfig.json`'s `files` arrays.

## Acceptance Criteria

- [ ] Pre-split baseline captured: a real build (project's existing
      `tools/make_deploy.py` / scratch-build workflow) run against
      today's unmodified `main.ts`; the resulting `.hex` and a
      generated block-surface listing (captions, `group=` values,
      parameter ranges, toolbox order) archived somewhere this
      ticket's own notes name explicitly, for ticket 007 to diff
      against.
- [ ] `src/sim.ts` created containing every function/state variable
      listed in the Description above, each with its JSDoc, `//%`
      annotation, and relative comment ordering preserved verbatim
      (cut, not rewritten).
- [ ] `main.ts` no longer contains any of the moved code; every
      remaining call site that used to reference it now calls into
      `sim.ts` (same function names, cross-file).
- [ ] No new file contains the literal string `radio.` (grep-checked)
      — `emitLine()`'s existing comment, which discusses this landmine
      without triggering it, moves to `sim.ts` unchanged, character for
      character.
- [ ] `pxt.json`'s `files` array: `src/sim.ts` inserted immediately
      before `src/main.ts`'s entry (which stays, slimmer, for now).
- [ ] `tsconfig.json`'s `files` array: same insertion, same position
      (this manifest has no automated completeness test today — see
      `design/src-root-DESIGN.md` §15 Open Questions; verify by
      actually running `tsc -p .` and comparing its error count/content
      against the pre-ticket baseline, not by inspection).
- [ ] A real PXT build succeeds (not just a type-check) with `sim.ts`
      split out — this is the empirical proof described above. If it
      fails specifically on a non-exported cross-file reference (a
      "cannot find name" class of error naming one of `sim.ts`'s
      un-exported symbols), the fallback is to `export` **only** the
      specific failing symbol(s) — record which ones and why in this
      ticket's own notes; do not export the whole file's surface
      pre-emptively.
- [ ] `test/test.ts` and `test/testrig.ts` run in the PXT simulator and
      behave identically to the pre-split baseline (same output/pose
      trace) — this is the load-bearing check for the no-initializer/
      panic-980 class and for the cross-file reference question alike.
- [ ] Full existing `tests/host/` suite passes unchanged (regression
      fence; this ticket touches no C++).
- [ ] `test_pxt_manifest_completeness.py` passes (it already covers
      `.ts` files per its own `_SOURCE_SUFFIXES`).
- [ ] No ticket acceptance criterion above requires a robot.

## Implementation Plan

**Approach**: cut the listed functions/state out of `main.ts` in one
pass, paste into a new `src/sim.ts` that opens with the same
`namespace diffDrive {` wrapper (no `export` keyword changes beyond
the acceptance criterion's named fallback), close the namespace at the
file's end. Do not reorder the functions relative to each other beyond
what's needed to keep the moved block contiguous — this keeps the diff
reviewable as "this whole block moved," not "this block moved and also
changed."

**Files to create**: `src/sim.ts`.

**Files to modify**: `src/main.ts` (remove the moved content),
`pxt.json`, `tsconfig.json` (both `files` arrays).

**Testing plan**: real build first (catches syntax/reference errors
cheaply before investing in simulator/host runs), then simulator
parity (`test/test.ts`/`test/testrig.ts`), then `tests/host/`
regression run, then the manifest-completeness test. Archive the
pre-split baseline **before** making any code change, not after.

**Documentation updates**: none required by this ticket specifically
(the overlay's §9/§15 already describe the target state); if this
ticket's real build surfaces something the overlay's Open Questions
got wrong (e.g. the non-exported-reference question resolves
differently than expected), note the actual outcome in this ticket's
own completion notes so ticket 007's handoff notes can cite it.

## C++11 Gate Coverage

Not applicable. This ticket touches only `src/main.ts`/`src/sim.ts`
(TypeScript) and the `pxt.json`/`tsconfig.json` manifests — no C++
source changes, so `test_cxx11_syntax_gate.py` doesn't apply. Evidence
instead comes from a real PXT build, `test_pxt_manifest_completeness.py`
(covers `.ts` files), a manual `tsc -p .` comparison for
`tsconfig.json` (no automated gate exists for it yet), and the
simulator/testrig parity check described above. No robot is required.

## Testing

- **Existing tests to run**: full `pytest tests/host/` (regression
  check — this ticket touches no host-tested C++); `tsc -p .`
  (manual comparison against pre-ticket baseline error count).
- **New tests to write**: none — no new host-testable surface (this
  ticket is TypeScript/manifest-only).
- **Verification command**: a real PXT build (`tools/make_deploy.py`
  or the project's equivalent) producing a `.hex`; run `test/test.ts`
  and `test/testrig.ts` in the PXT simulator; `uv run pytest
  tests/host/`.
