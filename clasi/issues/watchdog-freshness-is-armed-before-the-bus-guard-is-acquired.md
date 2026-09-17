---
status: pending
---

# The starvation watchdog is re-armed by a fiber that then blocks

`tickDrive()` (`src/shims.cpp`) sets `r.lastTick = cycleStart` as its
second statement, **before** `r.busGuard.acquire(r.sleeper)` and before
`r.kernel.step()`.

`r.lastTick` is the starvation watchdog's only freshness signal
(`watchdogEntry()`, same file): every ~50 ms it forces a stop if more
than ~100 ms has passed since the last tick AND something looks like it
is driving.

So merely *attempting* a tick re-arms the watchdog. A fiber that calls
`tickDrive()` and then blocks — waiting on the bus guard, or stalled
inside `kernel.step()`'s own I2C traffic — has already refreshed
`lastTick` on its way in. If it blocks for longer than the timeout, the
watchdog cannot fire, because the signal it reads says a tick just
happened.

That is exactly backwards for the case the watchdog exists to catch:
the wheels keep their last commanded duty while the one mechanism meant
to stop them is held off by the blocked fiber itself.

## Proposed fix

Move the `lastTick` write to **after** the tick's own work, so it
records a tick that completed rather than one that started. Consider
recording the attempt separately if something needs to distinguish
"nobody is ticking" from "a tick is stuck".

Watch the interaction with `tickDrive()`'s absolute-deadline pacing,
which reads `cycleStart` for its own drift-free cadence — that use is
independent of the watchdog's and should keep the start stamp.

## Provenance

Found by source audit during sprint 039 ticket 002 and written up in
`docs/knowledge/2026-09-15-reverse-to-forward-drivetick-hang-diagnosis.md`;
confirmed independently by team-lead review of `tickDrive()`. UNVERIFIED
on hardware: no run has yet shown the watchdog failing to fire because
of this. It is a source-level defect, found while investigating the
reverse-to-forward hang
(`captures/calibratel-vevov-20260915/bench-log.md` runs 7-8), and it may
be why that hang left the motors under a stale command instead of being
stopped.

Deliberately not fixed inside ticket 002: it is a separate defect from
that ticket's two, and the same dispatch constraint applied (no host
test can reach `shims.cpp`'s fiber/watchdog machinery, so the fix cannot
be verified before landing). A hardware repro that reproduces the hang
is the natural place to test it — see the knowledge doc's procedure.
