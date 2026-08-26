---
id: '021'
title: MakeCode blocks usability and correctness
status: roadmap
branch: sprint/021-makecode-blocks-usability-and-correctness
use-cases: []
issues:
- int32-sim-params-break-blocks-conversion.md
- simulator-crashes-at-on-start-startprotocol.md
- simulator-yaw-rate-divisor-diverges-from-hardware-track-width.md
- radio-group-setup-block.md
- block-toolbox-groups-reorganization.md
- document-the-local-makecode-editor-workflow.md
- make-deploy-accepts-a-silently-incomplete-hex.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 021: MakeCode blocks usability and correctness

> **Two governance notes carried from triage.** The toolbox reorganization
> (`block-toolbox-groups-reorganization.md`) is a draft layout reviewed once
> by team-lead, not a decision — no `//%` `group=`/`weight=`/`advanced=`
> annotation may be edited until Eric has approved the full before/after
> block-to-group mapping. The `make_deploy.py` build-gate ticket
> (`make-deploy-accepts-a-silently-incomplete-hex.md`) is this sprint's
> scope outlier: it touches build tooling, not blocks, and is included only
> because this sprint's own hardware verification (issue 1's shim-safety
> claim, the toolbox reorg's flash-and-check) leans on that gate meaning
> what it says. Eric may bounce it to a dedicated tooling sprint at review.

## Goals

Make the blocks extension usable and correct for a student sitting at the
local MakeCode editor: fix the three defects in `src/blocks/sim.ts` that
currently block basic JS<->Blocks conversion and simulator use, add a
radio-group Setup block, reorganize the toolbox groups (pending Eric's
approval of the layout), document the local-editor workflow this sprint's
own verification depends on, and close the build-gate hole that let a
27%-short hex report as a clean build.

## Problem

Three separate defects in `src/blocks/sim.ts` currently make the extension
close to unusable in the editor a student actually sits at:

- **JS->Blocks conversion fails outright.** `int32`-typed parameters on the
  sim-fallback shim functions trip pxt's decompiler typecheck (`TS9256:
  bit sizes are not supported for locals and parameters`) on every
  conversion attempt for a project using the extension. A sprint-013-era
  audit found `int32` params on ~10 functions, not just the two lines the
  error points at (`_setWheels`, `_driveTwist`, `_startMove`, `_cycleStat`,
  `_setGeometry`, `runCommandText`, `setTaperWindows`, `setTaperFloors`,
  and others).
- **The web simulator crashes at boot.** ~9 empty-bodied shim functions
  (`_startProtocol`, `_setGeometry`, `_setKernelValue`, `probe`,
  `setTaperWindows`, `setTaperFloors`, `setRampMs`, `otosSetOffset`,
  `otosZero`, `otosCalibrate`, `_clearStallLatch`) are emitted by pxt as
  native-only calls with no `pxsim` implementation, so the simulator
  throws on the first statement of `<main>` and dies with "Simulator
  crashed, no error handler."
- **The simulator disagrees with hardware, and with itself.** `_setWheels()`
  (`sim.ts:99`) divides yaw rate by a hard-coded 115, standing in for
  caliper-measured `trackWidth_` (114.2 mm) alone; hardware's equivalent
  path (`MotionEngine::wheelsV()`) divides by `effectiveTrackWidth()` =
  `trackWidth / rotationalSlip` = 119.96 mm — a 4.3% discrepancy. The
  sim's *other* turn path, `_driveTwist()`, already reproduces hardware's
  math exactly, so today `_setWheels()`- and `_driveTwist()`-driven turns
  disagree with each other before either is compared to hardware.

Beyond the sim/conversion defects, the toolbox itself doesn't read as
designed: Move/Drive/World groups mix continuous-drive, position-move, and
world-frame concerns, and nothing exposes the radio group a student's
program listens on (RX is already on by default at group 10 via
`ensureRadioReady()`, but nothing in the toolbox says so or lets it
change). And the knowledge needed to work on any of this — how to serve
the editor locally, see disk projects, build and flash a plain V2 hex
instead of MakeCode's unparseable universal hex — currently lives in one
evening's session memory (2026-08-25), not in the repo.

Finally, a build-gate integrity gap surfaced in sprint 016: `make_deploy.py`
judges build success purely from the compile log, so a stale vendored
`codal-microbit-v2` checkout produced a hex 27% short (1,046,410 vs the
correct 1,442,546 bytes) with a clean exit status and nothing in the log to
flag it. This sprint's own hardware verification rests on that gate
meaning what it says.

## Solution

Fix the `sim.ts` trio together — the int32 params, the empty-bodied shims,
and the yaw-rate divisor all live in one file, and the first two are
explicitly cross-referenced issues from the same editing session. Verify
in the local editor (`http://localhost:3232/index.html?ws=fs`): clean
JS->Blocks conversion, a simulator that boots without crashing, and — if
the divisor fix is accepted — `_setWheels()` and `_driveTwist()` producing
the same turn rate for the same input. Confirm on hardware afterward that
the TS-level type changes didn't touch the native shim ABI, the way
issue 1's own pre-verification already did (`RUN:go` on a patched build
landed a commanded 200 mm move at 200.3 mm).

Add the radio-group Setup block on top of the already-working
`ensureRadioReady()`/`kGroup = 10` default (`src/comms/radio_transport.*`),
applying idempotently whether the block runs before or after the radio
comes up, and leaving the fleet channel (4) fixed and out of student
control.

The toolbox reorganization is annotation-only (`//%` `group=`/`weight=`/
`advanced=` edits across `src/blocks/*.ts`, no shim or C++ change) but is
**gated on Eric's explicit approval of the proposed layout before any edit
lands** — present the full before/after block-to-group mapping for his
sign-off first; the issue's "Direction" section is a draft, not a
decision.

