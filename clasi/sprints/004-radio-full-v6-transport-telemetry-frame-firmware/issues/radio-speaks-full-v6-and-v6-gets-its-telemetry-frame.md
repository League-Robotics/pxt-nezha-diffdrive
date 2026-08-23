---
status: in-progress
split_into:
- retrofit-bench-tooling-onto-the-v6-telemetry-stream.md
sprint: '004'
tickets:
- 004-001
- 004-002
- 004-003
- 004-004
- 004-005
---

# Radio speaks full v6, and v6 gets its telemetry frame

## Description

Two holes sprint 003 left, which only became visible on the bench. They are one
issue because the second is worthless without the first: the tours run over
radio, so a telemetry frame that cannot reach the relay fixes nothing.

**There is no telemetry frame.** `WireHandler::emitTelemetry()`
(`src/wire_handler.cpp:977`) emits only the ack/nack reliability keepalive. The
v5 line `TLM:<ms>:<x>:<y>:<h>:<ox>:<oy>:<oh>:<vl>:<vr>` was deleted with no
replacement, so `tour_run.py`, `tour_capture.py`, `tour_watch.py`,
`truth_check.py`, `rotation_check.py` and `tour_practice.py` run to completion
and write **empty** CSVs. That is this project's recurring failure mode — an
instrument that returns nothing is indistinguishable from a robot that did
nothing — and it will produce confident, wrong tour scores until fixed.

**Radio only accepts `RUN:`.** Stakeholder intent, stated 2026-08-23: *the radio
is meant to be the full protocol, the same as every other path.*

## Cause

The telemetry frame **is** specified — `protocol.md` §5.2: `thdr` names the
columns, `t` carries the values, self-describing so a consumer never hardcodes a
column index. Sprint 003 marked its acceptance criterion satisfied by the
*absence* of the old cleartext line, reading the verb table's "—" reply column
as "no telemetry". That reading is wrong: the "—" means `TLM` has no
*acknowledgement* reply beyond its ack; the frames are a separate unsolicited
stream, and `TLM`'s `OFF`/`POSE`/`FULL`/`NOW`/`AUTO`/`BUFFER` argument only means
anything if there is a stream to select.

The radio restriction was sprint scope, not design — recorded as "sprint.md Open
Question 4". Its stated rationale is circular: *nothing can reach the v6 stack
over radio (RX stays RUN-only), so mirroring replies there had no host to
address.* It justifies itself with its own premise.

## Proposed fix

### Phase A — radio becomes a full v6 transport

The spec prescribes the shape: **one `ProtocolHandler` per transport over one
shared adapter** (`wifi-link.md:373`; `:249` — each transport's lines go to
"this transport's own `ProtocolHandler`").

That structure is what makes it safe. Two transports feeding one handler would
share `expectedNext_`/`gapOutstanding_`, so two independent hosts would corrupt
each other's sequence. A handler each, adapter shared, prevents it structurally.

- `src/protocol.h`/`.cpp`: a second `WireHandler` for radio, plus a `RadioSink`
  beside the existing `SerialSink` (`protocol.h:186`). `RadioSink` strips the
  trailing `'\n'` — `RadioTransport::sendLine()` appends its own.
- Route radio RX into that handler instead of the `RUN:` prefix test
  (`src/protocol.cpp:263-270`). **Keep the `RUN:` carve-out** — `test.ts`'s bench
  tooling still speaks it. Try v6 first, fall back on the old prefix.
- Both handlers emit their keepalive on the existing 50 ms cadence
  (`protocol.cpp:280`), each answering its own host.

**Re-entrancy guard.** `RadioTransport`'s `payloadBuf_`/`frameBuf_` are
documented single-fiber-only (`radio_transport.h:128-134`). Today only
`emitLine()` sends, from the TS fiber; this adds the protocol fiber as a second
caller, and `datagram.send()` can block and yield. Add a `sending_` bool so the
second caller drops, and a bool return so `emitLine()` can `fiber_sleep(2)` and
retry once. Losing a `t` frame is harmless — the `seq` gap makes it visible.
Losing an `OCAL:` corner fix silently degrades tour scoring.

### Phase B — the telemetry frame

Wire shape per §5.2: `thdr <col> …\n` then `t <v> …\n`, space-separated,
lowercase, **no `#id`** (telemetry is unsequenced). Signed base-10 integers;
`hex`-flagged columns print lowercase hex with no `0x`. Order within one
emission: `thdr` (if due), `t`, then the ack/nack line.

