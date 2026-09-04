# Code review 2026-09-02 — `src/comms/`

Scope: `protocol.h/.cpp`, `wire_handler.h/.cpp`, `wire_adapter.h/.cpp`,
`serial_transport.*`, `radio_transport.*`, `run_queue.h`, `emit_queue.h`,
read in full against `src/DESIGN.md` §4/§5/§6/§8, `src/comms/DESIGN.md`,
and `.claude/rules/fiber-yield-safety.md`. Every finding below was
verified against the current tree (branch
`claude/code-review-errors-cohesion-1bde6b`, HEAD 50efc2d); line numbers
are from that tree. Deduplicated against `clasi/issues/**`,
`clasi/sprints/done/*/issues/**` and `docs/code-review/2026-08-26/`.

## Summary table

| ID | Severity | file:line | One-line summary |
|---|---|---|---|
| CM-01 | Major | `protocol.cpp:342-345`, `shims.cpp:715` | The tick service hook gates on `motionOwner_`, not on fiber identity, so a second fiber calling `driveTick()` during a RUN job runs `serviceOnce()` — and with it `WireHandler::dispatch()` — concurrently with the protocol fiber |
| CM-02 | Major | `wire_adapter.cpp:735-741, 782-799, 834-842`; `protocol.cpp:553` | Natural motion completion clears the obligation only inside `lastDone()`/`lastDoneReason()`, which only a host reply triggers — a quiet host leaves the protocol fiber co-ticking for the full `timeout` and blocks queued RUN jobs (C-05 only partially fixed) |
| CM-03 | Major | `wire_adapter.cpp:882-885`; `shims.cpp:1122-1130`; `otos_port.cpp` `setPose()` | `SET rebase` performs an OTOS I2C write on the protocol fiber; its busy gate misses continuous-mode driving on another fiber, so the write can land inside that fiber's `kernel.step()` encoder settle window |
| CM-04 | Major | `wire_adapter.cpp:924-934`; `wire_handler.cpp:1178-1196` | `TLM NOW` acks `kOk` and emits nothing — the documented one-shot frame is never built |
| CM-05 | Minor | `radio_transport.cpp:170`, `serial_transport.cpp:61-68`, `protocol.cpp:183-188` | Both transports' two-writer guards and retry policies are vestigial since the emit ring made the protocol fiber the sole producer; the comments still describe a TS-fiber writer that no longer exists, and the real second serial writer (MakeCode's own `serial.writeLine`) bypasses the guard entirely |
| CM-06 | Minor | `protocol.cpp:416, 456-458`; `radio_transport.cpp:99`; `radio_transport.h:365-366` | One inbound line per transport per pass (= per 24 ms tick while a job runs); serial ring overflow and the radio single-slot drop are both silent, and `rxFrames_`/`rxAccepted_` are declared but never incremented |
| CM-07 | Minor | `wire_handler.cpp:1552-1567, 1569-1595`; `protocol.h:340-344, 358-370` | `emitHeader()`/`emitFrame()` drop their `\n` when the line reaches 239 bytes and both sinks then strip the last *data* byte blind; the pinned pathological FULL frame is exactly 239 bytes, zero headroom |
| CM-08 | Minor | `protocol.cpp:249-258, 274-278` | `handleRun()` drops overlong (≥48 B), non-printable and empty-name payloads silently and uncounted; the 400 ms dedupe also swallows a deliberately repeated `abort` |
| CM-09 | Minor | `wire_handler.cpp:1439-1475` | `execRun()` commits ~750 B of stack locals before the adapter can refuse, on the fiber whose 2 KB stack this project has already measured overflowing; reachable from any `RUN x #n` line, nested inside a job's call chain (stack impact UNVERIFIED) |
| CM-10 | Minor | `radio_transport.h:363`, `wire_adapter.h:320-324`, `run_queue.h:13-21`, `emit_queue.h:15-19`, `serial_transport.h:71-92`, `radio_transport.h:77-89`, `protocol.h:361-367`, `wire_handler.cpp:912`, `src/DESIGN.md` §6/§8 | Comments and design text that are actively false about the current code (not merely noisy) |
| CM-11 | Suggestion | `protocol.h:384-398`; `protocol.cpp:182, 456, 510` | Radio enable state lives on `Protocol` as three scattered gates while `RadioTransport` self-enables lazily; move it onto the transport |
| CM-12 | Suggestion | `protocol.cpp:415-478, 273, 377, 500, 533`; `protocol.h:337-374` | Serial/radio poll branches, the two sinks and four `nowMicros()/1000` conversions are copy-pairs; factor a `routeLine()`, one `TransportSink`, one `nowMs()` |
| CM-13 | Suggestion | `protocol.h:264-307`; `protocol.cpp:241-352` | The cleartext RUN bridge (dedupe, ring, bypass, current-text, dispatch) is a separable object living inside `Protocol` |
| CM-14 | Suggestion | `protocol.h:146-156`; `wire_adapter.h:333-338` | `motionOwner_` and `jobOwnsMotion_` store one fact twice |
| CM-15 | Suggestion | `wire_handler.cpp:706` | `expectedNext_ = id + 1` at `id == UINT32_MAX` wraps to 0 and stalls every later id until HELLO (theoretical) |
| CM-16 | Suggestion | `wire_adapter.cpp:854`; `wire_handler.cpp:1145-1148` | `GET rebase` answers `err 1` ("unknown name") for a field HELP/GET-dump advertise |

Status of the 2026-08-26 items this review was asked to re-check:

