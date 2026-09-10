---
id: '006'
title: 'Protocol integration: own the store and sequencer, report status over DBG:wifi'
status: open
use-cases: [SUC-001, SUC-004]
depends-on: ['005']
github-issue: ''
issue: wifi-credentials-live-in-flash-not-in-the-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Protocol integration: own the store and sequencer, report status over DBG:wifi

## Description

Wire everything built in tickets 001-005 into `Protocol` for real,
end-to-end, on-target behavior:

1. `Protocol` gains a `WifiCredentialStore` member (using the real
   `WifiFlashPort` from ticket 002) and a `WifiJoinSequencer` member
   (ticket 005), alongside its existing `wifiLink_`.
2. `Protocol::serviceWifi()` calls `sequencer.service()` instead of
   `wifiLink_.service()` directly.
3. `WireAdapter`'s `wifiCred*` seam (ticket 003) is re-pointed to the
   now-real `Protocol`-owned store (ticket 003 built the seam against
   whatever store instance was simplest to land first — this ticket
   finalizes the wiring).
4. `Protocol::emitWifiDebug()` gains `ssid=<current-or-attempted-ssid-or-dash>`
   and `haspw=0/1` fields (R1), completing the budget accounting
   ticket 001 started with `join=`.
5. **Regression guard, end-to-end on real Protocol code (not just
   host-mocked pieces)**: a board with an empty store and no
   `setupWifi()` call reaches EXACTLY `kDisabled`, zero module traffic
   — the sprint's own top-line success criterion, and the one most at
   risk from a wiring mistake in this integration ticket specifically
   (every piece below it was already host-tested in isolation; this
   ticket is where a mis-wire would first show up as observable
   behavior change).

## Acceptance Criteria

- [ ] Empty store + no `setupWifi()`: `wifiLink_.state() == kDisabled`
      at all times, identical to pre-sprint behavior (host/protocol
      test comparing before/after).
- [ ] Empty store + `setupWifi()` called OR baked `kWifiSsid` present:
      behaves exactly as pre-sprint (single-credential join, no list
      walking) — this is Design Rationale #3's precedence rule,
      verified here where it actually matters (Protocol-level, not
      just documented).
- [ ] 2+ occupied slots, one wrong one correct: end-to-end
      `Protocol`-level test (or as close to end-to-end as the host
      harness reaches) shows the robot reaching `kReady` on the correct
      slot within one boot.
- [ ] `DBG:wifi` reports `join=`, `ssid=`, and `haspw=` together within
      `wifiDbgBuf_`'s budget — final byte-count accounting stated in
      this ticket's own commit/PR notes, closing out Open Question 3.
- [ ] **No passphrase appears in any `DBG:wifi` line, any wire reply,
      or any telemetry frame, under any store state** — this is the
      sprint's hard constraint, tested explicitly at the integration
      level (not just at each component's own level) because
      integration is where a careless "for debugging" print is most
      likely to slip in.
- [ ] `WireAdapter`'s `wifiCred*` seam reads/writes the SAME store
      instance `WifiJoinSequencer` walks — verified by a test that sets
      a credential over the (simulated) wire and observes the
      sequencer pick it up on its next wrap, per ticket 005's
      mid-walk-pickup behavior, now proven through the real
      `Protocol`-owned store rather than a test-only one.

## Implementation Plan

**Approach**: This is glue work — no new algorithms, just correct
ownership and call-site wiring. Read `Protocol`'s existing
`serviceWifi()`/`enableWifi()`/constructor member-initialization order
carefully (per `protocol.h`'s own NSDMI declaration-order comment)
before adding new members, since `WifiCredentialStore`/
`WifiJoinSequencer` construction must respect whatever ordering
constraint the existing `wifiLink_`/`wifiSink_`/`wireHandlerWifi_`
chain already has.

**Files to modify**:
- `src/comms/protocol.h` — new members (`WifiCredentialStore`,
  `WifiJoinSequencer`, in the correct declaration order relative to
  `wifiLink_`), `emitWifiDebug()` signature/body changes.
- `src/comms/protocol.cpp` — `serviceWifi()`'s call-site change,
  `emitWifiDebug()`'s new fields.
- `src/comms/wire_adapter.h` / `.cpp` — re-point the `wifiCred*` seam
  to the real store.

**Testing plan**: Extend whatever `tests/host/test_protocol.py` (or
equivalent) exists today with the end-to-end scenarios in the
Acceptance Criteria above. Re-run the FULL existing `WifiLink`/
`WifiCredentialStore`/`WifiJoinSequencer`/`wire_handler` host suites to
confirm nothing already-passing regressed (per
`.claude/rules/source-code.md`'s scoped-run guidance for ticket work).

**Documentation updates**: None required by this ticket alone; folded
into ticket 007.
