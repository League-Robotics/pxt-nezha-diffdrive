---
status: pending
sprint: 008
---

# Wire timeout hardening: reject 0, cap 2^31, make verbs agree

Priority: **High** — code review 2026-08-23, R-06 + R-18 (KERN-06 +
WIRE-02; both CONFIRMED end-to-end).

Two timeout edge cases, one inconsistency:

1. **`WHEELS_X … timeout 0` (R-06)**: decode accepts 0; the motion
   obligation dies at `now+0` (nothing ticks, host sees `ok`), but a
   wall-clock ~10 s kernel lease stays armed — the robot lurches into the
   stale command whenever anything next ticks. Meanwhile `MOVE_X … 0` is an
   instant silent no-op: the two verbs disagree about what 0 means.
2. **Timeouts > 2^31 ms (R-18)**: `parseUint32` admits up to 4294967295;
   the deadline arithmetic wraps negative (`(int32_t)(-t) ≥ 0` for
   t > 2^31); the obligation never arms and the watchdog kills the acked
   move ~150 ms in — the ticket-011 starvation bug resurrected for large
   timeouts. (`wire_adapter.cpp:294-382,414-420`.)

## What to do

- Reject or clamp timeout 0 at decode; define one meaning across all X
  verbs; ensure the kernel lease is capped/cleared with the obligation.
- Cap timeout at decode (e.g. ≤ 2^31−1, or a sane protocol max).
- The existing host-test parametrize maxes at 5000 ms — add the boundary
  values (0, 2^31−1, 2^31, uint32-max); one added parameter would have
  caught R-18.
