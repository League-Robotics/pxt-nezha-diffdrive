---
id: '005'
title: 'WifiJoinSequencer: walk the credential list on boot'
status: open
use-cases: [SUC-004]
depends-on: ['001', '004']
github-issue: ''
issue: wifi-credentials-live-in-flash-not-in-the-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WifiJoinSequencer: walk the credential list on boot

## Description

Implement R5: on boot, try list entries in order until one joins.
Depends on ticket 001 (needs `WifiLink::lastJoinError()` to distinguish
a definitive bad-credential failure from a retryable one) and is
sequenced after ticket 004 (the flash-survival hardware gate) as a
deliberate risk-mitigation choice — no further feature work is built on
top of the store until its foundation is confirmed, per the sprint's
own "stop after the first bad hardware run" convention.

Per sprint architecture Design Rationale #2, this is a NEW,
host-portable class, `WifiJoinSequencer`
(`src/comms/wifi_join_sequencer.{h,cpp}`) — NOT logic folded into
`WifiLink` itself (would conflate AT bring-up mechanics with
credential-selection policy) and NOT logic folded directly into
`Protocol::serviceWifi()` (would make it untestable outside CODAL,
contradicting this sprint's own Test Strategy, which requires the
list-walker to be host-tested independent of the AT state machine).

