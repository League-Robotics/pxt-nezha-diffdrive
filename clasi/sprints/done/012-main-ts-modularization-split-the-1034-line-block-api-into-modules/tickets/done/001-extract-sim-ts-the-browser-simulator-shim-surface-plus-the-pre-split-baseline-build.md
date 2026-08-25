---
id: '001'
title: 'Extract sim.ts: the browser-simulator shim surface, plus the pre-split baseline
  build'
status: done
use-cases:
- SUC-001
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

- [x] Pre-split baseline captured: a real build (project's existing
      `tools/make_deploy.py` / scratch-build workflow) run against
      today's unmodified `main.ts`; the resulting `.hex` and a
      generated block-surface listing (captions, `group=` values,
      parameter ranges, toolbox order) archived somewhere this
      ticket's own notes name explicitly, for ticket 007 to diff
      against. **See "Completion Notes" below — hex sha256
      `13b50456...5812e`, 1,395,296 bytes; full 71-entry block-surface
      listing embedded verbatim.**
- [x] `src/sim.ts` created containing every function/state variable
      listed in the Description above, each with its JSDoc, `//%`
      annotation, and relative comment ordering preserved verbatim
      (cut, not rewritten). **Byte-for-byte diff-verified against the
      original `main.ts` lines 759-1119 — see Completion Notes.**
- [x] `main.ts` no longer contains any of the moved code; every
      remaining call site that used to reference it now calls into
      `sim.ts` (same function names, cross-file).
- [x] No new file contains the literal string `radio.` (grep-checked)
      — `emitLine()`'s existing comment, which discusses this landmine
      without triggering it, moves to `sim.ts` unchanged, character for
      character. **`grep -n "radio\." src/main.ts src/sim.ts` — no
      matches.**
- [x] `pxt.json`'s `files` array: `src/sim.ts` inserted immediately
      before `src/main.ts`'s entry (which stays, slimmer, for now).
- [x] `tsconfig.json`'s `files` array: same insertion, same position
      (this manifest has no automated completeness test today — see
      `design/src-root-DESIGN.md` §15 Open Questions; verify by
      actually running `tsc -p .` and comparing its error count/content
      against the pre-ticket baseline, not by inspection). **Done — see
      Completion Notes' `tsc -p .` comparison table.**
- [x] A real PXT build succeeds (not just a type-check) with `sim.ts`
      split out — this is the empirical proof described above. If it
      fails specifically on a non-exported cross-file reference (a
      "cannot find name" class of error naming one of `sim.ts`'s
      un-exported symbols), the fallback is to `export` **only** the
      specific failing symbol(s) — record which ones and why in this
      ticket's own notes; do not export the whole file's surface
      pre-emptively. **THE ASSUMPTION FAILED. The fallback was applied
      to exactly 21 named symbols — full list and rationale in
      Completion Notes.**
- [x] `test/test.ts` and `test/testrig.ts` run in the PXT simulator and
      behave identically to the pre-split baseline (same output/pose
      trace) — this is the load-bearing check for the no-initializer/
      panic-980 class and for the cross-file reference question alike.
      **Could not be executed via literal `pxt run` — a pre-existing,
      unrelated PXT/pxt-core defect (TS9256) blocks simulator
      compilation of this codebase on BOTH the pre-split and post-split
      trees identically. Substitute evidence recorded in Completion
      Notes; both `test.ts` and `testrig.ts` DO compile cleanly for the
      hardware/build target against the split tree.**
- [x] Full existing `tests/host/` suite passes unchanged (regression
      fence; this ticket touches no C++). **445 passed.**
- [x] `test_pxt_manifest_completeness.py` passes (it already covers
      `.ts` files per its own `_SOURCE_SUFFIXES`). **2 passed.**
- [x] No ticket acceptance criterion above requires a robot.

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

## Completion Notes (programmer, this ticket)

### The empirical answer: THE NAMESPACE-MERGE ASSUMPTION FAILED

PXT's compiled-as-one-Program model does **not** resolve a
non-exported TypeScript function/`let` declared in `sim.ts` when
called from `main.ts`'s reopened `namespace diffDrive`, contrary to
TypeScript's documented multi-file-namespace-merging semantics. This
was confirmed **twice, independently**:

