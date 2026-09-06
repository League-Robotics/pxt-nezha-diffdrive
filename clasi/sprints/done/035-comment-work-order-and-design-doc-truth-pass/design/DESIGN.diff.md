---
source_file: DESIGN.md
source_hash: 536d6f058d1afde7618a50fe3424a8ca257e0c9e1122ccea061cc21e121ec51a
---
# Diff: DESIGN.md

Comparison of the sprint overlay copy of `DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- DESIGN.md (pristine)
+++ DESIGN.md (current)
@@ -805,9 +805,12 @@
 the same surface (`kFields`, both `shims.cpp` switches, and the enum).
 The visible cost was `protocol.h`'s comment citing "diagValue ordinal
 30" for the RUN-queue drop counter: the real reader is
-`diagValue()`'s ordinal 28, ordinal 30 does not exist in `diagValue()`
-at all, and 30 in the *config* ordinal space — a different namespace
-entirely — is `omega_max`. Corrected to 28. `diagValue()` itself stays
+`diagValue()`'s ordinal 28; at that point ordinal 30 did not exist in
+`diagValue()` at all, and 30 in the *config* ordinal space — a
+different namespace entirely — is `omega_max`. Corrected to 28. (Sprint
+033 has since given `diagValue()` its own ordinal 30, the RUN bridge's
+sanitizer-refusal count — §8 — so both namespaces now carry a 30, still
+meaning unrelated things.) `diagValue()` itself stays
 a separate, read-only table and is deliberately NOT folded into
 `kConfigFields`: its ordinals have no `SET` counterpart and no natural
 unit, and merging them would force every consumer of the config table
@@ -904,9 +907,11 @@
 wire-reachable OTOS check — R-22/WIRE-06) plus a decimal `i2cf=` fault
 count sourced from the same `diagValue(8)` call the telemetry `i2cf`
 column reads (see the Telemetry projection paragraph below), so the
-two can never disagree. `onRun()` is an honest `kUnknown` — the real
-by-name test trigger is protocol.cpp's MessageBus RUN bridge, a CODAL
-mechanism this host-portable class must never touch.
+two can never disagree. `onRun()` is an honest `kUnknown` — there is no
+registration table here, because this project's real by-name test
+trigger is protocol.cpp's cleartext `RUN:` bridge, `RunBridge` plus
+`dispatchJob()` running the job on the protocol fiber itself (§8), a
+CODAL-side mechanism this host-portable class must never touch.
 
 **Motion-obligation tracking.** This class sees every accepted motion
 verb, so it records `now + duration/timeout` as a deadline and exposes
@@ -1104,20 +1109,28 @@
 otherwise format frames and advance its own header state for a link
 that cannot carry them) and lets the transport refuse everywhere else.
 `enable()` does not bring the radio up: bring-up stays
-lazy-on-first-use (group 10 by default, channel 4 — vevov's fleet
-assignment — power 7), so a program that enables the link and never
-sends or polls still never pays `uBit.radio.enable()`'s RAM/softdevice
-cost. Group is the one field a student program can change, via
-`setGroup()`/the blocks layer's "set radio group" block (sprint 021
-ticket 005). The supported path is calling it from `on start`, before
-the radio has come up: `setGroup()` just stores the value, and
-`ensureRadioReady()` reads it during lazy bring-up. Calling it after
-the radio is already armed re-applies immediately via
-`uBit.radio.setGroup()` so the call is not a silent no-op, but whether
-that re-apply actually changes what an already-armed radio receives on
-is UNVERIFIED on this hardware — no test of that path has been run.
-Channel and power stay fixed constexpr values with no settable
-surface. RX is
+lazy-on-first-use, so a program that enables the link and never sends
+or polls still never pays `uBit.radio.enable()`'s RAM/softdevice cost.
+The checked-in `kChannel`/`kGroup` (4 and 10) are **placeholders, not a
+fleet assignment**: `tools/make_deploy.py`'s `_inject_radio_channel()`
+rewrites BOTH in the deploy scratch copy from the robot's own
+`radio-robot-lib` config, so every per-robot build overwrites them (a
+build that reaches hardware still carrying 4/10 is a build that missed
+the injection). `kTransmitPower` = 7 is the one radio constant with no
+settable surface at all. **Both** channel and group are settable at
+runtime — `setChannel()`/`setGroup()` on this class, reached by
+students through the blocks layer's "setup radio channel %channel group
+%group" block (`run.ts`'s `setupRadio()` → `Protocol::setupRadio()`),
+and each stores into the mutable `channel_`/`group_` the constants only
+seed. The supported path is calling them from `on start`, before the
+radio has come up: they just store the value, and `ensureRadioReady()`
+reads the fields — not the constants — during lazy bring-up. Calling
+either after the radio is already armed re-applies immediately
+(`uBit.radio.setGroup()` / `setFrequencyBand()`) so neither is a silent
+no-op, but whether that re-apply changes what an already-armed radio
+receives on is UNVERIFIED on this hardware — no test of that path has
+been run (`clasi/issues/low/changing-the-radio-group-mid-run-is-unverified.md`).
+RX is
 a single-fragment command plane: `tryReceiveLine()` consumes a flag
 set by the MICROBIT_RADIO_EVT_DATAGRAM handler — `datagram.recv()` is
 **only** called inside that handler because polling an empty queue
@@ -1160,18 +1173,22 @@
 the bench. **Sprint 008**: `kMaxPayloadBytes`'s own doc comment
 previously claimed it was "sized the same as SerialTransport's bound"
 — false since ticket 005 (sprint 004) raised `SerialTransport`'s
-`kMaxLineBytes` to 240 while this constant stayed 200; the comment now
-states the true relationship: `kMaxPayloadBytes` is deliberately the
-**tighter** of the two transports' caps, and `protocol.cpp`'s
-`emitLine()` (§8) now names this constant directly instead of
-re-declaring its own bare `200` literal, so the two can never drift
-apart silently again the way they already had (WIRE-05/R-21). The
-*value* is unchanged — still 200, still radio's real capacity ceiling
-— this sprint single-sources the constant, it does not raise radio's
-capacity: that is `radio-rx-capacity-fragmentation.md`'s scope (sprint
-010), which also already tracks the adjacent, still-open finding that a
-legal `FULL`-mode telemetry frame can itself reach up to 239 bytes,
-above this same cap (§10's Open Questions).
+`kMaxLineBytes` to 240 while this constant stayed 200, which made
+radio's the **tighter** of the two caps at that time. Sprint 008
+replaced the false claim and pointed `protocol.cpp`'s `emitLine()` (§8)
+at this constant by name instead of its own bare `200` literal, so the
+two can never drift apart silently again the way they already had
+(WIRE-05/R-21). That sprint single-sourced the name, not the value.
+**The value has since moved: `kMaxPayloadBytes` is 240**, raised by
+sprint 010 (§10), and it is now EQUAL to
+`SerialTransport::kMaxLineBytes`, `Wire::WireHandler::kMaxLineBytes`
+and this class's own private RX capacity — all four the same number.
+The constant's doc comment states that four-way equality, not a
+tighter-of-two relationship, and
+`tests/host/test_wire_constants_drift.py` pins it by reading the
+headers as text. The 239-byte `FULL`-mode telemetry worst case that
+used to exceed the old 200 now fits under 240, with one byte of
+headroom (§10).
 
 **Sprint 030: `execRun()`'s locals, and the protocol fiber's stack
 margin under the sprint 028 call chain.** The radio scratch-buffer
@@ -1249,10 +1266,10 @@
 of its own. With this carrier in place the **v6 radio link is off by
 default** in `test/test.ts` (`BOOT_RADIO_LINK`, flipped by
 `make_deploy.py --radio-link`), leaving the radio to MakeCode's own
-blocks. Verified on tovez 2026-09-02: `captures/tovez-wifi-20260902/`
-(every v6 verb over TCP and UDP with wheels turning, identical results
-to USB on the same boot; a wheels tour captured over the net; the radio
-silent with the switch off), and
+blocks. Verified on tovez 2026-09-02 — every v6 verb over TCP and UDP
+with wheels turning, identical results to USB on the same boot; a
+wheels tour captured over the net; the radio silent with the switch
+off — recorded in
 `docs/knowledge/2026-09-02-wifi-transport-tovez.md`.
 
 ## 7. Hardware ports — `platform/nezha_port.*`, `platform/otos_port.*`, `core/heading_wrap.h`, `core/encoder_glitch_armor.h`, `platform/platform_ports.h`
@@ -1501,13 +1518,14 @@
 (constructed with a placeholder identity; `run()` installs the real
 one via `setIdentity()` once the fiber is executing — the proven-safe
 time to call `microbit_friendly_name()`/`microbit_serial_number()`),
-then **two** `Wire::WireHandler` instances — `wireHandler_` (serial)
-and `wireHandlerRadio_` (radio, sprint 004 ticket 001) — composed over
-that **same** `WireAdapter` instance, not two adapters. Each handler
+then **three** `Wire::WireHandler` instances — `wireHandler_` (serial),
+`wireHandlerRadio_` (radio, sprint 004 ticket 001) and
+`wireHandlerWifi_` (WiFi, 2026-09-02) — composed over that **same**
+`WireAdapter` instance, not three adapters. Each handler
 still keeps its own `expectedNext_` (a plain instance
-member) — the whole point: two independent hosts share one robot's
-adapter state without one transport's sequence gap nacking the
-other's next command.
+member) — the whole point: independent hosts on different carriers
+share one robot's adapter state without one transport's sequence gap
+nacking another's next command.
 
 **Fiber loop (`run()`).** Sends the boot banner unsolicited
 (byte-identical to HELLO's reply), then forever: poll serial
@@ -1738,12 +1756,13 @@
 reaches the bench stand, where the wheels are off the ground.
 **Sprint 008**: its cap now names `RadioTransport::kMaxPayloadBytes`
 directly instead of re-declaring its own bare `200` literal (WIRE-05/
-R-21) — this constant is deliberately the **tighter** of the two
-transports' caps (radio's, not serial's 240), chosen so a line this
-call clips never depends on which transport happens to carry it; the
-previous bare literal was numerically correct but disconnected from
-that rationale, which is what let it read as merely stale once ticket
-005 raised serial's own cap independently. `kMaxPayloadBytes` itself
+R-21), chosen so a line this call clips never depends on which
+transport happens to carry it; the previous bare literal was
+numerically correct but disconnected from that rationale, which is what
+let it read as merely stale once ticket 005 raised serial's own cap
+independently. At the time that made radio's the **tighter** of the two
+caps; sprint 010 raised `kMaxPayloadBytes` to 240 and the caps are now
+**equal** across all four line bounds (§6). `kMaxPayloadBytes` itself
 moves from `private` to `public` on `RadioTransport` to make this
 reference possible — a one-line access-specifier change with no
 encapsulation cost (it stays a compile-time constant, still used
```
