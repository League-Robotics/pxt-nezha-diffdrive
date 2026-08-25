---
id: '012'
title: 'main.ts modularization: split the 1034-line block API into modules'
status: ticketing
branch: sprint/012-main-ts-modularization-split-the-1034-line-block-api-into-modules
use-cases: []
issues:
- break-up-main-ts-into-modules.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 012: main.ts modularization: split the 1034-line block API into modules

> **Arc position.** Last of the planned sprints out of the 2026-08-23 code
> review (`docs/code-review/2026-08-23/review.md`) — after sprint 004
> (radio/wire transport, ticketing), sprint 005 (bench tooling, roadmap,
> blocked on 004's hardware checkpoint), sprint 006 (motion correctness,
> roadmap), sprint 007 (student API, roadmap), sprint 008 (wire hardening,
> roadmap), sprint 009 (comment/provenance hygiene, roadmap), sprint 010
> (port-layer robustness, roadmap), and sprint 011 (hardware validation,
> roadmap). It runs last **by necessity, not by triage order**, for two
> concrete reasons:
>
> 1. **Sprint 009 audits and rewrites comments keyed to file-and-line
>    coordinates**, `src/main.ts` included (135 items of the 854-block
>    comment work order touch this file). Splitting main.ts before 009
>    lands invalidates every one of those coordinates the moment a comment
>    moves to a different file at a different line; running 009 first
>    means the split just carries already-correct comments to their new
>    homes, with no rework.
> 2. **Sprints 006 and 007 substantively edit code inside main.ts**: 006
>    rewrites the `goTo`/`startGoTo` arc geometry and pivot-split logic
>    (lines ~285-378 today); 007 adds the stall-latch clear/readback
>    surface, fixes the `driveTick()` continuous-drive contract, resolves
>    the cruise sentinel on the block side, fixes the simulator's turn-rate
>    and e-stop parity bugs, adds a `rotationalSlip` setter, and guards
>    `runArgCount()` — touching the direct-drive functions, the RUN
>    dispatch, the simulator body, and the config setters respectively.
>    Every one of those edits lands in code this sprint would move. Running
>    the split first means 006 and 007 each rebase a real code change onto
>    a file layout that keeps changing underneath them; running it last
>    means the split touches settled code exactly once.
>
> Sprints 010 (port-layer robustness) and 011 (hardware validation) do not
> touch `main.ts` (grep-confirmed against both sprint plans) and are not
> blockers — they can land in any order relative to this one. Only 006,
> 007, and 009 gate this sprint's start.

## Goals

Theme: **the same 1034-line block API, filed under more than one name.**
Not one line of student-visible behavior, block appearance, or
generated-hex behavior changes — this is a restructuring sprint, and its
success is measured by what stays identical, not by what's new:

- Split `src/main.ts` into cohesion-sized modules along the lines
  `break-up-main-ts-into-modules.md` proposes — config, motion commands,
  local pose, world/OTOS + goToWorld, RUN dispatch, the browser simulator,
  and the shim surface — treated as a **starting proposal to validate
  during detail planning**, not a settled decision. Re-check the module
  boundaries against the code as it stands after 006/007/009 land, not
  against today's line numbers (see "Line-range drift" below).
- Update `pxt.json`'s `files` array so the new modules replace the
  `src/main.ts` entry, in file order that preserves PXT's
  compile-order-equals-file-order rule.
- Preserve, exactly, every PXT-specific load-bearing detail the issue's
  "Constraints that matter for this refactor" section names: the
  no-initializer/created-on-first-use pattern for `runParts`/`runNames`/
  `runHandlers`/`runAnyHandlers`/`runWired`, `//%` annotation adjacency to
  its signature, block `group=` toolbox placement, and the "never write
  `radio.` in a comment" landmine.
- Prove behavior neutrality with actual build and block-surface evidence,
  not an assertion that the diff "only moves code."

## Problem

