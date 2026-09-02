---
status: done
sprint: '027'
tickets:
- 027-002
---

# A cleartext `RUN:` command sent while v6 telemetry is streaming hangs the link, and there is no v6 alternative

Priority: **High** — it blocks the standard bench capture pattern (subscribe
telemetry, trigger a run, record the trajectory), which is what every accuracy
campaign needs. And the obvious workaround does not exist: there is no way to
trigger a by-name RUN handler over the v6 wire at all.

Found on hardware during sprint 018 ticket 003 (tovez, USB, 2026-08-26), while
trying to capture an h(t) trajectory. Six independent reproductions.

## Symptom

Subscribe `TLM POSE`, then send any cleartext `RUN:<name>` line. The link goes
**completely silent** — no reply to the command, **and telemetry itself stops**
— for at least 15 s, tested to that duration with zero recovery (141
consecutive empty reads). Re-opening the serial port recovers it every time,
because re-opening resets the target.

## Isolation, already done

| condition | result |
|---|---|
| `RUN:arc:180` standalone, no telemetry | works cleanly and reproducibly |
| `RUN:gap` (pre-existing, zero-motion verb) under active telemetry | **identical hang** |
| v6 `STATUS` under active telemetry | works; telemetry keeps flowing |
| v6 `RUN arc 180 #<id>` (sequenced) under active telemetry | no hang — 144 frames in 8 s — but **does nothing** |

So the trigger is specifically **a cleartext `RUN:` line arriving while v6
streaming is on**. It is not general concurrency, and it is not the new verb.

## Why the obvious workaround does not exist

`WireAdapter::onRun()` (`src/comms/wire_adapter.cpp`) is a permanent,
deliberate stub that always returns `kUnknown`. `src/DESIGN.md` states the
reasoning plainly: *"`onRun()` is an honest `kUnknown` — the real by-name test
trigger is protocol.cpp's MessageBus RUN bridge, a CODAL mechanism this
host-portable class must never touch."*

That is a defensible layering decision, but it has a consequence nobody appears
to have noticed: **the only working by-name RUN dispatch is the cleartext
prefix path, and that is exactly the path that hangs.** A sequenced v6
`RUN <name> ... #<id>` reaches the stub, returns `err 1`, and never touches the
handler.

So today there is no way to trigger a test program by name over the wire while
telemetry is active. Every capture tool that needs both is stuck.

## Suspected mechanism, not yet confirmed

Two separate receive paths in `src/comms/protocol.cpp`'s fiber loop: a literal
`"RUN:"`-prefix check calling `handleRun()`, versus `wireHandler_.feed()` for
everything else. `handleRun()` raises a MessageBus event, and the TS handler
then runs a whole tour on the event fiber — while the protocol fiber is also
emitting telemetry every 50 ms and, if a motion obligation is live, calling
`tickDrive()`.

Worth checking first, in rough order of suspicion:
1. **Serial TX contention.** `SerialTransport::writeLine()` has a two-writer
   guard with a bounded retry and a drop counter, readable via `probe(26)` /
   `diagValue(26)`. If the RUN handler's `emitLine()` calls and the protocol
   fiber's telemetry collide hard enough to exhaust the retry cap, that counter
   will be non-zero — a cheap first measurement.
2. **RX ring overflow.** The serial RX ring is capped at 255 bytes by codal's
   `uint8_t` API against a 240-byte max line; `serial_transport.h` already
   documents that two full lines in one drain window can overflow.
3. **Fiber starvation.** The event fiber running a tour may not yield in a way
   that lets the protocol fiber drain, and telemetry stopping (not just the
   reply) points this way.

## What to do

1. Measure `probe(26)` immediately after reproducing the hang — it
   distinguishes hypothesis 1 from the others in one reading, and needs no code
   change.
2. Decide whether the v6 RUN verb should actually work. If the layering
   objection to `onRun()` is about `WireAdapter` not touching CODAL, the bridge
   could live in `protocol.cpp` (which already owns the MessageBus path) with
   `WireAdapter` delegating through a forward declaration — the same pattern
   `shims.cpp` entry points already use. That would give bench tooling a
   sequenced, ack'd, non-hanging trigger and make the cleartext path a legacy
   fallback rather than the only road.
3. Fix the hang regardless — a legacy path that silently kills the link for 15 s
   is worse than one that refuses.

## Impact on what has been measured

Sprint 018 ticket 003 could not capture h(t) and fell back to endpoint-only
data. Any past campaign that subscribed telemetry and triggered a run by
cleartext `RUN:` may have lost frames or stalled without the operator
noticing — worth re-reading `tour_capture.py`-shaped captures with this in
mind, particularly any with unexplained telemetry gaps. Note
`first-camera-scored-tour-fails-closure-gate.md` already records "telemetry loss
degraded badly across the session: 5.5% early, then 44%, 88%, 98%" — that is a
candidate instance of this and should be re-examined.

Full evidence in sprint 018 ticket 003's Hardware Evidence section and
`tools/arc_capture.py`'s "KNOWN BLOCKER" docstring.

## Closed — fixed by sprint 027 ticket 001, hardware-confirmed 2026-09-02

Root cause confirmed to be
`concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`: two
fibers writing the nRF52 UARTE concurrently (the protocol fiber's own
telemetry emission, and the MessageBus fiber a cleartext `RUN:` line
with a payload spawns) can leave the UARTE wedged in both directions.
Telemetry streaming guarantees the protocol fiber is actively writing,
which is why this issue's own repro needed it — but the actual defect
never required telemetry, only a second concurrent writer (RUN with a
payload was always sufficient on its own).

**Fix**: sprint 027 ticket 001 makes the protocol fiber the single
producer for both serial and radio output
(`Protocol::emitLine()`/`drainEmitQueue()`, `comms/emit_queue.h`).

**MEASURED tigez 2026-09-02**, sprint 027 ticket 002 hardware
acceptance, fixed firmware (this repo's HEAD at the time, sha256
`d4e90bef6d0652083193f69447f3a67544a286649d675d1e3668cdfc8eac1473`,
`drainEmitQueue` confirmed present in the compiled source):
`captures/tigez-uart-wedge-20260902/08-fixed-tlm-subscribed-run.txt`
(directory on disk, not committed — `captures/` is repo-gitignored;
excerpt below is the load-bearing record).

One serial session: `HELLO`, then `TLM POSE #1` (sequenced), 58 `t`/
`thdr` frames read at the expected ~50 ms cadence over ~3 s. Then
cleartext `RUN:tlmsoak` (unbound, zero-motion name) sent **while
telemetry was still streaming** — this issue's exact trigger. Result:
telemetry never stopped. 151 more frames arrived over the following
~8 s, inter-line gaps staying in the same 0.00-0.06 s band the entire
time (`max_gap_after=0.06s`) — no multi-second silence, let alone this
issue's originally-recorded 15 s+ total hang. A final `HELLO` sent
after all that answered immediately with the normal boot banner,
interleaved cleanly with telemetry still arriving.

The v6 RUN verb question this issue also raised ("decide whether the v6
RUN verb should actually work") remains open as a separate, lower-
priority design question — `WireAdapter::onRun()` is still a permanent
`kUnknown` stub, and the cleartext `RUN:` prefix is still the only
by-name test trigger. That is unchanged by this fix and is not part of
what this issue was tracking (the **hang**, not the missing v6
alternative); it is not reopened here.
