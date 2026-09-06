---
id: '001'
title: Resolve dead tick-overrun counters left by cycleStat() deletion
status: done
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: dead-tick-overrun-counters-after-cyclestat-deletion.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Resolve dead tick-overrun counters left by cycleStat() deletion

## Description

Sprint 032 ticket 008 deleted `cycleStat()` (`src/shims.cpp`) and its
simulator stand-in `_cycleStat()` (`src/blocks/sim.ts`) after confirming
zero callers anywhere in the repo. It deliberately left the counters
those functions used to read — `r.tickOverrunCount` (`shims.cpp:188`,
incremented `shims.cpp:894`), `simCycleCount`/`simTickOverrunCount`
(`sim.ts:47-48`, incremented `sim.ts:364,378`) — out of scope. Those
three fields are now write-only: incremented every tick, read by
nothing (verified repo-wide by the issue itself, 2026-09-05).

Make the decision the issue leaves open, deliberately, and record it:

- **Default: delete.** Remove `r.tickOverrunCount` and both `sim.ts`
  counters and their per-tick increments — dead state that no longer
  earns its place, exactly this sprint's theme.
- **Alternative: wire up a real reader** only if a `DIAG`/`STATUS`
  field for Rig-level tick overruns (the `tickDrive()` pacing loop
  missing its own budget) is genuinely wanted, distinct from the
  kernel's own missed-deadline count. If you choose this path, assign
  and document a new diag ordinal — do not reuse or shadow ordinal 19.

**Do not touch `diagValue()` case 19** (`shims.cpp:1120`,
`out.cycleOverrunCount`) or its kernel-side source
(`src/core/diffdrive.h:124`/`:360`, `diffdrive.cpp:303`). That is a
different, real quantity (the kernel's own missed absolute deadlines)
with a real reader (`probe(19)`) — the issue's own named near-miss.
`shims.cpp:191`'s existing comment already draws this distinction;
preserve it.

Either way, update `src/DESIGN.md:1747-1748` and
`tests/host/test_cyclestat_deleted.py`'s docstring — both currently
say "deliberately left in place," which becomes stale the moment this
ticket lands.

## Decision

**Delete.** Taking the default from the issue and this ticket's own
description: `r.tickOverrunCount` (`src/shims.cpp`) and
`simCycleCount`/`simTickOverrunCount` (`src/blocks/sim.ts`) are removed
outright, along with their per-tick increments. No stakeholder demand
for a Rig-level tick-overrun diagnostic distinct from the kernel's own
`out.cycleOverrunCount` (diag ordinal 19) exists — the case for keeping
them was "a real reader might someday want this," which is exactly the
kind of unearned state sprint 033 exists to retire. If a real need for
this diagnostic surfaces later, it can be re-added with an actual
reader and a documented ordinal at that time.

## Acceptance Criteria

- [x] The decision (delete vs. wire up) is made and stated in this
      ticket's own record before implementation, not discovered mid-way.
- [x] If deleted: `r.tickOverrunCount`, `simCycleCount`, and
      `simTickOverrunCount`, plus their increments, are removed from
      `src/shims.cpp` and `src/blocks/sim.ts`.
- [x] If wired up: a new diag ordinal is added, documented in `probe()`'s
      doc comment the same way every other ordinal is, and is distinct
      from ordinal 19. (N/A — delete was chosen.)
- [x] `diagValue()` case 19 / `out.cycleOverrunCount` and its kernel
      source are untouched either way.
- [x] `src/DESIGN.md:1747-1748` and
      `tests/host/test_cyclestat_deleted.py`'s docstring both reflect
      the actual resulting state, not "deliberately left in place."

## Testing

- **Existing tests to run**: `tests/host/test_cyclestat_deleted.py`
  (docstring update, still green); `tests/host/` kernel-diag tests
  covering `diagValue()`/`probe()` if any exist — confirm ordinal 19 is
  unaffected.
- **New tests to write**: if deleted, a source-pin-style grep test
  asserting the three fields no longer exist; if wired up, a host test
  asserting the new ordinal reads a real, incrementing value distinct
  from ordinal 19.
- **Verification command**: `uv run pytest tests/host/`