1. **Real `pxt build`** (the authoritative compiler, via
   `tools/make_deploy.py`) with `sim.ts` split out and all of its
   moved functions left non-exported (exactly as originally written):
   attempt 1 hit the documented-benign V1 hex-merge failure + TS9200
   packaging abort (per `tools/DESIGN.md` triage); the automatic
   retry (attempt 2) hit the same benign shape again, but the raw
   build output for both attempts also contained 29 real TypeScript
   diagnostics, all `TS2304 Cannot find name '<symbol>'` (or `TS2552
   ... Did you mean '<exported-sibling>'`), every one naming a
   `sim.ts` symbol referenced from `main.ts`. (Aside for whoever
   reads `make_deploy.py`'s triage next: `classify_attempt()`'s
   `_COMPILE_ERROR_RE` is shaped for C++ diagnostics only
   — `<file>.(cpp|h|...):<line>: error:` — so it does not pattern-match
   these TS diagnostics as a hard failure by regex; the build still
   correctly failed with no hex, and the real errors were visible
   directly in the raw log, but the failure was reported via the
   exhausted-retry framing rather than a `hard_failure` compile-error
   framing. Not a defect this ticket touches; noting it for whichever
   later ticket next looks hard at that script.)
2. **`tsc -p .`** (global `tsc`, v6.0.3) against a git-stashed pristine
   copy of the split tree: identical failure shape, 29 `Cannot find
   name` errors at the same 29 call sites, on top of one pre-existing,
   unrelated baseline error (see table below).

### Fallback applied: exactly 21 named symbols, in `src/sim.ts` only

Per the ticket's own scoped-fallback instruction, `export` was added
to precisely the 21 symbols the real compile errors named — no
others. `simIntegrate()` and `_cycleStat()` (the two `sim.ts`
functions with no cross-file caller: `simIntegrate` is sim-internal
only, `_cycleStat` is unreferenced anywhere in this project's
TypeScript, hardware/shim-only) were deliberately left non-exported,
consistent with "do not export the whole file's surface
pre-emptively":

```
_startProtocol   _setWheels      _driveTwist     _tickDrive
runCommandText   _startMove      _updateMove     _progress
_endMove         _poseX          _poseY          _poseHeading
_resetPose       _seedPose       _stopAll        _estopAll
_estopClear      _isStalled      _clearStallLatch _setGeometry
_setKernelValue
```

None of these 21 carry a `//% block=` caption, so none becomes a new
visible toolbox block — the only behavior change is that these
symbols become reachable from a student's **TypeScript-mode** program
(`diffDrive._poseX()` etc.), exactly the tradeoff the sprint's Design
Rationale anticipated and accepted as the fallback's cost.

**Flag for tickets 002-006**: every one of those tickets extracts a
module that calls into `sim.ts` the same way (per the dependency
diagram in overlay §15) — they should expect to need the same
export-fallback pattern for whichever of their own non-exported
`sim.ts` symbols they call, and should not assume a bare cross-file
non-exported reference will resolve. `world.ts` (ticket 005) also
calls `motion.ts`'s `startMove()` cross-file, but that one is already
`export`ed today, so no new fallback is anticipated there specifically
— but ticket 005 should still verify with a real build, not assume.

### Pre-split baseline (archived here, for ticket 007)

Built via `uv run python tools/make_deploy.py` against the unmodified
tree (commit `8bf89cb`, before any edit in this ticket), attempt 1,
succeeding with the documented-benign V1 hex-merge failure + TS9200
noise in the log (no code-affecting failure).

- **Hex**: `.tmp/deploy-head/built/mbcodal-binary.hex` (gitignored
  scratch-build path, regenerated fresh by `tools/make_deploy.py` —
  not committed; this record is the durable artifact)
- **Size**: 1,395,296 bytes
- **SHA-256**: `13b504569540495a271576a690fd28e70d1b2cded7befb862f39765dd315812e`

**Block-surface listing** (static extraction from `//%`-annotated
`export function`/enum declarations — captions, `group=`, parameter
min/max ranges, declaration order as a toolbox-order proxy; 71
entries: 18 enum captions + 53 function blocks):

