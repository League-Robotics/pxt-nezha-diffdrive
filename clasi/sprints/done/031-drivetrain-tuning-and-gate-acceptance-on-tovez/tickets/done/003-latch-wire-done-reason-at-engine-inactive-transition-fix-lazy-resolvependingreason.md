---
id: '003'
title: Latch wire done-reason at engine-inactive transition (fix lazy resolvePendingReason)
status: done
use-cases:
- SUC-004
depends-on: []
github-issue: ''
issue: wire-done-reason-is-resolved-lazily.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Latch wire done-reason at engine-inactive transition (fix lazy resolvePendingReason)

**Type: (b) desk code change — programmer.**

## Description

`WireAdapter::resolvePendingReason()` (`src/comms/wire_adapter.cpp`)
decides `kStop` vs `kTimeout` by checking `hasLiveMotionObligation()` at
the moment something RESOLVES the pending goal
(`resolvePendingIfDue()`, driven by STATUS/ack traffic) — not at the
moment the engine's move actually went inactive. A pivot that arrives
in 1.4 s reads `reason=stop` if a STATUS poll happens to land before
the 5 s lease elapses, and `reason=timeout` if the next poll arrives
after — MEASURED tovez 2026-09-04,
`captures/bench-acceptance-029-20260904d/pivot-gates-gain2.log` vs
`g1-run.log` (`wire-done-reason-is-resolved-lazily.md`).

Latch the reason at the point the tick service hook observes
`engineMoveActive()` transition to false (that hook already runs every
tick, per `src/DESIGN.md` §5's motion-obligation section), or record
the lease deadline against the engine's own end time rather than
`now_()` at resolution time. Either approach must not change
`resolvePendingReason()`'s two possible OUTPUT values (`stop`/
`timeout`), only when the decision is made.

## Acceptance Criteria

- [x] A segment that arrives well inside its lease reports
      `reason=stop` regardless of when STATUS/ack traffic next polls,
      including a poll that lands after the OLD lease deadline would
      have elapsed.
- [x] No change to the wire grammar's `done=`/`reason=` value set or to
      any other verb's behavior.
- [x] A host test: arrive early, advance the simulated clock past the
      old lease boundary, confirm STATUS reads `reason=stop` (not
      `timeout`).
- [ ] An on-hardware spot check (can ride along in Session B, ticket
      009) reproduces a `reason=stop` result on a segment shaped like
      `pivot-gates-gain2.log`'s Phase B case. UNVERIFIED -- no hardware
      access in this dispatch; left for the Session B bench run.

## Testing

- **Existing tests to run**: `tests/host/` wire-adapter suite (the
  files exercising `resolvePendingReason`/`resolvePendingIfDue`/
  `hasLiveMotionObligation`).
- **New tests to write**: the early-arrival-then-late-poll host test
  described above.
- **Verification command**: `uv run pytest tests/host/`
