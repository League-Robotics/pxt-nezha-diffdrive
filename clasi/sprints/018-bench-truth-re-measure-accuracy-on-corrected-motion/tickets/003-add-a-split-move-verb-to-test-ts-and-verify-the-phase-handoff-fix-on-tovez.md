---
id: '003'
title: Add a split-move verb to test.ts and verify the phase-handoff fix on tovez
status: in-progress
use-cases: []
depends-on: []
github-issue: ''
issue: confirm-the-handoff-fix-on-hardware.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Add a split-move verb to test.ts and verify the phase-handoff fix on tovez

## Description

**This is the one hardware ticket in this sprint, and it is genuinely
runnable**: `mbdeploy probe` shows `tovez CONN=yes` over USB (the only
board reachable this session -- vevov, getez, and zavaz are all
`CONN=no`).

Sprint 015 ticket 005 (merged, v0.20260826.1) fixed a defect where a
split move (one command combining translation and a >=50 deg turn,
which `moveX()`'s reduction reissues as pivot-then-straight) unwinds
its own pivot at the phase 1 -> phase 2 handoff: the kernel's
`twistRef_` was never re-armed because the handoff never passed
through neutral. Measured before the fix on tovez: pivot peaked at
+185.5 deg, unwound 17.2 deg with the robot in place, the following
straight leg contributed +0.4 deg, and the move finished at 168.7 deg
against a 180 deg command. A two-command control (a separate turn,
then a separate go -- which DOES pass through neutral between them)
held heading to +0.3 deg on the same, unfixed firmware. The fix
(`MotionEngine::serviceMove()`) now defers `startSegment()` by one
service call at the handoff, so the caller's `step(); serviceMove();`
cadence delivers a real ~24 ms neutral tick and `twistRef_` re-arms
with a fresh origin.

**Worth recording because it nearly shipped wrong**: the naive fix
does not work. A bare `kernel_.neutral()` immediately followed by
`startSegment()` changes nothing -- both merely overwrite the kernel's
`command_`, and delivery (including the `twistRef_` disarm) happens
only on the NEXT `step()`, which `MotionEngine` never calls itself.

No flash was attempted during sprint 015 (a peer session's
instrumented rig held tovez at the time). The fix has zero hardware
evidence.

**The instrumentation gap.** This repo's `test/test.ts` has no
split-move verb: `RUN:pivot` is a pure pivot (`tickedMove(0, deg)`,
zero distance) and the tours issue translation and rotation as
separate commands -- exactly the two-command control shape that never
exercised the bug. There is currently nothing in this file that can
reproduce the measured defect or its fix.

## What to do

### 1. Add `RUN:arc:<deg>` to `test/test.ts`

A single verb that issues ONE combined move -- `tickedMove(20, deg)`
(20 cm, the commanded degrees) -- matching the shape that was measured
before the fix (`move(20, 180)`). Follow this file's existing
`onRun()` handler pattern (see `RUN:pivot` immediately below it in the
file for the closest existing analogue: guard on `touring`, set
`touring = true`, track `maxGapMs`, emit a `GAP:` line, emit an
`ARC:end` (or similarly named) terminal line, reset `touring = false`).
Use `diffDrive.runArg(0)` for the degree argument.

Shaping: use whichever mechanism is in place for the accuracy/open-loop
profile at the time this ticket executes -- `openLoopProfile()` if
ticket 001 has landed on this branch already (tickets in this sprint
execute serially in listed order, so it will have), or the equivalent
literal taper/floor/ramp values otherwise. Either way, use the
ACCURACY profile, not `RUN:goto`'s fast/closed-loop one -- matching
the profile in force during the original sprint-015 measurement
matters for a valid before/after comparison.

Only a magnitude of |deg| >= 50 exercises the split-move path
(`moveX()`'s own >=50 deg threshold, per `src/blocks/motion.ts`'s
`startGoTo()` doc comment) -- document this in a comment on the new
handler; no need to enforce it in firmware, `RUN:pivot`'s existing
convention of trusting the caller applies equally here.

### 2. Build and flash tovez

`uv run python tools/make_deploy.py --flash --robot tovez`. tovez may
be carrying unrelated prior firmware -- confirm the flash landed with
a firmware-identity check the same way sprint 019's build checkpoint
did (send a verb this build answers and a verb it should NOT, e.g.
`RUN:arc` should answer and any verb belonging only to a different
build should not).

### 3. Capture the heading trajectory across the move, not just the endpoint

The endpoint alone cannot distinguish this fix from the hypotheses it
displaced (see the peer-session note above -- +168.7 deg final could
still occur for reasons other than the unwind). Subscribe telemetry
with a sequenced `TLM POSE #<id>` (per this project's v6 sequencing
rule -- `tools/robotlink.py`'s `open_link()`/`sync_seq()` already
attach the id automatically) and record the `t` frames' `h` column
(the device heading -- encoder/IMU-derived, wire units 0.01 deg,
`tlm.py`'s `pose_from_row()` divides by 100) across the whole move, at
the frame's native ~24 ms cadence. `tools/tlm.py`'s `TlmStream` and
`tools/tour_capture.py`'s general shape (open link, subscribe, read
`link.lines()` into the stream, write a CSV) are the model to follow
-- `tour_capture.py` itself is tour-specific (`RUN:tour:<name>`) and
not directly reusable for a single `RUN:arc` command, so either adapt
it or write a small standalone capture; either is fine as long as the
per-frame `h` trajectory is recorded, not just a before/after pair.

Do NOT use the `oh` (OTOS world heading) column for this measurement:
`RUN:arc`, like `RUN:pivot`, deliberately does not call
`worldReady()`/`readWorld()`, so `oh` will read flat/stale. `h` is the
only column with signal here, which is exactly why this measurement is
valid on the bench stand in the first place (see below).

Send `RUN:arc:180` (matching the originally-measured shape) at least
once; repeat a few times if time allows for consistency, but this is a
confirmation of a specific, already-diagnosed mechanism, not a fresh
statistical campaign -- one clean, fully-captured trajectory that
matches the predicted shape is sufficient to confirm the fix.

**Measurement table to fill in (fix confirmed if the middle row
collapses toward zero):**

| measure | before the fix (measured) | prediction after | THIS RUN |
|---|---:|---:|---:|
| peak heading during the move | +185.5 deg | ~+185 deg (see note below) | |
| peak -> leg-start (the unwind) | **-17.2 deg** | **~0 deg** | |
| final heading | +168.7 deg | ~+180 deg | |

Note on the peak row: this fix does not address the pivot's own ~5.5
deg overshoot (peak +185.5 on a 180 deg command) -- that is a separate,
still-open mechanism (tracked by
`confirm-the-handoff-fix-on-hardware.md`'s "two findings this fix did
NOT address" section, not by this ticket). Expect the peak to still
be elevated; the fix's signature is specifically the middle row
collapsing.

The known control value to compare against: the two-command sequence
(`turn 180` then `go`) held heading to +0.3 deg on the UNFIXED
firmware. If `RUN:arc:180`'s post-fix final heading now lands near
that control's precision, the fix is confirmed -- no need to
re-measure the two-command control itself, it is already on record.

### 4. Bench-stand discipline -- mandatory, state this explicitly in completion notes

tovez is reachable only via USB this session (no relay is up), and USB
reaches only the bench stand, where the wheels are off the ground.
**This measurement is still valid** because heading here is integrated
from the encoder differential (`h`), which needs no floor contact --
unlike a translation or world-position measurement, which would not
be. State this reasoning explicitly rather than assuming it silently.
Do NOT report or imply any result that depends on real translation
(distance travelled, world position, closure) -- this ticket measures
heading only. Since USB is the only reachable path this session, the
bench-stand placement follows directly from the connection itself (no
ambiguous OTOS `ox`/`oy` discriminator is needed or available here --
tovez's OTOS/Nezha brick has been observed unpowered/undetected in
recent sessions) -- but confirm and record this in completion notes
rather than leaving it implicit, per this project's standing rule
against assuming rig placement from memory.

## Acceptance Criteria

- [x] `RUN:arc:<deg>` exists in `test/test.ts`, issues a single
      `tickedMove(20, deg)` call under the accuracy shaping profile,
      and emits a `GAP:`/terminal line following this file's existing
      handler conventions.
- [x] `test/test.ts` still compiles (confirmed directly here with a
      quick build check, and again by ticket 006's full build
      checkpoint).
- [x] tovez is flashed with this sprint's build; the flash is
      confirmed to have landed via a firmware-identity check (not just
      "the board answered").
- [ ] A full heading trajectory (not endpoint-only) is captured for at
      least one `RUN:arc:180` run, using the `t` frame's `h` column at
      native cadence. **BLOCKED this session** -- see Hardware
      Evidence: a newly-discovered link hang (cleartext `RUN:` sent
      while v6 POSE telemetry is actively subscribed) prevents the
      documented capture order. Endpoint-only data was collected
      instead as the closest safe substitute; it is NOT a substitute
      for this criterion, which stays unchecked.
- [ ] The measurement table above is filled in with this run's actual
      values and a stated verdict: does the peak-to-leg-start unwind
      collapse toward ~0 deg as predicted, confirming the fix? Only
      the final-heading row could be filled in (see table below); peak
      and peak->leg-start require the trajectory this session could
      not capture.
- [x] Completion notes explicitly address bench-stand discipline per
      "4" above -- no claim depending on real translation.
- [x] Completion notes state whether the fix is CONFIRMED, and if not,
      what the data showed instead (do not silently drop a
      disconfirming result). Verdict: NOT FORMALLY CONFIRMED (the
      required trajectory data is missing), but the endpoint data
      collected is strongly consistent with the fix working -- see
      Hardware Evidence.

## Hardware Evidence

**Session**: tovez, USB, `/dev/cu.usbmodem2121102` (confirmed via
`mbdeploy probe`: `tovez CONN=yes`; `getez`/`vevov`/`zavaz` all
`CONN=no` -- USB was the only reachable path, consistent with the
ticket's own framing). 2026-08-26.

### Build and flash

`uv run python tools/make_deploy.py --flash --robot tovez` succeeded.
The hex built on attempt 1 (1,448,621 bytes). The flash step initially
hit `flash erase sector failure (address 0x00000000; result code
0x67)`; `mbdeploy`'s own recovery path ("attempting CTRL-AP mass erase
to recover a locked device") ran automatically and the retry
succeeded cleanly: 394,240 bytes erased/programmed, 0 bytes identical
(a genuinely fresh image, not a no-op reflash).

### Firmware-identity check -- CONFIRMED

Sent a bogus verb (`RUN:notarealverb018003`): no reply within 1.5s
(after filtering the continuous `ack `/`nack ` keepalive noise), only
27 keepalive lines seen -- consistent with this project's "RUN verbs
are string-keyed" rule (an unmatched verb is a silent no-op, never an
echo). Sent `RUN:arc:180`: got `DBG:arc:profile=open`, then (after the
move) `GAP:26` and `ARC:end`. `RUN:arc` does not exist in any firmware
built before this ticket, so this reply is itself positive proof the
new build landed -- not merely "the board answered something."

### RUN:arc:<deg> verified working, standalone

Multiple direct sends of `RUN:arc:180` (no telemetry subscribed)
completed cleanly and reproducibly: `DBG:arc:profile=open` immediately
on receipt, then `GAP:26`/`ARC:end` roughly 2.8s later (the whole
20cm + 180deg split move, wheels-up). This confirms the new verb and
its shaping (accuracy/open-loop profile) work exactly as specified.

### BLOCKER discovered: cleartext RUN: hangs the link under active v6 telemetry

The ticket's documented capture order (`tlm.require_stream()` to
subscribe `TLM POSE`, THEN send the `RUN:arc` command, matching
`tour_capture.py`'s own shape) reproducibly makes the link go
completely silent: no reply to the command, AND telemetry itself
stops, for at least 15s (tested to that duration with zero recovery;
141 consecutive empty reads). This is **not specific to ticket 003's
new verb** -- the pre-existing, zero-motion `RUN:gap` verb (untouched
by this ticket except for its own DBG line, sprint 018 ticket 001)
exhibits the identical symptom. A v6 command (`STATUS`) sent under the
same active-telemetry condition works perfectly and telemetry keeps
flowing -- isolating the trigger specifically to a CLEARTEXT `RUN:`
line arriving while v6 POSE streaming is on, not general concurrency.
Six independent, reproducible tests confirmed this (see
`tools/arc_capture.py`'s module docstring "KNOWN BLOCKER" note for the
mechanism). Re-opening the port (which resets the target -- see
`.claude/rules/playfield-testing.md`) recovers the link every time.

**Root cause, from reading source (no firmware fix attempted --
out of scope for this ticket)**: `src/comms/wire_adapter.cpp`'s
`WireAdapter::onRun()` is a permanent, deliberate stub that always
returns `kUnknown` (see its own comment, and `src/DESIGN.md`: "`onRun()`
is an honest `kUnknown` -- the real by-name test trigger is
protocol.cpp's MessageBus RUN bridge, a CODAL mechanism this
host-portable class must never touch"). The only real by-name dispatch
is `protocol.cpp`'s literal `"RUN:"`-prefix `handleRun()`, a completely
separate code path from `wireHandler_.feed()` (which telemetry and
every other v6 verb go through) -- confirmed empirically too: a
sequenced v6 `RUN arc 180 #<id>` line (a real, distinct wire verb,
`src/comms/wire_handler.cpp`'s `kCommandTable`) does NOT hang the link
(telemetry kept flowing, 144 frames in 8s), but it also does NOT
trigger the `arc` handler at all -- it just returns `err 1` (`kUnknown`)
from the stub, confirming there is no existing verb that reaches a
test.ts RUN handler without going through the path that hangs.

This is a genuine, newly-discovered defect independent of this
sprint's work, appended to the issue file below rather than
investigated further here (fixing a `src/comms/` concurrency defect is
well beyond this ticket's scope, which measures a `diffdrive.cpp`
motion fix, not the comms layer).

### What WAS captured: endpoint-only, three independent trials

Given the trajectory capture was blocked, a working (but weaker)
order was used instead: run `RUN:arc:180` to completion FIRST (known
reliable, no telemetry involved), THEN subscribe `TLM POSE` and read
the resting heading. This is NOT the trajectory the ticket asks for --
no peak, no leg-start, endpoint only -- recorded as the closest safe
substitute, explicitly caveated.

Confirmed the fresh-boot starting heading is `0.0 deg` (a clean
baseline for each trial below; each trial re-opens the port, which
resets the target and re-zeroes pose per the rule file's own note).

| trial | final heading (RUN:arc:180) |
|---|---:|
| 1 | +183.89 deg |
| 2 | +183.32 deg |
| 3 | +184.87 deg |
| mean | +184.03 deg (range 1.55 deg) |

**Measurement table (per the ticket's own template) -- only the final
row could be filled in:**

| measure | before the fix (measured) | prediction after | THIS RUN |
|---|---:|---:|---:|
| peak heading during the move | +185.5 deg | ~+185 deg | **not captured -- blocked (see above)** |
| peak -> leg-start (the unwind) | -17.2 deg | ~0 deg | **not captured -- blocked (see above)** |
| final heading | +168.7 deg | ~+180 deg | **+184.0 deg (mean of 3 trials)** |

### Bench-stand discipline

Confirmed from the connection itself, not memory: `mbdeploy probe`
showed `tovez CONN=yes` over USB and every other board `CONN=no`
(vevov, getez, zavaz), so USB was the only reachable path and the
bench-stand placement (wheels off the ground) follows directly --
no ambiguous OTOS discriminator needed. This measurement is valid
wheels-up because `h` (the only column read) is integrated from the
ENCODER DIFFERENTIAL, which needs no floor contact -- the twist-hold
unwind this fix addresses is a control-loop phenomenon driven by
encoder feedback, reproducing wheels-up exactly as it would on the
floor. No claim is made or implied about translation, distance
travelled, world position, or closure -- `RUN:arc`, like `RUN:pivot`,
deliberately never calls `worldReady()`/`readWorld()`, so the OTOS
`oh`/`ox`/`oy` columns were never read and carry no signal here.

### Verdict

**NOT FORMALLY CONFIRMED** -- the acceptance criterion requires the
peak-to-leg-start unwind to collapse toward ~0 deg, which needs the
trajectory this session could not capture. What WAS measured is
**strongly consistent with the fix working**: three independent
final-heading trials (183.89 / 183.32 / 184.87 deg, mean 184.0 deg,
1.55 deg spread) cluster far above the pre-fix post-unwind value of
+168.7 deg and land close to the pre-fix PEAK of +185.5 deg (the
pivot's own ~5.5 deg overshoot is a separate, still-open finding this
fix does not address, so a final heading near the peak rather than
near 180 is exactly the predicted signature of "unwind gone, overshoot
still present"). This is consistent with, but does not by itself
prove, the specific unwind mechanism -- per this ticket's own framing,
endpoint data alone cannot fully distinguish this fix from the
hypotheses it displaced. A repeat session with the trajectory capture
either working around this blocker or with the underlying `src/comms/`
hang fixed is needed to move this from "consistent with" to
"confirmed."

## Testing

- **Existing tests to run**: none of the C++/Python host suite is
  touched by the `test/test.ts` addition in a way that changes
  existing behavior -- `uv run pytest tests/tools/test_run_verbs.py`
  as a sanity check that no existing RUN verb string regressed.
- **New tests to write**: none in the host suite for the new verb
  itself (no host harness exists for `test/test.ts`'s TypeScript
  handlers, same as ticket 001) -- this ticket's evidence is the real
  build, the real flash, and the captured heading-trajectory data,
  recorded in completion notes. If a capture script is written for
  step 3, keep it as a `tools/` script following this project's
  existing conventions (argparse, `open_link()`), not a pytest test.
- **Verification command**: `uv run python tools/make_deploy.py --flash --robot tovez`
  followed by the telemetry capture described above.