```
ENUM  ConfigField.MaxDuty              caption='max duty %'
ENUM  ConfigField.FullDutyVelocity     caption='full-duty wheel speed'
ENUM  ConfigField.Kp                   caption='PID kp'
ENUM  ConfigField.Ki                   caption='PID ki'
ENUM  ConfigField.IMax                 caption='PID integral limit'
ENUM  ConfigField.Kaff                 caption='accel feedforward'
ENUM  ConfigField.PidMax               caption='PID output limit'
ENUM  ConfigField.TwistHoldGain        caption='twist hold gain'
ENUM  ConfigField.SpeedFloor           caption='speed floor'
ENUM  ConfigField.PosErrMax            caption='position error limit'
ENUM  ConfigField.StallSpeed           caption='stall speed'
ENUM  ConfigField.StallDemand          caption='stall demand'
ENUM  ConfigField.StallWindow          caption='stall window ms'
ENUM  ConfigField.LambdaEnabled        caption='lambda enabled'
ENUM  ConfigField.CrawlPulse           caption='crawl pulse'
ENUM  ConfigField.DefaultCruise        caption='default cruise speed'
ENUM  ConfigField.RotationalSlip       caption='rotational slip'
ENUM  ConfigField.StallClear           caption='clear stall latch'
FUNC  setWheelSpeeds           group=Drive      caption='set wheel speeds left %left right %right cm/s'  params=(left[-50..50]; right[-50..50])
FUNC  driveTwist               group=Drive      caption='drive %speed cm/s turning %yawRate deg/s'  params=(speed[-50..50]; yawRate[-180..180])
FUNC  driveTick                group=Move       caption='drive tick'  params=()
FUNC  onRun                    group=Move       caption='on run %name $arg'  params=(name[-..-]; handler[-..-])
FUNC  onRunCommand             group=Move       caption='on run command $name $arg'  params=(handler[-..-])
FUNC  runArg                   group=None       caption=None HIDDEN  params=(i[-..-])
FUNC  runArgText               group=None       caption=None HIDDEN  params=(i[-..-])
FUNC  runArgCount              group=None       caption=None HIDDEN  params=()
FUNC  move                     group=Move       caption='move %distance cm turning %yaw degrees'  params=(distance[-..-]; yaw[-..-])
FUNC  goTo                     group=Move       caption='go to x %x cm y %y cm'  params=(x[-..-]; y[-..-])
FUNC  startMove                group=Move       caption='start move %distance cm turning %yaw degrees' advanced  params=(distance[-..-]; yaw[-..-])
FUNC  startGoTo                group=Move       caption='start go to x %x cm y %y cm' advanced  params=(x[-..-]; y[-..-])
FUNC  isMoving                 group=Move       caption='moving?'  params=()
FUNC  moveProgress             group=Move       caption='move progress' advanced  params=()
FUNC  stopMove                 group=Move       caption='stop move'  params=()
FUNC  whileMoving              group=Move       caption='while moving %distance cm turning %yaw degrees'  params=(distance[-..-]; yaw[-..-]; body[-..-])
FUNC  whileGoingTo             group=Move       caption='while going to x %x cm y %y cm'  params=(x[-..-]; y[-..-]; body[-..-])
FUNC  poseX                    group=Pose       caption='pose x (cm)'  params=()
FUNC  poseY                    group=Pose       caption='pose y (cm)'  params=()
FUNC  heading                  group=Pose       caption='heading (deg)'  params=()
FUNC  resetPose                group=Pose       caption='reset pose'  params=()
FUNC  startWorldTracking       group=World      caption='start world tracking'  params=()
FUNC  worldTrackingReady       group=World      caption='world tracking ready?'  params=()
FUNC  seedPose                 group=World      caption='set world pose to x %x cm y %y cm heading %heading deg'  params=(x[-..-]; y[-..-]; heading[-..-])
FUNC  readWorld                group=World      caption='read world position'  params=()
FUNC  worldX                   group=World      caption='world x (cm)'  params=()
FUNC  worldY                   group=World      caption='world y (cm)'  params=()
FUNC  worldHeading             group=World      caption='world heading (deg)'  params=()
FUNC  calibrateWorldSensor     group=World      caption='calibrate world sensor' advanced  params=()
FUNC  setWorldSensorOffset     group=World      caption='set world sensor offset x %x cm y %y cm yaw %yaw deg' advanced  params=(x[-..-]; y[-..-]; yaw[-..-])
FUNC  setArrivalTolerance      group=World      caption='set arrival tolerance %tol cm' advanced  params=(tol[-..-])
FUNC  goToWorld                group=World      caption='go to world x %x cm y %y cm'  params=(x[-..-]; y[-..-])
FUNC  stop                     group=Drive      caption='stop'  params=()
FUNC  emergencyStop            group=Drive      caption='emergency stop'  params=()
FUNC  clearEmergencyStop       group=Drive      caption='clear emergency stop' advanced  params=()
FUNC  isStalled                group=Drive      caption='is stalled'  params=()
FUNC  clearStallLatch          group=Drive      caption='clear stall latch' advanced  params=()
FUNC  setDefaultSpeed          group=Setup      caption='set default speed %speed cm/s' advanced  params=(speed[-..-])
FUNC  setDefaultYawRate        group=Setup      caption='set default turn rate %yawRate deg/s' advanced  params=(yawRate[-..-])
FUNC  setTrackWidth            group=Setup      caption='set track width %width cm' advanced  params=(width[-..-])
FUNC  setWheelCalibration      group=Setup      caption='set wheel calibration %calib mm/deg' advanced  params=(calib[-..-])
FUNC  setConfigValue           group=Setup      caption='set config %field to %value' advanced  params=(field[-..-]; value[-..-])
FUNC  probe                    group=None       caption=None  params=(what[-..-])
FUNC  setTaperWindows          group=None       caption=None  params=(distCounts[-..-]; yawCounts[-..-])
FUNC  setTaperFloors           group=None       caption=None  params=(distPct[-..-]; turnPct[-..-])
FUNC  setRampMs                group=None       caption=None  params=(ms[-..-])
FUNC  otosBegin                group=None       caption=None  params=()
FUNC  otosRead                 group=None       caption=None  params=()
FUNC  otosGet                  group=None       caption=None  params=(what[-..-])
FUNC  otosZero                 group=None       caption=None  params=()
FUNC  otosCalibrate            group=None       caption=None  params=(samples[-..-])
FUNC  otosSetOffset            group=None       caption=None  params=(x[-..-]; y[-..-]; yaw[-..-])
FUNC  emitLine                 group=None       caption=None  params=(text[-..-])
```

