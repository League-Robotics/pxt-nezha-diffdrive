---
id: '006'
title: 'Extract motion.ts: config, direct drive, and position-mode moves; retire main.ts'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
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

- [x] `src/motion.ts` created (or `main.ts` renamed in place, git-mv
      style, once its content matches this description) containing
      everything listed in the Description, each with JSDoc/`//%`
      annotations preserved verbatim.
- [x] `src/main.ts` no longer exists.
- [x] The file-header doc comment (the extension-level `/** DiffDrive
      — ... */` block) lands somewhere sensible — `motion.ts` is the
      recommended home (see overlay §15 Open Questions) but this is a
      free implementation choice with no behavior consequence.
- [x] `pxt.json`'s `files` array: `src/main.ts`'s entry replaced by
      `src/motion.ts`, positioned **after** `src/sim.ts`. Confirm the
      full six-entry list matches `sprint.md`'s Architecture section
      and the overlay's §15 Sprint Changes.
- [x] `tsconfig.json`'s `files` array: same replacement, same ordering
      constraint.
- [x] `docs/design/specification.md` updated per the Description's
      bullet list — grep-confirm zero remaining `main.ts` references
      in that file once done.
- [x] A real PXT build succeeds.
- [x] `test/test.ts`/`test/testrig.ts` simulator run matches ticket
      005's baseline exactly — this is the point where the full
      six-file split first exists together; treat any divergence here
      as this sprint's most serious possible finding, not a minor
      note.
- [x] Full existing `tests/host/` suite passes unchanged.
- [x] `test_pxt_manifest_completeness.py` passes.
- [x] No acceptance criterion above requires a robot.

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

## Completion Notes (programmer, this ticket)

### Load-order reasoning (Risk 1)

`git mv src/main.ts src/motion.ts` — a pure rename, zero content
changes (`diff` of `git show HEAD:src/main.ts` against `src/motion.ts`
returns empty; see verbatim-diff evidence below). The top-level
`_startProtocol()` call therefore stayed exactly where it already was
inside the file, and the file itself stayed exactly where the manifest
already had it: `sim.ts` was listed before `main.ts` in both
`pxt.json` and `tsconfig.json` `files[]` before this ticket (ticket
001's doing), and the rename-in-place preserves that same relative
position — `motion.ts` is now the LAST entry in both arrays, `sim.ts`
is the FIRST of the six `src/*.ts` entries. `sim.ts`'s
`_startProtocol` definition (line 277) is therefore already loaded and
defined by the time `motion.ts`'s top-level call executes. No manifest
reordering was needed or done beyond the literal string substitution
`main.ts` -> `motion.ts` in both arrays, at the same array position.
Confirmed by loading both JSON files and checking list index:
`sim.ts` index 8, `motion.ts` index 13, in both files.

### Export decisions (Risk 2)

Zero new exports, matching the narrow-rule pattern from 002-005.
Grepped actual cross-file callers before touching anything:
`startMove`/`startGoTo` were already `export`ed (world.ts's
`tickedMove()` already calls `startMove()` per ticket 005). No other
symbol in the moved block gained a new cross-file caller.
`defaultSpeed`/`defaultYawRate` stay non-exported bare `let`s, per the
ticket's explicit instruction not to split config away from motion —
`startMove()` still reads them directly, same-file, exactly as before
the move.

### Verbatim-diff evidence

```
git show HEAD:src/main.ts > /tmp/main_ts_old.txt
diff /tmp/main_ts_old.txt src/motion.ts
# exit code 0 -- zero differences, byte-identical (318 lines both sides)
```

### Guard-test / stale-reference sweep (Risk finding 5)

Full-repo grep for `main\.ts` after the rename, evaluated file by
file:

- `tests/host/test_wire_constants_drift.py` — historical narrative
  docstring only (documents sprint 008's original findings); the
  file's executable code already targets `run.ts` (retargeted by
  ticket 002); no live path/existence check on `main.ts`. Left as-is.
- `tests/tools/test_make_deploy_triage.py` — a self-contained
  synthetic fixture that invents its own isolated temp-repo
  `main.ts`/`pxt.json` to test `classify_attempt()`'s triage logic in
  the abstract; does not read this repo's real `src/` or `pxt.json`.
  Left as-is.
- `tools/tour_square.py` — a comment referencing `main.ts`'s
  `turnFirstDeg`, but `turnFirstDeg` actually lives in `world.ts` (has
  since ticket 005) — already stale before this ticket, pre-existing
  and unrelated to this ticket's payload (config/motion, not
  world/goToWorld). Not fixed here — flagging for a future comment-
  cleanup pass rather than guessing at an unrelated ticket's intent.
