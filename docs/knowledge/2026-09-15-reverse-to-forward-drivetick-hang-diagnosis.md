---
date: 2026-09-15
tags: [firmware, fiber-scheduling, bus-guard, i2c, watchdog, drivetick, sprint-039]
related-tickets: [039/002]
---

# Reverse-to-forward `driveTick()` loop stops advancing (source-level diagnosis, no hardware access)

## Status

**Diagnosis only. No hardware was run to produce this document** -- sprint
039 ticket 002 was worked by a programmer agent with no robot available
(`.claude/agents/programmer` dispatch note: "THIS TICKET IS HALF
HARDWARE AND YOU HAVE NO ROBOT"). Every claim below not attributed to
the pre-existing bench log is source reading and reasoning, labeled
**UNVERIFIED**, not a measurement. The hardware repro this document
recommends is the thing that would turn a UNVERIFIED line into a
MEASURED one or refute it outright.

## Problem

`captures/calibratel-vevov-20260915/bench-log.md` (the evidence this
ticket was opened against) shows two `driveTick()` loops immediately
following a reversal that stop advancing partway through their
commanded tick budget, and the test program's own post-loop tail
(`stop(); pause(40);` then a printed pose line) never runs:

- Run 7: `reverse -10/-10 x40` completes normally (`i2cf +3 over cyc
  +40`, prints `CALL:nudged x=-7.2cm heading=2.71deg`); the immediately
  following `forward 10/10 x40` ends at `cyc +16` with **no**
  `CALL:nudged` line within an 8 s wait.
- Run 8: `reverse -4/-4 x40` completes normally (prints its line); the
  immediately following `forward 4/4 x40` ends at `cyc +17`, again no
  line.
- Run 9: `STOP now` (sequenced) is issued after run 8. It is `ack`ed
  normally. Three subsequent `STATUS` reads, several seconds apart, all
  read `active=1` with `cyc` frozen at exactly `2901`.

## What run 9 is (and is not) evidence of

Run 9's frozen `cyc` was the sprint plan's own reason to treat symptom 1
(STATUS staleness) and symptom 2 (the hang) as possibly one mechanism.
Re-reading `shims.cpp`'s tick model narrows this: `cyc`
(`Output.cycleCount`) only advances when something calls `tickDrive()`,
and nothing does that unconditionally -- the kernel's own background
fiber pacer is deliberately unwired (`ensure()`'s own comment). An idle
robot with no live motion obligation and no RUN job ticking is expected
to show a **frozen** `cyc`, by design, whether or not anything is wrong.
So run 9's frozen `cyc` by itself is not distinguishing evidence.

What IS diagnostic in run 9: the sequenced `STOP` got a normal `ack`,
and `STATUS` answered promptly and repeatedly. Both of those paths read
published state or do a non-blocking `busGuard.held()` peek --
`WireAdapter::status()` never touches `busGuard`, and
`Rig::softStop()`'s own guard check never blocks (`held()` is a bare
read, not an `acquire()`). So run 9 proves the **protocol/wire fiber**
stayed healthy throughout; it says nothing about whether some OTHER
fiber (the one that had been running the `forward 10/10 x40` loop) was
still alive. `active=1` staying stuck is fully explained by ticket 002's
own Defect 1 fix (`Rig::softStop()` now forces a fresh `Output` via
`engine.settleToRest()` -- see `src/shims.cpp` and
`tests/host/test_status_active_after_soft_stop.py`) and needs no
hang theory at all.

## Source audit performed

Every `busGuard.acquire()` in `src/shims.cpp` (8 call sites as of this
ticket, `enginePulseWheels()`, `tickDrive()`, `configureMotor()`, the
six OTOS entry points, `otosSetOffset()`, `seedPose()`) was read in
full. Every one is a short, single-exit acquire/body/release bracket
with no early return in between -- the file's own commenting convention
for this ("Manual acquire/release, not RAII... every call site is a
short, single-exit body", `bus_guard.h`'s header comment) holds in
every instance checked. This rules out the simplest version of
candidate (b) -- "somewhere a guard is acquired and a return skips its
release" -- as a static code defect. It does **not** rule out a runtime
deadlock where the fiber holding the guard never returns from something
*inside* that bracket (see below).

`NezhaMotorPort::collect()`, `writeShapedDuty()`, and
`encoder_glitch_armor.h`'s decision logic were read for loops. None
contains an unbounded loop; the reversal-dwell branch
(`nezha_port.cpp`'s `writeShapedDuty()`) is a single comparison against
`reversalDwell_` with no loop at all -- it either writes a held zero or
falls through, once, per call. This rules out a simple spin-forever bug
in the dwell logic itself.

## Leading hypothesis: a genuine I2C-level stall inside `kernel.step()`, landing on the loop's own fiber

`tickDrive()` acquires `busGuard` and then calls `kernel.step()`, which
talks I2C to both wheels (select, settle, read, per wheel) before
returning. If that I2C exchange hangs on real hardware -- a NACK'd or
wedged transaction -- `kernel.step()` does not return, `busGuard` stays
held, and `cyc` freezes exactly as observed. This would:

- Explain the frozen `cyc` (the step that would have advanced it never
  finishes).
- Explain the missing `CALL:nudged` line (the loop's own fiber is
  parked inside the stuck `tickDrive()` call, never reaching its
  `stop(); pause(40); emitLine(...)` tail -- this is a genuine hang, not
  an early-exited loop with a merely-dropped print).
- Be consistent with run 9's healthy protocol fiber (STATUS/STOP do not
  need the guard, as above).
- Be consistent with the "reversal" correlation only loosely: nothing
  in the reversal-dwell CODE loops or blocks, but the dwell's repeated
  zero-duty I2C writes (one per tick, for up to 100 ms) are exactly the
  kind of unusual bus traffic pattern that could trigger a real
  hardware I2C fault that a steadier duty stream would not. This is
  speculative and UNVERIFIED -- it is offered as a plausible trigger,
  not a confirmed one.

`nezha_port.cpp::begin()`'s own comment documents that this class of
fault is real on this hardware family: `NRF52I2C::waitForStop()` bounds
one stuck transaction at ~10 s (source reading, not re-measured by this
ticket), well past run 9's own several-second observation window and
easily long enough to look like "frozen" over an 8 s test wait or a
handful of STATUS polls.

**This hypothesis requires the hardware repro to confirm or refute.** A
host test cannot reach it: `shims.cpp` includes `pxt.h` and is not
host-compilable (`tests/host/README.md`'s own standing convention), and
even the host-portable pieces (`NezhaMotorPort`, `SimNezhaBus`) model
the WIRE PROTOCOL, not a hardware I2C bus fault -- there is nothing in
this codebase's host harness capable of injecting "the transaction never
completes" at the bus level. No fix was written against this hypothesis
for exactly that reason (the ticket's own instruction: land a fix only
if the mechanism can be demonstrated in a host test).

## A real, source-diagnosable, secondary defect found along the way: the watchdog's freshness signal is set too early

Independent of what causes a fiber to get stuck, `tickDrive()`
(`src/shims.cpp`) currently reads:

```cpp
bool tickDrive() {
  Rig& r = ensure();
  const uint64_t cycleStart = r.clock.nowMicros();
  r.lastTick = cycleStart;   // <-- set BEFORE busGuard.acquire()
  r.busGuard.acquire(r.sleeper);
  r.kernel.step();
  ...
```

`r.lastTick` is "the watchdog's only freshness signal" (the field's own
comment). It is written before the guard is even requested, so ANY
fiber that merely *attempts* a tick -- including one that immediately
blocks spinning inside `busGuard.acquire()` because another fiber holds
it -- re-arms the watchdog's freshness clock. If some other caller (the
protocol fiber's own `hasLiveMotionObligation() -> tickDrive()` path is
the obvious candidate) keeps calling `tickDrive()` on a normal cadence
while the guard is held by a genuinely wedged fiber, every one of those
calls refreshes `lastTick` before blocking, and the starvation watchdog
-- whose entire job is to notice exactly this class of abandonment --
can never see staleness. This would explain why nothing rescued runs
7-9 over several seconds, well past the watchdog's own ~100-150 ms
design window, regardless of what actually wedged the guard.

This is a genuine defect by inspection (the freshness signal should
mean "a tick actually completed," not "a tick was attempted"), it is
low-risk to fix (move one assignment from before `busGuard.acquire()`
to after `r.kernel.step()` returns -- no new yield point, no new call
site), and it directly serves the safety property `fiber-yield-
safety.md` exists for (the watchdog must be able to catch a wedged
fiber). **It was not applied in this ticket** because `shims.cpp` is not
host-compilable and the ticket's own instruction was to land a fix only
where the mechanism can be demonstrated in a host test -- this is
recorded here as a strong recommendation for whoever picks up the
hardware repro or a follow-up ticket, not as a landed change.

## Recommended hardware repro (for team-lead, per `hardware-tickets-run-them-yourself`)

1. Enable `TLM FULL` streaming before the run (not enabled in the
   original bench session -- "Not recorded" section of
   `captures/calibratel-vevov-20260915/bench-log.md`).
2. Read diag 28 (lease-expiry / refusal, per that same "Not recorded"
   note) and diag 29 (emit-queue drops) before and after every step,
   not just at the end.
3. Reproduce runs 7/8's exact command pair (`reverse <l>/<r> x40` then
   `forward <l>/<r> x40`, same test verb) several times, watching for
   the same short tick count (~16-17/40) and missing completion line.
4. On a reproduction, without touching anything: wait well past the
   ~150 ms watchdog window (several seconds is enough per run 9) and
   read `STATUS` and diag 29. If `active` is stuck at 1 with the
   Defect-1 fix ALREADY FLASHED, that refutes Defect 1 as the
   explanation and points squarely at a genuine hang (confirming this
   document's leading hypothesis, or a different one -- see the
   candidates list in the ticket itself for the full set).
5. If `TLM FULL`'s own telemetry stream also stalls at the same tick
   the completion line goes missing, that further confirms `tickDrive()`
   itself is not returning (a general fiber-level hang), rather than
   the RUN job merely never reaching its own print statement for some
   other reason downstream of a normally-completing loop.
6. If time allows, flash a build with the watchdog `lastTick`
   reordering described above (as an isolated, separately-flashed
   experiment, NOT bundled with anything else) and repeat: if the
   watchdog now visibly fires (a forced stop, `cyc` still frozen but
   `active` reads 0 within ~150 ms of the hang instead of staying
   stuck) that confirms the watchdog-starvation hypothesis and makes
   the reorder a strong candidate for landing in a follow-up ticket.

## What this document does not claim

No MEASURED line appears in this document for anything about the hang
itself -- only the pre-existing bench-log citations above, which were
already measured by the 2026-09-15 session and are cited, not
re-derived. Everything about *why* the hang happens is UNVERIFIED
hypothesis, clearly labeled as such, pending the repro above.
