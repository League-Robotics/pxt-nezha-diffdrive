# Correctness review — wire/protocol stack

**Date:** 2026-08-23
**Reviewer scope:** `src/protocol.{h,cpp}`, `src/wire_handler.{h,cpp}`,
`src/wire_adapter.{h,cpp}`, `src/radio_transport.{h,cpp}`,
`src/serial_transport.{h,cpp}` — correctness (dimension 1), future
landmines (dimension 2), student readability (dimension 5).
Callers in `src/shims.cpp` / `src/main.ts` were read only to judge
contracts. Comment hygiene and kernel/motion internals are other
reviewers' scope.

**Dedup honored:** no findings below re-report the missing v6 telemetry
frame or radio-v6 RX (sprints 004/005, planned), the STATUS/DIAG numeric
surface (issue `status-lost-diag-numeric-surface`), the settle-tick loop
(issue `settle-tick-loop-is-not-host-testable`), or the boot wedge
(issue `unpowered-nezha-brick-wedges-program-at-boot`).

---

## Major findings

### WIRE-01 — ID/VER report a stale firmware version: kVersion "1.0.0" vs pxt.json "1.0.10"

- **File:** `src/protocol.cpp:63` (`constexpr const char* kVersion = "1.0.0";  // keep in sync with pxt.json`); consumed at `protocol.cpp:173` and emitted by `wire_handler.cpp:605` (execId) and `:619` (execVer).
- **Dimension:** 2 (future landmine, already sprung) / 1.
- **Severity:** Major.
- **Scenario:** `pxt.json:3` is `"version": "1.0.10"`. Host sends `VER #1` → robot answers `ver 1.0.0`. Ten version bumps have happened since the constant was written; the "keep in sync" comment has already failed. Any deploy-verification workflow (mbdeploy-style "did the new build actually flash?") that reads ID/VER gets the same `1.0.0` from every build and can never distinguish a stale hex from a fresh one — the exact failure mode the shared-board bench etiquette exists to prevent.
- **Coverage:** not host-testable as written — the wire host tests exercise `WireMockAdapter`'s identity, never `protocol.cpp`'s constants. A cheap guard: a host-side test that regex-extracts `kVersion` from `protocol.cpp` and compares it to `pxt.json` (pure text, no compile needed).
- **Remedy:** short term, bump the constant and add the text-compare test so drift fails CI. Real fix: generate a `version_generated.h` from `pxt.json` at build time (the reference firmware already does this) so the constant cannot exist twice. Note `src/DESIGN.md` §10 already lists this drift as a known limitation — it is now an *actual* drift, not a risk.
- **Confidence:** high.

### WIRE-02 — Motion-obligation deadline wraps for timeout > 2^31 ms: the move is accepted, then killed by the watchdog ~150 ms later