Adapter→handler API, copied from the reference (`adapter.h:113-139`) into
`src/wire_handler.h`:

```cpp
struct Column  { const char* name = ""; int32_t value = 0; bool hex = false; };
struct Snapshot{ const Column* columns = nullptr; size_t count = 0; };
```

The adapter builds and scales; the handler only prints.

Split the method, because the keepalive must survive `TLM OFF`:

```cpp
void emitReliability();                        // today's emitTelemetry()
void emitTelemetry(const Snapshot& snapshot);  // thdr? -> t -> emitReliability()
```

Header memo on the handler (`headerChanged()`/`rememberHeader()`, comparing
count, names and hex-ness, storing a **copy**; `kMaxHeaderColumns=40`,
`kMaxHeaderNameBytes=16`).

**Plus a 1 Hz header refresh.** "Emit `thdr` only on change" assumes a reliable
stream with the consumer present from byte one. Over a lossy broadcast radio,
with tools that attach the relay *after* boot, `thdr` goes out once and is never
seen again, leaving every `t` undecodable. Re-emit every 20 frames. ~60 bytes/s.

**Columns.** POSE is the archived v6 set (`seq now flags x y h ox oy oh`,
`radio-robot-lib/src/archive/protocol-v6/wire_v6_telemetry.h:18-31`) plus
`vl vr i2cf`:

| col | source | unit |
|---|---|---|
| `seq` | adapter counter, `(seq_+1) & 0x7F` | 1 |
| `now` | `WireAdapter::now()` | ms |
| `flags` | shared `computeFlags()` | **hex** |
| `x` `y` | `poseX()` `poseY()` | mm |
| `h` | `poseHeading()` | cdeg |
| `ox` `oy` | `otosGet(0)/10`, `otosGet(1)/10` | mm |
| `oh` | `otosGet(2)` | cdeg (already) |
| `vl` `vr` | `wheelSpeed(0)` `wheelSpeed(1)` | mm/s |
| `i2cf` | `diagValue(8)` | count |

FULL adds `cyc posl posr dutl dutr lexc wrng cycovr`.

`vl`/`vr` sit in POSE, not FULL, because wheel speed must **never** be
re-derived by differencing the pose stream — 24 ms ticks sampled at ~56 ms alias
into a ±25% sawtooth (a steady 44 cm/s once read as 55/55/84). Putting the
correct instrument on the default channel is what stops a consumer inventing the
wrong one. `i2cf` because the I2C fault counter is the documented signal for a
wedged brick and `STATUS` currently has no numeric surface at all.

**Units stay v5-compatible integers.** Do not adopt the reference's `mm/s ×10`
quantum — every tool's arithmetic is written against the v5 scales, and changing
scale during a format migration is exactly the silent-wrong-number failure to
avoid. Keep `otosGet(n)/10`'s truncation toward zero and pin it in a test.

**Boot default `TlmMode::kOff`, spec-conformant.** Phase A is what permits this:
a radio host can now send `TLM POSE #1`. Had radio stayed RUN-only, defaulting
ON would have been forced as a documented deviation.

**Projection on `WireAdapter`** — the only object holding `mode_`
(`wire_adapter.h:334`). Add `buildSnapshot()` and `telemetryEnabled()` as public
methods (not on `Wire::Adapter`; the app calls them). Reach live state through
the existing forward-declaration block (`wire_adapter.cpp:12-70`) — all five
sources already exist in `shims.cpp`, so no new entry point and no header:

```cpp
int poseX(); int poseY(); int poseHeading();  // MUTATE: each calls odomUpdate()
int otosGet(int what);                        // 0,1 -> 0.1mm; 2 -> cdeg; CACHE ONLY
int wheelSpeed(int which);                    // mm/s
```

Three hazards to comment at that block:
- `poseX/Y/Heading` mutate, and that is **load-bearing** — between moves nothing
  else advances odometry, so the 50 ms frame is what keeps pose current when
  idle. v5 depended on it. Do not collapse into one cached read.
- `otosGet(0)/(1)` are **0.1 mm**; `otosGet(2)` is already cdeg. Divide the
  first two only.
- `otosGet()` reads the **cache**. The protocol fiber must **never** call
  `otosRead()` — an I2C transaction interposed in the Nezha encoder's
  select→read window destroys the sample (the Phase F failure).

