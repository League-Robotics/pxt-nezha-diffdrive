---
status: pending
---

# Reorganize the DiffDrive block toolbox groups

## Problem

Eric (2026-08-25): the Move / Drive / World segments and
World-vs-Setup blocks "don't feel like cohesive groups." Current
`//% group=` layout across `src/blocks/`:

- **Drive**: continuous-mode (`setWheelSpeeds`, `driveTwist`) in
  motion.ts, plus all five stop/estop blocks in stop.ts
- **Move**: `driveTick`, position moves (`move`, `goTo`,
  `whileMoving`, `whileGoingTo`, async starts, `isMoving`,
  `moveProgress`, `stopMove`) in motion.ts, plus `onRun` /
  `onRunCommand` in run.ts
- **Setup**: speed/turn-rate/track-width/calibration/config setters
- **Pose**: pose.ts blocks
- **World**: everything in world.ts — world setup AND world moves mixed

## Direction (draft reviewed once by team-lead, needs Eric's approval)

- **Move**: `move`, `go to x/y`, `while moving`, `while going to`,
  `moving?`, `move progress`, `stop move`; async starts advanced.
- **Drive**: `set wheel speeds`, `drive … turning`, `drive tick`.
- **Remote**: `on run`, `on run command`, plus the new
  `set radio group` block ([[radio-group-setup-block]]).
- **World**: world-frame moves and read-only queries.
- **World Setup** (advanced): OTOS calibration/pose/offset/tolerance.
- **Setup** (advanced): speed/turn-rate/track-width/tuning +
  stall/estop diagnostics.

Acceptance criterion is Eric's cohesion judgment: present the full
layout (every block's group/weight/advanced) for his review BEFORE
editing. Mechanically the change is `//% group=`/`weight=`/
`advanced=` annotation edits only across `src/blocks/*.ts` — no
signature, shim, or C++ change; verify by loading the toolbox in the
local editor.