`src/main.ts` (1034 lines as of this writing — see "Line-range drift on
verification" below) is the entire student-facing block API plus a
200+-line browser simulator wearing one filename. The 2026-08-23 code
review's modularity annex (DES-05 in `raw/modularity-api.md`) independently
reaches the same conclusion the filed issue does: seven distinct
responsibilities share the file, and `shims.cpp` on the C++ side has the
same shape (cross-referenced there, not duplicated as a second sprint).
Left as one file, every future edit to any one subsystem risks touching
lines that belong to another, and the file fails the cohesion test (its
purpose cannot be stated in one sentence without "and").

This sprint cannot run first, though, because the review's other
main.ts-touching work (006, 007) and the comment-hygiene sprint keyed to
main.ts's current line numbers (009) all have to land in settled code
before a restructuring sprint can move it without triggering rework in
three other sprints at once.

### Line-range drift on verification

The issue's proposed-split table was checked against the current
`src/main.ts` (1034 lines, confirmed) for this roadmap pass. The table is
directionally right — every named function is in the file and grouped
roughly where claimed — but several of its line-range boundaries have
already drifted or were never exact:

- Row 1 ("config state," ~49-104) mixes `defaultSpeed`/`defaultYawRate`
  (actually lines 49-50) with `setTrackWidth`/`setWheelCalibration`, which
  actually live at lines ~700-714, inside the "configuration" section
  (row 8's territory), not in 49-104.
- Row 2 ("RUN dispatch," ~73-245) and row 3 ("direct drive," ~106-138)
  overlap in the current file: the run-dispatch state variables are
  declared at lines 73-84, but `setWheelSpeeds`/`driveTwist`/`driveTick`
  (row 3's functions) sit at lines 90-141, *before* the actual RUN dispatch
  code (`wireRunDispatch`/`onRun`/`onRunCommand`/`runArg*`, lines 154-235)
  — the two rows' ranges are not physically separable as written.
- Row 6's world/OTOS block actually runs to line 524 (close); row 7's
  goToWorld block actually ends around line 643, with the stop/config
  section (row 8) starting at 645, not 652.
- Row 9 ("the simulator," ~730-950) is close (actual sim-state-and-tick
  block is lines 730-949) but row 10 ("shim surface," ~951-1000)
  undershoots: the OTOS/taper shim surface it describes actually runs from
  951 to line 1033, the last line before the namespace's closing brace.

None of this changes the split's basic shape — it confirms the module
boundaries are real, function-shaped things, not exact line spans, and
that whoever detail-plans this sprint should re-derive fresh line ranges
from the post-006/007/009 file rather than trusting either the issue's
table or this note's numbers, both of which will be stale by then.

## Solution

Detail Mode should:

1. Re-read `src/main.ts` fresh once 006, 007, and 009 have landed — the
   module boundaries the issue proposes are sound in shape, but the exact
   line ranges above are already approximate and will move further as
   those three sprints edit the file.
2. Sequence the simulator extraction (`sim.ts`) first among this sprint's
   own tickets. The 2026-08-23 review's modularity annex (DES-05) singles
   this out as the highest-value, lowest-risk cut: it is ~200 lines with
   zero coupling to anything hardware needs, and can move with no
   behavioral risk. The RUN dispatcher is the other zero-coupling piece
   per the same finding.
3. Move `config`/`motion`/`pose` together rather than independently — per
   DES-05, they share the `defaultSpeed`/`defaultYawRate` state and
   splitting them apart risks separating a value from the functions that
   read it.
4. For every module boundary, preserve the four PXT constraints verbatim
   (see Risks) and update `pxt.json`'s `files` array in the same ticket
   that introduces the file it lists.
5. Gate every ticket's acceptance criteria on a PXT build plus a
   block-surface comparison — see Test Strategy.

## Success Criteria

- `src/main.ts` is replaced by cohesion-sized modules (config, motion,
  pose, world, run dispatch, simulator, shims, or whatever boundary detail
  planning validates), each stating its purpose in one sentence without
  "and."
- `pxt.json`'s `files` array lists the new modules in place of
  `src/main.ts`, in an order that preserves current initialization
  behavior; the project builds green.
- A PXT build produces a `.hex`/block-surface result that is unchanged
  from the pre-split build in every way a student or host could observe:
  same block captions, same `group=` toolbox placement, same generated
  behavior for `test/test.ts` and `test/testrig.ts`.
- The run-dispatch state variables keep the no-initializer,
  created-on-first-use pattern in whichever file they land in; no boot-time
  panic (the panic-980 signature this pattern exists to prevent) appears
  in a smoke check after the split.
- No new file contains the literal string "radio." in prose (grep-checked)
  unless the project's actual `radio` package usage changes, which this
  sprint does not intend.
- Existing `tests/host` suite passes unchanged (a sanity check that the
  C++ side, which this sprint does not touch, stays untouched).

## Scope

### In Scope

- Splitting `src/main.ts` into modules along the lines
  `break-up-main-ts-into-modules.md` proposes (config / motion / pose /
  world / run / sim / shims), re-validated against the file as it stands
  after 006/007/009 land.
- Updating `pxt.json`'s `files` array to reference the new modules in
  place of `src/main.ts`.
- Preserving the four PXT-specific constraints the issue names: the
  run-dispatch no-initializer pattern, `//%` annotation adjacency, block
  `group=` placement, and avoiding the `radio.` literal-text landmine.
- Verifying behavior neutrality via a PXT build and block-surface/hex
  comparison (see Test Strategy).

### Out of Scope

- Any change to student-visible behavior, block appearance (captions,
  groups, parameter ranges), or wire-protocol behavior. This is a pure
  restructuring sprint.
- Any API rename a student would see — function names, block captions,
  and parameter names carry over unchanged.
- Any re-layout of the C++ side (`shims.cpp`, `diffdrive.*`,
  `motion_engine.*`, ports, transports). `shims.cpp`'s own monolith shape
  (DES-05) is a separate, unclaimed concern, not this sprint's.
- Applying the comment-hygiene work order — that is sprint 009's job,
  finished before this sprint starts; this sprint only carries
  already-correct comments to their new file homes, verbatim.
- Fixing any of the other code-review findings that happen to live in
  main.ts (stall latch, driveTick contract, cruise sentinel, simulator
  parity, rotationalSlip, runArgCount guard) — all owned by sprint 007,
  landed before this sprint starts.
- The `src/`/`test/` source-layout migration the issue mentions as a
  "parallel issue" — already done: `pxt.json`'s current `files`/`testFiles`
  arrays already reference `src/main.ts` and `test/test.ts`/`test/testrig.ts`,
  so this sprint's new modules land under `src/` as a continuation of that
  existing layout, not a second migration.

## Test Strategy

Behavior neutrality is the entire point of this sprint, so it needs actual
evidence, not an assertion that the diff "only moves code." What's cheaply
available in this project:

- **Build + hex comparison.** Produce a build before the split and one
  after (per the project's existing scratch-build/`mbdeploy` workflow) and
  diff the resulting `.hex`. If it is byte-identical (or differs only in
  source-map/file-path metadata that carries no runtime effect), that is
  the strongest available evidence nothing changed.
- **Block-surface comparison.** If the hex isn't byte-identical (source
  paths embedded in debug info are a likely, harmless cause), compare the
  generated block metadata instead — captions, `group=` values, parameter
  ranges, block ordering in the toolbox — before and after. This is the
  minimum bar: "the refactor compiled" is not the same claim as "the
  blocks still work," and a build succeeding says nothing about
  initialization-order or annotation-adjacency regressions that only
  surface at block-generation or runtime.
- **Simulator/test-program parity.** Run `test/test.ts` and
  `test/testrig.ts` in the PXT simulator before and after the split and
  compare output — these two files are exactly the load-bearing surface
  the "no-initializer" constraint exists to protect (a test file's
  top-level code running before a namespace initializer would resurrect
  the panic-980 boot death the pattern was built to prevent).
- **Existing host suite as a regression fence.** Run `tests/host` unchanged
  before and after. This sprint doesn't touch the C++ side, so this is a
  cheap check that nothing did so by accident.

Detail Mode should confirm these are actually run (not just described) as
part of each ticket's acceptance criteria — a PXT build that merely
type-checks is not sufficient evidence for this sprint's goal.

## Architecture

**Substantial/structural.** `src/main.ts` splits into six cohesion-sized
modules (`sim.ts`, `run.ts`, `pose.ts`, `stop.ts`, `world.ts`,
`motion.ts`) — 3+ modules touched clears the substantial-tier
module-count signal on its own, and the split introduces a genuine new
cross-module dependency class: previously-implicit, same-file
references between these responsibilities become explicit,
compile-order-sensitive, cross-file references within one TypeScript
namespace (the roadmap's "compact-to-substantial" framing is resolved
here, explicitly, as substantial). No dependency-direction change and
no data-model change — the other two substantial-tier signals don't
independently apply, but the module count and the new cross-module
dependency are each independently sufficient.

Per the `design_docs` overlay convention (this project has opted in),
the full write-up — Sprint Changes, the component/dependency diagram,
Migration Concerns, Risk, Design Rationale, and Open Questions — lives
in this sprint's `design/` overlay, not here:
[`design/src-root-DESIGN.md`](design/src-root-DESIGN.md) §9 (current
module structure) and §15 (the sprint 012 record), and
[`design/design.md`](design/design.md) (one units-ladder table cell,
`main.ts` → the five new block-API files). Both overlay files'
`.diff.md` siblings are hand-written (no `generate_diffs` tool in this
project) and `validate_design` returns `ok: true` against this
overlay directory as of this planning pass.

The one line worth restating here without reading the overlay: this
sprint's entire technical risk is PXT-specific compile/load behavior
outside any host test's reach (§1's layering table places `main.ts`'s
successors outside the C++11 gate and `tests/host/` entirely) — the
sprint is sequenced (sim.ts first) so that its first ticket's build
doubles as the empirical proof the rest of the split relies on, rather
than asserting the split is safe from inspection alone. See the
overlay's Design Rationale for the full reasoning.

## Use Cases

Confirmed against `docs/design/usecases.md` (UC-001 through UC-016):
none needs a content change from this sprint — the file's own use-case
prose describes student-visible behavior, never file/line structure
(the one internal cross-reference, UC-007's "see `startMove`'s doc
comment in `main.ts`," is a pointer that stays accurate in spirit once
that doc comment moves to `motion.ts`, and is exactly the kind of
stale-pointer detail this sprint's doc-update tickets track). This
sprint adds no new SUC in the "a new capability now exists" sense
sprint 011's SUCs had — its point is that UC-001 through UC-016 all
continue to hold, unchanged, which is itself the scenario worth
stating explicitly rather than skipping:

### SUC-001: Every existing use case behaves identically before and after the split

A student (or the host-side test programs standing in for one) runs
any of UC-001 through UC-016 — install the extension, drive at a
constant speed, drive a straight distance, pivot, drive an arc, drive
a curved path to a point, start a move without blocking, run code
while moving, read pose, reset pose, stop/emergency-stop, clear an
emergency stop, calibrate the chassis, tune default speed/turn rate,
use the config escape hatch, develop in the browser simulator — and
observes no difference in behavior, block appearance, or generated-hex
output attributable to this sprint. This is the sprint's success
criterion restated as a use case: the six new files change where code
lives, never what it does. Evidence is the Test Strategy already in
this document (build/hex comparison, block-surface comparison,
simulator/test-program parity, the existing host suite as a regression
fence) plus each ticket's own build-and-simulator-run acceptance
criteria — not an assertion that "the diff only moves code."

### SUC-002: A future contributor can change one motion concern without reading the whole file

Today, editing anything in `main.ts` — a Pose fix, a World tuning
constant, a Setup default — means opening a single 1128-line (as of
this planning pass) file that also holds the RUN dispatcher and a
200+-line browser simulator, none of which the edit touches. After
this sprint, editing `pose.ts` means opening a ~40-line file whose
purpose is stated in one sentence with no "and." This is the
motivating use case behind the issue and the code review's DES-05
finding, restated concretely: sprints 009 (comment hygiene, already
planned) and any future sprint touching motion/pose/world/stop/RUN
code get smaller, single-concern diffs instead of a diff against a
file most of whose lines are unrelated to the change. Not independently
tested by this sprint (there is no "file is easier to read" test) —
served by the module boundaries themselves, reviewed for cohesion in
this sprint's own architecture self-review (see the overlay's Design
Rationale for how each boundary was chosen and re-checked against the
real file rather than assumed from the issue's proposal).

### SUC-003: A student opening the Blocks editor sees the same toolbox

The Drive/Move/Pose/World/Setup toolbox groups, their block captions,
and their parameter ranges are unchanged — a student who already knows
where `set wheel speeds` or `go to world x %x cm y %y cm` lives in the
toolbox finds it in the same place after this sprint ships, because
`//%` annotations (including `group=`) travel verbatim with their
functions into the new files (Success Criteria; verified per-ticket
via block-surface comparison, not asserted from the fact that the
annotation text itself is unchanged — PXT toolbox layout also depends
on load order and file structure in ways worth actually checking, not
assuming).

## GitHub Issues

None. This sprint's one issue (`break-up-main-ts-into-modules.md`) is
an internal CLASI issue file, not a GitHub issue — no `gh-import`
provenance to propagate.

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [x] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections)
- [x] Architecture review passed (or skipped, for changes with no
      architectural impact)
- [ ] Stakeholder has approved the sprint plan

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | Extract sim.ts: the browser-simulator shim surface, plus the pre-split baseline build | — |
| 002 | Extract run.ts: the RUN command dispatcher | 001 |
| 003 | Extract pose.ts: local pose readback | 001 |
| 004 | Extract stop.ts: stop and fault-latch blocks | 001 |
| 005 | Extract world.ts: OTOS world-pose tracking and goToWorld | 001 |
| 006 | Extract motion.ts: config, direct drive, and position-mode moves; retire main.ts | 001, 002, 003, 004, 005 |
| 007 | Final build checkpoint: hex and block-surface parity, flashable hex, handoff notes | 006 |

Tickets execute serially in the order listed. Tickets 002-005 each
depend only on 001 (sim.ts must exist before anything calls into its
shim bodies) — they have no dependency on each other, but execute in
this listed order by convention (simplest/most self-contained first:
run.ts is fully self-contained, pose.ts and stop.ts are small and
single-purpose, world.ts is the largest of the four and benefits most
from the cross-file pattern being proven three times over already).
Ticket 006 depends on all five prior extractions in the practical
sense that it is "whatever remains once everything else is carved
out," not because each one is a strict technical prerequisite. Ticket
007 depends on 006 alone but implicitly verifies the whole sprint.