Write `docs/local-editor.md` from the already-working scaffold on
`claude/blocks-local-codeserver-test-bf93c6` (`.claude/launch.json` +
`projects/`), covering every gotcha the 2026-08-25 session hit: the
`?ws=fs` double-navigate, the `_history` auto-save-disabled
wedge, and building a plain V2 hex via `pxt build` + `mbdeploy` instead of
MakeCode's Download (which produces a universal hex that mass-erases the
board on a failed flash attempt).

Harden `make_deploy.py`'s triage with the two cheap assertions the issue
proposes — a `binary.hex` size floor set below the 1,423,241-1,442,546
byte band the last three checkpoints measured, and a check that all ten
nezha-diffdrive `.cpp` files appear as `Building CXX object` lines — before
this sprint's own build checkpoint leans on that gate.

## Success Criteria

- [ ] A project using the extension converts JS -> Blocks cleanly in the
      local editor: no `TS9256`, no Problems-pane error.
- [ ] The web simulator boots without crashing for a bare project using the
      extension (start icon shows; no "Simulator crashed" error).
- [ ] `_setWheels()`'s simulated yaw rate matches `_driveTwist()`'s for the
      same wheel-speed input, or the decision to leave them mismatched is
      recorded with reasoning.
- [ ] A hardware run (e.g. `RUN:go`) after the `sim.ts` changes lands within
      the same tolerance as pre-sprint firmware, confirming the TS-level
      type/divisor changes are shim-ABI-safe.
- [ ] A "set radio group" block exists in the toolbox, defaults to 10,
      works from `on start`, and is idempotent regardless of whether the
      radio has already come up.
- [ ] Eric has approved the toolbox group layout **before** any `//%`
      annotation is edited; the shipped layout matches what was approved.
- [ ] `docs/local-editor.md` exists, is linked from the README, and a
      fresh reader can serve the editor, see a disk project, and flash a
      plain V2 hex using only the doc.
- [ ] `make_deploy.py` rejects a hex below the size floor and a build
      missing any of the ten expected translation units, demonstrated with
      a synthetic short-hex case, while a genuine clean build still passes.

## Scope

### In Scope

`src/blocks/sim.ts` (int32 params, empty-bodied shims, yaw-rate divisor),
`src/blocks/*.ts` (toolbox group/weight/advanced annotations; new radio
Setup block), `src/comms/radio_transport.*` (radio group setter),
`docs/local-editor.md` (new) plus a README pointer, `tools/make_deploy.py`
(build-gate assertions).

### Out of Scope

- Playfield accuracy campaigns and the `travelCalib`/`goToWorld`/rotation
  work — that's sprint 020, independent of this one in source (020 is
  campaigns/tools on already-corrected motion; this sprint doesn't touch
  motion firmware at all).
- The pivot-overshoot and arc/stop-path work already closed in sprints
  015-019.
- Any simulator physics beyond the yaw-rate divisor — whether the sim's
  contract is exact hardware parity or an approximation is a question for
  this sprint's architecture pass, not a license to rewrite more of
  `sim.ts`.
- `make_deploy.py`'s stale-vendored-checkout detection (comparing the
  resolved `dockercodal` revision against the `codal.json` pin) — the
  issue flags this as "worth considering additionally," not required; the
  size floor and translation-unit count are the scoped fix.
- `cleartext-run-hangs-the-link-under-active-telemetry.md`-style wire
  concerns and anything in the v6 sequenced-command path — this sprint's
  remote-testing pattern (issue 6) uses unsequenced cleartext `RUN:name`
  only.

## Test Strategy

Two verification tracks, matching where each defect actually lives:

- **Local editor, software-only.** `http://localhost:3232/index.html?ws=fs`
  covers JS->Blocks conversion, the simulator-boot check, and the toolbox
  group layout review — all three are editor-observable and need no
  hardware.
- **Hardware, for anything touching the shim boundary or firmware.** `pxt`
  CLI build + `mbdeploy` flash + serial `RUN:` verbs confirms the `sim.ts`
  type changes don't affect the native shim ABI, and confirms the radio
  group block actually changes what the robot listens on.

The build-gate ticket needs its own negative test: a synthetic short hex
(or a mocked build log) that the strengthened `make_deploy.py` triage must
reject, alongside confirmation that a genuine clean build still passes.

The toolbox-reorganization ticket cannot proceed past "present the layout
for review" until Eric approves it — that stakeholder gate is independent
of whatever order the other tickets execute in, and blocks only that one
ticket's `//%` edits.

## Architecture

(Architecture for this sprint's change, sized to the change — a
one-paragraph note for a trivial sprint, a fuller write-up with
component/data-model detail for a substantial one. May read "N/A —
trivial" when the change has no architectural impact.)

### Architecture Overview

(High-level structure and component relationships, if applicable.)

### Design Rationale

(Significant decisions with alternatives considered and reasoning, if
applicable.)

### Migration Concerns

(Data migration, backward compatibility, deployment sequencing — or
"None" if not applicable.)

## Use Cases

(Use cases sized to the change — may read "N/A — trivial" for small
sprints that don't warrant new or updated use cases.)

### SUC-001: (Title)
Parent: UC-XXX

- **Actor**: (Who)
- **Preconditions**: (What must be true before)
- **Main Flow**:
  1. (Step)
- **Postconditions**: (What is true after)
- **Acceptance Criteria**:
  - [ ] (Criterion)

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [ ] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [ ] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|

Tickets execute serially in the order listed.
