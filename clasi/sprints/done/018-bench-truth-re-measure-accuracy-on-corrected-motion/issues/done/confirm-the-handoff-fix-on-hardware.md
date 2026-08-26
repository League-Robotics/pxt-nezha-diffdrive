---
status: done
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

## OUTCOME -- sprint 018 ticket 003, 2026-08-26

`RUN:arc:<deg>` (a single `tickedMove(20, deg)`) was added to
`test/test.ts`, master's current hex was built and flashed onto tovez
over USB (`/dev/cu.usbmodem2121102` -- `mbdeploy probe` confirmed it
was the only reachable board this session), and the flash was
confirmed via a firmware-identity check (a bogus verb drew no reply;
`RUN:arc` -- which exists in no earlier build -- drew
`DBG:arc:profile=open`/`GAP:`/`ARC:end`).

**The planned full h(t) trajectory capture (subscribe v6 `TLM POSE`,
then send the `RUN:arc` command, per this issue's own "the check"
section and `tour_capture.py`'s shape) could not be completed.**
Newly discovered this session: sending a cleartext `RUN:`/`DIAG`
command while v6 POSE telemetry is actively subscribed makes the link
go completely silent (no command reply, telemetry itself stops) for
at least 15s, with zero recovery short of reopening the port (which
resets the target). This is independent of ticket 003's own change --
the pre-existing, zero-motion `RUN:gap` verb reproduces it identically
-- and independent of general concurrency, since a v6 `STATUS`
command sent under the same active-telemetry condition works fine and
telemetry keeps flowing. Root cause (read, not fixed -- out of this
ticket's scope): `WireAdapter::onRun()` (`src/comms/wire_adapter.cpp`)
is a permanent stub that always returns `kUnknown`; the only real
by-name RUN dispatch is `protocol.cpp`'s literal `"RUN:"`-prefix
`handleRun()` bridge into CODAL's MessageBus, a code path entirely
separate from `wireHandler_.feed()` (which telemetry runs through) --
confirmed empirically too: the v6 wire grammar's own sequenced
`RUN <name> ... #<id>` verb does NOT hang the link, but also does NOT
reach test.ts's handlers at all (always `err 1`/`kUnknown` from the
stub). There is currently no existing verb that can trigger a
test.ts RUN handler without going through the path that hangs under
active telemetry. Full mechanism and six reproducing tests are in
sprint 018 ticket 003's own "Hardware Evidence" section and
`tools/arc_capture.py`'s module docstring.

**What was measured instead (endpoint-only, not the required
trajectory)**: `RUN:arc:180` run to completion, then telemetry
subscribed afterward to read the resting heading -- three independent
trials, fresh port reopen each (confirmed fresh-boot heading is
exactly 0.0 deg each time): **+183.89, +183.32, +184.87 deg** (mean
+184.0, spread 1.55 deg). This clusters far above the pre-fix
post-unwind final of +168.7 deg and close to the pre-fix PEAK of
+185.5 deg -- the signature predicted if the unwind is gone but the
separate, still-open ~5.5 deg pivot overshoot (this issue's "Two
findings this fix did NOT address" item 1) remains. **Strongly
consistent with the fix working, but NOT a formal confirmation** --
endpoint data alone cannot fully distinguish this fix from the
hypotheses it displaced, which is exactly this issue's own original
caution. Ticket 003 stays `in-progress`; a repeat session either
working around or fixing the newly-found comms hang is needed to
reach an actual CONFIRMED verdict.

## OUTCOME, repeat session -- vevov, 2026-08-26 -- CONFIRMED

The link-hang blocker was worked around, not fixed (it remains open in
`clasi/issues/cleartext-run-hangs-the-link-under-active-telemetry.md`):
`RUN:arc` now samples `diffDrive.heading()` on-device, once per tick,
and dumps the trajectory as `ARCT:` lines after the move completes,
with no telemetry ever subscribed -- the exact "sample into arrays and
dump afterwards" pattern `src/shims.cpp`'s `probe()` doc comment
already prescribes for a request/reply round trip that is dangerous
mid-move. `tools/arc_capture.py` sends one `RUN:arc:180` and reads this
dump back.

tovez was unreachable this session (`mbdeploy probe`: `CONN=no`);
vevov was flashed and measured instead (same NEZHA2 firmware target,
USB-only, bench stand, wheels off the ground). Three independent
trials (fresh port reopen each, confirmed re-zeroed `h[0]=0.00 deg`
every time):

| measure | before the fix | prediction after | THIS RUN (mean of 3) |
|---|---:|---:|---:|
| peak heading during the move | +185.5 deg | ~+185 deg | +187.3 deg |
| peak -> leg-start (the unwind) | **-17.2 deg** | **~0 deg** | **-0.49 deg** |
| final heading | +168.7 deg | ~+180 deg | +183.2 deg |

The middle row -- this fix's own signature -- collapsed from a
measured -17.2 deg unwind to a -0.49 deg mean, indistinguishable from
per-tick sampling noise. Final heading landed close to the peak rather
than ~17 deg below it, exactly the predicted "unwind gone, the
separate ~5.5 deg pivot overshoot (still open, see "Two findings this
fix did NOT address" item 1 above) still present" signature. The
sprint 015 ticket 005 phase-handoff fix is **CONFIRMED** by direct
h(t) trajectory measurement. Full trial-by-trial data and raw CSVs are
in ticket 003's own Hardware Evidence section ("Repeat session --
vevov, full trajectory captured, fix CONFIRMED"). Ticket 003, and this
issue, are both closed by this outcome.
