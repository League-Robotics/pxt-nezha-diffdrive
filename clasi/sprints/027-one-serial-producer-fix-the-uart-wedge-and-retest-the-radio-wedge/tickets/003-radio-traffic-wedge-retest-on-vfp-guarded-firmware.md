---
id: '003'
title: Radio-traffic wedge retest on VFP-guarded firmware
status: open
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Radio-traffic wedge retest on VFP-guarded firmware

## Description

`fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` root-caused
a hard fault (`CFSR 0x8200`, `PRECISERR|BFARVALID`, radio payload bytes
— the literal ASCII text "PING" — landing on a live `this` pointer
inside `DifferentialDrive::controlStep()`) that reads "critical — do
not drive any 1.20260829.1 robot over the radio." Sprint 026 ticket
001's VFP yield guard is the leading candidate fix (a fiber parked at
an unguarded yield can have a pointer-holding register clobbered by
another fiber's float arithmetic — the same class of corruption, on a
different register bank, from the same root cause CODAL not saving VFP
registers across a context switch). But the radio-traffic retest that
would confirm or rule that out was never run — sprint 026 closed having
retested only the non-radio kill tests. This issue has sat unconfirmed
since 2026-08-30.

This ticket runs that retest, on **tigez** (farm node meili), with
sprint 026's VFP-guarded firmware (already merged — no new firmware
change needed to start this ticket): drive `MOVE_X` over USB while
hammering `PING` over the radio relay (tuned to tigez's migrated
address, `!CG 55 114`, per
`.claude/rules/playfield-testing.md`'s fleet-migration table), many
trials, mirroring the original reproducer's script and conditions in
`captures/tigez-cal-20260830/`. The fault is probabilistic — a single
survival proves nothing — so "many trials" means enough to match or
exceed the original reproducer's own trial count (10+ move-cycles under
hammering) before calling either outcome.

**Report the result either way — an inconclusive session does not
satisfy this ticket:**

- **If the fault does not reproduce**: close
  `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md` as fixed
  by sprint 026 ticket 001, and correct the still-open corruption
  attribution in `src/platform/nezha_port.cpp`'s comment (and any other
  doc referencing the unresolved root cause) to state it was
  resolved by the VFP guard, with the retest's own capture cited.
- **If the fault still reproduces**: it is a separate, still-open
  defect from the VFP fault (the issue's own "This is NOT the VFP
  fault"-shaped distinction, mirrored for the concurrent-serial-writer
  issue, applies here too) — capture CFSR/BFAR with pyOCD on the wedged
  chip and re-attribute the issue with the fresh evidence rather than
  letting the guard stand as an unproven explanation. Do not attempt a
  further code fix in this ticket if it still reproduces — re-attribute
  and stop; a new fix is a separate ticket's scope.

This ticket has no code dependency on tickets 001/002 (the serial-wedge
fix and the VFP guard are unrelated fixes to unrelated hazards) but
shares the same bench setup, so it is sequenced after ticket 002 to
reuse one physical session on tigez/meili.

## Acceptance Criteria

- [ ] The retest runs on tigez (meili), VFP-guarded firmware, `MOVE_X`
      over USB while `PING` hammers over the radio relay (`!CG 55
      114`), for a trial count at or above the original reproducer's
      (10+ move-cycles).
- [ ] Every trial's outcome is recorded with a `MEASURED` comment
      naming its capture file, board, and date — no trial result is
      asserted without one.
- [ ] Exactly one of the two outcomes is reached and acted on:
      - [ ] Closed: `fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`
            moved to done, `src/platform/nezha_port.cpp`'s comment (and
            any doc citing the unresolved attribution) corrected to
            state the VFP guard resolved it, evidence cited.
      - [ ] Re-attributed: the issue stays open, updated with fresh
            CFSR/BFAR evidence from the wedged chip and an explicit
            statement that this is a separate defect from the VFP
            fault, not explained by it.
- [ ] `uv run pytest` (full host suite) passes — this ticket is not
      expected to change firmware source unless re-attribution requires
      a documentation-only correction.

## Implementation Plan

**Approach**: Hardware-verification ticket, mirroring ticket 002's
shape. No firmware change is needed to start — the VFP guard is
already merged. Bench tigez on meili, tune a torture-pool relay to
`!CG 55 114`, and run the `MOVE_X`-over-USB / `PING`-over-radio
reproducer for many trials, capturing each one. If the fault
reproduces, halt the wedged chip with pyOCD and read CFSR/BFAR/the
faulting PC before power-cycling, same technique the original issue's
"ROOT CAUSE" section used.

**Files to create**: capture files under `captures/` for the retest
session (e.g. `captures/tigez-radio-retest-20260902/`).

**Files to modify (only if the fault does NOT reproduce)**:
`src/platform/nezha_port.cpp`'s comment,
`clasi/issues/fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`
(closed via issue linkage).

**Files to modify (only if the fault DOES reproduce)**:
`clasi/issues/fw-1-20260829-1-wedges-on-radio-traffic-during-motion.md`
(updated with fresh evidence, left open — do not close this ticket's
`issue:` linkage in this branch; use `completes_issue: false` on
completion if the issue stays open, or throw a ticket exception if
closing conventions are unclear).

**Files NOT to modify**: no attempt at a NEW fix if the fault
reproduces — that is a separate ticket's scope, not this one's.

## Testing

- **Existing tests to run**: `uv run pytest` (full host suite) as a
  pre-flight sanity check before spending bench time.
- **New tests to write**: none — this is a hardware measurement
  ticket, not a code ticket.
- **Verification command**: the many-trial reproducer above, each
  trial MEASURED and cited; `uv run pytest` as the regression floor.