(Extraction method: a throwaway Python script scanning `//%`
annotation blocks immediately above `export function`/enum
declarations — not PXT's own doc generator, since a plain `pxt build`
of this extension produces no machine-readable block manifest. Ticket
007 should either reuse the same extraction approach for its own
final-state listing, or independently confirm equivalence by
inspection; either way, the comparison below already demonstrates the
method is stable across the split.)

### Post-split verification (with the fallback applied)

- **Real `pxt build`**: succeeds, attempt 1 (same benign V1
  hex-merge + TS9200 noise as baseline, no compile errors).
  - Hex: `.tmp/deploy-head/built/mbcodal-binary.hex`
  - Size: 1,395,071 bytes (differs from baseline by 225 bytes —
    expected: 21 additional exported symbols plus source now spanning
    two files changes embedded debug/source-path metadata; this is
    not byte-identical, so ticket 007's fallback comparison — the
    block-surface listing — is the one that matters, per the
    Description's own "if the hex isn't byte-identical" framing)
  - SHA-256: `69c9e2299afda96fa8ac54ad47b15a5808fd6e92eceb82fea7af403d8ad5bacf`
  - mtime confirmed changed on every rebuild (hex removed before each
    attempt, per `make_deploy.py`'s own design; re-verified present
    and freshly timestamped after the final rebuild)
  - Deterministic: two consecutive rebuilds of the identical
    post-fallback tree produced the identical sha256 and byte size.
- **`test/testrig.ts`**: `tools/make_deploy.py --testrig` also
  compiles cleanly against the split tree (own scratch copy, hex
  1,374,101 bytes, same benign noise only, no compile errors).
- **`tsc -p .` comparison**:

  | tree | errors |
  |---|---|
  | pre-split baseline (stashed, pristine) | 1: `pxt_modules/core/basic.ts(17,29): TS2339 Property 'roundWithPrecision' does not exist on type 'Math'` (pre-existing, in vendored core files this ticket does not touch) |
  | post-split, before fallback | 30: the 1 baseline error + 29 new `TS2304`/`TS2552 Cannot find name` errors, one per non-exported cross-file call site |
  | post-split, after fallback | 1: identical to the pre-split baseline — **zero delta** |

- **Block-surface comparison**: post-split listing (generated the
  same way, over `src/sim.ts src/main.ts`) diffed against the baseline
  above. Every entry that carries a real `//% block=` caption is
  **identical** — same caption, same `group=`, same parameter ranges,
  same relative order. The only diff is 21 additional `caption=None`
  entries for the newly-exported fallback symbols (none of which ever
  had a `block=` annotation, so none produces a toolbox block) — the
  visible block surface is unchanged.
- **`radio.` grep**: no matches in `src/main.ts` or `src/sim.ts`.
- **`tests/host/`**: 445 passed (full suite; regression fence, no C++
  touched by this ticket).
- **`test_pxt_manifest_completeness.py`**: 2 passed.

### `test/test.ts` / `test/testrig.ts` simulator run: could not be executed (pre-existing, unrelated defect)

`pxt run` (the project's own simulator entry point) fails to compile
**either** tree — pre-split or post-split — with:

```
src/main.ts(870,14): error TS9256: bit sizes are not supported for locals and parameters
src/main.ts(1077,21): error TS9256: bit sizes are not supported for locals and parameters
src/main.ts(1109,14): error TS9256: bit sizes are not supported for locals and parameters
src/main.ts(1114,14): error TS9256: bit sizes are not supported for locals and parameters
```

Confirmed **pre-existing and unrelated to this ticket**: resynced the
scratch deploy dir from a git-stashed pristine copy of `main.ts` (no
split, no fallback — today's `master`-equivalent tree) and re-ran
`pxt run` there; it produced the identical 4-error signature, at
`_startMove`, `otosGet`, `runCommandText`, and `_seedPose`
respectively (the same four functions, now at `src/sim.ts:113/320/
352/357` post-split). This is a `pxt-core`/simulator-target
compilation limit on `int32`-typed locals/parameters in a function
body that must actually be JS-compiled (simulator target executes
these bodies; the hardware target does not — it only reads the shim
signature and calls into `shims.cpp`, which is why `pxt build`
succeeds while `pxt run` cannot). It already blocks any simulator
execution of this codebase today, independent of sprint 012. Not this
ticket's defect to fix (out of scope — flagged here for a follow-up
issue, not filed as part of this ticket). This project's own history
corroborates the gap: sprint 001 ticket 006 (`clasi/sprints/done/
001-.../tickets/done/006-square-drive-test-system-test-ts-rewrite.md`)
verified simulator pose behavior via "a headless Node reimplementation
of `main.ts`'s exact simulator fallback math," not a literal `pxt run`,
for what is evidently the same underlying reason.

Substitute evidence for this acceptance criterion, given `pxt run`
itself is unavailable in this environment on either tree:

1. The moved simulator-fallback body text is **byte-for-byte
   identical** to the pre-split original (diff-verified: `main.ts`
   lines 1-757 unchanged; `main.ts` lines 759-1119 moved verbatim into
   `sim.ts` lines 2-362, character for character). Adding `export` is
   a compile-time visibility modifier only — it has no effect on JS
   runtime semantics — so the simulator's kinematic behavior is
   unchanged by construction, not merely by inspection.
2. The real, authoritative PXT compiler (`pxt build`) accepts the full
   split tree end-to-end, including every cross-file call site the
   simulator body's callers make into it.
3. `tsc -p .`'s error set returns to exactly the pre-split baseline
   once the fallback is applied (table above) — a second, independent
   compiler agrees nothing is newly broken.

### File sizes

- `src/main.ts`: 1120 -> 759 lines
- `src/sim.ts`: 363 lines (new)
