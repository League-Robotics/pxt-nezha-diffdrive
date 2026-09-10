---
id: '006'
title: 'Protocol integration: own the store and sequencer, report status over DBG:wifi'
status: done
use-cases:
- SUC-001
- SUC-004
depends-on:
- '005'
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

- [x] Empty store + no `setupWifi()`: `wifiLink_.state() == kDisabled`
      at all times, identical to pre-sprint behavior (host/protocol
      test comparing before/after). Already proven by ticket 005's own
      `test_empty_store_is_a_pure_pass_through_to_wifilink`
      (test_wifi_join_sequencer.py) plus this ticket's source-pins
      (test_setupwifi_precedence_source_pin.py section 7) confirming
      `Protocol::serviceWifi()` delegates to exactly that sequencer/
      link pair with no logic of its own left to regress.
- [x] Empty store + `setupWifi()` called OR baked `kWifiSsid` present:
      behaves exactly as pre-sprint (single-credential join, no list
      walking) — this is Design Rationale #3's precedence rule,
      verified here where it actually matters (Protocol-level, not
      just documented). Covered by
      `test_setupwifi_precedence_source_pin.py` sections 1-7
      (unchanged by this ticket) plus
      `test_service_wifi_calls_sequencer_service_not_link_service_
      directly`, which proves EVERY precedence branch, not just flash,
      goes through `wifiJoinSequencer_.service()`.
- [x] 2+ occupied slots, one wrong one correct: end-to-end
      `Protocol`-level test (or as close to end-to-end as the host
      harness reaches) shows the robot reaching `kReady` on the correct
      slot within one boot. Ticket 005's
      `test_one_wrong_entry_then_one_correct_reaches_ready_within_one_
      boot` (test_wifi_join_sequencer.py) IS this test — `protocol.cpp`
      cannot be host-compiled, and its own source-pins prove
      `serviceWifi()` performs no slot-walk logic of its own, only
      delegation to the exact `WifiJoinSequencer`/`WifiLink`/
      `WifiCredentialStore` trio that test drives directly.
- [x] `DBG:wifi` reports `join=`, `ssid=`, and `haspw=` together within
      `wifiDbgBuf_`'s budget — final byte-count accounting stated in
      this ticket's own commit/PR notes, closing out Open Question 3.
      Worst case is now 368 bytes + NUL = 369/384 used (up from ticket
      001's 323/384), 15 bytes of headroom remaining — pinned in
      Python by
      `tests/host/test_wifi_join_error_debug_source_pin.py::test_worst_case_dbg_wifi_line_fits_the_declared_buffer`.
- [x] **No passphrase appears in any `DBG:wifi` line, any wire reply,
      or any telemetry frame, under any store state** — this is the
      sprint's hard constraint, tested explicitly at the integration
      level (not just at each component's own level) because
      integration is where a careless "for debugging" print is most
      likely to slip in. `emitWifiDebug()`'s `haspw=%u` field is a
      bool, never a `%s` on any password-shaped member; pinned by
      `test_haspw_never_reads_a_passphrase_value_only_a_boolean_check`
      and the narrowed `test_join_field_present_and_sourced_from_last_
      join_error` (both test_wifi_join_error_debug_source_pin.py), plus
      `WifiJoinSequencer::currentHasPassword()`'s own contract
      (wifi_join_sequencer.h) exercised directly (not source-pinned) in
      test_wifi_join_sequencer.py.
- [x] `WireAdapter`'s `wifiCred*` seam reads/writes the SAME store
      instance `WifiJoinSequencer` walks — verified by a test that sets
      a credential over the (simulated) wire and observes the
      sequencer pick it up on its next wrap, per ticket 005's
      mid-walk-pickup behavior, now proven through the real
      `Protocol`-owned store rather than a test-only one. New file
      `tests/host/test_wifi_protocol_seam.py` (+
      `wifi_protocol_seam_shim.cpp`) sends a real `WIFICRED SET` through
      the REAL `WireAdapter`/`wire_handler.cpp` (built in a different
      translation unit than the `WifiJoinSequencer` under test) and
      confirms the sequencer picks it up, including replaying ticket
      005's own mid-walk scenario end to end over the wire instead of
      via a direct `store.set()` call.

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
