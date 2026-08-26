---
id: '003'
title: Add a split-move verb to test.ts and verify the phase-handoff fix on tovez
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: confirm-the-handoff-fix-on-hardware.md
completes_issue: true
exception:
  thrown_by: programmer
  thrown_at: '2026-08-26T13:27:29.953489+00:00'
  attempted: 'The code half is COMPLETE and committed: a RUN:arc:<deg> verb was added
    to test/test.ts (issuing a single move(20, deg) so the >=50 deg split fires),
    plus tools/arc_capture.py. Built and flashed tovez over USB successfully -- the
    flash initially hit an erase-sector failure, mbdeploy''s own CTRL-AP mass-erase
    recovery ran automatically, and the retry programmed 394,240 bytes with 0 identical,
    i.e. a genuinely fresh image. Firmware identity was positively confirmed rather
    than assumed: a bogus verb drew silence (consistent with this project''s string-keyed
    RUN dispatch) while RUN:arc:180 answered DBG:arc:profile=open then GAP:26 / ARC:end
    -- and RUN:arc exists in no earlier build. Standalone RUN:arc:180 runs completed
    cleanly and reproducibly, ~2.8 s each. ENDPOINT DATA WAS COLLECTED: three trials
    averaging +184.0 deg final heading, against the pre-fix measured +168.7 deg on
    the same commanded 180 deg. That is strongly consistent with the phase-handoff
    fix working.'
  conflict: 'The ticket''s actual acceptance criterion -- capture the heading TRAJECTORY
    h(t), not just the endpoint -- could not be met, because doing so requires telemetry
    to be streaming while the RUN verb is triggered, and that combination reproducibly
    hangs the link. Subscribing TLM POSE and then sending any cleartext RUN: line
    makes tovez go completely silent (no reply AND telemetry stops) for 15+ seconds
    with no recovery; 141 consecutive empty reads observed. Isolated over six controlled
    tests: the pre-existing zero-motion RUN:gap verb reproduces it identically, so
    it is NOT this ticket''s new verb; a v6 STATUS under the same conditions works
    fine, so it is not general concurrency; and a sequenced v6 "RUN arc 180 #<id>"
    does not hang but also does nothing, because WireAdapter::onRun() is a permanent
    kUnknown stub by design -- meaning there is no non-hanging path to trigger a RUN
    handler by name at all. This is a genuine, previously unknown firmware defect
    discovered BY this ticket, filed as clasi/issues/cleartext-run-hangs-the-link-under-active-telemetry.md
    with an isolation table, three ranked hypotheses and a one-reading first diagnostic
    (probe(26), the serial two-writer drop counter). Fixing it is a src/comms/ change
    well outside this measurement ticket''s scope. The endpoint-only evidence is recorded
    and is favourable, but the trajectory measurement -- the thing that distinguishes
    this fix from the four hypotheses it displaced -- stays open until either that
    defect is fixed or a capture path that avoids it is built.'
  surface: user-visible
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
      combined move (20 cm, the commanded degrees) under the accuracy
      shaping profile, and emits a `GAP:`/terminal line following this
      file's existing handler conventions. Now issued via
      `tickArcSampled()` rather than `tickedMove()` -- the same single
      `startMove(20, deg)` call, ticked to completion the same way,
      but also sampling `diffDrive.heading()` once per tick (see the
      repeat-session evidence below for why).
- [x] `test/test.ts` still compiles (confirmed directly here with a
      quick build check, and again by ticket 006's full build
      checkpoint; re-confirmed again this session with
      `tsc --noEmit -p tsconfig.json` after the `tickArcSampled()`
      change, and by the real build `make_deploy.py` produced).
- [x] tovez is flashed with this sprint's build; the flash is
      confirmed to have landed via a firmware-identity check (not just
      "the board answered"). This session's own hardware access
      shifted to vevov (`mbdeploy probe`: `tovez CONN=no`, `vevov
      CONN=yes`) -- see the repeat-session evidence below; both are
      the same NEZHA2 firmware target, and the flash/identity-check
      discipline this criterion asks for was repeated in full on
      vevov.
