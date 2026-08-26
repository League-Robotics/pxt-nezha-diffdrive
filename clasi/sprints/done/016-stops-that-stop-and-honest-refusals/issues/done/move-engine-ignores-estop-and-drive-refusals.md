---
status: done
sprint: '016'
tickets:
- 016-002
---

# `serviceMove()` never checks `estopped`, and `kernel_.drive()`'s refusal is discarded everywhere

Priority: **High** -- two small fixes that together remove a class of silent
30-second nothings, and retire a load-bearing undocumented calling order.

## (a) `serviceMove()` does not end on e-stop

`motion_engine.cpp:352` ends a move on distance/yaw margin, deadline,
`out.stallHalted`, or wrong-way. **`out.estopped` is not in that list**, though
it is the same kind of published latched refusal as `stallHalted`.

The kernel does refuse to drive under the latch (`diffdrive.cpp:485`), so the
**wheels are safe**. The move engine does not know, so `isMoveActive()` stays
true, `isMoving()` keeps answering yes, `progress()` freezes, and every
`while (driveTick())` loop spins until the deadline.

Measured (latching the kernel e-stop mid-move on a 30 s-timeout move, which is
what `emergencyStopMotors()` does as a side effect):

```
  mid-move                       dutyL= 10.7%  dutyR= 10.7%  moveActive=1
  10 ticks after estop latch     dutyL=  0.0%  dutyR=  0.0%  moveActive=1
  move stayed 'active' for 1230 further ticks (29.5 s) after the e-stop
```

Masked today only because `shims.cpp:722 estopAll()` happens to call
`engine.endMove()` *before* `kernel.estop()`. The safety of the path rests on an
undocumented calling order in a different file -- and
`kernel.emergencyStopMotors()` latches the e-stop as a *side effect*
(`diffdrive.cpp:379-381`) that the kernel header does not document, so any
future caller reaching for it directly reopens this.

**Fix**: add `|| out.estopped` to `serviceMove()`'s end condition.

## (b) `drive()`'s `Status` return is ignored at all four call sites

`DifferentialDrive::drive()` returns `kRefusedNotBegun`, `kRefusedEstopped`,
`kRefusedUnconfigured`, `kRefusedNonFinite`. `MotionEngine` discards it at
`motion_engine.cpp:49`, `:83`, `:137` (the one that arms `move_.active`), and
`:340`.

A refused move still arms, still reports progress, still spins to its deadline,
and still resolves as `kStop` on the wire -- indistinguishable from a move that
ran and stopped normally. The kernel latches the first refusal in `lastError()`
(`diagValue(20)` / `probe(20)`); nothing between it and any caller reads it.

**Fix**: `startSegment()` should not set `move_.active` when its own `drive()`
was refused. That turns a silent 30-second nothing into an immediate honest
"no", and gives `resolvePendingReason()` something truthful to report.

Detail: [`docs/code-review/2026-08-26/raw/correctness-stop-paths.md`](docs/code-review/2026-08-26/raw/correctness-stop-paths.md).