| Item | Status |
|---|---|
| C-05 (obligation never cleared) | **Partially fixed.** `resolvePendingIfDue()`/`forceResolvePending()` now clear `motionObligationActive_` (`wire_adapter.cpp:798, 825`), but nothing on the fiber loop ever calls them — see CM-02. |
| C-10 (`execHelp` terminator drop) | **Fixed.** `buildHelpLine()` bounds content at `bufCap - 2` and writes `\n` last into reserved space (`wire_handler.cpp:1020-1029`); HELP is chunked to 60 B lines. The same defect pattern survives in `emitHeader()`/`emitFrame()` — CM-07. |
| Q-04 (`kMaxLineBytes` ×4) | **Still open, still guarded.** `serial_transport.h:23`, `radio_transport.h:205` (`kMaxPayloadBytes`), `radio_transport.h:356`, `wire_handler.h:380`; pinned by `test_radio_serial_wire_capacity_constants_are_equal_at_240`. |
| 08-26 comment audit "stale cross-layer claims" (`radio_transport.h` cites `Protocol::formatDiag()`) | **Still present** at `radio_transport.h:363`. Listed under CM-10. |

---

## Yield-point inventory (dimension 1 groundwork)

CODAL is cooperative, so a race needs a real yield between check and
use. Every yield reachable from `src/comms/`:

| Site | Yield | Who calls it |
|---|---|---|
| `serial_transport.cpp:22-26` `guardedSerialSend()` — `uBit.serial.send(..., SYNC_SLEEP)` | blocks on `fiber_wait_for_event` when the 255 B TX ring fills | `SerialTransport::writeLine()` ← `SerialSink::write()` (every reply/telemetry line), `Protocol::emitLineNow()` |
| `serial_transport.cpp:67` `vfpSafeSleep(2)` | yes | `writeLine()` guard retry |
| `protocol.cpp:185` `vfpSafeSleep(2)` | yes | `emitLineNow()` radio retry |
| `protocol.cpp:571` `vfpSafeSleep(kPollIntervalMs)` | yes | `run()` idle branch |
| `protocol.cpp:555` `tickDrive()` → `shims.cpp:647-649` (`stepBusy` wait), `kernel.step()`'s two encoder settle sleeps (via `CodalSleeper`), the pacing sleep after the hook | yes | `run()` while `motionOwner_ == kWire`; a RUN job's own `driveTick()` loop |
| `protocol.cpp:325, 332` `runDispatch()` → `runAction0()` (TS job body) | yes — the job runs for as long as it likes and ticks inside | `dispatchJob()`, `invokeRunDispatch()` |
| `uBit.radio.datagram.send` (`radio_transport.cpp:142`) | **no** (audited, `fiber-yield-safety.md`) | `sendFragmented()` |
| `uBit.serial.read(ASYNC)`, `uBit.i2c`, `MessageBus::send` | **no** (audited) | `tryReadLine()`, kernel |

Not a yield but a second *fiber*: `RadioTransport::onDatagram()`
(`radio_transport.cpp:79-103`) runs as a MessageBus listener, i.e. on a
scheduler-dispatched fiber, cooperatively — it touches only `rxLine_`,
`rxLen_`, `rxReady_`, `rxOversizeDropped_`.

Fibers that exist in a running program: the protocol fiber (`run()`),
the MessageBus/event fibers (datagram listener, `input.onButtonPressed`
handlers), the student's main fiber, any `control.inBackground` fiber,
and — in `test/test.ts` — a background OTOS sampler (`test.ts:808-813`).
Since sprint 028 a RUN job runs *on the protocol fiber*; the old
second job fiber is gone.

---

## Findings

### CM-01 — Major — the service hook runs `serviceOnce()` on whatever fiber called `driveTick()`, not only the protocol fiber

**Dimension:** race / fiber safety.

**Code.** `protocol.cpp:342-345`:

```cpp
void Protocol::serviceHookEntry() {
  if (protocol().motionOwner_ != MotionOwner::kJob) return;
  protocol().serviceOnce();
}
```

`shims.cpp:715`: `if (r.serviceHook) r.serviceHook();` — fires on *every*
`tickDrive()` call, from *any* fiber, after `stepBusy = false`.

`protocol.h:221-229` states the invariant the guard is supposed to
enforce: "(b) from a student's own program driving continuous-mode
motion on THAT program's own fiber ... (b) must never run serviceOnce()
on a fiber other than this one." The guard checks *state*
(`motionOwner_ == kJob`), not *which fiber is calling*. Those are the
same thing only if exactly one fiber ever ticks while a job runs.

**Concrete scenario** (from the shipped test program). A `RUN:tour:...`
job is dispatched on the protocol fiber (`motionOwner_ = kJob`,
`protocol.cpp:323`). The operator presses button B; `test.ts:534-536`
runs `tourWorld()` on a MessageBus fiber, which loops
`while (diffDrive.driveTick())` (`test.ts:74`). Each of that fiber's
`tickDrive()` calls now runs `serviceOnce()` on the button fiber while
the protocol fiber is somewhere inside its own `serviceOnce()` or
parked in its own `tickDrive()`.

**Why it corrupts state.** `serviceOnce()` is not re-entrant across
fibers:

