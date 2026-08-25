---
id: '006'
title: 'Extract motion.ts: config, direct drive, and position-mode moves; retire main.ts'
status: open
use-cases: [SUC-001, SUC-002, SUC-003]
depends-on: ['001', '002', '003', '004', '005']
github-issue: ''
issue: break-up-main-ts-into-modules.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Extract motion.ts: config, direct drive, and position-mode moves; retire main.ts

## Description

Sixth and final extraction. By the time this ticket starts, `main.ts`
has already had `sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, and `world.ts`
carved out of it (tickets 001-005) — what remains is exactly this
ticket's payload: the top-level `ConfigField` enum, the two
movement-default `let`s (`defaultSpeed`, `defaultYawRate`) and their
Setup-group setters (`setDefaultSpeed`, `setDefaultYawRate`,
`setTrackWidth`, `setWheelCalibration`, `setConfigValue`),
continuous-mode drive (`setWheelSpeeds`, `driveTwist`, `driveTick`),
position-mode move (`move`, `goTo`, `startMove`, `startGoTo`,
`isMoving`, `moveProgress`, `stopMove`, `whileMoving`,
`whileGoingTo`), and the namespace's one load-time side-effecting
statement, the top-level `_startProtocol()` call. Rename this
remainder `src/motion.ts` and delete `src/main.ts`.

Config and motion stay together deliberately (unlike pose/stop, which
were split out in tickets 003/004): `startMove()` reads `defaultSpeed`/
`defaultYawRate` directly as bare **non-exported** `let`s, not through
a getter — the one place in this whole split where a real same-file
requirement exists (see `sprint.md`'s Architecture section and the
overlay's §15 Design Rationale). Do not split config away from motion
in this ticket even though it would be mechanically possible.

**The hard file-order constraint lands here**: `motion.ts`'s top-level
`_startProtocol()` call needs `sim.ts`'s `_startProtocol` definition
to already exist when it executes at load time. `sim.ts` **must** be
listed before `motion.ts` in both `pxt.json`'s and `tsconfig.json`'s
`files` arrays — this was already true when `sim.ts` was inserted
ahead of `main.ts` in ticket 001; this ticket's job is to make sure
renaming `main.ts` to `motion.ts` doesn't disturb that relative order.

This ticket also updates `docs/design/specification.md`, the one
non-overlay canonical doc whose content becomes actively wrong once
`main.ts` no longer exists (out of the sprint-planner's write scope
during planning; execution-time work, tracked here):

- Its files-array table (listing `pxt.json`'s exact `files` content)
  — replace the `main.ts` entry with the six new files, in their final
  `pxt.json` order.
- The "public surface is the `diffDrive` namespace in `main.ts`"
  sentence — update to name the module split (or point to `src/
  DESIGN.md` §9 rather than re-describing it inline).
- The `startMove`'s doc-comment cross-reference (in the `start move`
  block's table row) — the doc comment now lives in `motion.ts`.
- The shim-boundary paragraph referencing `main.ts` as the TS-side
  shim-body location — update to `sim.ts` specifically (that is where
  shim bodies now live, not `motion.ts`).
- The closing list of "this repo's own" files mentioning `main.ts`.

(Exact line numbers as of this planning pass: ~5, 35, 70, 76, 151, 269,
765 — re-locate by content; sprint 009's comment cleanup and tickets
001-005 of this sprint will both have shifted them by the time this
ticket executes.) `docs/design/overview.md` (one `main.ts` mention) and
`tools/DESIGN.md` (one `main.ts` mention, still true in substance) are
lower-priority touch-ups — do them if time allows, but don't let them
block this ticket's completion.

## Acceptance Criteria

- [ ] `src/motion.ts` created (or `main.ts` renamed in place, git-mv
      style, once its content matches this description) containing
      everything listed in the Description, each with JSDoc/`//%`
      annotations preserved verbatim.
- [ ] `src/main.ts` no longer exists.
- [ ] The file-header doc comment (the extension-level `/** DiffDrive
      — ... */` block) lands somewhere sensible — `motion.ts` is the
      recommended home (see overlay §15 Open Questions) but this is a
      free implementation choice with no behavior consequence.
- [ ] `pxt.json`'s `files` array: `src/main.ts`'s entry replaced by
      `src/motion.ts`, positioned **after** `src/sim.ts`. Confirm the
      full six-entry list matches `sprint.md`'s Architecture section
      and the overlay's §15 Sprint Changes.
- [ ] `tsconfig.json`'s `files` array: same replacement, same ordering
      constraint.
- [ ] `docs/design/specification.md` updated per the Description's
      bullet list — grep-confirm zero remaining `main.ts` references
      in that file once done.
- [ ] A real PXT build succeeds.
- [ ] `test/test.ts`/`test/testrig.ts` simulator run matches ticket
      005's baseline exactly — this is the point where the full
      six-file split first exists together; treat any divergence here
      as this sprint's most serious possible finding, not a minor
      note.
- [ ] Full existing `tests/host/` suite passes unchanged.
- [ ] `test_pxt_manifest_completeness.py` passes.
- [ ] No acceptance criterion above requires a robot.

## Implementation Plan

**Approach**: with `main.ts` already reduced to this ticket's exact
payload by tickets 001-005, this is largely a rename (`git mv
src/main.ts src/motion.ts`) plus fixing the two manifests' entries and
confirming `sim.ts` still precedes it.

**Files to create**: `src/motion.ts` (or rename from `src/main.ts`).

**Files to modify/delete**: `src/main.ts` (removed), `pxt.json`,
`tsconfig.json`, `docs/design/specification.md`.

**Testing plan**: real build, simulator/testrig parity (the most
consequential check in the sprint, per the acceptance criteria above),
`tests/host/` regression, manifest completeness.

**Documentation updates**: `docs/design/specification.md` as described;
optionally `docs/design/overview.md`/`tools/DESIGN.md`'s minor
references.

## C++11 Gate Coverage

Not applicable — TypeScript/manifest/docs-only ticket, no C++ source
touched. Evidence: real PXT build, `test_pxt_manifest_completeness.py`,
simulator/testrig parity. No robot required.

## Testing

- **Existing tests to run**: full `pytest tests/host/`; `tsc -p .`.
- **New tests to write**: none.
- **Verification command**: real PXT build; `test/test.ts`/
  `test/testrig.ts` in the PXT simulator; `uv run pytest tests/host/`.