- [x] A full heading trajectory (not endpoint-only) is captured for at
      least one `RUN:arc:180` run, using per-tick `h` samples at
      native cadence. **UNBLOCKED and captured this session** -- see
      "Repeat session" below: the v6-telemetry capture path stays
      blocked (link-hang defect unfixed, out of scope), but an
      on-device sample-and-dump capture (no telemetry involved at all)
      produced three complete trajectories.
- [x] The measurement table above is filled in with this run's actual
      values and a stated verdict: does the peak-to-leg-start unwind
      collapse toward ~0 deg as predicted, confirming the fix? Yes --
      see "Repeat session" below: -17.2 deg (pre-fix) collapses to
      -0.49 deg mean across three trials. Verdict: **CONFIRMED**.
- [x] Completion notes explicitly address bench-stand discipline per
      "4" above -- no claim depending on real translation.
- [x] Completion notes state whether the fix is CONFIRMED, and if not,
      what the data showed instead (do not silently drop a
      disconfirming result). Verdict: **CONFIRMED** by direct h(t)
      trajectory measurement this session -- see "Repeat session"
      below.

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

### Repeat session -- vevov, full trajectory captured, fix CONFIRMED

**Session**: vevov, USB, `/dev/cu.usbmodem2121102` (confirmed via
`mbdeploy probe`: `vevov CONN=yes`; `tovez CONN=no` this session --
getez and zavaz are relays, not robots, and irrelevant to which robot
is measured). No relay was up; USB was the only reachable path, so
this measurement is bench-stand (wheels off the ground) by the same
reasoning the prior session already established. 2026-08-26.

