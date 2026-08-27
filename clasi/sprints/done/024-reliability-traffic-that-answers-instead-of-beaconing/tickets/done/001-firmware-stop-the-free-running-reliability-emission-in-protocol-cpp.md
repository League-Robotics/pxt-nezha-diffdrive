---
id: '001'
title: 'Firmware: stop the free-running reliability emission in protocol.cpp'
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: reliability-line-free-runs-at-20-hz-on-the-radio-with-no-host.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Firmware: stop the free-running reliability emission in protocol.cpp

## Description

`Protocol::run()`'s fiber loop (`src/comms/protocol.cpp:346-369`) calls
`emitReliability()` on both `wireHandler_` (serial) and
`wireHandlerRadio_` (radio) every `kReliabilityEmitPeriodMs` (50 ms)
whenever `wireAdapter_.telemetryEnabled()` is false — the boot default,
so this is the normal case. `ack`/`nack` is defined as a response to a
request; this call has no "has anyone spoken on this transport" gate at
all, so an idle robot broadcasts 20 packets/sec on its own radio
channel, addressed to nobody, forever. Stakeholder requirement (stated
directly, reaffirmed three times): **no beacon**. Exactly one
reliability line per inbound line, and none otherwise — not a reduced
rate, not a bounded repeat count, not a configurable cadence.

The current loop:

```cpp
if (nowMs - lastEmitMs >= kReliabilityEmitPeriodMs) {
  if (wireAdapter_.telemetryEnabled()) {
    ... emitTelemetry(snapshot) on both handlers   // UNCHANGED by this ticket
  } else {
    wireHandler_.emitReliability();       // REMOVE
    wireHandlerRadio_.emitReliability();  // REMOVE
  }
  lastEmitMs = nowMs;
}
```

Delete the `else` branch outright — do not replace it with a
rate-limited or gap-only-triggered version. Two facts make this safe and
sufficient on their own, with **no change needed anywhere in
`WireHandler`**:

1. Per-line `ack`/`nack` is already the entire reliability plane for a
   non-subscribed transport. `WireHandler::dispatch()`
   (`wire_handler.cpp:450`) already calls `replyAck()`/`replyNack()` on
   every received line, completely independent of the periodic call this
   ticket removes (`dispatch()` is only ever invoked from
   `onLineComplete()`, which only ever runs when `feed()` has just
   assembled a real inbound line). "Exactly one reliability line per
   inbound line, and none from a transport that has received nothing"
   falls out automatically once the free-running call is gone — there is
   no separate gate to add.
2. The telemetry piggyback is untouched: `emitTelemetry()` still calls
   `emitReliability()` internally as its own third write
   (`wire_handler.cpp:1231`), so a host subscribed via `TLM` keeps
   getting the reliability line exactly as before. That stream is itself
   a host request, so it correctly stays a response.

`kReliabilityEmitPeriodMs` and the outer `if` timing gate stay — they
still govern the telemetry-on cadence. The one-time unsolicited boot
banner (`protocol.cpp:267`, `wireHandler_.sendBanner()`, fired once at
fiber startup, before this loop ever runs) is a separate mechanism and
is **not** touched by this ticket.

