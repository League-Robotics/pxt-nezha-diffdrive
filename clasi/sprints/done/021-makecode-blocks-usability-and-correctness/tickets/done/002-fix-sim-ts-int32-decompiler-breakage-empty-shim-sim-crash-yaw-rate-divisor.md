---
id: '002'
title: 'Fix sim.ts: int32 decompiler breakage, empty-shim sim crash, yaw-rate divisor'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-003
depends-on:
- '001'
github-issue: ''
issue:
- int32-sim-params-break-blocks-conversion.md
- simulator-crashes-at-on-start-startprotocol.md
- simulator-yaw-rate-divisor-diverges-from-hardware-track-width.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Fix sim.ts: int32 decompiler breakage, empty-shim sim crash, yaw-rate divisor

## Description

Fix all three `src/blocks/sim.ts` defects in one pass, since they share
one file and one editing session (the two decompiler/crash issues are
explicitly cross-referenced from each other; the divisor issue was found
enumerating the same file):

1. **TS9256 / int32 params**: every sim-fallback function parameter
   still typed `int32` breaks JS->Blocks conversion. Change parameter
   types to `number` (return types stay `int32` where they already are
   — TS9256 fires on locals/parameters only, not return types).
2. **Empty-bodied shims crash the simulator**: any function whose TS
   body is a bare `{}` is emitted by pxt as native-only, so the sim
   throws when it's reached. Give each a real, if trivial, body.
3. **Yaw-rate divisor**: `_setWheels()`'s divisor (currently `115`,
   standing in for `trackWidth_` alone) must be re-derived from the same
   quantities hardware's `effectiveTrackWidth()` uses
   (`trackWidth_ / rotationalSlip_` = 119.96 mm today), so it agrees
   with `_driveTwist()`'s sim body (which already reproduces hardware
   exactly) instead of disagreeing with it by 4.3%.

See this sprint's Architecture section (Design Rationale) for why: the
simulator's contract is exact parity on *observable* output, not a
physical model of hardware's calibration mechanism — `_setWheels()`
needs to match `effectiveTrackWidth()`'s resulting value, not grow its
own "slip" concept.

**Audit fresh, don't trust the issue lists verbatim.** Both linked
issues enumerate specific function names from a sprint-013-era audit.
Cross-checking the *current* file during sprint planning found one
discrepancy already: `probe(what: int32): number` has a real body
(`return 0`), not an empty `{}` — it does not need an empty-body fix,
only the `int32` parameter sweep. Re-verify the rest of both lists
against the current file rather than assuming either list is exhaustive
or exactly correct.

## Acceptance Criteria

- [x] No function in `sim.ts` declares an `int32` parameter (return
      types unaffected). Fresh audit found 15 functions with int32
      params (not "~10" as estimated) -- see completion note below.
- [x] No function in `sim.ts` has a bare `{}` body where pxt would treat
      it as native-only; every previously-empty function now has a
      real, if trivial, TS body (e.g. `_startProtocol` sets a
      module-level `simProtocolStarted` flag, matching the pattern the
      issue suggests). Fresh audit found 11 functions needing this fix,
      including one (`_setGoToDeadline`) not on either issue's list --
      see completion note below.
- [x] `_setWheels()`'s yaw-rate divisor is derived from the same
      `trackWidth` / `rotationalSlip` relationship
      `MotionEngine::effectiveTrackWidth()` uses (motion_engine.h),
      not a bare geometric stand-in — see Architecture Open Question 1
      for the two-named-constants-vs-single-literal choice (leaning
      toward two named constants). Implemented as two named constants
      (`kSimTrackWidthMm`, `kSimRotationalSlip`).
- [x] For a matched wheel-speed-differential vs. body-speed+yaw-rate
      input, `_setWheels()` and `_driveTwist()` produce the same
      simulated yaw rate (within rounding). Verified numerically
      (Node.js scratch script reproducing both formulas exactly):
      agree to within 0.0032 deg/s (integer-quantization rounding on
      the centidegrees/s parameter) -- see completion note.