- `WireHandler::dispatch()` (`wire_handler.cpp:706-712`) sends the ack
  (`replyAck` → `SerialSink::write` → `writeLine` → SYNC_SLEEP **yield**)
  and only *then* runs `execute(fields, ...)`. `fields` are pointers into
  `WireHandler::lineBuf_` (`wire_handler.cpp:401-402, 422-423`). If the
  other fiber's `serviceOnce()` feeds the next inbound line into the
  same `wireHandler_` during that yield, `appendByte()` overwrites
  `lineBuf_` under the parked fiber's `fields[]`, and the parked fiber
  then executes a motion verb with the *new* line's digits. This is
  execute-a-command-the-host-never-sent, the exact class
  `radioRxLineFits()` was written to prevent at the transport.
- `Protocol::lineBuf_` (`protocol.h:434`) and `rxLineBuf_` are shared
  scratch with the same problem one layer up; the comment at
  `protocol.h:424-433` argues safety only for *same-fiber* nesting.
- `drainEmitQueue()` gets two consumers; `dispatchJob()` is protected by
  `motionOwner_` but `handleRun()`'s abort bypass and `lastRunMs_`/
  `lastRunText_` are not.
- `SerialTransport::writeLine()` / `RadioTransport::sendLine()` get a
  genuine second writer again — the situation sprint 027 removed.

`stepBusy` still serializes `kernel.step()`, so this does not by itself
interleave I2C; it corrupts the wire layer.

**Remedy.** Compare fiber identity, not owner state: capture
`codal::currentFiber` (or `fiber_get_current()`-equivalent) in `run()`
into a `Fiber* protocolFiber_` and make `serviceHookEntry()` return
unless the current fiber is that one. Alternatively register the hook
only for the duration of `dispatchJob()`'s `runDispatch()` call *and*
still compare fibers — a state check alone cannot express "this fiber".
Add a host test for the invariant if `serviceHookEntry()` is given an
injectable "current fiber" seam.

**Dedupe:** none found. `single-executor-for-command-dispatch.md` (sprint
028, done) designed the hook; `fiber-safety-and-command-dispatch.md`
(sprint 026, done) is about the VFP bank, not this. Not the same as
`ensure-is-not-reentrant-two-rigs-can-be-constructed.md`.

---

### CM-02 — Major — natural completion clears the motion obligation only when a host happens to ask; a quiet host keeps the protocol fiber ticking for the full `timeout` and starves queued RUN jobs

**Dimension:** correctness (C-05 follow-through) / bus discipline.

**Code.** The fiber loop's tick gate, `protocol.cpp:553-555`:

```cpp
if (wireAdapter_.hasLiveMotionObligation()) {
  motionOwner_ = MotionOwner::kWire;
  tickDrive();
```

`hasLiveMotionObligation()` (`wire_adapter.cpp:735-741`) reads
`motionObligationActive_` and the deadline — it never resolves. The only
natural-completion clear is `resolvePendingIfDue()`
(`wire_adapter.cpp:782-799`), which is private and called from exactly
two places: `lastDone()` and `lastDoneReason()` (`:834-842`). Those are
called from `replyAck()`/`replyNack()`/`execStatus()`
(`wire_handler.cpp:735-736, 744-745, 1006-1007`) — i.e. only when an
inbound sequenced line or `STATUS` arrives. `buildSnapshot()` does not
call them.

**Scenario.** Host sends `MOVE_X 500 0 0 30000 #7` (30 s backstop, the
documented "set it generously" posture), the move completes in 3 s, the
host then sends `RUN:tour:wheels` over cleartext (unsequenced — no ack,
no `lastDone()` call). `dispatchJob()` refuses while
`motionOwner_ == kWire` (`protocol.cpp:311, 553-554`); the job sits in
`runQueue_` for the remaining 27 s, and the kernel is stepped (encoder
I2C every 24 ms) the whole time. With `TLM POSE` on, nothing changes —
telemetry never touches the completion channel. `tools/robotlink.py`'s
`send_until()` happens to poll with sequenced verbs, which is why this
is invisible from the bench scripts and visible from a raw relay
session.

**Remedy.** Resolve on the fiber loop, not only on reply formatting:
have `hasLiveMotionObligation()` call `resolvePendingIfDue()` first
(both are already `const`/`mutable`-safe), or expose a
`pollCompletion()` and call it at the top of `run()`'s loop. Update the
C-05 closure note in `src/DESIGN.md` §5 ("sprint 016 ticket 003") to say
*when* the clear happens.

**Dedupe:** C-05 in `docs/code-review/2026-08-26/review.md:366-408` —
this is its residual, not a re-report. Related open issue:
`i2c-fault-count-climbs-on-idle-bus.md` (idle-bus traffic; C-05 named
this as a candidate mechanism and it still applies).

---

### CM-03 — Major — `SET rebase` writes the OTOS over I2C from the protocol fiber; its busy gate does not see continuous-mode driving on another fiber

**Dimension:** I2C / shared-bus interposition (dimension 2).

**Trace.** `SET rebase 1 #n` → `execSet` → `WireAdapter::onSet()`
(`wire_adapter.cpp:861-900`) → gate at `:882-885`:

```cpp
if ((entry->ordinal == kOrdinalRebase || entry->ordinal == kOrdinalEstopClear) &&
    (hasLiveMotionObligation() || engineMoveActive())) {
  return Wire::Result::kBusy;
}
```

→ `setKernelValue(32, 1000)` → `shims.cpp:1122-1130`:

```cpp
case 32:
  if (v != 0.0f) {
    odomUpdate(r);
    k.rebasePosition();
    r.x = 0.0f; r.y = 0.0f; r.heading = 0.0f;
    otosRef().setPose(0.0f, 0.0f, 0.0f);
```

