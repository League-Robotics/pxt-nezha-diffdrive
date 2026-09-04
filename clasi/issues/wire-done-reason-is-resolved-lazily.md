---
status: pending
sprint: '031'
---

# Wire `done= reason=` is resolved lazily, so an early arrival reads `timeout`

Priority: **Low** · Found 2026-09-04 during sprint 029 ticket 007 on tovez.

## Description

`WireAdapter::resolvePendingReason()` decides `kStop` vs `kTimeout` by
asking `hasLiveMotionObligation()` AT THE MOMENT SOMETHING RESOLVES the
pending goal (`resolvePendingIfDue()`, driven by STATUS/ack traffic), not
at the moment the engine's move went inactive. A `MOVE_X 0 1571 100 5000`
pivot that arrives at 1.4 s is labelled `stop` if a STATUS poll lands
before 5 s and `timeout` if the next line arrives after the lease
elapsed. MEASURED tovez 2026-09-04:
`captures/bench-acceptance-029-20260904d/pivot-gates-gain2.log` (Phase
B: every pivot `timeout`) versus `g1-run.log` (same pivots, STATUS
polled at 8 Hz: every one completes in 1.28-1.45 s, `stop`).

Diagnostic label only -- the motion itself is unaffected -- but any tool
that classifies a run by `reason=` (the tour tools, the acceptance
scripts) reads a healthy early arrival as a deadline hit.

## Remedy

Latch the reason when the engine transitions inactive (the tick service
hook already observes `engineMoveActive()` every tick), or record the
lease deadline against the engine's own end time rather than `now_()`
at resolution. Host test: arrive early, advance the clock past the
lease, then STATUS -> `reason=stop`.
