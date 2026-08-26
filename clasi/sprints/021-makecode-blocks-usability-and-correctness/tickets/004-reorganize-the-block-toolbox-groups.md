---
id: '004'
title: Reorganize the block toolbox groups
status: open
use-cases: [SUC-005]
depends-on: ['001']
github-issue: ''
issue: block-toolbox-groups-reorganization.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Reorganize the block toolbox groups

## Description

Reassign every existing block to the eight approved toolbox groups and
declare their drawer order, per `block-toolbox-groups-reorganization.md`'s
"Decision" section — a stakeholder-delegated, already-approved layout.
This is annotation-only: `//% group=`/`weight=`/`advanced=` edits across
`src/blocks/motion.ts`, `stop.ts`, `world.ts`, `run.ts`, plus one new
`groups=[...]` declaration on the `diffDrive` namespace (`motion.ts:55`,
which today has no `groups=` at all, so drawer order is whatever pxt
infers). No signature, shim, or C++ change — do not touch any block's
parameters, its `block=` string, or any `.cpp`/`.h` file.

Do not re-litigate the layout itself — it is decided. If something in
the approved table doesn't fit the current code (a listed block that
doesn't exist, or vice versa), that is a discrepancy to flag, not a
license to redesign.

Runs after ticket 001 (verification uses the local-editor doc) but is
independent of tickets 002/003 (different files: this ticket never
touches `sim.ts`). Ticket 005 (radio-group block) depends on this one
completing first, since it places its new block into the Remote group
this ticket creates.

## Acceptance Criteria

- [ ] `groups=[...]` on the `diffDrive` namespace (`motion.ts:55`)
      declares, in order: Move, Drive, Stop, World, Pose, Remote,
      World Setup, Setup.
- [ ] Every block's `//% group=`/`advanced=` matches the approved table
      exactly, including both departures from the earlier draft:
      - `stop`, `emergency stop`, `is stalled` are top-level in Stop
        (not advanced); only `clear emergency stop` and
        `clear stall latch` are advanced.
      - `start world tracking`, `set world pose`,
        `world tracking ready?`, `go to world x/y`,
        `read world position`, `world x`/`y`/`heading` stay in World
        (not moved to World Setup); only `calibrate world sensor`,
        `set world sensor offset`, `set arrival tolerance` move to the
        new World Setup group.
      - `driveTick` moves from Move into Drive.
      - `on run`/`on run command` move from Move into the new Remote
        group (leaving a slot in Remote for ticket 005's new block —
        do not assign it a weight that would force a specific
        position relative to a block that doesn't exist yet).
    - [ ] Resolve any weight collisions created by blocks moving between
      groups (e.g. `driveTick`'s old Move weight vs. `set wheel
      speeds`'s existing Drive weight) — no two blocks share a weight
      within the same group.
- [ ] Total existing block count is unchanged: 39 in, 39 out (verify by
      counting `//%` block annotations across the four files before and
      after).
- [ ] No `.ts` function signature, `shim=` binding, or any `.h`/`.cpp`
      file changes.
- [ ] In the local editor (per ticket 001's doc), the toolbox renders
      all eight groups in the declared order with the correct blocks in
      each.

## Implementation Plan

**Approach**: Work file by file against the approved table:
`motion.ts` (add `groups=[...]`; reassign `driveTick`, the Setup-group
blocks stay Setup), `stop.ts` (make the four non-latch-clearing blocks
top-level, keep the two latch-clearing blocks advanced), `world.ts`
(split World vs. the new World Setup per the table), `run.ts` (move
`on run`/`on run command` into Remote). Recheck per-group weights after
reassignment — blocks moving into a group with existing blocks can
collide with an existing weight value.

**Files to create/modify**:
- `src/blocks/motion.ts` (namespace `groups=[...]`; `driveTick`
  reassignment; Setup-group blocks unchanged in group, re-check
  weights)
- `src/blocks/stop.ts` (group/advanced reassignment)
- `src/blocks/world.ts` (World vs. World Setup split)
- `src/blocks/run.ts` (Move -> Remote for `on run`/`on run command`)
- `src/blocks/pose.ts`: verify only — the approved table keeps Pose
  unchanged (4 blocks), so no edit is expected, but confirm rather than
  assume.

**Testing plan**: Local editor toolbox review (per ticket 001's doc) —
open the DiffDrive category, confirm group order and membership match
the approved table block-for-block. `node_modules/.bin/tsc --noEmit -p
tsconfig.json` to confirm the annotation-only edits didn't break
compilation. No hardware verification needed (annotation-only, no ABI
surface).

**Documentation updates**: None expected — the toolbox structure isn't
separately documented outside the blocks' own `//%` annotations and
`docs/design/usecases.md` (which this ticket doesn't touch).