- `tests/host/README.md` and
  `tests/host/test_motion_engine_deadline_boundary.py` — plain prose/
  comment mentions of `src/main.ts`, updated to `src/*.ts` and
  `motion.ts` respectively for accuracy (no test logic depended on
  these strings).
- `docs/design/specification.md` — all 7 locations (lines ~5, 35, 70,
  76, 151, 269, 761 pre-edit) updated per the Description's bullet
  list; grep-confirmed zero `main.ts` remaining.
- `docs/design/overview.md` and `tools/DESIGN.md` — the two
  lower-priority touch-ups, both done (one mention each: the "Shim +
  blocks" layer list in overview.md now names all six `src/*.ts`
  files; `tools/DESIGN.md`'s RUN-dispatch sentence now names `run.ts`,
  matching ticket 002's actual move of that dispatcher).
- `src/*.cpp`/`src/*.h`/`src/DESIGN.md` C++-side comments mentioning
  `main.ts` (protocol.h, wire_adapter.cpp, motion_engine.{h,cpp},
  shims.cpp, protocol.cpp, src/DESIGN.md) and `docs/design/usecases.md`
  / `docs/design/design.md` — explicitly out of this ticket's scope
  (TypeScript/manifest/docs-only per the C++11 Gate Coverage section;
  only `specification.md` is named as required, `overview.md`/
  `tools/DESIGN.md` as optional — `usecases.md`/`design.md` are not
  named at all). Left untouched; not this ticket's payload.
- `docs/code-review/**` — dated historical review artifacts, not
  living documentation; left untouched.

### Build verification

Both hexes removed first (`.tmp/deploy-head/built/mbcodal-binary.hex`,
`.tmp/deploy-testrig/built/mbcodal-binary.hex`), then rebuilt fresh:

- `uv run python tools/make_deploy.py`: attempt 1 hit the documented-
  benign V1 `srec_cat` hex-merge failure + `TS9200` packaging abort
  (per `tools/DESIGN.md` triage); `classify_attempt()` correctly
  triaged it as benign since `codal-microbit-v2` compiled clean (no
  `.cpp`/`.h` diagnostic). Hex produced: 1,395,161 bytes, fresh mtime
  (post-removal).
- `uv run python tools/make_deploy.py --testrig`: same benign shape,
  same triage outcome. Hex produced: 1,374,191 bytes, fresh mtime
  (post-removal).
- `tsc -p .` (global tsc, since no local install exists in this repo):
  exactly the one known baseline error,
  `pxt_modules/core/basic.ts(17,29): error TS2339:
  Math.roundWithPrecision` — nothing new.

### Simulator/testrig parity (Risk: "most serious possible finding")

Literal `pxt run` is blocked by the same pre-existing, unrelated
TS9256 defect ticket 001 first documented (bit-sized int32
locals/parameters in `sim.ts` cannot be JS-compiled for the simulator
target). Re-ran it against both scratch copies post-split to confirm
no new divergence:

- `deploy-head` (`test.ts` promoted): `src/sim.ts(113,21)`,
  `(320,21)`, `(352,21)`, `(357,21)` — TS9256, same four call sites
  ticket 001 documented (`_startMove`, `otosGet`, `runCommandText`,
  `_seedPose`).
- `deploy-testrig` (`testrig.ts` promoted): `src/sim.ts(83,21)`,
  `(320,21)`, `(352,21)` — a different subset/line for the first hit
  (83 vs 113) because `testrig.ts`'s call graph exercises a different
  first `int32`-parameter function than `test.ts`'s does, but all
  three are still TS9256 diagnostics inside `sim.ts` — zero errors
  inside `motion.ts` or any other file this ticket touched.

All errors are confined to `sim.ts`, a file this ticket did not touch.
No divergence from the established baseline. Substitute evidence (real
`pxt build` succeeding for both `test.ts` and `testrig.ts` promoted
scratch copies, per Build verification above) stands in for literal
`pxt run`, consistent with ticket 001's precedent.

### Test suite

`uv run pytest tests/host/`: **445 passed** in 43.88s (includes
`test_pxt_manifest_completeness.py`'s 2 tests, both passing).

### Per-module line counts (post-split, final)

```
src/motion.ts   318
src/sim.ts      363
src/world.ts    230
src/run.ts      121
src/stop.ts      55
src/pose.ts      39
------------------
total          1126
```

`src/main.ts` no longer exists (confirmed: `test -f src/main.ts` ->
absent; `ls src/` lists no `main.ts`).