- [ ] In the local editor (`http://localhost:3232/index.html?ws=fs`,
      per ticket 001's doc): a project using the extension converts
      JS->Blocks cleanly (no `TS9256`, no Problems-pane error), and the
      web simulator boots without crashing for a bare project (`on
      start` + one `diffDrive` block). **NOT empirically verified via a
      live browser click-through** -- no browser-automation tool was
      available this session. What WAS verified instead (see completion
      note for detail): (1) direct read of `node_modules/pxt-core/built/
      pxt.js`'s `hasShimDummy()`/`setCellProps()` -- the exact compiler
      logic that triggers TS9256 and the empty-shim sim-crash --
      confirming zero remaining trigger conditions in `sim.ts`; (2)
      `pxt serve --noBrowser --noauth --noSerial` boots cleanly and
      `curl` on `http://localhost:3232/index.html?ws=fs` returns HTTP
      200 with these changes in place; (3) a standalone `pxt decompile`
      CLI attempt (a non-browser equivalent) hit a pre-existing,
      unrelated environment gap (the `pxt-microbit` target's `libs/`
      directory was never built in this checkout -- the same gap
      `docs/local-editor.md` already documents as a harmless
      `pxt serve` startup message). Flagging per this ticket's own
      instruction to "say so plainly rather than claiming it passed."
- [x] No `//%` shim signature grows past four parameters and no shim
      signature spans more than one line (hard PXT-build constraints).
- [x] `src/core/diffdrive.{h,cpp}` is not touched (vendored,
      byte-stable).
- [x] `node_modules/.bin/tsc --noEmit -p tsconfig.json` passes.

## Implementation Plan

**Approach**: Sweep `sim.ts` top to bottom once, applying all three
fixes together per function where they overlap (e.g. `_setWheels()`
gets both the `int32`->`number` param change and the divisor fix in the
same edit). Use ticket 001's now-published local-editor doc to verify
JS->Blocks conversion and simulator boot. This ticket is software-only
(browser/editor); hardware ABI safety is verified separately in ticket
003, which depends on this one.

**Files to create/modify**:
- `src/blocks/sim.ts` only. No changes to `motion.ts`, `run.ts`,
  `stop.ts`, `world.ts` (those are ticket 004's annotation-only scope),
  and no changes anywhere in `shims.cpp`/`protocol.cpp`/C++ (the native
  shim ABI is explicitly out of this ticket's scope — see ticket 003).

**Testing plan**:
- Local editor: JS->Blocks conversion check and simulator-boot check
  for a bare project using the extension, per ticket 001's doc.
- Manual comparison of `_setWheels()` vs `_driveTwist()` simulated yaw
  rate for a matched input (e.g. via the browser console or a scratch
  test program), confirming they now agree.
- `node_modules/.bin/tsc --noEmit -p tsconfig.json` for a compile-level
  check independent of the full pxt decompiler.
- Scope test runs to whatever this repo's test suite covers for
  `src/blocks/` (TS-only sim fallbacks are not expected to be under
  `uv run pytest`'s host-test coverage, which targets the C++ host
  tests — confirm scope before assuming zero Python-side impact).

**Documentation updates**: None required beyond code comments (the
existing in-file comments already document the sim-vs-hardware
relationship; update them in place if the divisor fix changes which
constants are named).

## Completion Notes

**Fresh audit, defect 1 (int32 params).** 15 functions declared an
int32 parameter, not "~10": `_setWheels`, `_driveTwist`, `_startMove`,
`_cycleStat`, `_setGeometry`, `_setKernelValue`, `probe`,
`setTaperWindows`, `setTaperFloors`, `setRampMs`, `otosGet`,
`otosCalibrate`, `otosSetOffset`, `runCommandText`, `_seedPose` (24
individual parameters total). All changed to `number`; every int32
*return* type (`_cycleStat`, `_progress`, `_poseX`, `_poseY`,
`_poseHeading`) left untouched, matching the acceptance criterion.

**Fresh audit, defect 2 (empty-bodied shims).** 11 functions needed a
real body, not "~9"/"~8 more": the 10 literal `{}` bodies the issue
named (`_clearStallLatch`, `_setGeometry`, `_setKernelValue`,
`_startProtocol`, `setTaperWindows`, `setTaperFloors`, `setRampMs`,
`otosZero`, `otosCalibrate`, `otosSetOffset`) PLUS one the issue's list
missed: `_setGoToDeadline`, whose body held only a comment (no
statements). Confirmed by reading the actual trigger condition in
`node_modules/pxt-core/built/pxt.js`'s `hasShimDummy()`: for a
non-native (simulator) build, `hasShimDummy(node)` is `node.body &&
(node.body.kind != Block || node.body.statements.length > 0)`; the
call site is `if (attrs.shim && !hasShimDummy(decl)) return
emitShim(...)` (routes to an unimplemented `pxsim.<ns>.<fn>(...)`
call). Comments are trivia, not AST statements, so a body containing
only a comment has `statements.length === 0` and trips the exact same
crash path as a literal `{}` -- `_setGoToDeadline` was silently broken
the same way, just not caught by a textual `{}` scan. `probe()`
(already had `return 0`) was confirmed correctly excluded, matching
the ticket's own pre-verification.

**Divisor fix.** `_setWheels()` now divides by `kSimTrackWidthMm /
kSimRotationalSlip` (two named module-level constants, 114.2 and
0.952, mirroring `motion_engine.h`'s `trackWidth_`/`rotationalSlip_`)
instead of the bare `115` literal -- effectiveTrackWidth = 119.958 mm,
matching hardware exactly. Verified with a Node.js scratch script
reproducing both `_setWheels()`'s and `_driveTwist()`'s exact formulas:
for a matched wheel differential (left=-50, right=50 mm/s) vs. the
kinematically-equivalent `driveTwist` yaw-rate command, the two now
agree to within 0.0032 deg/s (pure integer-quantization rounding on
the centidegrees/s parameter). The old `/115` divisor was 4.31% off
from the corrected value, matching the issue's cited figure.

**Gates run in the foreground**: `node_modules/.bin/tsc --noEmit -p
tsconfig.json` (clean), `uv run pytest tests/host/
test_wire_constants_drift.py tests/host/
test_archaeology_marker_budget.py` (20 passed -- the archaeology-marker
ratchet stayed at/under its 388 budget despite the extensive comment
rewrites), `uvx ruff check tools tests` (clean, no Python touched).

**Local-editor verification**: no browser-automation tool was
available this session, so the live JS->Blocks click-through and
simulator start-icon check (this ticket's remaining unchecked
acceptance criterion) were not empirically observed. Verified instead:
`pxt serve --noBrowser --noauth --noSerial` boots cleanly (only the
doc's own documented harmless `ENOENT ... scandir 'libs'` message) and
`curl http://localhost:3232/index.html?ws=fs` returns HTTP 200 with
these changes in place; a standalone `pxt decompile` attempt (as a
non-browser proxy for the same check) hit a pre-existing, unrelated
environment gap -- the `pxt-microbit` target's `libs/` directory was
never built in this checkout, the same condition the doc already
documents. `pxt serve` was stopped and the ports (3232/3233) confirmed
clear afterward.
