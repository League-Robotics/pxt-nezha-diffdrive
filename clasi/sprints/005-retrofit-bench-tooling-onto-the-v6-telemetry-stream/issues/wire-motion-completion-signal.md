---
status: in-progress
sprint: '005'
tickets:
- 005-004
---

# Wire hosts have no motion-completion signal

Priority: **Medium** — code review 2026-08-23, R-23 (WIRE-07; CONFIRMED as
landmine; targets sprint 005).

`lastDone()`/`lastDoneReason()` in `wire_adapter.h:318-321` are permanently
inert (`0`/`none`) — a documented sprint-003 decision. Combined with STATUS
hardcoding `otos=0` (issue `status-lost-diag-numeric-surface`) the only way
a host can observe "the move finished" is watching STATUS `active` flicker
at poll granularity. Sprint 005's closed-loop tour tooling needs a real
completion signal; neither sprint 004 nor 005 currently plans one
(verified against both sprint plans).

## What to do

Plan into sprint 005: either a DONE event line (fits the v6 grammar's
event surface) or truthful done/doneReason fields in STATUS, with the
motion engine actually publishing completion + reason (done, superseded,
timeout, stall, estop). Host tests for each terminal reason.
