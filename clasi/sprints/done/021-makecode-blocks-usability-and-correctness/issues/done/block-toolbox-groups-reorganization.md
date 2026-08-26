---
status: done
sprint: '021'
tickets:
- 021-004
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

## Decision (delegated by Eric to team-lead, 2026-08-26 -- APPROVED)

Eric delegated this call rather than reviewing a layout ("you just make a
decision on it... just look at it and make it better"). The stakeholder gate
in sprint 021 is therefore satisfied by this section. Ground truth: 39 blocks,
enumerated from the `//%` annotations across `src/blocks/*.ts`.

### Three problems being fixed

1. **Stop is not a kind of driving.** All five stop/estop blocks currently sit
   in **Drive**, next to `set wheel speeds`. Stop gets its own top-level group.
2. **`on run` is not a move.** Remote invocation sits in **Move** purely
   because it needed somewhere to go.
3. **World mixes "use it" with "calibrate it."** OTOS sensor calibration sits
   beside `go to world x/y`.

### Approved layout

Declare order explicitly via `groups=[...]` on the namespace at
`src/blocks/motion.ts:55` -- there is no `groups=` declaration today, so drawer
order is currently whatever pxt infers. Order: Move, Drive, Stop, World, Pose,
Remote, World Setup, Setup.

| Group | Blocks | Advanced |
|---|---|---|
| **Move** | `move`, `go to x/y`, `while moving`, `while going to`, `moving?`, `stop move` | `start move`, `start go to`, `move progress` |
| **Drive** | `set wheel speeds`, `drive turning`, `drive tick` | -- |
| **Stop** *(new)* | `stop`, `emergency stop`, `is stalled` | `clear emergency stop`, `clear stall latch` |
| **World** | `start world tracking`, `set world pose`, `world tracking ready?`, `go to world x/y`, `read world position`, `world x`, `world y`, `world heading` | -- |
| **Pose** | `pose x`, `pose y`, `heading`, `reset pose` | -- |
| **Remote** *(new)* | `on run`, `on run command`, + `set radio group` ([[radio-group-setup-block]]) | -- |
| **World Setup** *(new)* | -- | `calibrate world sensor`, `set world sensor offset`, `set arrival tolerance` |
| **Setup** | -- | `set default speed`, `set default turn rate`, `set track width`, `set wheel calibration`, `set config` |

39 blocks in, 39 out (+1 new `set radio group`). Verify the count.

### Two calls that differ from the earlier draft, with reasoning

- **The draft folded stop/estop into an advanced `Setup` group** ("tuning +
  stall/estop diagnostics"). Rejected. Advanced drawers are collapsed by
  default; `stop` is the block a student needs to find fastest, and a safety
  control must never be one disclosure click away. Only the two *latch-clearing*
  blocks are advanced -- they are recovery, not stopping.
- **The draft put all OTOS setup in an advanced `World Setup` group.**
  Narrowed. `start world tracking` and `set world pose` are *mandatory* steps
  before `go to world x/y` works at all, so hiding them would break the
  feature's discoverability. `World Setup` keeps only true sensor calibration.

### Mechanics

`//%` `group=`/`weight=`/`advanced=` annotation edits across `src/blocks/*.ts`
plus one `groups=[...]` on the namespace. No signature, shim, or C++ change.
Verify by loading the toolbox in the local editor and confirming every group
renders in the declared order with the block counts above.
