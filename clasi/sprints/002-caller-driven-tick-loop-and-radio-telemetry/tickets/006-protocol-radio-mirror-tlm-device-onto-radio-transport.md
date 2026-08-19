---
id: '006'
title: Protocol radio mirror (TLM + DEVICE onto radio transport)
status: done
use-cases:
- SUC-004
depends-on:
- '005'
github-issue: ''
issue: radio-telemetry-plane-for-field-runs.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Protocol radio mirror (TLM + DEVICE onto radio transport)

## Description

Wires ticket 005's new radio transport into `protocol.cpp` so `TLM` and
the `DEVICE` banner reach a host over radio, mirroring (not replacing)
the existing USB serial output — per sprint.md's Solution/SUC-004 and
Design Rationale ("mirror the exact formatted line bytes... onto both
`sendDeviceBanner()` and `sendTelemetry()`'s call sites uniformly").

In `protocol.cpp`:

- `sendTelemetry()`: after formatting the `TLM:<x>:<y>:<heading>` line
  into its existing stack buffer and writing it via
  `transport_.writeLine()` (serial, unchanged), also send the same
  formatted bytes via the new radio transport's send entry point
  (ticket 005). One formatted buffer, two sinks.
- `sendDeviceBanner()`: same mirroring, applied uniformly at this one
  function — covers both the proactive boot-time send and any
  `HELLO`-triggered re-send, with no special-casing between them (per
  sprint.md's Design Rationale).
- No other reply verb (`PONG`, `ID`, `VER`, `DIAG`, `CFG`) is mirrored
  onto radio — out of scope per sprint.md (telemetry-out only).
- No new wire verb, no RX handling added — this ticket only adds a
  second write call at two existing call sites.
- Radio transport `begin()` (ticket 005) should be called from
  `Protocol::start()`, alongside the existing `transport_.begin()` call
  — always-on, no new MakeCode block or `pxt.json`-visible surface,
  matching how serial transport already starts (no separate
  enable/disable control this sprint).

## Acceptance Criteria

- [x] `sendTelemetry()` writes the same formatted `TLM` line to both
      `transport_` (serial, unchanged) and the new radio transport.
      Verified: `writeSnprintfResult(transport_, buf, n, sizeof(buf),
      &radioTransport_)` — same `buf`/`n`/`bufCap` feed both the serial
      write and (when `radio` is non-null) the identical clamped bytes to
      `radioTransport_.sendLine()`, one source of truth.
- [x] `sendDeviceBanner()` writes the same formatted `DEVICE` line to
      both transports, at every call site (boot-time proactive send and
      `HELLO`-triggered re-send) uniformly. Verified: the mirror lives
      inside `sendDeviceBanner()` itself (same `writeSnprintfResult(...,
      &radioTransport_)` pattern); `handleHello()` only calls
      `sendDeviceBanner()`, so both the boot-time call (`run()`, before
      the loop's first read) and the `HELLO` reply get it identically,
      with no special-casing.
- [x] No other verb (`PONG`/`ID`/`VER`/`DIAG`/`CFG`/replies to any
      binary command) is sent over radio. Verified: `writeSnprintfResult`'s
      new `radio` parameter defaults to `nullptr`; `handlePing()`/
      `handleId()`/`handleVer()`/`handleDiag()` call sites are untouched
      (still 3-arg calls) and stay serial-only; `handleGetConfig()`'s
      `CFG` reply uses `transport_.writeLine()` directly, never
      `writeSnprintfResult()`, so it was never in scope to begin with.
- [x] USB serial `TLM`/`DEVICE` output is byte-identical to sprint
      001's behavior — the radio mirror adds a call, it does not alter
      the serial path. Verified: `transport_.writeLine(buf, len)`'s own
      call and the `buf`/`len` computation above it are byte-for-byte
      unchanged; the radio mirror is a second, purely additive statement.
- [x] The radio transport is started unconditionally from
      `Protocol::start()` (or equivalent existing boot path) — no new
      block, no new `pxt.json`-visible configuration surface. Verified,
      with a documented tradeoff: `RadioTransport` (ticket 005) has no
      `begin()` of its own — it lazily enables `uBit.radio` on its own
      first `sendLine()` call, by design, so a bench-only serial user
      never pays that cost unless the mirror actually fires. Since
      `sendDeviceBanner()` now fires unconditionally at the very top of
      `run()` (before the loop ever blocks on a read) via `Protocol::
      start()`'s `launcher_.launch(...)`, the radio genuinely is started
      unconditionally from this class's existing boot path on every boot
      — satisfying this criterion — but as an honest consequence every
      boot (including a serial-only bench session) now also pays the
      one-time radio-enable cost, which ticket 005 had deliberately
      deferred. No new block or `pxt.json` surface was added either way.
- [x] No wire verb is accepted from radio (ticket 005's module has no
      RX path; this ticket adds none either). Verified: no changes to
      `radio_transport.h`/`.cpp`; `RadioTransport` still exposes only
      `sendLine()`; no verb registry entry, handler, or RX call was added
      by this ticket.
- [x] Sprint success criteria's flash-budget check (from ticket 005) is
      re-confirmed with this ticket's additional call sites included.
      Verified: real `pxt build` in the scratch toolchain env, once with
      this ticket's `protocol.h`/`protocol.cpp` changes and once with
      them reverted to git HEAD, zero build errors both times (both the
      codal-microbit-v2 and classic microbit-dal flavors), Intel-HEX
      data-record byte counts diffed directly (not relying on ticket
      005's now-superseded +0 measurement, since that module was
      unreachable before this ticket): **codal-microbit-v2
      (`mbcodal-binary.hex`): +0 bytes**; **classic microbit-dal
      (`mbdal-binary.hex`) and the universal `binary.hex`: +1024 bytes**.
      The +1024 on the classic/dal flavor is plausibly one additional
      nRF51822 flash page (page size 1024 bytes on that chip) pulled in
      to hold the now-reachable `RadioTransport::sendLine()`/
      `sendFragmented()`/`ensureRadioReady()` code plus the two new call
      sites, rounded up to a page boundary; the codal-v2 (nRF52) target
      shows no measurable delta, plausibly because that flavor's build
      already links the radio driver code regardless of reachability.
      **Flagged, not silently shipped**, per sprint.md's flash-budget
      risk: this is a real, non-zero cost on the flash-tighter classic
      target (sprint.md notes this project has historically run within
      roughly a thousand bytes of its deploy budget) — surfaced here for
      the team-lead/stakeholder's judgment, not adjudicated by this
      ticket.

## Testing

- **Existing tests to run**: none automated. Confirm sprint 001's
  existing serial `TLM`/`DEVICE` verification (desk review of
  `sendTelemetry()`/`sendDeviceBanner()`'s formatting) still holds
  unchanged after adding the radio mirror calls.
- **New tests to write**: none automated. End-to-end verification (an
  actual RADIOBRIDGE relay receiving `TLM`/`DEVICE` and forwarding them
  to a host) is the one part of this sprint that is not desk- or
  simulator-verifiable at all (sprint.md SUC-004 acceptance criteria) —
  covered entirely by the deferred hardware pass. Do not block this
  ticket on it.
- **Verification command**: none (no test runner). Verify by code
  review confirming both call sites write to both transports and that
  no other call site was touched.