Lift the flags word out of `status()` (`wire_adapter.cpp:236-245`) into a shared
`computeFlags()` so `STATUS`'s `flags=` and the telemetry column cannot disagree,
and add `i2cf=<n>` to `STATUS`.

**Format into a `WireHandler` member buffer, not a stack local.** The protocol
fiber is 2 KB and `run()` already holds a 240-byte line buffer;
`radio_transport.h:128` records a *measured* hard-fault ~1 s after boot from
exactly this. Also plain `snprintf` (not `std::snprintf` — not in `namespace
std` on newlib-nano) and **no `%f`**; emit scaled integers.

### Phase C — bench checkpoint

Flash; verify telemetry flows over both serial and radio; check `diagValue(19)`
(tick overruns) before and after; confirm boot still survives an unpowered brick
(the first `poseX()` now triggers `ensure()` from the protocol fiber ~50 ms after
boot rather than at the user's first block call). **Stop and hand over here**
before any tooling is written against an unconfirmed format.

### Phase D — tooling

Split out into
[[retrofit-bench-tooling-onto-the-v6-telemetry-stream]], so it can be planned
against a wire format a robot has actually confirmed. It must not start until
this issue's Phase C bench checkpoint has passed.

## Verification

**Scale, not shape** — a shape test proves nothing about units. Each test must be
one where source and wire values differ by the factor under test:

| test | input | expects | catches |
|---|---|---|---|
| OTOS 0.1mm→mm | raw `1234,-5678,9000` | `123 -567 9000` | missing `/10`; `/100`; round-half → `-568` |
| pose passthrough | `123,-45,6789` | unchanged | accidental scaling |
| `h`/`oh` both cdeg | `9000` | `9000` not `90` | a deg conversion |
| wheel speed | `440,-440` | unchanged | a `×10` copied from the reference |
| `flags` hex | `0x2A` | ` 2a ` | `%d`, `%X`, `0x` prefix |
| `i2cf` decimal | `26` | `26` not `1a` | wrong `hex` bit |

Negatives on `oy`/`vr` so a `static_cast<uint32_t>` slip shows.

**Frame mechanics**: `thdr` on frame 1 and not frame 2; re-emitted on count
change, name change, and **hex-ness-only change** (a lazy memo misses that);
re-emitted on frame 20; byte-exact ordering `thdr`→`t`→`ack`; `seq` wraps 127→0
over 130 frames; `emitReliability()` alone emits no `t`; the telemetry sink gets
frames but **not** the ack; the widest FULL set is < 200 bytes
(`RadioTransport::sendLine()` truncates silently there); the header memo is a
copy.

**Per-transport reliability**: a sequence gap on radio must not disturb serial's
`expectedNext_`, and vice versa. That is the whole justification for two
handlers — test it directly.

**Two unusual tests worth their keep**: one asserting `otosRead` appears nowhere
in `wire_adapter.cpp` (Phase F is catastrophic, silent, and one careless line
away); and one golden frame in `tests/host/golden_telemetry.py` imported by both
the C++-driven test and the Python parser test, so emitter and parser cannot
drift.

**End to end**: `uv run pytest` (220 at time of writing), `uv run python
tools/make_deploy.py` (re-run on the documented nondeterministic V1 `TS9283`
abort), the Phase C bench check, then a real `tour_run.py --tour world`
producing a non-empty CSV with a loss report.

## Related

- Supersedes `v6-has-no-telemetry-frame-bench-tooling-collects-nothing.md`,
  which this issue absorbs.
- Closes `status-lost-diag-numeric-surface.md` via the `i2cf` column and the
  `STATUS i2cf=` addition.
- **Two tools are already silently dead, independent of v6**:
  `tour_watch.py:202` tests `len(f) == 7` and `tour_capture.py:70` accepts only
  7/4/3, but the v5 line carried **nine** fields. Both branches died when
  `vl`/`vr` were added and nobody noticed — the same empty-CSV failure, already
  in the tree, and the strongest argument for the shared parser plus the loud
  guard.
- Spec authority: `radio-robot-lib/docs/design/protocol.md` §5.2, §6, §8.5;
  `wifi-link.md` §6; reference implementation in that repo's
  `src/protocol/protocol_handler.cpp` and `src/adapter/diffdrive_adapter.cpp`.