- **File:** `src/wire_adapter.cpp:294-297` (onWheelsX), `:314-317` (onMoveX), `:352-355` (onGoToR), `:379-382` (onGoToW) — `motionObligationDeadlineMs_ = nowMs_() + timeout;` — checked at `wire_adapter.cpp:414-420` with `static_cast<int32_t>(nowMs - motionObligationDeadlineMs_) < 0`.
- **Dimension:** 1 (correctness).
- **Severity:** Major.
- **Scenario:** `WHEELS_X 500 500 100 4294967295 #1` (a host passing uint32-max as "no timeout" — the natural spelling once `-1` is rejected by `parseUint32`). The verb decodes, acks, and `engineWheelsX()` commits the move. Deadline arithmetic: `deadline = now + 4294967295` wraps to `now - 1`, so `(int32_t)(now - deadline) = +1 ≥ 0` and `hasLiveMotionObligation()` is **false from the first poll**. `protocol.cpp:291-293` therefore never calls `tickDrive()`; the kernel is never stepped; the starvation watchdog port-stops the motors ~100–150 ms later. This is precisely the ticket-011 bug (arming missed → "move starved and watchdog-stopped almost immediately") that ticket 012 fixed, resurrected for any `timeout` (or MOVE_V/WHEELS_V `duration`, though those are capped at 5000) strictly greater than 2^31 ms (~24.9 days). Everything ≤ 2^31 is fine. The V-forms are protected by `kWheelsVDurationCeiling`; the X-forms and GO_TO forms have no ceiling at all, so the whole uint32 range reaches the adder unclamped.
- **Coverage:** `tests/host/test_wire_motion_verbs.py::test_every_motion_verb_arms_motion_obligation` (~line 1498) already has the exact harness needed (`waSetNowMs`) — it just never parameterizes a window ≥ 2^31. Adding `window_ms=2**31 + 1` and `2**32 - 1` cases would fail today.
- **Remedy:** clamp the armed window (e.g. `timeout = min(timeout, INT32_MAX)` at arming, or clamp at decode with kRange). A protocol-level ceiling on X-form timeouts (mirroring the V-form 5000 ms decision, but sized for backstops — say 10 min) would also close it and is worth a design decision either way.
- **Confidence:** high (arithmetic traced; test harness would confirm).

### WIRE-03 — Serial RX ring (128 B) is smaller than one legal line (240 B), and the fiber drains it only every ~24 ms during wire-driven motion: guaranteed byte loss for long lines mid-move