**REVISED 2026-09-10 — read this before writing any code.** Ticket
001's on-hardware run (gopiv, `captures/wifi-join-codes-20260909/
notes.md`, `badpw-boot.log`) found that the Ai-WB2 module persists the
last AP it associated with and auto-reconnects after every
`AT+RST` — which `serviceJoin()`'s existing `AT+CWJAP?` poll (matched
on SSID name only) cannot distinguish from the module actually using
the credential `WifiLink` was told to test. A wrong baked password
reached `state=5`/`join=-` with no `+CWJAP:` code ever sent, because
the explicit join step was never reached. **This sequencer cannot
assume that walking the list in order is what the module actually
tries** unless it forces the credential under test — see the sprint
architecture's 2026-09-10 Revision section for the full option
analysis (`AT+CWAUTOCONN=0`, a bare poll-skip, and `AT+CWQAP` were all
weighed).

**Decision this ticket implements**: extend `WifiLink::Config` with one
additive field, `bool forceExplicitJoin` (default `false` — every
existing caller, including the `setupWifi()`/baked single-credential
fallback, is unaffected). `WifiJoinSequencer` sets
`forceExplicitJoin = true` on every `Config` it builds. When true,
`WifiLink::serviceJoin()`'s step 0 sends `AT+CWQAP` (tolerant — an
`ERROR` because nothing was associated is expected) instead of polling
`AT+CWJAP?`, then proceeds directly to the existing explicit
`AT+CWJAP=` send — so the credential actually tried is always the one
`WifiJoinSequencer` selected, never whatever the module remembered.
The `AT+CWJAP?` poll-first LANDMINE-avoidance path
(`src/comms/wifi_link.cpp` `serviceJoin()` step 0, the wifi-link note
section 5.3) is NOT deleted — it remains, byte-for-byte, as the
default (`forceExplicitJoin == false`) path for every non-sequencer
caller. This ticket's own scope includes both the `WifiJoinSequencer`
class AND this small, additive `WifiLink` extension (Config field +
the `AT+CWQAP`-then-explicit-join branch in `serviceJoin()`) — it does
NOT require reopening ticket 001, which is closed and unaffected.

**Responsibilities**: own a current slot index; on `service()`, drive
`WifiLink` (already `begin()`-ed, with `forceExplicitJoin = true`, on
the current slot's config) and watch its state. On a join outcome
classified as a DEFINITIVE credential failure (per the
`+CWJAP:<code>` policy below), advance to the next OCCUPIED slot and
`begin()` a new `WifiLink::Config` for it (also with
`forceExplicitJoin = true`). On a retryable outcome (a code — or
absence — that means "the AP might just be slow," e.g. code
1/timeout, vs. code 2/wrong-password, per the
UNVERIFIED-until-ticket-001's-hardware-confirmation table), let
`WifiLink`'s own existing backoff/retry continue on the SAME slot up to
a bounded attempt count, then advance anyway — an all-wrong store must
not wedge forever on slot 0.

After the LAST occupied slot (definitive-fail or attempt-count-exhausted),
wrap to slot 0 and RE-READ the store fresh from `WifiCredentialStore` —
this is what lets a wire `SET` made mid-walk (ticket 003) be picked up
without any dedicated re-point mechanism in `WifiLink` (sprint
architecture Design Rationale #3 — this is the resolution to the
sprint's "setupWifi() late-call refusal" open question).

**Empty-store / no-entries fallback**: if the store has zero occupied
slots, the sequencer must fall back to EXACTLY today's behavior —
`Protocol`'s existing `setupWifi()`-supplied or baked `kWifiSsid`/
`kWifiPassword` single credential, or `kDisabled` if neither is set.
This is the sprint's own regression-guard success criterion; do not
special-case it away.

## Acceptance Criteria

- [ ] `WifiLink::Config` gains `forceExplicitJoin` (default `false`);
      every existing `WifiLink` host test (ticket 001's suite and
      earlier) passes UNMODIFIED, proving the default path is
      byte-for-byte unchanged.
- [ ] When `forceExplicitJoin` is true, `serviceJoin()` sends
      `AT+CWQAP` then the explicit `AT+CWJAP=`, skipping the
      `AT+CWJAP?` poll entirely (host test, scripted fake module: assert
      the exact command sequence sent, no `AT+CWJAP?` present).
- [ ] Store with one wrong entry followed by one correct entry: the
      sequencer reaches `kReady` on the correct entry within one boot
      (host test, scripted `+CWJAP:2` on slot 0 then `OK` on slot 1,
      via the existing `WifiLink` host harness driven by the
      sequencer, with `forceExplicitJoin` exercised).
- [ ] **The module-memory regression case, per the sprint architecture's
      2026-09-10 Revision**: a host test scripts the fake module to
      answer `AT+CWJAP?` (if issued) as already joined to slot 0's SSID
      — simulating the module having auto-rejoined from a stale,
      DIFFERENT stored password — and asserts that with
      `forceExplicitJoin = true` the sequencer still sends
      `AT+CWQAP` + an explicit `AT+CWJAP=` for slot 0's actual
      configured password and correctly classifies its outcome,
      rather than accepting the module's stale association as success.
      This is the test that makes "entry 2 wins when entry 1 is wrong"
      trustworthy rather than a measurement of the module's memory —
      do not consider this ticket's slot-ordering criteria met without
      it.
- [ ] **MEASURED on real hardware (gopiv, Ai-WB2-12F)**: re-run the
      `badpw-boot.log` scenario from `captures/wifi-join-codes-20260909/
      notes.md` — a board that has previously joined a real SSID,
      reflashed with the SAME SSID but a WRONG password, this time with
      `forceExplicitJoin` in effect — and confirm (a) a `+CWJAP:2` (or
      equivalent definitive-failure) code is now captured instead of a
      silent `state=5`/`join=-` success, and (b) `AT+CWQAP` followed by
      the explicit `AT+CWJAP=` does not reproduce the join/backoff/RST
      near-livelock the poll-first design exists to avoid (wifi-link
      note section 5.3). Cite the artifact path per
      `.claude/rules/measurement-citations.md`. Coordinate with the
      team-lead to run this directly, same convention as ticket 001's
      hardware step and ticket 004's HARDWARE ticket.
- [ ] An all-wrong store cycles without wedging or crashing — a bounded
      host test runs several laps and asserts the slot index keeps
      advancing/wrapping, never stalls.
- [ ] A wire `SET` (simulated at the store level, since ticket 003's
      wire path may not yet be integrated with this ticket's harness)
      made mid-walk is picked up by the NEXT wrap-to-slot-0, not only
      after a reboot.
- [ ] An empty store produces IDENTICAL behavior to `WifiLink` alone
      with no sequencer involvement at all — host test compares the
      two paths' observable state sequence.
- [ ] The exact retry-vs-advance policy table (which `lastJoinError()`
      values retry the current slot vs. advance immediately) is written
      down as a comment citing ticket 001's hardware confirmation
      artifact, not invented independently in this ticket.
- [ ] No passphrase appears in any log/debug output this class produces
      (it operates on `WifiLink::Config` objects that carry passwords
      by pointer — never print/format one). Ticket 009 (sequenced
      before this one) already guarantees `WifiLink::lastCommand()`
      itself never carries the passphrase, including for the
      `AT+CWQAP` step this ticket adds.
- [ ] Identifier names carry no units
      (`.claude/rules/no-units-in-identifiers.md`) — this ticket
      introduces attempt-count and timeout-adjacent fields that are
      exactly the kind of name this rule targets (e.g. a bounded-retry
      counter is `retryCount`/`attemptsOnSlot`, not `retryCountMax3` or
      similar). `forceExplicitJoin` itself carries no unit and needs
      none.

## Implementation Plan

**Approach**: `WifiJoinSequencer` holds references to a `WifiLink&`
and a `WifiCredentialStore&` (constructor-injected, same ownership
shape `WifiLink` itself uses for `WifiUart&`). `service()` is called
once per poll from `Protocol` (replacing a direct
`wifiLink_.service()` call — that rewiring is ticket 006's job, not
this one's; THIS ticket can be fully host-tested by calling
`sequencer.service()` directly in a test harness without any `Protocol`
involvement at all).

**REVISED 2026-09-10**: this ticket also makes a small, additive
extension to `WifiLink` itself (per the sprint architecture's
2026-09-10 Revision) — a `forceExplicitJoin` field on `Config`, and a
branch in `serviceJoin()`'s step 0 that sends `AT+CWQAP` and skips the
`AT+CWJAP?` poll when it is set. This is scoped narrowly: the existing
poll-first path is untouched for `forceExplicitJoin == false`
(everything ticket 001 shipped), and every `Config` `WifiJoinSequencer`
constructs sets the flag true.

**Files to create**:
- `src/comms/wifi_join_sequencer.h` / `.cpp`.
- `tests/host/test_wifi_join_sequencer.py`.

**Files to modify**:
- `pxt.json`'s `files` list.
- `src/comms/wifi_link.h` — `Config::forceExplicitJoin` field (default
  `false`).
- `src/comms/wifi_link.cpp` — `serviceJoin()` step 0's new
  `AT+CWQAP`-then-skip-poll branch, gated on `config_.forceExplicitJoin`.
- `tests/host/test_wifi_link.py` (or equivalent) — new cases for the
  `forceExplicitJoin` branch, including the module-memory regression
  case described in Acceptance Criteria above.

**Testing plan**: New host suite driving a real `WifiLink` (against
`tests/host/wifi_link_shim.cpp`'s existing fake UART) plus a real
`WifiCredentialStore` (against ticket 002's fake `WifiFlashPort`) —
this ticket is the first to exercise all three host-portable pieces
together, still entirely off real hardware. Plus the dedicated
`WifiLink`-level `forceExplicitJoin` host tests above, plus the
gopiv hardware re-run of `badpw-boot.log` (Acceptance Criteria).

**Documentation updates**: None required by this ticket alone.
