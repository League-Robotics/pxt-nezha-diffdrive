---
id: '004'
title: Propose and apply toolbox group reorganization
status: open
use-cases: []
depends-on: ['002']
github-issue: ''
issue: block-toolbox-groups-reorganization.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Propose and apply toolbox group reorganization

## Description

The current `//% group=` layout doesn't read as cohesive (Eric's own
words: "don't feel like cohesive groups"). Current state, inventoried
during sprint planning (all block labels, current group, weight):

**Drive** (motion.ts): `set wheel speeds` (w200), `drive ... turning`
(w190). **Drive** (stop.ts): `stop` (w180), `emergency stop` (w170),
`clear emergency stop` (w160, advanced), `is stalled` (w150), `clear
stall latch` (w140, advanced).

**Move** (motion.ts): `drive tick` (w200), `move ... turning` (w170),
`go to x/y` (w160), `start move ... turning` (w150, advanced), `start
go to x/y` (w140, advanced), `moving?` (w130), `move progress` (w120,
advanced), `stop move` (w110), `while moving` (w100), `while going to`
(w90). **Move** (run.ts): `on run` (w190), `on run command` (w180).

**Setup** (motion.ts, all advanced): `set default speed`, `set default
turn rate`, `set track width`, `set wheel calibration`, `set config`.

**Pose** (pose.ts, no explicit weights): `pose x`, `pose y`, `heading`,
`reset pose`.

**World** (world.ts): `start world tracking`, `world tracking ready?`,
`set world pose`, `read world position`, `world x/y/heading`,
`calibrate world sensor` (advanced), `set world sensor offset`, `set
arrival tolerance` (advanced), `go to world x/y` — setup and moves
mixed together in one group.

This ticket has TWO steps, and the second is gated on the first:

### Step 1 — Produce the proposal (do this first, always)

Write a proposed layout: which group each block moves to, its weight
(ordering within the group), and its `advanced=` flag. Base it on the
issue's own direction: everyday moves together; world-frame *moves*
separate from world/OTOS *setup*; `on run`/`on run command` arguably
their own "Remote" group next to the new `set radio group` block
(Ticket 002); stop blocks live with the moves students actually use;
tuning setters live under Setup/advanced. A reasonable starting point
(not a final answer — Eric's cohesion judgment is the acceptance
criterion, not this ticket's own aesthetic sense):

- **Move**: `move`, `go to x/y`, `stop`, `moving?`, `move progress`,
  `stop move`, `while moving`, `while going to`, `start move`
  (advanced), `start go to` (advanced) — the blocks a student reaches
  for constantly.
- **Drive**: `set wheel speeds`, `drive ... turning`, `drive tick` —
  continuous/manual-mode driving, a distinct mental model from
  position-mode `move`.
- **Remote**: `on run`, `on run command`, `set radio group` (new,
  Ticket 002) — "how does my program receive commands", one group.
- **World**: `go to world x/y`, `start world tracking`, `world
  tracking ready?`, `world x/y/heading` (read-only queries used in
  normal programs) — the world-frame moves and status a student
  actually programs against.
- **World Setup** (advanced, or `advanced=true` items within World):
  `set world pose`, `calibrate world sensor`, `set world sensor
  offset`, `set arrival tolerance` — OTOS/world configuration, not
  something touched every program.
- **Setup** (advanced): `set default speed`, `set default turn rate`,
  `set track width`, `set wheel calibration`, `set config`, `emergency
  stop`, `clear emergency stop`, `is stalled`, `clear stall latch` —
  tuning and safety/diagnostic blocks a student sets up once or
  reaches for only when something's wrong, not everyday moves.
- **Pose**: unchanged — `pose x/y`, `heading`, `reset pose`.

Deliver this proposal in a form Eric can review quickly (a table or
list in this ticket's own notes, or a message to him directly) — do
NOT touch `src/*.ts` until he approves it.

### Step 2 — Apply the approved layout (only after approval)

Once Eric approves (possibly with changes), make the `//%
group=`/`weight=`/`advanced=` annotation edits across `src/motion.ts`,
`src/stop.ts`, `src/run.ts`, `src/pose.ts`, `src/world.ts` to match.
This is annotation-only — no function signature, no block input/output,
no C++ call ever changes.

## Acceptance Criteria

- [ ] A proposed layout (every block's group/weight/advanced) is
      written and presented to Eric BEFORE any `src/*.ts` edit in this
      ticket.
- [ ] Eric has explicitly approved the layout (or an amended version
      of it) — record the approval (what was approved, any changes he
      requested) in this ticket before proceeding to Step 2.
- [ ] After Step 2, every block in `motion.ts`/`stop.ts`/`run.ts`/
      `pose.ts`/`world.ts` carries the approved `group=`/`weight=`/
      `advanced=` values.
- [ ] No block's TS signature, shim binding, or C++ call changed —
      diff should be `//%` comment lines only.
- [ ] In the local editor, the toolbox visually matches the approved
      layout (group names, block order within each group, which
      blocks are hidden under "more...").
- [ ] Full native and simulator builds still succeed (annotation-only
      change should not be able to break either, but verify).

## Implementation Plan

**Approach**: Two-step ticket with a hard stop for stakeholder review
between them — do not conflate "propose" and "apply" into one pass.
If Eric requests changes to the proposal, iterate on the proposal
before touching any file.

**Files to modify** (Step 2 only): `src/motion.ts`, `src/stop.ts`,
`src/run.ts`, `src/pose.ts`, `src/world.ts` — `//% group=`/`weight=`/
`advanced=` lines only.

**Testing plan**:
- No automated test coverage exists or is needed for toolbox layout
  (this project's tests are bench/editor verifications per
  sprint.md's Test Strategy).
- Local editor: load the toolbox after Step 2, visually confirm
  against the approved layout.
- Full build (native + simulator) as a regression check that no
  annotation syntax error was introduced.

**Documentation updates**: If `docs/design/specification.md` documents
current toolbox groups (it's described as "the authoritative
block-API reference" in `docs/design/design.md`), update it to match
the new layout after Step 2.
