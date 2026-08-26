---
status: done
sprint: '016'
tickets:
- 016-001
---

# `stop move` does not stop a continuous drive, and the simulator says it does

Priority: **High** -- a stop block that does not stop, plus a
simulator/hardware divergence in the direction that trains students wrong.

## Measured

Via [`docs/code-review/2026-08-26/raw/stop_probe.cpp`](docs/code-review/2026-08-26/raw/stop_probe.cpp):

```
A. `stop move` after setWheelSpeeds(200,200):
  driving, before stop move        dutyL=  23.5%  dutyR=  23.5%
  one tick later                   dutyL=  23.5%  dutyR=  23.5%
  ten ticks later                  dutyL=  24.3%  dutyR=  24.3%   <-- and climbing

   the same sequence via `stop` (stopAll(), which also calls kernel.neutral()):
  one tick later                   dutyL=   0.0%  dutyR=   0.0%
```

The duty *rises* after the stop -- the PID makes up the ground the port-level
zero cost it. The visible effect on the robot is a stumble, not a stop.

## Mechanism

`shims.cpp:704 endMove()` calls `engine.endMove()` then `deliverStopNow()`.
`MotionEngine::endMove()` issues `kernel_.neutral()` **only if a move-engine
move was active** (`motion_engine.cpp:88`). After `setWheelSpeeds()` none is --
`wheelsV()` called `cancelMove()` on the way in. So nothing is staged;
`deliverStopNow()` writes port-level zeros; the kernel's commanded velocity mode
(holding `kLeaseMax`, one hour) is untouched, and the next `step()` re-commands.

`deliverStopNow()` being non-latching is correct and deliberate (sprint 006
ticket 002). The gap is that this one caller uses it *without* pairing it with
`kernel.neutral()`.

## Simulator parity

`blocks/sim.ts:208 _endMove()` sets `simVel = 0` and `simYawRate = 0` -- a full
stop. A student who develops in the browser sees `stop move` halt the robot,
then flashes it and it does not. Opposite direction from R-13 (2026-08-23),
same class.

## What to change

Decide the contract and make all three sites agree.

- **"End the move"**: drop `deliverStopNow()` from `endMove()` (keep it in
  `updateMove()` and `stopAll()`, where a move genuinely was active), and change
  `sim.ts`'s `_endMove()` to leave `simVel`/`simYawRate` alone.
- **"Stop"**: add `r.kernel.neutral()` -- one line -- and say so in the block
  doc.

The second is closer to what the caption promises and to what the simulator
already does.

Related, same family: `WHEELS_X 0 0 ...` / `MOVE_X 0 0 ...` are documented as
"a no-op -- nothing is driven" but likewise do not stop motion already in
progress. See `docs/code-review/2026-08-26/raw/correctness-stop-paths.md` (C-09).
