---
id: '001'
title: 'WifiLink: retain and expose the +CWJAP failure code'
status: in-progress
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: wifi-join-failure-does-not-say-why.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WifiLink: retain and expose the +CWJAP failure code

## Description

`WifiLink::serviceJoin()` (`src/comms/wifi_link.cpp:529-572`) sends
`AT+CWJAP="ssid","pw"` and, on anything but a matched `OK`, falls
straight into `enterBackoff()` (line 571) — discarding the module's own
`+CWJAP:<code>` reply. That reply is the one signal that distinguishes
a wrong password from a slow or absent AP, and Sprint 038's later
join-list walker (ticket 005) depends on being able to make that
distinction — hence this ticket is sequenced first.

Add a `lastJoinError_` field to `WifiLink`, populated during the join
await (mirroring the existing `rejectError_`/`rejectFail_`/
`rejectBusy_` `Matcher` pattern used elsewhere in this class) whenever
the module's reply contains a `+CWJAP:<n>` token before falling into
`enterBackoff()`. Expose it with a getter:
`int lastJoinError() const;` (0 or a sentinel = "no code captured this
attempt" — e.g. a plain timeout with no reply at all). Do NOT map the
number to a word — the vendor code semantics (1=timeout, 2=wrong
password, 3=AP not found, 4=connect failed) are UNVERIFIED on the
Ai-WB2-12F per
`clasi/issues/wifi-join-failure-does-not-say-why.md`, and mapping
before hardware confirmation risks shipping a wrong label, which is
worse than a bare number (see that issue's "Proposed resolution" step
4).

Add one field to `Protocol::emitWifiDebug()`'s `DBG:wifi` line:
`join=<code>` (or `join=-` when no code was captured for the current
attempt). Check the `wifiDbgBuf_` budget before adding it — the
comment above that buffer already documents ~294/320 bytes used
against its 384-byte size before this field; if the new field does not
fit, either grow the buffer (as a prior sprint already did once,
320→384) or drop/shorten a lower-value existing field. State in this
ticket's own PR/commit which approach was taken and the resulting byte
count — this settles the budget for ticket 006's `ssid=`/`haspw=`
addition, which comes after this one specifically so it knows what
room is left (sprint architecture Open Question 3).

No units in the field's own name (`.claude/rules/no-units-in-identifiers.md`
— `lastJoinError_` names what it is, not a unit; it has none).

## Acceptance Criteria

- [x] `WifiLink` retains the `+CWJAP:<code>` (or absence) across the
      `kJoin` → `kBackoff` transition and exposes it via
      `lastJoinError()`.
- [x] The code is the RAW vendor number; no word/enum mapping is
      introduced in this ticket.
- [x] `DBG:wifi` gains a `join=<code>` field (or `join=-`); the byte
      budget against `wifiDbgBuf_` (384 bytes) is explicitly checked
      and the ticket states the resulting used/total byte count.
      **Result**: worst-case line is 322 chars + NUL = 323/384 bytes
      used (up from 315/384 before this ticket), computed by
      substituting each format-string field's declared C++ type range
      into the exact `emitWifiDebug()` format string (arithmetic, not
      a hardware measurement — see
      `tests/host/test_wifi_join_error_debug_source_pin.py`'s
      `test_worst_case_dbg_wifi_line_fits_the_declared_buffer`, which
      re-derives this number in Python on every run so it cannot
      silently drift from the code). 61 bytes remain for ticket 006's
      `ssid=`/`haspw=` fields; ticket 006 must re-check this budget
      against its own field widths (an SSID is up to 32 octets), not
      assume 61 bytes covers them.
- [x] Host tests (`tests/host/test_wifi_link.py` or equivalent)
      script a `+CWJAP:2` reply and assert the code is captured and
      retained through backoff; also cover a plain timeout (no
      `+CWJAP:` seen at all) reporting the "no code" sentinel, not a
      stale previous value.
- [ ] MEASURED on real hardware (gopiv, Ai-WB2-12F, per
      `.claude/rules/connecting-to-a-robot.md`): a join attempt with a
      deliberately wrong password is run and the resulting
      `+CWJAP:<code>` is captured and cited by artifact path per
      `.claude/rules/measurement-citations.md` — this is the "confirm
      code 2 on a real wrong-password join" step the issue's proposed
      resolution asks for before any future word-mapping ticket could
      be justified. Coordinate with the team-lead to run this
      on-hardware step directly rather than assuming it from the host
      test alone.
      **NOT RUN by this ticket's programmer dispatch** — on-robot work
      is the team-lead's, by project convention
      (`docs/knowledge`/sprint.md Tickets table note on ticket 004's
      hardware step, same convention applied here). Host-side capture
      and retention are implemented and host-tested above; the vendor
      code-2-means-wrong-password mapping stays UNVERIFIED until the
      team-lead runs this step directly against gopiv.
- [x] No passphrase appears in the `DBG:wifi` line, any other reply, or
      any captured test/measurement artifact this ticket produces —
      `join=<code>` is a bare integer, never the credential itself.
- [x] Room reserved in wire budget accounting for ticket 006's
      `ssid=`/`haspw=` fields is documented (even if just "N bytes
      remain") so that ticket isn't guessing. **Result**: 61 bytes
      remain (see above).

## Implementation Plan

**Approach**: Add a small incremental token-capture state to
`WifiLink`, following the existing `IpdParser`/`ownIpTag_` pattern
already used to pull a value (the CIPSTA `ip:"..."` capture) out of a
byte-at-a-time AT reply stream, rather than trying to parse
`lastReply_`'s trace buffer after the fact (that buffer keeps only the
FIRST ~72 bytes and is sized for human debugging, not machine
parsing). Watch for the literal `"+CWJAP:"` token during the join
await (alongside the existing `expect_`/`rejectError_`/etc. matchers)
and, on match, capture the following 1-2 ASCII digits into
`lastJoinError_`.

**Files to modify**:
- `src/comms/wifi_link.h` — `lastJoinError_` field, `lastJoinError()`
  getter, any new small parser-state member.
- `src/comms/wifi_link.cpp` — capture logic in `serviceJoin()`/the byte
  feed path; reset `lastJoinError_` to the sentinel at the START of
  each new join attempt (not just once at construction), so a stale
  code from a previous slot never survives into the next attempt.
- `src/comms/protocol.cpp` — `emitWifiDebug()`'s `join=` field,
  `wifiDbgBuf_` sizing if needed.
- `src/comms/protocol.h` — buffer size comment update if the size
  changes.

**Testing plan**: Extend `tests/host/wifi_link_shim.cpp` /
`tests/host/test_wifi_link.py` with a scripted `+CWJAP:2` join failure
and a plain-timeout join failure (no `+CWJAP:` at all), asserting
`lastJoinError()` in each case and that it resets on the next `begin()`/
join attempt. Add a `tests/host/test_protocol.py` (or equivalent)
assertion that `DBG:wifi` contains `join=` and that the line stays
within `wifiDbgBuf_`'s capacity for a worst-case field combination.

**Documentation updates**: None required beyond this ticket's own
commit message citing the hardware measurement artifact.