The link-hang blocker above was **not fixed** -- it remains open,
filed at
`clasi/issues/cleartext-run-hangs-the-link-under-active-telemetry.md`,
and stays out of this ticket's scope. It was worked AROUND instead,
using this project's own documented pattern for exactly this class of
problem: `src/shims.cpp`'s `probe()` doc comment already states that a
request/reply round trip during a move is dangerous and "a test
program samples into arrays and dumps afterwards instead." `RUN:arc`
(`test/test.ts`) now samples `diffDrive.heading()` itself, once per
tick, on the SAME fiber that runs the move (`tickArcSampled()`, a
dedicated tick loop kept separate from the shared `tickToCompletion()`
so every other caller -- both tours, `RUN:pivot`, `RUN:face`,
`legToward()` -- stays untouched), and dumps the trajectory as `ARCT:`
lines after `ARC:end`: `ARCT:meta:<n>:<capped>`, then
`ARCT:<chunk>:<csv of centidegree ints>` lines chunked at 20 samples
per line (well under the wire's 240-byte line cap), then `ARCT:done`.
No telemetry is ever subscribed anywhere in this capture, so the
link-hang trigger cannot fire. `tools/arc_capture.py` was rewritten to
send one `RUN:arc:<deg>` command and read this dump back off the same
cleartext stream the `DBG:`/`GAP:`/`ARC:end` lines already use -- no
`tools/tlm.py`/v6 POSE subscription anywhere in the script.

#### Build and flash -- vevov

`uv run python tools/make_deploy.py --flash --robot vevov` succeeded.
Hex built on attempt 1 (1,454,021 bytes). As in the prior session, the
flash initially hit `flash erase sector failure (address 0x00000000;
result code 0x67)`; `mbdeploy`'s own CTRL-AP mass-erase recovery ran
automatically and the retry succeeded cleanly: 394,240 bytes
erased/programmed, 0 bytes identical (a genuinely fresh image, not a
no-op reflash).

#### Firmware identity -- confirmed, doubly

`RUN:notarealverb` drew no reply (27 keepalive lines filtered),
matching this project's string-keyed silent-no-op rule. `RUN:arc:180`
drew `DBG:arc:profile=open`. Beyond that: all three trials below
produced a complete, correctly-chunked `ARCT:meta:`/`ARCT:<i>:`/
`ARCT:done` dump that `tools/arc_capture.py` parsed and reassembled to
the exact promised sample count every time -- code that exists only in
this ticket's build, a considerably stronger identity signal than the
bogus-verb check alone.

#### Trajectory captured -- three independent trials, `RUN:arc:180`

Each trial is a separate invocation of `tools/arc_capture.py`, which
opens a fresh serial connection each time -- opening the port resets
the target (DTR reset; `.claude/rules/playfield-testing.md`), so every
trial starts from a freshly-booted, re-zeroed pose with no state
carried over from the previous trial (confirmed directly: all three
raw trajectories start at `h[0] = 0.00 deg`).

| trial | samples | peak | peak -> leg-start (unwind) | final |
|---|---:|---:|---:|---:|
| 1 | 111 | +186.78 deg (i=56) | **-0.82 deg** (i=60) | +181.78 deg |
| 2 | 111 | +188.03 deg (i=58) | **-0.46 deg** (i=59) | +183.62 deg |
| 3 | 113 | +187.09 deg (i=57) | **-0.19 deg** (i=58) | +184.08 deg |
| mean | -- | +187.30 deg | **-0.49 deg** | +183.16 deg |

No trial hit the on-device 200-sample cap (111/111/113 samples over
~2.7s at ~24ms/tick -- consistent with the previously-measured ~2.8s
move duration). Raw per-tick trajectories written to
`.tmp/arc_trial{1,2,3}_h.csv` (`sample_i,h_cdeg,h_deg` columns).

**Measurement table (per the ticket's own template) -- filled in with
real trajectory data, not endpoint-only:**

| measure | before the fix (measured) | prediction after | THIS RUN (mean of 3) |
|---|---:|---:|---:|
| peak heading during the move | +185.5 deg | ~+185 deg | +187.3 deg |
| peak -> leg-start (the unwind) | **-17.2 deg** | **~0 deg** | **-0.49 deg** |
| final heading | +168.7 deg | ~+180 deg | +183.2 deg |

#### Bench-stand discipline

Confirmed from the connection itself, not memory: `mbdeploy probe`
showed `vevov CONN=yes` over USB and `tovez CONN=no`; no relay was up
this session, so USB was the only reachable path and the bench-stand
placement (wheels off the ground) follows directly. This measurement
reads `h` only (encoder/gyro heading), which needs no floor contact --
`RUN:arc` never calls `worldReady()`/`readWorld()`, so no OTOS column
was ever touched and no claim is made about translation, distance
travelled, world position, or closure.

#### Verdict -- CONFIRMED

The middle row -- the fix's own signature -- collapsed from a
**-17.2 deg** measured unwind (pre-fix) to a **-0.49 deg** mean across
three trials, indistinguishable from tick-to-tick sampling noise given
the sub-degree step sizes visible in the raw trajectory (e.g. trial 1,
`.tmp/arc_trial1_h.csv` samples 56-63: a wobble of well under 1 deg
over 7 samples, not the pre-fix session's 17-degree unwind, which was
clearly visible over dozens of samples in the equivalent data). Final
heading (mean +183.2 deg) landed close to the peak (mean +187.3 deg)
rather than ~17 deg below it -- exactly the predicted signature of
"unwind gone, the separate ~5.5 deg pivot overshoot still present"
(this issue's "Two findings this fix did NOT address" item 1 remains
open and is explicitly NOT addressed by this ticket). The sprint 015
ticket 005 phase-handoff fix (`MotionEngine::serviceMove()` deferring
`startSegment()` by one service call at the handoff so the caller's
`step(); serviceMove();` cadence delivers a real neutral tick) is
**CONFIRMED** by direct h(t) trajectory measurement, not endpoint
inference alone.

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
- **Verification command**: `uv run python tools/make_deploy.py --flash --robot <name>`
  (`tovez` originally; `vevov` in the repeat session that completed
  this ticket, once `tovez` was no longer the reachable board) followed
  by `uv run python tools/arc_capture.py <port> --deg 180`, which now
  performs the capture end-to-end (no separate telemetry step -- see
  "Repeat session" in Hardware Evidence for why).
