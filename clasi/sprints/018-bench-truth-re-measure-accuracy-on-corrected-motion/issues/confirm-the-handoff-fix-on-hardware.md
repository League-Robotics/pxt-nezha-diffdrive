---
status: in-progress
sprint: 018
tickets:
- 018-003
---

# Confirm the phase-handoff fix on hardware, and close out two findings it did not address

Priority: **High** — sprint 015 shipped a behavioural fix to the motion engine
whose evidence is entirely host-side. The hardware measurement that motivated it
has not been repeated against the fix.

## What shipped, unverified

Sprint 015 ticket 005 (merged, v0.20260826.1): `MotionEngine::serviceMove()` now
defers `startSegment()` by one service call at the phase 1 -> phase 2 handoff, so
the caller's `step(); serviceMove();` cadence delivers a real ~24 ms neutral tick
and the kernel's `twistRef_` re-arms with a fresh origin.

Worth recording because it nearly shipped wrong: the **naive fix does not work**.
A bare `kernel_.neutral()` immediately followed by `startSegment()` changes
nothing — both merely overwrite the kernel's `command_`, and delivery (including
the `twistRef_` disarm) happens only on the next `step()`, which `MotionEngine`
never calls itself.

No flash was attempted during sprint 015: a peer session's instrumented rig held
tovez and flashing would have destroyed it. That session has since ended.

## The check

Flash master's current hex, run a split move of the `move(20, 180)` shape, and
capture the heading trajectory h(t) — not just the endpoint. The endpoint alone
cannot distinguish this fix from the several hypotheses it displaced.

| measure | before the fix (tovez, measured) | prediction after |
|---|---:|---:|
| peak heading during the move | +185.5 deg | ~ +185 deg (see "still open" below) |
| peak -> leg-start | **−17.2 deg** | **~0 deg** |
| final heading | +168.7 deg | ~ +180 deg |

**Instrumentation note.** This repo's `test/test.ts` has no split-move verb —
`RUN:pivot` is a pure pivot and the tours issue separate commands, which is
exactly the case that never showed the bug. The peer's `RUN:arc:<deg>` verbs in
`projects/blocktest` were the right instrument. Either recover that rig or add an
equivalent verb to `test.ts` first; without one there is nothing to measure.

A useful control is already known: a two-command sequence (`turn 180` then `go`)
passes through neutral between commands and held heading to +0.3 deg on the
unfixed firmware. If the split move now matches that, the fix is confirmed.

## Two findings this fix did NOT address

1. **The pivot overshoots by ~5.5 deg** before the unwind (peak +185.5 on a 180
   command). Separate mechanism, still unexplained, and it survives the handoff
   fix by construction.
2. **`serviceMove()` is heading-blind during phase 2.** The straight phase is
   issued with `rotation = 0`, so `move_.yawTarget == 0` and the entire yaw block
   in `serviceMove()` is skipped — no measurement, no correction, no wrong-way
   check for the whole leg. That was the *enabling condition* for the handoff bug
   rather than its cause, and it remains true. Any future heading error during a
   straight phase will likewise go unobserved and the move will report complete.

Item 2 is the one worth designing for: giving the straight phase a heading *hold*
target instead of zero would close it, and would also be the general fix for
`rotation-error-is-injected-by-the-legs-not-the-pivots.md`. Cost it against that
issue rather than this one.

## Provenance

Measured across three campaigns on tovez by the `blocks-local-codeserver-test`
session (2026-08-25/26); mechanism identified in `diffdrive.cpp` and the fix
designed during the 2026-08-26 code review. Full evidence trail in
`clasi/sprints/done/015-one-arc-implementation-stops-that-stop-and-a-green-doc-gate/issues/done/pivot-stops-11-degrees-short-of-commanded.md`.
