---
status: done
sprint: '016'
tickets:
- 016-003
- 016-004
---

# The wire's motion obligation is never cleared on completion, so the protocol fiber co-ticks for the whole timeout

Priority: **High** -- and it is a concrete candidate mechanism for
`i2c-fault-count-climbs-on-idle-bus.md`, which should be re-checked against it
rather than investigated separately.

## Mechanism

All six motion verbs set `motionObligationActive_ = true`
(`wire_adapter.cpp:345, 376, 405, 428, 449, 487`). It is cleared in exactly two
places: `onEstop()` (`:536`) and `onStop()` (`:568`). **Natural completion never
clears it** -- `resolvePendingIfDue()` clears `pendingActive_` and leaves the
obligation armed.

`protocol.cpp:355` reads it as the protocol fiber's tick gate:

```cpp
if (wireAdapter_.hasLiveMotionObligation()) { tickDrive(); }
else { fiber_sleep(kPollIntervalMs); }
```

So after **any** wire motion verb, the protocol fiber ticks the kernel at 24 ms
for the whole declared `timeout` -- regardless of when the move actually
finished. `timeout` is a mandatory backstop the API tells hosts to set
generously, and the only ceiling is `kMaxMotionTimeoutMs` = 2^31-1 ms =
**24.8 days**.

## Why it matters beyond waste

1. **Idle-looking I2C traffic.** Directly matches what
   `i2c-fault-count-climbs-on-idle-bus.md` observes: `i2cf` climbing while the
   robot does nothing.
2. **Two fibers on the bus.** `stepBusy` (`shims.cpp:521`) serializes
   `kernel.step()` correctly -- but an OTOS read is not a `step()`.
   `blocks/world.ts:9` states the invariant plainly: OTOS reads "must be called
   from the same fiber that calls `driveTick()` -- never concurrently with one
   (an OTOS transaction landing inside the Nezha encoder's select->read window
   destroys that encoder sample)." A `RUN:` tour handler doing `readWorld()` on
   the event fiber while the protocol fiber sits in `step()`'s 4 ms settle
   window is exactly that collision -- and one earlier wide-timeout `MOVE_X` is
   enough to keep the protocol fiber ticking for the whole tour.
3. A stale obligation survives across unrelated later work in the same session.

Noted asymmetry: `onWheelsV`/`onMoveV` bound `duration` at
`kWheelsVDurationCeiling` (5000 ms, "a dead host cannot mean a runaway"), but
the four goal-directed verbs have no ceiling beyond the shared decode clamp.
Defensible for the *move* (it ends on arrival, not the clock) -- but the
obligation window inherits the unbounded value, and that is what causes the
tail.

## What to change

Clear `motionObligationActive_` in `resolvePendingIfDue()` and
`forceResolvePending()` -- the two places that already know the motion is over.
The flag then means "a motion is outstanding", which is what `protocol.cpp`
reads it as.

**Then re-check `i2c-fault-count-climbs-on-idle-bus.md`**: capture `i2cf` and
`cyc` across a session with and without a preceding wide-timeout `MOVE_X` and
see whether the climb tracks the obligation window. This is a hypothesis with a
mechanism, not a confirmed cause.

Detail: [`docs/code-review/2026-08-26/raw/correctness-wire-blocks.md`](docs/code-review/2026-08-26/raw/correctness-wire-blocks.md).
