---
id: '004'
title: Rig::softStop() consolidation and go-to deadline as a config field
status: open
use-cases:
- SUC-002
depends-on:
- '003'
github-issue: ''
issue: config-descriptor-table-softstop-goto-deadline.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Rig::softStop() consolidation and go-to deadline as a config field

## Description

**Depends on ticket 003** (the go-to-deadline field is added to the
config table 003 builds; doing this after 003 also means 003's own
`shims.cpp` diff has already landed, reducing merge noise in a heavily
shared file).

**Part A — `Rig::softStop()`.** The soft-stop triplet
(`engine.endMove()` + `kernel.neutral()` + the port-level immediate-zero
write, `deliverStopNow`-shaped) is written out independently in
`stopAll()`, `endMove()`, the starvation watchdog, and `updateMove()`'s
completion branch — four places that must agree. `deliverStopNow`
appears 15 times in `shims.cpp` as of this reading (calls plus
comments) — note this number will keep moving as other tickets land;
assert the target (exactly one definition), not a specific starting
count. Add `Rig::softStop()` and have all four call sites route through
it, deleting the duplicated triplet everywhere else.

**Part B — go-to deadline as a config field.** `pendingGoToDeadlineMs_`
(`shims.cpp:1523-1544`, `engineSetGoToDeadline()`/
`engineSetGoToYawRate()`) is a `shims.cpp`-local singleton that exists
purely to dodge PXT's 4-argument shim limit — **confirmed this lives
entirely in `shims.cpp`, with no `wire_adapter.cpp` involvement**,
lower-risk to move than the issue text alone suggests. Add the go-to
timeout as an ordinary field in the descriptor table ticket 003 built;
`engineSetGoToDeadline()`/`engineSetGoToYawRate()`'s existing TS-facing
call signatures are unchanged (they still exist as the pre-arming shim
calls `startGoTo`/`goTo` use) — only their internal storage moves from
a bespoke singleton field to the shared config table.

## Acceptance Criteria

- [ ] `grep -c 'deliverStopNow' src/shims.cpp` is 1 (sprint Success
      Criteria's own bar).
- [ ] `stopAll()`, `endMove()`, the starvation watchdog, and
      `updateMove()`'s completion branch all call `Rig::softStop()`;
      none duplicates the triplet inline.
- [ ] The go-to deadline is settable/gettable through the same
      descriptor table as every other config field (round-trip test).
- [ ] `pendingGoToDeadlineMs_` (or its successor storage) is no longer
      a bespoke, call-scoped singleton field.
- [ ] `engineSetGoToDeadline()`/`engineSetGoToYawRate()`'s existing
      call signatures (and every caller in `blocks/motion.ts`) are
      unchanged.

## Testing

- **Existing tests to run**: anything exercising `goTo`/`startGoTo`'s
  dual-rate reconciliation (`MotionEngine::reconcileDualRateCruise()`/
  `decomposeGoToR()` callers) to confirm the deadline's new storage
  doesn't change behavior; the watchdog/stop-delivery tests if any
  exist under `tests/host/`.
- **New tests to write**: a call-count or mock-port host test proving
  all four soft-stop call sites route through `Rig::softStop()`; a
  SET/GET round-trip test for the go-to deadline field.
- **Verification command**: `uv run pytest tests/host/`
