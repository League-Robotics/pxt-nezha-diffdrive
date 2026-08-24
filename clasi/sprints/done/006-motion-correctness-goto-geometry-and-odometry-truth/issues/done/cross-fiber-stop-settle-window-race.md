---
status: done
sprint: '006'
tickets:
- 006-002
---

# Cross-fiber stop lands in the kernel settle window ~⅓ of the time

Priority: **High** — code review 2026-08-23, R-08 (BLK-01; CONFIRMED, timing
independently re-derived in `verify-blocks.md`).

`stopMove()`/`stop()` called from another fiber — or `isMoving()` polling
that ends a move at its deadline — can land inside `kernel.step()`'s settle
window (staged-only `neutral()` at `diffdrive.cpp:364-368`; snapshot at
:472, duty write at :493, settle sleeps at :496/:500). The stop is staged
but not delivered; the delivery gate (`shims.cpp:466/482`) reads
`wasActive` only after `step()` returns. Wheels hold their last duty until
the lease watchdog fires ~100–150 ms later — reintroducing the measured
+9–13°/turn overshoot that the settle logic was built to eliminate.

Window arithmetic: 8 ms settle + busy lead-in of a 24 ms tick ≈ roughly a
third of calls. Reachable from documented blocks (e.g. a button handler
calling `stop` during `while moving`).

## What to do

Deliver staged neutral inside `step()`'s settle path (or make the stop path
push duty directly through the anti-latch pipeline). Honor the one-ticker-
per-move constraint documented in issue
`settle-tick-loop-is-not-host-testable` — do not fix this by adding a second
ticker.