- **File:** `src/serial_transport.cpp:24-25` (`setRxBufferSize(128)`, comment still sized against "one binary v5 frame (~27 wire bytes)"); interacts with `src/serial_transport.h:32` (`kMaxLineBytes = 240`, raised in ticket 005) and `src/protocol.cpp:291-298` (during a live motion obligation the loop's only delay is `tickDrive()`, which self-paces to the 24 ms cadence — `src/shims.cpp:525-542` — so the ring is drained once per ~24 ms, vs `fiber_sleep(5)` when idle).
- **Dimension:** 1 / 2.
- **Severity:** Major.
- **Scenario:** ticket 005 deliberately raised the line cap to 240 so "this transport is never the tighter cap" — but the RX ring was left at 128, which *is* now the tighter cap under load. Concretely: host issues `WHEELS_V 150 150 5000 #7` (acked; obligation live; loop now iterates at ~24 ms), then sends a 200-byte line (a long `RUN`, or simply three or four commands back-to-back totaling > 128 bytes) as one burst. At 115200 baud ≈ 11.5 bytes/ms, up to ~276 bytes arrive inside one 24 ms tick window; the 128-byte ring overflows and CODAL drops the excess — mangled/merged lines, the identical bench-measured v5 failure the `begin()` comment describes. The reliability layer nacks the mangled line and the host resends — into the same 24 ms window, so a long line can stall in a resend loop until the motion obligation lapses. Idle behavior (5 ms poll ≈ 58 bytes/gap) is safe; the exposure is exactly "command traffic while a wire move runs", which is sprint-005 bench tooling's normal mode.
- **Coverage:** CODAL-side; not host-testable. Bench-reproducible with a script that starts a 5 s WHEELS_V then immediately streams a 200-byte line.
- **Remedy:** `setRxBufferSize(2 * kMaxLineBytes)` (480) or at least 256, with the comment re-derived from v6 numbers; optionally drain serial once more after `tickDrive()` returns inside the obligation branch.
- **Confidence:** high on the arithmetic; medium on how often real host traffic hits it (the reliability layer masks single losses).

### WIRE-04 — Two fibers write the same serial port with no serialization: emitLine (TS fiber) vs replies/keepalives (protocol fiber) can silently drop or interleave lines

- **File:** `src/protocol.cpp:89-96` (`emitLine`, documented at `protocol.h:82-96` as "Called from the TS layer … NOT from this object's own fiber") and `src/protocol.h:186-197` (`SerialSink` → `transport_.writeLine`) — both funnel into `src/serial_transport.cpp:28-35`, two `uBit.serial.send(..., SYNC_SLEEP)` calls per line, return values ignored.
- **Dimension:** 1 (concurrency/fiber-safety).
- **Severity:** Major.
- **Scenario:** a RUN-triggered test handler calls `diffDrive.emitLine("<180-byte tour result>")` on its MessageBus fiber. With a 128-byte TX ring, the content `send()` blocks (SYNC_SLEEP) mid-line; the protocol fiber wakes for its 50 ms keepalive (`protocol.cpp:277-281`) and calls `send()` on the same port. CODAL's `Serial::send` refuses a busy TX with `DEVICE_SERIAL_IN_USE` — `writeLine` ignores the return, so the keepalive line (or, in the mirrored ordering, the *result* line) silently vanishes; and because `writeLine` is two sends, one of the pair can succeed while the other is refused, producing a delimiter-less merge or a stray blank line on the host. A lost keepalive self-heals in 50 ms; a lost `emitLine` result is unrecoverable bench data. Radio has the same shape one layer down: `RadioTransport`'s scratch buffers are documented "Single-fiber use only" (`radio_transport.h:127-134`) yet `sendLine` is reached from whatever fiber calls `emitLine` — safe only while exactly one handler emits at a time, an invariant nothing enforces.
- **Coverage:** CODAL-side, not host-testable; bench-observable as intermittently missing/garbled result lines while the keepalive stream runs (i.e., always).
- **Remedy:** route `emitLine` through the protocol fiber (a small outbound queue the run() loop drains), or add a cooperative TX guard in `SerialTransport::writeLine` (same `while (busy) sleep` pattern `tickDrive()`'s `stepBusy` uses) and check `send()` returns.
- **Confidence:** medium — the fiber-interleaving mechanism and ignored return values are verified in this repo's code; the exact refuse-vs-block behavior of this CODAL version's `Serial::send` is from memory (codal-core returns `DEVICE_SERIAL_IN_USE` on a busy TX), unverified in-tree because CODAL sources are not vendored. Either behavior (drop or interleave) is a failure.

### WIRE-05 — emitLine silently truncates at a hard-coded 200 bytes; radio payload cap also 200 with a comment that claims parity with the (now 240) serial cap

- **File:** `src/protocol.cpp:92` (`while (text[len] != '\0' && len < 200) ++len;` — bare literal); `src/radio_transport.h:118-126` (`kMaxPayloadBytes = 200`, comment: "Sized the same as SerialTransport's bound" — false since ticket 005 raised serial to 240); truncation applied at `radio_transport.cpp:134`.
- **Dimension:** 2 (duplicated constants drifting) / 1 (silent corruption).
- **Severity:** Major.
- **Scenario:** seeded lead 2, confirmed. A test program emits a 220-byte calibration/result line via `emitLine`. The serial side could legally carry 240, but `emitLine` clips to the first 200 bytes and appends the delimiter — the host receives a *plausible, parseable, wrong* line: truncation mid-number yields a shorter number that parses cleanly, so nothing flags the corruption (unlike the wire handler's own careful discard-whole-line-never-truncate rule one layer up, which this free function bypasses). Radio clips at the same 200 via its own private constant. Three "max line" numbers now coexist (240 handler/serial, 200 emitLine, 200 radio) with no shared definition and one stale parity claim.
- **Coverage:** `protocol.cpp` is not in the host harness; bench-only today. The truncation loop is trivially unit-testable if `emitLine`'s length logic is extracted or the constant shared.
- **Remedy:** define the cap once (reuse `kMaxLineBytes`), and make over-length input loud — either drop whole (matching the wire stack's rule) or truncate with a visible marker. Fix or delete the radio comment's parity claim when sprint 004 touches that file.
- **Confidence:** high.

### WIRE-06 — STATUS hardcodes otos=0 even when an OTOS is connected and GO_TO_W works

- **File:** `src/wire_adapter.cpp:222-227` (`out.otos = false;` with a rationale comment — "No OTOS in this project's wire-reachable surface yet" — that predates ticket 012 wiring GO_TO_W for real); `diagValue()`'s ordinal table (`src/shims.cpp:679-716`) confirms no OTOS-presence ordinal exists to read.
- **Dimension:** 2 (landmine for sprint-005 host work) / 1.
- **Severity:** Major.
- **Scenario:** on vevov with the OTOS begun and healthy, host sends `STATUS #1` → `status … otos=0 …`; the same session's `GO_TO_W 500 300 150 10 8000 #2` acks and drives. Any sprint-005 bench script that gates world-frame tours on the STATUS otos flag (the obvious probe) will conclude no OTOS is fitted and skip or refuse tours on a fully equipped robot; conversely, when GO_TO_W answers `err 6` (no OTOS), STATUS "agrees" for the wrong reason, sending a debugging operator toward the sensor when the flag is simply never wired. The field exists on the wire and is populated with a constant — worse than absent, it is *confidently wrong*.
- **Coverage:** host tests can't currently express the truthful value (no shims ordinal); adding e.g. `kDiagOtosConnected` and asserting `status()` reflects it is straightforward in `tests/host/test_wire_motion_verbs.py`'s `wa` harness.
- **Remedy:** add an OTOS-connected diag ordinal (shims.cpp already owns `gOtos` and a connected notion via `engineGoToW`'s availability check) and read it in `status()`. If deferred, at least update the comment to say the flag is a stub so nobody trusts it.
- **Confidence:** high.

### WIRE-07 — lastDone/lastDoneReason permanently 0/none: the reliability channel can never report motion completion (documented decision; assessed as a sprint-005 landmine)

- **File:** `src/wire_adapter.h:318-321` (inert overrides; the long DECISION comment at `:295-317` is accurate); consumed fresh on every ack/nack at `wire_handler.cpp:476-489` and in every keepalive (`:977-991`).
- **Dimension:** 2 (future landmine).
- **Severity:** Major (as a planning landmine; the code is internally consistent and spec-legal per protocol.md S8.8.1).
- **Scenario:** seeded lead 3, confirmed. Every ack/nack/keepalive this firmware ever emits ends `… 0 none`. A wire host has exactly two ways to learn a move finished: (a) telemetry frames — which don't exist until sprint 004 — or (b) polling `STATUS` and inferring from `active` (itself derived from instantaneous wheel velocity, `wire_adapter.cpp:232-234`, which flickers through zero during reversals and settle). Sprint 005's bench-tooling retrofit therefore has *no reliable completion signal at all* on current firmware: a tour runner must fall back to fixed sleeps sized to worst-case move duration. The infrastructure on the handler side is fully built and tested (`test_wire_reliability.py::test_last_done_is_read_fresh_not_cached_across_calls`) — only the adapter end is inert, and the engine genuinely has the event (`isMoveActive()` edge) one bridge-function away.
- **Remedy:** when sprint 004/005 planning lands, give one bridge function a completion return (e.g. `engineLastDone()` polled by the adapter, keeping the shims decoupling) rather than letting host tooling ossify around sleep-based sequencing. This finding is the "real use case" the DECISION comment says it is waiting for.
- **Confidence:** high (behavior verified; severity is a judgment about sprint-005 exposure).

---

## Minor findings

### WIRE-08 — Unclamped numeric funnels at the adapter boundary: int32-max wire values hit float→int UB; SET values ×1000 can overflow lround

- **File:** `src/wire_adapter.cpp:257` (`setWheelsTimed(static_cast<int>(left), …)`); `:433-434` (`std::lround(value * 1000.0f)` cast to int).
- **Dimension:** 1 (malformed-input behavior).
- **Severity:** Minor (inputs are absurd-but-legal; robot-side effect mostly saturates).
- **Scenario:** `WHEELS_V 2147483647 0 1000 #1` decodes (parseInt32 accepts all of int32). `static_cast<float>(2147483647)` rounds up to `2147483648.0f`; casting that back to `int` is UB — on Cortex-M VCVT it saturates to INT32_MAX (benign), but on the x86 host harness it yields INT32_MIN: full-speed *reverse* from a max-forward command, so the host tests and hardware disagree in sign for wire values in [2147483584, 2147483647]. Similarly `SET pid_kp 3000000 #2`: 3e9 exceeds long's 32-bit range on the target, `lround` is UB/unspecified, and a garbage (typically huge-negative) gain lands in the kernel from an acked, in-grammar line. Neither path has a range check between the full-int32 wire grammar and the narrower internal domain.
- **Coverage:** host-testable today (extreme-value cases in `test_wire_motion_verbs.py` would expose the x86 sign flip directly).
- **Remedy:** clamp at the adapter (mm/s, config values, and SET's ×1000 product) to sane physical ranges, refusing with kRange beyond them — consistent with the existing cruise/duration policing.
- **Confidence:** high on mechanism.

### WIRE-09 — kCommandTable's explicit [18] size zero-fills on under-initialization: a future verb removal compiles and then strcmp's a nullptr

- **File:** `src/wire_handler.h:431` (`static const VerbEntry kCommandTable[18];`), `src/wire_handler.cpp:214-233` (definition repeats the 18), lookup at `:427-432` (`std::strcmp(verb, e.name)`).
- **Dimension:** 2.
- **Severity:** Minor.
- **Scenario:** the size is spelled twice. Adding a 19th verb without touching the header fails loudly (too many initializers) — fine. *Removing* one (or forgetting one while renaming) compiles silently: the array zero-fills the last entry, `e.name == nullptr`, and the first inbound sequenced verb walks the table into `strcmp(verb, nullptr)` — UB, in practice a hard fault on the robot, for every command. Sprint 004's planned verb additions make table edits imminent.
- **Remedy:** declare `static const VerbEntry kCommandTable[];` … define with deduced size and `static_assert` a `kVerbCount`, or keep the count in one constant both files share.
- **Confidence:** high.

### WIRE-10 — RUN bridge cap chain (radio 64 → slot 48) silently swallows long RUN commands on both transports

- **File:** `src/protocol.cpp:115` (`if (dataLen == 0 || dataLen >= kRunTextBytes) return;` — kRunTextBytes 48, `protocol.h:131`); `src/radio_transport.cpp:60` + `radio_transport.h:139` (`rxLine_[64]` truncation of a single fragment the header itself says can carry ~247 bytes with the fleet's 250-byte packets); `protocol.h:224` (`rxLineBuf_[64]`).
- **Dimension:** 1 / 2.
- **Severity:** Minor.
- **Scenario:** `RUN:tour:A1:B4:C2:D5:E1:F3:G2:H4:9000` — 4-byte prefix + 44-byte payload runs; grow the argument list four more characters and the whole command vanishes: no event, no reply, no counter, on serial and radio alike (radio adds its own 64-byte pre-truncation, whose *output* is then always ≥ 60 bytes post-prefix and therefore also silently dropped by the 48-byte slot check — so truncated execution can't happen, only silent loss, verified by tracing both caps together). The v6 plane at least nacks; the RUN bridge is the one command path with zero feedback, and its real ceiling (47 payload bytes) is documented only at the buffer declaration.
- **Remedy:** cheapest honest fix: count drops (a diag ordinal) and/or emit a one-line `runerr too-long` via emitLine. Document the 47-byte payload ceiling where `onRun`/test authors will see it (main.ts's onRun doc).
- **Confidence:** high.

### WIRE-11 — RUN slot ring wraps silently after 4 queued commands: the 5th overwrites text a queued MessageBus event has not read yet, so a *different* command runs

- **File:** `src/protocol.cpp:148-151` (round-robin `nextRunSlot_` advances unconditionally; no occupancy check), design assumption at `protocol.h:126-134` ("Four slots covers any burst a host can plausibly send inside one handler").
- **Dimension:** 2.
- **Severity:** Minor.
- **Scenario:** a long-running RUN handler (a full tour, minutes) holds the single dispatcher fiber (`main.ts:157-172` — one `control.onEvent(RUN_EVENT_SOURCE, 0, …)` wildcard listener, handlers run inline, later events queue). Host sends five *distinct* commands during the tour (dedupe only absorbs identical text). The 5th overwrites slot 1's text; when the queue drains, the event for the original command 1 reads command 5's text: command 5 executes twice, command 1 never, silently. On a robot this is "the wrong test drives the wheels". The 4-slot capacity is a documented guess with no enforcement and no drop-signal when exceeded.
- **Remedy:** track per-slot "consumed" (set in `runText()`), and refuse+count (or overwrite the *oldest consumed*) instead of blind round-robin; or simply raise slots and add a wrap counter to diag.
- **Confidence:** high on mechanism (MessageBus queue-if-busy semantics assumed per CODAL default; the ring comment itself describes events queuing behind a minute-long handler).

### WIRE-12 — Protocol-fiber stack margin in the RUN reply path is thin (~1.2 KB of a 2 KB fiber already spoken for)

- **File:** `src/wire_handler.cpp:928-963` — `execRun` stacks `result[224] + sanitized[224] + buf[241] + argv[16×8]` ≈ 820 B, beneath `Protocol::run()`'s `lineBuf[240]` (`protocol.cpp:223`) plus call frames. `radio_transport.h:128-132` records this exact fiber hard-faulting once already over ~450 B of stack buffers (bench-measured).
- **Dimension:** 2.
- **Severity:** Minor.
- **Rationale:** safe today only because `onRun` is inert (returns immediately, `wire_adapter.cpp:453-462`). The moment sprint 004/005 gives `onRun` a real body — or `execGet`/`execHelp` (240 B frames each) grows — the same fiber that already overflowed once is within a few hundred bytes of doing it again, and CODAL stack overflow presents as a delayed hard fault, not a diagnosable error.
- **Remedy:** when RUN gets a real adapter body, move `execRun`'s three big buffers to WireHandler members (single-fiber use, same justification as `RadioTransport`'s member scratch), or measure headroom on bench first.
- **Confidence:** low-medium (no measurement; mechanism and precedent are real).

### WIRE-13 — Grouped readability nits (students will read these files)

- `src/serial_transport.h:36-51`: the doc block above `begin()` describes a blocking `readLine()` that **does not exist** on the class (deleted; only `begin/writeLine/tryReadLine` remain), and claims it is "Kept as a general blocking-read primitive on this class's public contract". `:58-59` then introduces `tryReadLine` as the "Non-blocking counterpart to readLine()". A student looking for `readLine()` will hunt for a phantom. Fix the two references (the file's v5/COBS framing in its top comment is the hygiene reviewer's list).
- `src/protocol.cpp:92`: the bare literal `200` (see WIRE-05) — even after the cap decision, name it.
- `src/wire_adapter.cpp:88-104` + `src/shims.cpp` ordinal switches + `src/main.ts` `ConfigField`: the 15-entry name/ordinal mapping exists as three parallel lists in three languages, correct today by inspection; a reorder in any one silently remaps a SET onto the wrong kernel field (`pid_kp` writing `stall_window`). The host round-trip test (`test_get_set_field_name_table_round_trips`) exercises the shim harness's own table, so cross-file drift is not fully pinned. Whole-repo constant-duplication is the modularity reviewer's dimension; flagged here because it is visible from `kFields`. Same class, lower risk: `kRunEventSource` 0x2001 (`protocol.cpp:85`) vs `RUN_EVENT_SOURCE` (`main.ts:154`), and radio group 10 / channel 4 (`radio_transport.h:112-115`) vs `tools/robotlink.py` and the zavaz relay config — each pair carries "must match" comments and no check.

---

## Not findings — suspicious things verified correct

- **Serial 240 "content" vs handler 240 "including terminator" off-by-one** (`serial_transport.h:32` vs `wire_handler.h:275`): the transport is one byte *looser*, the handler still enforces; "never the tighter cap" holds. A 300-byte line truncated to 240 by the transport lands in the handler's overflow-discard (content ≥ 239+1) and is counted malformed, never executed truncated — traced end to end, including the RUN: prefix path (long payloads die at the 48-byte slot check).
- **`#0` handling**: falls into the stale-retransmit bucket with zero special-case code, exactly as `wire_handler.h:42-44` claims; pinned by `test_hash_zero_is_a_stale_retransmit_not_specially_handled`.
- **Embedded-NUL C-string truncation** (`PING\0extra` == `PING`) and the first-non-space-byte-NUL memory-safety guard (`wire_handler.cpp:296-315`): pinned characterization, guard verified — `tokens[0]` is never read uninitialized.
- **Tokenizer overflow past `kMaxFieldTokens`**: true count returned, only 20 pointers stored; every decode path (including `decodeRun`'s explicit `fieldCount > kMaxFieldTokens - 1` check at `wire_handler.cpp:923`) was traced to never index beyond stored pointers.
- **`parseInt32`/`parseUint32` accepting a leading `+`**: documented deliberate looseness (`wire_handler.cpp:106-111`); id grammar stays strict via `parseIdDigits`.
- **Garbage uppercase line with a large well-formed trailing id** (e.g. `#5 #9`) sets `gapOutstanding_` and nacks: spec-conformant — id resolves before verb lookup by design; self-heals when the real id arrives.
- **HELLO resetting `expectedNext_` mid-session**: spec (S8.3 resync); single-host serial makes a spurious in-band `HELLO` implausible, and radio cannot reach the v6 parser.
- **`SerialSink::write` stripping the last byte unconditionally** (`protocol.h:190-193`): safe under Sink's contract (WireHandler always appends `\n`; `writeLine` re-appends its own).
- **`onDatagram` length clamp** `len = sizeof(rxLine_)` at `radio_transport.cpp:60`: boundary checked — memcpy of exactly 64 into `rxLine_[64]`, no overflow; header-vs-plen check prevents reading past the packet.
- **Radio RX single-slot drop + host-repeat + 3 s dedupe**: measured, documented design; `rxReady_` handoff is race-free under cooperative fibers (checked both directions).
- **`protocol()` singleton / `wireNowMs` reentrancy**: `gProtocol` is assigned before `start()` launches the fiber; `wireNowMs` is only reachable from adapter methods running on that fiber. NSDMI member ordering in `protocol.h:199-219` verified against declaration order.
- **`formatConfigValue` NaN/Inf paths** (`wire_handler.cpp:178-192`): NaN forced to 0.0, Inf clamped below the uint32 cast — the UB the comment worries about is actually handled.
- **`decodeStop` rejecting `NOW`/`Now`**: case-sensitive per S2.1, pinned by `test_stop_now_uppercase_is_decode_failure`.
- **No duration ceiling on X-form/GO_TO timeouts** (only V-forms capped at 5000): deliberate — timeout is a backstop, the engine dead-reckons its own lease. (The *wrap* at 2^31 is WIRE-02; the absence of a ceiling per se is a design choice.)
- **`execTlm` discarding the adapter Result / TLM modes accepted with no frames behind them**: spec-conformant and dedup'd — telemetry frames are sprint 004.
- **Boot keepalive stream (`ack 0 0 none` every 50 ms from power-on)**: S8.5 behavior, byte cost negligible at 115200.