`OtosPort::setPose()` ends in `writePoseMm(...)` (`otos_port.cpp`), an
I2C transaction to 0x17 on the bus the Nezha encoders share.

**When this runs.** `onSet` executes inside `serviceOnce()`, which runs
either (a) at the top of `run()`'s loop — the protocol fiber is *not*
inside `kernel.step()`, but any other ticking fiber may be — or (b)
nested in the hook, after `stepBusy = false` (safe against the job's own
step). Case (a) is the problem: a student `on start` / button handler
running `setWheelSpeeds()` + `while (driveTick())` (`motion.ts:118-124`,
the documented continuous-mode idiom) has **no** move-engine move
(`engineMoveActive()` false) and **no** wire obligation, so the gate
admits the rebase. `kernel.step()` on that fiber yields twice in its
encoder select→read settle (`shims.cpp:706-710`), and the OTOS write
lands there. The comment at `wire_adapter.cpp:878-881` acknowledges
exactly this hole ("Not caught by either: a job driving wheel speed
directly").

**Consequences.** The settle-window interposition destroys that encoder
sample (`fiber-yield-safety.md` "Related invariants"; Phase F), which
feeds the PID as a velocity glitch; and per this project's own hardware
notes any OTOS transaction is a wedge risk (`run-probe-bricks-the-board`
memory, `first-i2c-command-can-wedge-the-program-with-no-recovery.md`).
`SET estop_clear` (`case 33`) is a kernel-internal call with no I2C, so
only `rebase` carries the bus hazard; `stall_clear` is a deferred
counter.

**Also in this class, accepted trade-offs worth recording:** wire `ESTOP`
→ `estopAll()` → `kernel.emergencyStopMotors()` → `left_/right_.emergencyStop()`
(Nezha I2C, `shims.cpp:874-878`, `diffdrive.cpp`), and wire `STOP` →
`stopAll()` → `deliverStopNow()` → the same port-level writes
(`shims.cpp:863-871`). Both are motor writes from the protocol fiber that
can interpose the same window when another fiber is mid-step. For a
panic stop that is the right trade; for `STOP` it is the deliberate
sprint-006 fix (`cross-fiber-stop-settle-window-race.md`). Neither is a
new finding; `rebase` is, because it is a *sensor* write with no urgency.

**Remedy.** Do not perform the OTOS write synchronously on the caller.
Make the rebase request deferred like `kernel.rebasePosition()` already
is: set a `pendingOtosZero_` on the Rig and perform `otosRef().setPose()`
inside `tickDrive()` after `stepBusy = false` (the same fiber that just
stepped, so no interposition is possible). If a synchronous path must
stay, gate on `stepBusy` via a `kernelStepInProgress()` shim and refuse
`kBusy` while it is set.

**Dedupe:** `no-wire-verb-reaches-rebaseposition-so-tours-cannot-zero-their-frame.md`
(sprint 028, done) introduced the verb; it does not cover the bus
hazard. Not `tour-corner-fixes-are-stale-cache.md` (that is the read
side). Not `i2c-fault-count-climbs-on-idle-bus.md`.

---

### CM-04 — Major — `TLM NOW` is accepted and does nothing

**Dimension:** correctness, user-visible.

**Code.** `wire_adapter.cpp:924-934`:

```cpp
  // TLM NOW is a one-shot request in the CURRENT subscription's shape,
  // not a new subscription (protocol.md S6.1: "does not change mode") --
  // so it is deliberately never stored into mode_. ...
  if (mode != Wire::TlmMode::kNow) mode_ = mode;
  return Wire::Result::kOk;
```

`execTlm()` (`wire_handler.cpp:1178-1196`) forwards the adapter's result
and nothing else. No `buildSnapshot()`/`emitTelemetry()` call exists on
any `kNow` path (`grep -n kNow src/comms` → the enum, `parseTlmMode`,
`tlmModeWireName`, and this branch only). So `TLM NOW #5` → `ack 5 …`
and silence. `wire_handler.h:252-263` and `wire_adapter.h:222-223`
both describe NOW as "the pre-existing one-shot exception" — the
exception is that it is a no-op.

This is the "accepted, then answered nothing" shape the 2026-08-27
stakeholder direction (`wire_handler.cpp:584-612`) was written to
eliminate, and with telemetry off it is the only way a host could ask
for a single pose fix without subscribing.

**Remedy.** Either implement it — `onTlm(kNow)` sets a `oneShotDue_`
flag that `Protocol::serviceOnce()` checks alongside
`telemetryEnabled()` and emits one `thdr`+`t` pair on both handlers,
then clears — or refuse it honestly with `kUnimplemented` the way
`kBuffer` is (`:923`) and say so in `HELP`/protocol notes. Add a host
test either way (`test_wire_telemetry_projection.py` has the shim).

**Dedupe:** none found (grep `TLM NOW|kNow|one-shot` across
`clasi/issues`, sprint issues, 08-26 review).

---

### CM-05 — Minor — the transports' two-writer guards and retry policies are vestigial, and their comments describe a writer that no longer exists

**Dimension:** cohesion / stale invariants.

Since `EmitQueue` landed, `Protocol::emitLine()` (`protocol.cpp:135-163`)
only enqueues; every transport write happens in `emitLineNow()` or a
`Sink::write()`, both on the protocol fiber (`protocol.h:232-240`
states this correctly). Consequences:

- `RadioTransport::sendLine()`'s `sending_` (`radio_transport.cpp:170`)
  can never be observed true by a second caller: the only yield-free
  body (`datagram.send` does not yield) runs on one fiber. The retry in
  `emitLineNow()` (`protocol.cpp:183-188`) and the "ignore the drop"
  note in `RadioSink` (`protocol.h:361-367`) guard a race that cannot
  occur. `radio_transport.h:77-89` and `:319-322` still say "TWO fibers
  can call this — the TS fiber via Protocol::emitLine()".
- `SerialTransport::writeLine()`'s bounded retry
  (`serial_transport.cpp:61-68`) likewise has no legitimate second
  caller; `serial_transport.h:71-92` still names the TS fiber. The one
  *real* remaining second writer on `uBit.serial` — MakeCode's own
  `serial.writeLine` from student code — does not go through this
  class at all, so the guard cannot see it. That is the sprint-027
  wedge mechanism and stays outside this layer's power to fix.
- The only path that would make the guards live again is CM-01.

**Remedy.** Delete `sending_` + retry on both transports (keep
`dropCount_` for send failures), or keep a single `contention_` counter
that a future CM-01-style regression would light up. Rewrite the four
comment blocks to state the actual invariant: "single writer — the
protocol fiber". Update `src/DESIGN.md` §6's two-writer paragraphs.

**Dedupe:** `concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`
(sprint 027, done) — root cause of the wedge; this finding is the
cleanup it left behind, not a re-report.

---

### CM-06 — Minor — one inbound line per transport per pass, silent overflow on both, and two dead RX counters

**Dimension:** correctness / diagnosability.

`serviceOnce()` reads at most one serial line (`protocol.cpp:416`) and
one radio line (`:456-458`) per call. While a RUN job runs, the hook is
the only caller, so the poll rate is the 24 ms tick; in `kWire` it is
also the tick; idle it is 5 ms. Serial at 115200 delivers ~276 B per
24 ms into a 255 B ring (`serial_transport.h:55`): a host that writes
two full-length lines back-to-back (e.g. `SET a … #1\nSET b … #2\n` from
a script) overflows the ring within one tick and CODAL drops bytes with
no signal. On radio the second datagram in the same window is dropped
at `radio_transport.cpp:99` (`if (rxReady_) return;`) with no counter —
`rxFrames_`/`rxAccepted_` (`radio_transport.h:365-366`) are never
incremented anywhere (`grep -rn rxFrames_ src/` → declaration only).

**Remedy.** Drain in a bounded loop: `for (int n = 0; n < 4 && tryReadLine(...); ++n)`
per transport per pass. Count the `rxReady_` drop (`++rxDroppedUnconsumed_`)
and either wire `rxFrames_`/`rxAccepted_` into `diagValue` or delete
them.

**Dedupe:** not `rxlinebuf-64-truncates-long-inbound-radio-lines.md`
(that is per-line truncation, still open and cross-referenced here, not
re-reported); not `radio-telemetry-loss-is-wifi-interference-at-the-relay-site.md`
(air loss). The single-slot inbound design is acknowledged in
`playfield-testing.md`; the missing counter and the per-pass cap are
not filed.

---

### CM-07 — Minor — `emitHeader()`/`emitFrame()` drop the terminator at 239 bytes, and both sinks strip the last byte blind

**Dimension:** correctness (C-10's twin).

`wire_handler.cpp:1554-1558` and `1571-1575`:

```cpp
auto append = [&](const char* text) {
  while (*text != '\0' && pos < sizeof(emitBuf_) - 1) { emitBuf_[pos++] = *text++; }
};
... append("\n");
```

With `emitBuf_[240]`, content stops at 239 and a trailing `append("\n")`
is silently skipped once `pos == 239`. `SerialSink::write`/`RadioSink::write`
(`protocol.h:341, 359`) then compute `contentLen = length - 1` on the
assumption the last byte is `\n` — so a terminator-less line loses its
last *data* byte and is re-terminated, e.g. `… -12345\n` on the wire as
`… -1234\n`: a plausible, wrong number, not a parse error.
`test_widest_pathological_int32_min_frame_confirms_open_question_2`
pins the FULL worst case at exactly 239 bytes *including* `\n`, so
today the terminator survives with zero headroom; the next column added
to FULL, or any `Column::name` longer than the memo's 15 chars, crosses
it. `buildHelpLine()` (`:1020-1029`) already does this right
(`pos < bufCap - 2`, terminator written last into reserved space).

**Remedy.** Bound the append at `sizeof(emitBuf_) - 2` and write `\n`
unconditionally, as `buildHelpLine()` does; make both sinks check
`data[length-1] == '\n'` before stripping (or better, CM-12: pass the
terminated line through and let the transport not append). Extend the
pathological-frame test to assert the trailing `\n` is present.

**Dedupe:** C-10 (`review.md:497-503`) — fixed for HELP; this is the
same pattern in a different function and was not filed.

---

### CM-08 — Minor — `handleRun()` drops silently and uncounted; the dedupe window also eats a deliberate repeated `abort`

`protocol.cpp:249-258`: an overlong payload (`dataLen >= 48`), any byte
outside 0x20–0x7E, and a leading `:` all `return` with no counter and
no reply — `runQueue_.dropped()` counts only ring-full refusals. A
48-character `RUN:` line (e.g. a `RUN:tour:...` with several numeric
args) simply vanishes; from the relay it is indistinguishable from
radio loss. `:274-278`: the 400 ms same-text suppression is applied
before the abort/clearestop bypass, so `RUN:abort` twice within 400 ms
(an operator hammering the key) drops the second — harmless today, but
the bypass exists precisely so `abort` is never gated.

**Remedy.** Count all three refusals (one `runMalformed_` is enough) and
surface it next to ordinal 30; exempt bypass names from dedupe.

**Dedupe:** none found.

---

### CM-09 — Minor (UNVERIFIED impact) — `execRun()` allocates ~750 B of stack before the adapter can refuse

`wire_handler.cpp:1444-1447, 1462, 1471`: `argv[16]` (64 B),
`result[224] = {}` (zero-filled), `sanitized[224]`, `buf[241]` are all
live at entry, on the protocol fiber, before `adapter_.onRun()` — which
in production always returns `kUnknown` immediately
(`wire_adapter.cpp:1021-1030`). Call depth at that point can be
`run()` → `serviceOnce()` → `dispatchJob()` → TS job → `tickDrive()` →
hook → `serviceOnce()` → `feed()` → `onLineComplete()` (`tokens[20]`,
80 B) → `dispatch()` → `execRun()`. `radio_transport.h:314-318` records
a measured hard fault from ~450 B of locals on this same fiber. Whether
CODAL's heap-copied fiber stacks make this benign is UNVERIFIED — what
would settle it is a `RUN x #1` sent over radio mid-tour on a
`DIFFDRIVE_FAULT_SPIN` build, watching for CFSR.

**Remedy.** Move the three buffers below the `outcome != kOk` /
`!hasResult` early returns (they are only needed on the success path),
or make them `WireHandler` members like `emitBuf_`.

**Dedupe:** none found.

---

### CM-10 — Minor — comments and design text that are false about the current code

These are not verbosity (that is the boil-down list below); they assert
something the code no longer does:

| Location | Says | Actually |
|---|---|---|
| `radio_transport.h:363` | "the cleartext DIAG verb that used to read them (`Protocol::formatDiag()`)" | no `formatDiag` anywhere; flagged 2026-08-26, still present |
| `wire_adapter.h:320-324` | "protocol.cpp's own MessageBus RUN bridge (runSlots_/handleRun())" | no MessageBus, no `runSlots_` — it is `runQueue_` + `dispatchJob()` |
| `run_queue.h:13-21`, `emit_queue.h:15-19` | "The consumer is a MessageBus listener that receives an integer" | consumer is `dispatchJob()` on the same fiber |
| `serial_transport.h:71-92`, `radio_transport.h:77-89, 319-322`, `protocol.h:361-367`, `src/DESIGN.md` §6 | "two fibers call this today — the TS fiber via `Protocol::emitLine()`" | one fiber (CM-05) |
| `wire_handler.cpp:912-913` | "`version` (kVersion) is currently "1.0.10" (6 chars), drift-tested against pxt.json" | `kVersion` is `"unbaked"` / `0.YYYYMMDD.n`; the drift test now asserts it is *not* the pxt.json version (`test_k_version_is_the_uninjected_placeholder`) |
| `src/DESIGN.md` §8 "RUN bridge" | "3 s same-text dedupe" | `kRunDedupeMs = 400` (`protocol.h:305`) |
| `src/DESIGN.md` §6 | "`kMaxPayloadBytes` … still 200" | 240 (`radio_transport.h:205`); §10 says so correctly |
| `protocol.cpp:471` | "(wifi-link.md:373)" | no such file in this tree |
| `protocol.h:7-14` | v6's RUN "is kUnknown" as the reason the cleartext bridge exists | true, but the paragraph still describes the "v5 retirement" era; fold into a 3-line note |

**Dedupe:** the 08-26 comment audit (`raw/comment-audit.md` §6.3) lists
the `formatDiag` one; the rest are new since sprint 026–028.

---

### CM-11 — Suggestion — put radio enable state on `RadioTransport`

`radioEnabled_` (`protocol.h:384-398`) is enforced at three sites in
`Protocol` (`protocol.cpp:182, 456, 510`) because `RadioTransport`
self-enables in `ensureRadioReady()` from both `sendLine()` and
`tryReceiveLine()`. Give the transport `enable()`/`enabled()`; have
`sendLine()` return false and `tryReceiveLine()` return false while
disabled; `setupRadio()`/`enableRadio()` become one-liners and the
three gates and their "Gate N of 3" comments disappear. The
"whichever comes up first owns the radio" invariant then lives on the
class that owns the radio.

### CM-12 — Suggestion — collapse the copy-pairs in `Protocol`

- `serviceOnce()`'s serial (`protocol.cpp:416-433`) and radio
  (`:456-478`) branches are the same 12 lines with a different handler
  and buffer → `void routeLine(Wire::WireHandler& h, const uint8_t* buf, size_t len)`.
- `SerialSink`/`RadioSink` (`protocol.h:337-374`) differ only in the
  callee → one `TransportSink` over a `bool (*)(const uint8_t*, size_t)`
  or, better, make both transports accept the already-terminated line
  (drop their own `\n` append; `emitLineNow()` appends once) so the
  strip-and-re-append round trip — and CM-07's blind strip — go away.
- `static_cast<uint32_t>(clock_.nowMicros() / 1000ull)` at `:273, 377, 500, 533`
  → `uint32_t nowMs() const`.

### CM-13 — Suggestion — the cleartext RUN bridge is its own object

`handleRun()`, the dedupe pair, `runQueue_`, `currentRunText_`,
`dispatchJob()`, `invokeRunDispatch()`, `isBypassRunName()`
(`protocol.h:264-307`, `protocol.cpp:118-131, 241-352`) share no state
with the v6 stack except `motionOwner_`. A `RunBridge` class (host-
portable like `RunQueue`) with `offer(text, len, nowMs)`,
`dispatchOne()`, `currentText()` would let the dedupe and bypass rules
be host-tested (today only the ring is) and would shrink `Protocol` to
composition.

### CM-14 — Suggestion — `motionOwner_` and `jobOwnsMotion_` are one fact stored twice

`protocol.cpp:323-327` writes both in lockstep. Either pass a
`bool (*jobOwnsMotion)()` into `WireAdapter` (same pattern as
`NowMsFn`) or let `Protocol` be the only owner and have the six verb
handlers ask through it.

### CM-15 — Suggestion — sequence wrap at `UINT32_MAX`

`wire_handler.cpp:706` `expectedNext_ = id + 1` with `id == 4294967295`
gives 0; every later id is then `> expectedNext_` and nacked until
HELLO. Unreachable in practice (4 × 10⁹ commands); a one-line
`if (expectedNext_ == 0) expectedNext_ = 1` or a `parseIdDigits` upper
bound of `UINT32_MAX - 1` closes it.

### CM-16 — Suggestion — `GET rebase` reports "unknown name"

`wire_adapter.cpp:854` returns `false` for a known field; `execGet`
(`wire_handler.cpp:1145-1148`) maps that to `err 1` (`ERR_UNKNOWN`) —
the same code a typo gets, for a name `HELP`'s successor (bare `GET`)
silently omits. `Adapter::onGet` returning `bool` cannot express
"write-only"; returning `true` with `0` would be equally misleading. A
`Result onGet(...)` signature (like `onSet`) is the clean fix; short of
that, a comment on the wire doc that `err 1` on GET also means
"write-only field".

---

## What held up

Checked and found sound, one line each:

- **Emit ring producer/consumer.** `EmitQueue::enqueue()`/`dequeue()`
  contain no yield; `drainEmitQueue()` copies each line to a stack
  buffer before the yielding write (`protocol.cpp:197-203`), so a
  concurrent `enqueue()` from the TS fiber cannot overwrite a line
  mid-send. Clip (240) < slot (241): `enqueue()` can never refuse on
  length.
- **Run ring.** `enqueue()` and `peek()/at()/release()` are both on the
  protocol fiber with no yield between them; `dispatchJob()` copies and
  releases before the long call (`protocol.cpp:320-321`).
- **Radio RX handoff.** `onDatagram()` runs on a MessageBus fiber
  (cooperative), and `tryReceiveLine()`'s read-`rxLen_`/copy/clear
  sequence (`radio_transport.cpp:153-158`) has no yield, so the
  single-slot handoff is atomic. Over-length frames are rejected whole
  (`:89-98`); `recv()` is only called inside the handler.
- **Serial RX vs handler cap.** `tryReadLine()` truncates at 240
  content bytes; the handler discards any line whose content reaches
  239 (`wire_handler.cpp:356-365`), so a truncated serial line can
  never parse as a shorter command — the two caps compose correctly.
- **Tokenizer bounds.** `tokenizeLine()` returns the true count but
  stores ≤ 20 pointers; every decode checks arity before indexing;
  `decodeRun()` checks `fieldCount > kMaxFieldTokens - 1` first;
  `findLastFieldToken()` is independent of the cap. A 30-token line
  cannot read past `tokens[]`.
- **Field parsing.** `parseIdDigits`/`parseInt32`/`parseUint32`/
  `parseFloatField` demand whole-field consumption, reject leading
  sign/space on ids, bar `e/E/x/X` and NaN/Inf; unchanged since 08-26
  and still correct.
- **Same-fiber nesting of `serviceOnce()`.** The hook fires only after
  `stepBusy = false` (`shims.cpp:703-715`); nested `dispatchJob()`
  returns on `motionOwner_ == kJob`; the abort bypass reads its text at
  handler entry (`run.ts:46-47`) before any nested overwrite could
  matter. Sound *on the protocol fiber* — CM-01 is the cross-fiber
  case.
- **`kBusy` arbitration.** All six motion verbs check `jobOwnsMotion_`
  first; `STOP`/`ESTOP` are deliberately ungated and reach the job's
  engine state so a wire stop ends a running job's move.
- **Clock arithmetic.** Every ms comparison is a signed-difference
  idiom (`protocol.cpp:275, 501`; `wire_adapter.cpp:740`); the decode
  clamp keeps `now + timeout` inside the half-range.
- **ESTOP ordering.** Executes before replying (`wire_handler.cpp:848-854`);
  `onEstop()` commits `kEstop` before clearing the obligation.
- **Telemetry once per tick.** One `buildSnapshot()` shared by both
  handlers (`protocol.cpp:504-512`); each handler keeps its own header
  memo and `expectedNext_` (`test_wire_per_transport_isolation.py`).
- **Identity/handshake.** Boot banner and HELLO reply are the same
  bytes; `ID` appends `name` as a 4th field additively; `HELLO` resets
  only handler state.
- **`sendLine()` framing.** `n ≤ 240`, `+1` delimiter, `kMtu = 247` →
  always the single-fragment path; `frameBuf_[256]` is asserted to hold
  a full frame.
- **VFP discipline in this layer.** Every yield reachable from
  `src/comms/` goes through `vfpSafeSleep` or `guardedSerialSend`
  (inventory above).

---

## Comment boil-down list

Standard applied: a comment earns its lines by stating something not
recoverable from the code — a unit, a sign, an invariant, a measured
hardware fact, a wire layout, a hazard. Sprint/ticket numbers, diff
narration, reviewer-facing justification, and quoted stakeholder
dialogue are noise. The worst offenders, with a replacement each:

| # | file:lines | Now | Replace with |
|---|---|---|---|
| 1 | `protocol.cpp:40-101` (62 lines, identity constants) | history of `kProfile`/`kVersion`, the 2026-08-27 VER decision, the tovez fleet-wide bug | `// kProfile/kVersion are injected into the deploy scratch copy by tools/make_deploy.py; the checked-in "unbaked" can never impersonate a fleet board. name (silicon) is identity; profile is build provenance — they legitimately differ on a wrong-build board.` |
| 2 | `radio_transport.h:248-288` (41 lines, name→channel derivation) | the whole fleet addressing scheme and its rationale | keep `:240-245` (the DO-NOT-REFORMAT regex warning) verbatim; replace the rest with `// (channel, group) are baked here from the robot's config at deploy; the name-derived default scheme lives in tools/make_deploy.py derive_radio_from_name().` |
| 3 | `wire_handler.cpp:505-548` + `584-612` + `626-648` (dispatch essays with quoted dialogue) | three essays on why ID/VER/STATUS are unsequenced, why missing-id nacks, why `#0` nacks | one block at `:505`: `// Unsequenced iff position-independent (ID/VER/STATUS answer constants; GET stays sequenced because SET orders it). A recognized verb with a missing/`#0` id gets nack <expectedNext_> so the operator is never answered with silence; unknown verbs stay silent on a shared channel.` |
| 4 | `serial_transport.h:25-55` (31 lines, `kRingBytes`) | ticket 006/007 archaeology | `// codal's setRx/TxBufferSize take uint8_t: 255 is the ceiling (480 silently truncated to 224, below one line). One 240 B line + 15 B slack; two full lines can still overflow. Brace-init so >255 is a compile error.` |
| 5 | `radio_transport.h:169-205` (37 lines, `kMaxPayloadBytes`) | why it moved public, sprint 008/010 history | `// = the wire's 240 B line cap (drift-tested with serial_transport.h and wire_handler.h). 241 B incl. '\n' fits one fragment (MTU 247). Public: Protocol::emitLine() clips to it.` |
| 6 | `wire_handler.cpp:122-152` (`kMaxMotionTimeoutMs`) + `213-247` (`kGetValueCeiling`) | two "sibling not reuse" layering essays | `// 2^31-1: the signed-difference half-range, so now+timeout can never wrap past now.` and `// 1e6 input ceiling: keeps magnitude*1e6 exactly representable in double; a clamped value prints as a recognisable round number.` |
| 7 | `wire_adapter.cpp:657-700` (`onEstop`, 44 lines) | three numbered hazards + point 3 | `// Commit kEstop unconditionally: the estopped diag flag is not published until the next step(), and estopAll() already ended any engine move, so resolvePendingReason() would misread this as kStop. Clear the obligation after the commit.` |
| 8 | `wire_handler.cpp:952-993` (`execStatus` buffer sizing, 42 lines) | two rounds of worst-case width arithmetic | `// Worst case ~160 B ("status " + 8 bools + flags=ffffffff + i2cf=-2147483648 + cyc/next/done at 10 digits + reason=aborted); 200 leaves margin.` |
| 9 | `wire_handler.h:184-201` + `221-229` (Column/Snapshot C++11 essay) | why the constructors exist, why Snapshot is left alone | `// Explicit ctor: NSDMIs make this a non-aggregate under the target's -std=c++11, so `{"name", v, hex}` needs one; the C++20 host would compile without it.` |
| 10 | `run_queue.h:1-27`, `emit_queue.h:1-37` ("WHAT THIS REPLACES") | the old cursor's failure story, MessageBus listener (stale, CM-10) | `run_queue.h`: `// Fixed ring with occupancy; a slot is in flight from enqueue() to release(); full → refuse and count (saturating). Host-portable.` `emit_queue.h`: `// FIFO of clipped lines; dequeue() copies out so the consumer's yielding write never holds a pointer into the ring. Single consumer (protocol fiber). Host-portable.` |
| 11 | `wire_handler.cpp:806-833` (`emitReminderIfStalled`) + `wire_handler.h:730-757` (`gapOutstanding_`) | stakeholder quotes and anti-beacon defence | `// Reply predicate only: re-nack on an unsequenced verb iff a gap/decode stall is outstanding. Never periodic; an idle link is silent.` |
| 12 | `protocol.h:61-82` (`emitLine`), `:97-116`, `:118-140`, `:293-307` | four public-API doc blocks written as justification | `emitLine`: `// Clip to 240 B and enqueue for both transports; callable from any fiber; drained by the protocol fiber within one poll; full ring drops newest, counted.` `kRunDedupeMs`: `// 400 ms: swallows a host's retransmit burst, lets a deliberate repeat through.` |

Also worth a mechanical pass (not individually listed): every
`// sprint NNN ticket MMM` / `// WIRE-NN` / `// R-NN` / `// SUC-NNN`
prefix in these files (`grep -cE 'sprint [0-9]{3}|ticket [0-9]{3}|WIRE-[0-9]|R-[0-9]{2}|SUC-[0-9]' src/comms/*` → 130 lines, 43 of them in `wire_adapter.cpp`) is
archaeology the 08-26 audit already proposed a ratchet for
(`comment-standard-and-archaeology-ratchet.md`, sprint 017, done — the
files grew back).
