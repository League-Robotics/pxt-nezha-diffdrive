---
status: pending
sprint: '032'
---

# Odometry as an object that is the PoseSource; delete the three rebase-epoch copies

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: CO-02, CO-03 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)). Triage #10.
Depends on `kernel-reference-handling-...` (K4) and the design's lazy
origin capture for the engine half.

## Description

`Rig` holds `x/y/heading`, `odomPos*`, `odomPrimed`, two epochs;
`odomUpdate()` is a free function over them; `EncoderPoseSource` holds
`const float&` into `Rig` with a 45-line lifetime essay; `resetPose()`,
`seedPose()` and `SET rebase` are three writers with three different
pre-steps; `poseX()` mutates it as a side effect of reading. The
rebase-epoch guard is written in `odomUpdate()`, `serviceMove()` and
`progress()`. 08-26 Q-02 asked for this; sprint 028 made it more urgent.

## Remedy

- `Odometry` class (host-portable, `src/motion/` or `src/platform/`):
  `update(const Output&)`, `reset()`, `seed(x, y, h)`, implements
  `PoseSource` directly. Retires `EncoderPoseSource`, the lifetime essay,
  and the `Rig` fields.
- One epoch guard, inside `Odometry`. The engine's two copies go with the
  motion-profile design's lazy origin capture.
- Decide once whether pose reads advance odometry (today `poseX()` does,
  `updateMove()` gates on `wasActive`, `tickDrive()` does not gate).

## Acceptance

- `odomUpdate()`'s math moves unchanged into `Odometry::update()` with a
  host test that integrates a known wheel path.
- `grep -n positionEpoch src/motion src/shims.cpp` finds one reader.
