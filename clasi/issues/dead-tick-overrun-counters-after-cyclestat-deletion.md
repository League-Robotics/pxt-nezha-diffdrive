---
status: pending
---

# Three tick-overrun counters are write-only since `cycleStat()` was deleted

Sprint 032 ticket 008 deleted `cycleStat()` (`src/shims.cpp`) and its
simulator stand-in `_cycleStat()` (`src/blocks/sim.ts`) after confirming
zero callers anywhere in `src/`, `test/`, `tests/` or `tools/`. It
deliberately left the counters those functions read, as out of scope,
and recorded that decision in `src/DESIGN.md:1747-1748`.

Those counters are now **write-only**: incremented every tick, read by
nothing.

## Verified, not assumed (source reading, 2026-09-05)

| counter | declared | incremented | readers |
|---|---|---|---|
| `r.tickOverrunCount` | `src/shims.cpp:188` | `src/shims.cpp:894` | **none** |
| `simCycleCount` | `src/blocks/sim.ts:47` | `src/blocks/sim.ts:364` | **none** |
| `simTickOverrunCount` | `src/blocks/sim.ts:48` | `src/blocks/sim.ts:378` | **none** |

`grep -rn` across `src/ test/ tests/ tools/` finds only the declaration,
the increment, `src/DESIGN.md`'s note, and
`tests/host/test_cyclestat_deleted.py`'s docstring describing the
decision. No functional reader.

**The near-miss worth recording:** `diagValue()` case 19
(`src/shims.cpp:1120`) returns `out.cycleOverrunCount`, which looks like
the same thing and is NOT. That is the **kernel's** counter
(`src/core/diffdrive.h:124` and `:360`, incremented in
`diffdrive.cpp:303`, published in `:839`), a separate quantity with a
real reader. `src/shims.cpp:191` already carries a comment drawing that
distinction. Anyone deleting the Rig-level counter must not touch the
kernel one.

## The decision to make

Either:

- **delete the dead writes** (`r.tickOverrunCount` and both `sim.ts`
  counters), removing state nothing consumes; or
- **wire up a real reader** if a `STATUS`/`DIAG` wire field for
  Rig-level tick overruns is actually wanted — note the kernel already
  exposes its own overrun count at diag ordinal 19, so a second one
  needs a reason to exist beyond "the variable is there."

Deleting is the default unless someone wants the diagnostic. A
Rig-level tick overrun (the `tickDrive()` pacing loop missing its
budget) is genuinely a different measurement from the kernel's missed
absolute deadlines, so the case for keeping it is not zero -- but it
should be made deliberately, and if kept it needs a reader and a
documented ordinal, not a silent increment.

## Why sprint 033

This is exactly 033's theme (cohesion: retiring state that no longer
earns its place). Small, self-contained, host-testable, no hardware.

Whichever way it goes, update `src/DESIGN.md:1747-1748` and
`tests/host/test_cyclestat_deleted.py`'s docstring, both of which
currently record "deliberately left in place."