The comment block immediately above this code (`protocol.cpp` lines
~332-356) currently documents the unconditional call as deliberate,
citing sprint 003 ticket 003's self-heal rationale. That rationale was
narrower than what the code became (piggyback-only, not unconditional —
see `clasi/issues/reliability-line-free-runs-at-20-hz-on-the-radio-with-no-host.md`'s
"The drift" section for the full history). Rewrite this comment to state
the new behavior plainly and cite this sprint/issue, so the code and its
neighboring comment agree. See `sprint.md`'s Architecture → Design
Rationale ("delete the periodic emission outright..." and "the
lost-reply case moves from a firmware-side timer to the host's own
retransmit loop...") for the reasoning to carry into the rewritten
comment, including the explicit warning that a future reader must not
"restore" this emission as a fix for a perceived regression — the
self-heal path moved to `tools/robotlink.py`'s existing
`send_until()`, it did not disappear.

## Acceptance Criteria

- [x] The `else` branch in `Protocol::run()`'s fiber loop that calls
      `wireHandler_.emitReliability()` / `wireHandlerRadio_
      .emitReliability()` unconditionally when telemetry is off is
      removed. No periodic call replaces it — a non-subscribed transport
      emits nothing until it receives a line.
- [x] The telemetry-on branch (`emitTelemetry(snapshot)` on both
      handlers) is unchanged.
- [x] `kReliabilityEmitPeriodMs` and the outer timing `if` remain (they
      still govern the telemetry-on cadence).
- [x] The rationale comment directly above the loop is rewritten to
      describe the new behavior and cites this sprint's issue, not
      sprint 003/004's now-superseded rationale.
- [x] No file under `src/comms/wire_handler.*` is modified by this
      ticket — `dispatch()`'s per-line ack/nack and
      `emitReliability()`/`emitTelemetry()`'s piggyback already implement
      everything required; only `Protocol`'s calling policy changes.
- [x] The one-time boot banner (`protocol.cpp:267`) is untouched.
- [x] Bench-verified over USB (record the observation in this ticket's
      own notes): open a link with `tools/robotlink.py`, send nothing,
      confirm no `ack`/`nack` line appears for a window well past the old
      50 ms period; then send `TLM POSE #1` and confirm the piggybacked
      reliability line resumes exactly as before.
      **MEASURED on tovez 2026-08-26 — see Implementation Notes below.**
- [x] `uv run pytest tests/host/` passes unchanged — proof that
      `WireHandler`'s own behavior, exercised through the ctypes shim
      independent of `Protocol`, is untouched by this firmware-loop
      change.

## Implementation Notes (programmer, 2026-08-26)

- Rewrote the comment block at `src/comms/protocol.cpp:337-374` (was
  ~332-360 pre-edit) and deleted the `else { wireHandler_
  .emitReliability(); wireHandlerRadio_.emitReliability(); }` branch,
  restructuring the outer `if` to a bare `if
  (wireAdapter_.telemetryEnabled()) { ... }` with no `else`, per the
  ticket's own suggested approach. `lastEmitMs` still updates
  unconditionally inside the outer timing `if`, exactly as before, so the
  telemetry-on cadence is unaffected. The comment now: (a) states that
  per-line `ack`/`nack` via `dispatch()` is already the entire
  reliability plane for a non-subscribed transport, independent of this
  gate; (b) explains this gate exists only to pace the telemetry
  piggyback; (c) cites sprint 024 ticket 001 and
  `clasi/issues/reliability-line-free-runs-at-20-hz-on-the-radio-with-no-host.md`
  for why the unconditional `else` was removed; (d) explicitly states the
  lost-reply self-heal moved to the host's own retransmit
  (`tools/robotlink.py`'s `send_until()`), not away; (e) explicitly warns
  a future reader not to restore any periodic/rate-limited/gap-gated
  re-emission as a fix for a perceived regression.
- `src/comms/wire_handler.h`/`.cpp` untouched — confirmed via `git diff
  --stat` after the edit, only `src/comms/protocol.cpp` (plus incidental
  `uv.lock` version-string resync from a prior commit, unrelated to this
  change) appears in the diff.
- **Bench verification: MEASURED on tovez, 2026-08-26, over USB
  (`/dev/cu.usbmodem2121102`), capture
  `captures/bench-024-tovez-20260826-1735.txt`.** VERDICT: PASS.

  *(Superseding the programmer's original UNVERIFIED note: at the time
  ticket 001's code was written, `mbdeploy probe` showed `CONN: no` on
  all five boards and no bench claim was recorded. The stakeholder then
  attached tovez, and team-lead ran the check. The original refusal to
  invent a result was correct; this entry replaces it with a real one.)*

  Firmware under test was built from this branch with
  `uv run python tools/make_deploy.py --robot tovez --flash`
  (`kProfile` baked `"tovez"`; hex 1 474 901 bytes, 0 `:0400000A`
  markers = plain V2). Verified before flashing that the compiled
  translation unit `built/dockercodal/.../src/comms/protocol.cpp`
  contains `emitReliability` on comment lines ONLY (349, 356) — no call
  site — i.e. this ticket's deletion is genuinely in the flashed image.
  Note the first build attempt was REJECTED by `make_deploy.py`'s own
  checkpoint ("not all nezha-diffdrive translation units were
  compiled") from a stale `.tmp/deploy-head`; the scratch copy was
  wiped and rebuilt rather than flashing a partially-recompiled hex.

  Measured with a deliberately RAW pyserial script, NOT
  `tools/robotlink.py` — ticket 002 made `open_link()` send `HELLO` on
  connect, which would put a request on the wire and contaminate the
  silence measurement. Script preserved at the top of the capture file.

  | phase | window | observed |
  |---|---|---|
  | A — port opened, NOTHING sent | 3.0 s | **0 lines, zero bytes** |
  | B — `HELLO` sent | 1.5 s | exactly 1 line: `device NEZHA2 robot tovez 2314287040` |
  | C — quiet, after B's reply consumed | 3.0 s | **0 lines, zero bytes** |
  | D — `TLM POSE #1` sent | 2.0 s | 38 `t`/`thdr` frames + 37 piggybacked `ack 1 0 none` |

  Phase A and C are the criterion: 3.0 s is 60x the old
  `kReliabilityEmitPeriodMs` (50 ms), so pre-024 firmware would have
  emitted ~60 `ack` lines in each window. Both read zero. Phase D is the
  regression check — the piggyback is intact, one reliability line per
  telemetry frame, exactly as before. Phase B doubles as the identity
  proof: `HELLO` is the only identity authority per CLAUDE.md (the
  `probe` ROLE column is a stale cached registry), and it reports
  `tovez`, confirming the board measured is the board flashed.

  **Scope limit of this measurement:** it exercises the SERIAL handler
  only. Ticket 001 deleted both handlers' calls in the same block, so
  the radio handler is symmetric by construction, but radio silence was
  not independently observed here — that would need the zavaz relay.
  Recorded as a known gap, not claimed as measured.
- Test run: `uv run pytest tests/host/` — 530 passed, 0 failed (full
  output observed in the foreground; no `--no-cov` flag, per this
  project's `pyproject.toml` pytest config).

## Implementation Plan

**Approach**: Delete the `else` block inside `Protocol::run()`'s
periodic-emission `if`, leaving only the telemetry-on branch (restructure
to a single `if (wireAdapter_.telemetryEnabled()) { ... }` with no
`else`, or keep the outer shape and just empty the `else` — whichever
reads more clearly against the surrounding code; implementer's call).
Rewrite the preceding comment block per the Description above.

**Files to modify**: `src/comms/protocol.cpp` (the `run()` loop body and
its immediately preceding comment block, lines ~332-369).

**Files to create**: none.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` (scoped to the
  module this ticket's surrounding code lives in; `Protocol` itself has
  no host shim — see below — so this run is a regression check that
  `WireHandler`'s own tested behavior, which this ticket does not touch,
  stays correct).
- **New tests to write**: none possible at the host level. `Protocol` is
  CODAL-bound and has no host shim — established precedent in this exact
  area: `tests/host/test_wire_per_transport_isolation.py`'s own docstring
  states that `wireHandler_`/`wireHandlerRadio_`'s composition in
  `protocol.h` "can only be verified by code review, per this ticket's
  own testing plan." The same is true of this periodic-call removal.
  Verification is (a) code review of the diff against the Description
  above, and (b) the bench check listed in Acceptance Criteria.
- **Verification command**: `uv run pytest tests/host/`, plus the manual
  bench check (open a USB link, confirm silence, then confirm the
  telemetry piggyback still works) recorded as this ticket's own
  acceptance evidence.
