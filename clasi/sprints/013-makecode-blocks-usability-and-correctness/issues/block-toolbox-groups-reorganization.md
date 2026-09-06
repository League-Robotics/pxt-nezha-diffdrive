---
status: in-progress
sprint: '013'
tickets:
- 013-004
---

# Reorganize the DiffDrive block toolbox groups

## Problem

Eric: the Move / Drive / World segments and World-vs-Setup blocks
"don't feel like cohesive groups". Current `//% group=` layout:

- **Drive**: continuous-mode (`setWheelSpeeds`, `driveTwist`) in
  motion.ts, plus all five stop/estop blocks in stop.ts
- **Move**: `driveTick`, position moves (`move`, `goTo`,
  `whileMoving`, `whileGoingTo`, async starts, `isMoving`,
  `moveProgress`, `stopMove`) in motion.ts, plus `onRun` /
  `onRunCommand` in run.ts
- **Setup**: speed/turn-rate/track-width/calibration/config setters in
  motion.ts
- **Pose**: pose.ts blocks
- **World**: everything in world.ts (world setup AND world moves mixed)

## Direction

Regroup for student comprehension, e.g.: everyday moves together;
world-frame *moves* separate from world/OTOS *setup*; `on run` blocks
arguably their own "Remote" group next to the radio-group block
([[radio-group-setup-block]]); stop blocks with the moves students
actually use; tuning setters under Setup/advanced. Exact grouping is a
design decision for the sprint plan — present the proposed toolbox
layout (groups, order, weights, advanced flags) for Eric's review
before implementing, since "feels cohesive" is the acceptance
criterion and he is the judge.

Mechanically this is `//% group=`/`weight=`/`advanced=` annotation
edits across src/motion.ts, stop.ts, run.ts, pose.ts, world.ts — no
behavior change, verify by loading the local editor toolbox.
